"""
Claim-Based Financial Forensics Synthesis
Location: lib/python/legal_platform/financial_forensics.py
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import dataiku
import pandas as pd

from .config import (
    FINANCIAL_FINDINGS_DATASET,
    FINANCIAL_TIMELINE_DATASET,
    FINANCIAL_LINE_ITEMS_DATASET,
)

from .storage import case_rows, replace_case_rows
from .financial_corrections import load_fact_resolutions, load_latest_corrections
from .financial_facts import build_fact_ledger, format_amount, parse_amount
from .ids import random_id
from .llm import parse_json_object, strip_think

try:
    from .config import GENERATION_LLM_ID as TEXT_MODEL_ENDPOINT
except ImportError:
    TEXT_MODEL_ENDPOINT = "openai:Nutamix_GPU:qwen3-32b"

logger = logging.getLogger("FinancialForensics")

# -----------------------------------------------------------------------------
# PROMPTS
# -----------------------------------------------------------------------------
CLAIM_BASED_ACCOUNTING_PROMPT = r"""
You are a senior forensic accountant representing Banque Saudi Fransi (BSF).
Compare the financial claims made in a legal case with the reviewed financial ledger.

INPUTS:
- Claims: {claims_json}
- Final normalized financial ledger (atomic facts, already reviewed): {ledger_json}
- User analysis instructions: {instructions}

THE LEDGER
Each record is one atomic financial fact with a record_id, fact_type, the fields the document supports
(null = not stated) and a status:
- EXTRACTED / USER_CONFIRMED / USER_CORRECTED: the value is established.
- CALCULATED: derived arithmetically from other facts (and verified).
- INFERRED: printed, but its meaning was interpreted from context. Treat conclusions that depend on it as
  less certain and list it under unresolved_evidence when it is decisive.
- MISSING: the document is silent on this point; it is an evidence gap, never evidence.

METHOD
1. Break every claim into ATOMIC CLAIMS: one assertion each (one amount, one payment, one date, one
   balance). "The customer paid SAR 500,000 and owes nothing" becomes two atomic claims. Keep the original
   wording in parent_claim.
2. For each atomic claim state the financial question and the evidence that would normally prove it.
3. Classify the ledger records that bear on it:
   - supporting_evidence: records that establish the claim.
   - partially_supporting_evidence: records that establish only part of it (e.g. 350,000 of a claimed 500,000).
   - contradicting_evidence: records that cannot be true at the same time as the claim.
   - unresolved_evidence: records whose relevance or meaning is ambiguous (e.g. INFERRED facts), with why.
   - missing_evidence: what would be needed but is not in the ledger (a missing record is NOT a contradiction).
   Every evidence entry cites record_ids from the ledger and explains in one sentence how it bears on the claim.
4. claimed_amount: the amount the claim asserts, if any. substantiated_amount: the part the records establish.
5. accounting_position: a precise statement such as "Available financial records substantiate SAR 350,000 of
   the claimed SAR 500,000; no record of the remaining SAR 150,000 was located." Cite amounts and pages.
6. result: SUPPORTED, PARTIALLY_SUPPORTED, CONTRADICTED, NOT_VERIFIABLE, NO_FINANCIAL_EVIDENCE or
   NOT_FINANCIAL_CLAIM (for claims that make no financial assertion).

USER INSTRUCTIONS
They set the scope, period, focus or method of the analysis. They MUST NOT decide the conclusion: do not
assume a hypothesis in them is true, do not ignore evidence that contradicts it, and say so clearly when the
evidence does not support it. With no instructions, perform the normal analysis.

RULES
- Use ONLY the claims and the ledger. Never invent records, amounts, dates, references or calculations.
- Cite only record_ids that appear in the ledger.
- No legal conclusions (liability, violations, entitlement) — accounting positions only.
- State limitations where the ledger cannot fully answer the question.

RETURN JSON ONLY:
{
  "claim_evaluations": [
    {
      "claim_id": "CLM_001",
      "parent_claim": "original claim text",
      "claim": "atomic claim",
      "claimed_amount": "500,000",
      "currency": "SAR",
      "financial_question": "...",
      "expected_evidence": "...",
      "supporting_evidence": [{"record_ids": ["..."], "explanation": "..."}],
      "partially_supporting_evidence": [{"record_ids": ["..."], "explanation": "..."}],
      "contradicting_evidence": [{"record_ids": ["..."], "explanation": "..."}],
      "unresolved_evidence": [{"record_ids": ["..."], "explanation": "..."}],
      "missing_evidence": ["..."],
      "substantiated_amount": "350,000",
      "accounting_position": "...",
      "result": "PARTIALLY_SUPPORTED",
      "limitation": "..."
    }
  ]
}
""".strip()


# -----------------------------------------------------------------------------
# PARSING & UTILITIES
# -----------------------------------------------------------------------------
def _call_text_llm(prompt: str) -> dict:
    """Executes completion on Dataiku LLM endpoint with robust JSON parsing."""
    project = dataiku.api_client().get_default_project()
    llm = project.get_llm(TEXT_MODEL_ENDPOINT)
    completion = llm.new_completion()
    try:
        completion.settings["temperature"] = 0.0
    except Exception:
        pass
    completion.with_message(prompt, role="user")
    response = completion.execute()

    if getattr(response, "success", None) is False:
        raise RuntimeError(str(getattr(response, "error_message", "LLM request failed.")))

    text = getattr(response, "text", "") or ""
    return parse_json_object(strip_think(text))


# -----------------------------------------------------------------------------
# TIMELINE BUILDER & LEDGER PREP
# -----------------------------------------------------------------------------
def build_full_normalized_ledger(case_id: str) -> list[dict]:
    """Rebuilds the COMPLETE normalized ledger for a case applying the latest human corrections."""
    rows_df = case_rows(FINANCIAL_LINE_ITEMS_DATASET, case_id)
    if rows_df.empty:
        return []

    ledger, _withheld = build_fact_ledger(
        rows_df.to_dict(orient="records"),
        load_latest_corrections(case_id),
        load_fact_resolutions(case_id),
    )
    return ledger


def build_and_save_financial_timeline(case_id: str, normalized_ledger: list[dict]) -> pd.DataFrame:
    """Persists all sorted chronological transactions to the financial timeline dataset."""
    if not normalized_ledger:
        return pd.DataFrame()

    df = pd.DataFrame(normalized_ledger)
    if "date" in df.columns:
        df = df.sort_values(by="date", ascending=True)

    df["case_id"] = str(case_id)
    df["timeline_id"] = [random_id("TIMELINE") for _ in range(len(df))]
    if "corrected_fields" in df.columns:
        df["corrected_fields"] = df["corrected_fields"].apply(lambda v: json.dumps(v or [], ensure_ascii=False))

    try:
        replace_case_rows(FINANCIAL_TIMELINE_DATASET, case_id, df.to_dict(orient="records"))
        logger.info(f"Persisted {len(df)} transactions to {FINANCIAL_TIMELINE_DATASET}")
    except Exception as e:
        logger.warning(f"Could not persist timeline dataset: {e}")

    return df


# -----------------------------------------------------------------------------
# CLAIM-BASED SYNTHESIS
# -----------------------------------------------------------------------------
def run_claim_based_accounting_analysis(
    case_id: str,
    normalized_ledger: list[dict],
    customer_claims: list[dict],
    instructions: str = "",
    claims_source: str = "",
) -> dict:
    """Evaluate each financial claim against the reviewed ledger.

    The user's instructions steer the scope and method of the analysis
    only; they are passed to the LLM as guidance and never modify the
    ledger. The instructions and claims used are stored with the result
    so every finding can be traced back to the run that produced it.
    An LLM failure raises, so the stage reports an error instead of
    saving an empty "complete" result.
    """
    if not normalized_ledger:
        raise ValueError("No normalized transactions available for forensic analysis.")

    run_metadata = {
        "instructions": instructions or "",
        "claims_source": claims_source,
        "claims_count": len(customer_claims or []),
        "ledger_rows": len(normalized_ledger),
        "run_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    if not customer_claims:
        result = {"claim_evaluations": [], "run_metadata": run_metadata}
        _persist_forensic_results(case_id, result)
        return result

    compact_ledger = [compact_ledger_record(r) for r in normalized_ledger]

    prompt = CLAIM_BASED_ACCOUNTING_PROMPT.replace("{claims_json}", json.dumps(customer_claims, ensure_ascii=False)) \
                                          .replace("{ledger_json}", json.dumps(compact_ledger, ensure_ascii=False)) \
                                          .replace("{instructions}", instructions or "None provided.")

    print("[forensic synthesis] Evaluating customer claims against financial ledger...", flush=True)
    try:
        findings_result = _call_text_llm(prompt)
    except Exception as err:
        logger.warning(f"Accounting analysis failed: {err!r}")
        raise RuntimeError(f"The accounting analysis model call failed: {err}") from err

    known_ids = {str(r.get("row_id")) for r in normalized_ledger}
    findings_result["claim_evaluations"] = [
        normalise_claim_evaluation(evaluation, known_ids, index)
        for index, evaluation in enumerate(findings_result.get("claim_evaluations") or [])
        if isinstance(evaluation, dict)
    ]

    findings_result["run_metadata"] = run_metadata
    _persist_forensic_results(case_id, findings_result)
    return findings_result


CLAIM_RESULTS = (
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "CONTRADICTED",
    "NOT_VERIFIABLE",
    "NO_FINANCIAL_EVIDENCE",
    "NOT_FINANCIAL_CLAIM",
)


def _as_text_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    items = value if isinstance(value, list) else [value]
    out = []
    for item in items:
        if isinstance(item, dict):
            item = item.get("description") or item.get("item") or item.get("text") or ""
        text = str(item or "").strip()
        if text and text.lower() not in {"none", "n/a", "-"}:
            out.append(text)
    return out


EVIDENCE_GROUPS = (
    "supporting_evidence",
    "partially_supporting_evidence",
    "contradicting_evidence",
    "unresolved_evidence",
)

_LEDGER_KEYS = (
    "fact_type", "date", "description", "amount", "currency", "debit", "credit", "balance",
    "amount_due", "paid_amount", "remaining_amount", "account_number", "transaction_reference",
    "counterparty", "status", "page_number",
)


def compact_ledger_record(entry: dict) -> dict:
    """One ledger fact as the analysis prompt sees it: only non-null fields."""
    record = {"record_id": entry.get("row_id")}
    for key in _LEDGER_KEYS:
        value = entry.get(key)
        if value not in (None, "", []):
            record[key] = str(value)[:160] if key == "description" else value
    if entry.get("user_note"):
        record["reviewer_note"] = str(entry["user_note"])[:200]
    return record


def _evidence_group(value: Any, known_ids: set, unverified: list) -> list[dict]:
    items = value if isinstance(value, list) else ([value] if value else [])
    out = []
    for entry in items:
        if isinstance(entry, dict):
            ids = [str(x) for x in (entry.get("record_ids") or []) if str(x).strip()]
            if entry.get("record_id"):
                ids.append(str(entry["record_id"]))
            text = str(entry.get("explanation") or entry.get("description") or "").strip()
        else:
            ids, text = [], str(entry or "").strip()
        ids = list(dict.fromkeys(ids))
        unverified.extend(x for x in ids if x not in known_ids)
        kept = [x for x in ids if x in known_ids]
        # Evidence that rests only on records the ledger does not contain
        # is not evidence: drop it (its ids are listed as unverified).
        if ids and not kept:
            continue
        if kept or text:
            out.append({"record_ids": kept, "explanation": text})
    return out


def _amount_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"null", "none", "n/a"}:
        return ""
    amount = parse_amount(text)
    return format_amount(amount) if amount is not None else text


def normalise_claim_evaluation(evaluation: dict, known_ids: set, index: int = 0) -> dict:
    """Make one LLM claim evaluation safe to store and display.

    * evidence is grouped as supporting / partially supporting /
      contradicting / unresolved, each entry {record_ids, explanation};
      only ids present in the reviewed ledger are kept, others move to
      `unverified_record_ids`;
    * missing_evidence is a list of strings;
    * results from the earlier single-list format (evidence_record_ids,
      contradictions, financial_evidence_found) are mapped onto the groups;
    * a result outside CLAIM_RESULTS is not reinterpreted: it becomes
      NOT_VERIFIABLE and the model's wording is kept in result_raw.
    """
    item = dict(evaluation)
    item["claim_id"] = str(item.get("claim_id") or f"CLM_{index + 1:03d}")
    unverified: list = []

    for group in EVIDENCE_GROUPS:
        item[group] = _evidence_group(item.get(group), known_ids, unverified)

    # Earlier format -> groups.
    legacy_ids = [str(x) for x in (item.get("evidence_record_ids") or []) if str(x).strip()]
    for found in item.get("financial_evidence_found") or []:
        if isinstance(found, dict) and str(found.get("record_id") or "").strip():
            legacy_ids.append(str(found["record_id"]))
    if legacy_ids and not item["supporting_evidence"] and not item["partially_supporting_evidence"]:
        item["supporting_evidence"] = _evidence_group(
            [{"record_ids": list(dict.fromkeys(legacy_ids)), "explanation": ""}], known_ids, unverified)
    if item.get("contradictions") and not item["contradicting_evidence"]:
        item["contradicting_evidence"] = _evidence_group(item.get("contradictions"), known_ids, unverified)

    item["missing_evidence"] = _as_text_list(item.get("missing_evidence"))
    item["claimed_amount"] = _amount_text(item.get("claimed_amount"))
    item["substantiated_amount"] = _amount_text(item.get("substantiated_amount"))
    item["accounting_position"] = str(item.get("accounting_position") or item.get("accounting_response") or "").strip()
    item["parent_claim"] = str(item.get("parent_claim") or item.get("claim") or "").strip()

    # Flat views kept for the pleading and chatbot context.
    item["evidence_record_ids"] = list(dict.fromkeys(
        x for group in ("supporting_evidence", "partially_supporting_evidence")
        for entry in item[group] for x in entry["record_ids"]))
    item["contradictions"] = [
        {"description": entry["explanation"], "record_ids": entry["record_ids"]}
        for entry in item["contradicting_evidence"]
    ]
    item["unverified_record_ids"] = list(dict.fromkeys(unverified))

    result = str(item.get("result") or "").strip().upper().replace(" ", "_").replace("-", "_")
    if result not in CLAIM_RESULTS:
        item["result_raw"] = item.get("result")
        result = "NOT_VERIFIABLE"
    item["result"] = result
    return item


# -----------------------------------------------------------------------------
# DISCREPANCY / NUMBERS-AGREEMENT SYNTHESIS (no customer claims required)
# -----------------------------------------------------------------------------
DISCREPANCY_AND_FINDINGS_PROMPT = r"""
You are the Chief Forensic Auditor for Banque Saudi Fransi (BSF), cross-checking
the bank's own extracted financial ledger for internal numeric consistency and
preparing the forensic accounting findings that will support the bank's
written pleading.

FINANCIAL LEDGER (all extracted transactions, chronological):
{ledger_json}

TASKS:
1. Cross-check the numbers: total inflows, total transfers to the bank, any
   disputed freeze/hold amount, and whether the ledger is internally
   consistent (debits, credits and running balances agree with each other,
   no unexplained gaps).
2. Identify and categorize any discrepancies (e.g. bank_error,
   ocr_extraction_issue, customer_misstatement, missing_evidence, rounding,
   other), each with a clear explanation and the ledger record(s) it draws on.
3. Write the forensic accounting findings summary supporting the bank's defence.

RULES:
- Use ONLY the transactions given. Never invent amounts, dates or references.
- Every discrepancy must cite the record(s) (date/description/amount) it is
   based on in "evidence_support".
- Provide the executive summary in BOTH Arabic and English.
- If the ledger is too small or too clean to raise any discrepancy, return an
   empty "discrepancies" list rather than inventing one.

RETURN JSON ONLY:
{
  "cross_check_summary": {
    "numbers_agree_overall": true,
    "total_inflows": "...",
    "total_transfers_to_bank": "...",
    "disputed_freeze_amount": "...",
    "primary_discrepancy_narrative": "..."
  },
  "discrepancies": [
    {
      "issue_title": "...",
      "category": "...",
      "analysis": "...",
      "evidence_support": "...",
      "source_quote": "..."
    }
  ],
  "accounting_findings": {
    "executive_summary_en": "...",
    "executive_summary_ar": "...",
    "bank_financial_posture": "...",
    "recommended_legal_arguments": ["..."]
  }
}
""".strip()


def run_discrepancy_and_findings_analysis(case_id: str, normalized_ledger: list[dict]) -> dict:
    """Case-wide numbers-agreement cross-check over the normalized ledger —
    no customer claims involved, unlike run_claim_based_accounting_analysis.
    Persists cross_check_summary / discrepancies / accounting_findings so
    load_saved_forensic_results can serve them back to /case and /accounting/synthesize.
    """
    if not normalized_ledger:
        raise ValueError("No normalized transactions available for forensic analysis.")

    compact_ledger = [
        {
            "page_number": r.get("page_number"),
            "date": r.get("date"),
            "type": r.get("debit_or_credit"),
            "amount": r.get("amount"),
            "currency": r.get("currency"),
            "description": str(r.get("description", ""))[:120],
        }
        for r in normalized_ledger
    ]

    prompt = DISCREPANCY_AND_FINDINGS_PROMPT.replace(
        "{ledger_json}", json.dumps(compact_ledger, ensure_ascii=False)
    )

    try:
        print("[forensic synthesis] Cross-checking ledger numbers and building findings...", flush=True)
        result = _call_text_llm(prompt)
    except Exception as err:
        logger.warning(f"Discrepancy/findings analysis failed: {err!r}")
        result = {"cross_check_summary": {}, "discrepancies": [], "accounting_findings": {}}

    _persist_forensic_results(case_id, result)
    return result


def _persist_forensic_results(case_id: str, results: dict):
    row = {
        "finding_id": random_id("FIND"),
        "case_id": str(case_id),
        "accounting_findings_json": json.dumps(results, ensure_ascii=False),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        replace_case_rows(FINANCIAL_FINDINGS_DATASET, case_id, [row])
    except Exception as e:
        logger.warning(f"Could not persist findings dataset: {e}")
        raise


def load_saved_forensic_results(case_id: str) -> dict:
    """Reads back persisted timeline and new claim findings for the case."""
    out = {
        "timeline": [],
        "claim_evaluations": [],
        "discrepancies": [],
        "cross_check_summary": {},
        "accounting_findings": {},
        "run_metadata": {},
    }
    try:
        df_t = case_rows(FINANCIAL_TIMELINE_DATASET, case_id)
        if not df_t.empty:
            out["timeline"] = df_t.to_dict(orient="records")
    except Exception:
        pass

    try:
        matches = case_rows(FINANCIAL_FINDINGS_DATASET, case_id)
        if not matches.empty:
            latest = matches.iloc[-1].to_dict()
            parsed_findings = json.loads(latest.get("accounting_findings_json", "{}") or "{}")
            out["claim_evaluations"] = parsed_findings.get("claim_evaluations", [])
            out["discrepancies"] = parsed_findings.get("discrepancies", [])
            out["cross_check_summary"] = parsed_findings.get("cross_check_summary", {})
            out["accounting_findings"] = parsed_findings.get("accounting_findings", {})
            out["run_metadata"] = parsed_findings.get("run_metadata", {})
    except Exception:
        pass

    return out

