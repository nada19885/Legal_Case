"""
Claim-Based Financial Forensics Synthesis
Location: lib/python/legal_platform/financial_forensics.py
"""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any, Callable, Optional

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
def _response_error(response: Any) -> str:
    for name in ("error_message", "errorMessage"):
        value = getattr(response, name, None)
        if value:
            return str(value)
    raw = getattr(response, "_raw", None)
    if isinstance(raw, dict):
        for name in ("errorMessage", "error_message", "error"):
            if raw.get(name):
                return str(raw[name])
    return ""


def _call_text_llm(prompt: str, attempts: int = 2) -> dict:
    """Executes completion on Dataiku LLM endpoint with robust JSON parsing.
    Retries once; the error names the prompt size, since an over-long
    prompt is the usual cause of a failure with no message."""
    last_error = ""
    for attempt in range(1, attempts + 1):
        project = dataiku.api_client().get_default_project()
        llm = project.get_llm(TEXT_MODEL_ENDPOINT)
        completion = llm.new_completion()
        try:
            completion.settings["temperature"] = 0.0
        except Exception:
            pass
        completion.with_message(prompt, role="user")
        try:
            response = completion.execute()
        except Exception as error:
            last_error = repr(error)
        else:
            if getattr(response, "success", None) is not False:
                text = getattr(response, "text", "") or ""
                return parse_json_object(strip_think(text))
            last_error = _response_error(response) or "no error message returned"
        if attempt < attempts:
            time.sleep(2.0)
    raise RuntimeError(f"LLM request failed ({last_error}; prompt of {len(prompt):,} characters).")


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
    progress: Optional[Callable[[str, int, int], None]] = None,
) -> dict:
    """Evaluate each financial claim against the reviewed ledger.
    A ledger too large for one request is read in parts with a notebook
    per claim (see _rolling_claim_analysis); progress(detail, current,
    total) reports which part is being read.

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
    claims = [
        dict(claim, claim_ref=f"C{index + 1:03d}") if isinstance(claim, dict)
        else {"claim_ref": f"C{index + 1:03d}", "allegation_text": str(claim)}
        for index, claim in enumerate(customer_claims)
    ]

    print("[forensic synthesis] Evaluating customer claims against financial ledger...", flush=True)
    try:
        prompt = _claims_prompt(claims, compact_ledger, instructions)
        if len(prompt) <= MAX_SINGLE_PROMPT_CHARS:
            evaluations = _call_text_llm(prompt).get("claim_evaluations") or []
            run_metadata["method"] = "single_call"
        else:
            evaluations = _rolling_claim_analysis(claims, compact_ledger, instructions, run_metadata, progress)
    except Exception as err:
        logger.warning(f"Accounting analysis failed: {err!r}")
        raise RuntimeError(f"The accounting analysis model call failed: {err}") from err

    findings_result = {"claim_evaluations": evaluations}
    known_ids = {str(r.get("row_id")) for r in normalized_ledger}
    findings_result["claim_evaluations"] = [
        normalise_claim_evaluation(evaluation, known_ids, index)
        for index, evaluation in enumerate(findings_result.get("claim_evaluations") or [])
        if isinstance(evaluation, dict)
    ]
    ids = [e["claim_id"] for e in findings_result["claim_evaluations"]]
    if len(set(ids)) != len(ids):
        # Claims analysed in separate groups can repeat ids: renumber.
        for index, evaluation in enumerate(findings_result["claim_evaluations"]):
            evaluation["claim_id"] = f"CLM_{index + 1:03d}"

    findings_result["run_metadata"] = run_metadata
    _persist_forensic_results(case_id, findings_result)
    return findings_result


# -----------------------------------------------------------------------------
# Large ledgers: read the ledger in parts, keeping a notebook per claim
# -----------------------------------------------------------------------------
# When the whole ledger does not fit in one request, it is read in parts, in
# order. For every claim the code keeps a NOTEBOOK: the facts found so far that
# support, partially support, contradict or leave the claim unclear, plus short
# notes. Each part is read together with the notebook so far; the model reports
# only what is NEW in that part, and the code adds it to the notebook, so
# nothing found earlier can be lost or silently changed. After the last part,
# a final step writes each claim's verdict and accounting position from the
# complete notebook, the facts it cites and a whole-ledger summary.
MAX_SINGLE_PROMPT_CHARS = 45000
LEDGER_CHUNK_CHARS = 25000
CLAIMS_PER_ANALYSIS = 5
ANALYSIS_WORKERS = 4
MAX_NOTES_PER_CLAIM = 6
MAX_FINAL_RECORDS_PER_CLAIM = 150

NOTEBOOK_GROUPS = ("supporting", "partially_supporting", "contradicting", "unresolved")

READ_PART_PROMPT = r"""
You are a senior forensic accountant representing Banque Saudi Fransi (BSF). You are reading a large case
ledger ONE PART AT A TIME. For every claim there is a notebook of what was found in the parts already read.

Claims: {claims_json}
Notebook so far (per claim: record_ids already found in each group, amounts found so far, notes):
{notebook_json}
User analysis instructions (they set scope and method, never the conclusion): {instructions}
This part of the ledger ({part_label}): {ledger_json}

TASK: for each claim, report ONLY what is NEW in THIS PART:
- supporting: records in this part that establish the claim (or part of it);
- partially_supporting: records that establish only part of it;
- contradicting: records that cannot be true together with the claim;
- unresolved: records whose relevance or meaning is ambiguous (e.g. INFERRED facts).
Every entry cites record_ids FROM THIS PART and explains in one sentence how they bear on the claim.
Add a short "note" updating the running picture (e.g. "350,000 of the claimed 500,000 found so far").
A missing record is not a contradiction. Do not repeat records already in the notebook.
Omit claims for which this part contains nothing new. Use only the ledger; never invent records or amounts.

RETURN JSON ONLY:
{"updates": [{"claim_ref": "C001",
  "supporting": [{"record_ids": ["..."], "explanation": "..."}],
  "partially_supporting": [], "contradicting": [], "unresolved": [],
  "note": "..."}]}
""".strip()


def _claims_prompt(claims: list, ledger: list, instructions: str, summary: Optional[dict] = None,
                   notebook: Optional[dict] = None) -> str:
    ledger_json = json.dumps(ledger, ensure_ascii=False)
    if summary is not None:
        ledger_json = json.dumps({
            "note": ("The ledger was read in parts. 'evidence_found_while_reading' lists, per claim, what was "
                     "found in every part; 'records' are the facts it cites; 'ledger_summary' covers the whole "
                     "ledger. Base the verdict on all of it; echo each claim's claim_ref."),
            "ledger_summary": summary,
            "evidence_found_while_reading": notebook or {},
            "records": ledger,
        }, ensure_ascii=False)
    return CLAIM_BASED_ACCOUNTING_PROMPT.replace("{claims_json}", json.dumps(claims, ensure_ascii=False)) \
                                        .replace("{ledger_json}", ledger_json) \
                                        .replace("{instructions}", instructions or "None provided.")


def _chunks_by_size(records: list, max_chars: int) -> list:
    chunks, current, size = [], [], 0
    for record in records:
        length = len(json.dumps(record, ensure_ascii=False)) + 1
        if current and size + length > max_chars:
            chunks.append(current)
            current, size = [], 0
        current.append(record)
        size += length
    if current:
        chunks.append(current)
    return chunks


def _record_value(record: dict) -> tuple[Optional[str], Optional[Decimal]]:
    for field in ("amount", "paid_amount", "remaining_amount", "amount_due", "balance", "debit", "credit"):
        value = parse_amount(record.get(field))
        if value is not None:
            return field, value
    return None, None


def ledger_summary(records: list) -> dict:
    """Whole-ledger overview: counts and totals per fact type and currency,
    and the date range."""
    by_type: dict = {}
    dates = []
    for record in records:
        key = f"{record.get('fact_type') or 'other'} ({record.get('currency') or 'no currency'})"
        entry = by_type.setdefault(key, {"count": 0, "total": Decimal(0)})
        entry["count"] += 1
        _, value = _record_value(record)
        if value is not None:
            entry["total"] += value
        if record.get("date"):
            dates.append(str(record["date"]))
    return {
        "facts": len(records),
        "by_type": {key: {"count": v["count"], "total": format_amount(v["total"])} for key, v in by_type.items()},
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
    }


def new_notebook(claim_refs: list) -> dict:
    return {ref: dict({group: [] for group in NOTEBOOK_GROUPS}, notes=[]) for ref in claim_refs}


def merge_part_updates(notebook: dict, updates: list, part_ids: set, part_label: str) -> None:
    """Add one part's findings to the notebook. Only ids that belong to the
    part just read are accepted, and ids already in the notebook are not
    added twice; existing entries are never changed or removed."""
    for update in updates or []:
        if not isinstance(update, dict) or update.get("claim_ref") not in notebook:
            continue
        page = notebook[update["claim_ref"]]
        seen = {x for group in NOTEBOOK_GROUPS for entry in page[group] for x in entry["record_ids"]}
        for group in NOTEBOOK_GROUPS:
            for entry in update.get(group) or []:
                if not isinstance(entry, dict):
                    continue
                ids = [str(x) for x in entry.get("record_ids") or [] if str(x) in part_ids and str(x) not in seen]
                if ids:
                    seen.update(ids)
                    page[group].append({"record_ids": ids,
                                        "explanation": str(entry.get("explanation") or "")[:400],
                                        "found_in": part_label})
        note = str(update.get("note") or "").strip()
        if note:
            page["notes"].append(f"{part_label}: {note[:300]}")
            page["notes"] = page["notes"][-MAX_NOTES_PER_CLAIM:]


def notebook_view(notebook: dict, by_id: dict) -> dict:
    """What the model sees of the notebook: ids per group, amounts found so
    far (computed here, per currency) and the latest notes."""
    view = {}
    for ref, page in notebook.items():
        found: dict = {}
        for group in ("supporting", "partially_supporting"):
            for entry in page[group]:
                for record_id in entry["record_ids"]:
                    record = by_id.get(record_id) or {}
                    _, value = _record_value(record)
                    if value is not None:
                        currency = record.get("currency") or "no currency"
                        found[currency] = found.get(currency, Decimal(0)) + value
        view[ref] = {
            **{group: [x for entry in page[group] for x in entry["record_ids"]] for group in NOTEBOOK_GROUPS},
            "amount_found_so_far": {currency: format_amount(total) for currency, total in found.items()},
            "notes": page["notes"],
        }
    return view


def _rolling_claim_analysis(claims: list, ledger: list, instructions: str, run_metadata: dict,
                            progress: Optional[Callable[[str, int, int], None]] = None) -> list:
    parts = _chunks_by_size(ledger, LEDGER_CHUNK_CHARS)
    by_id = {str(record.get("record_id")): record for record in ledger}
    compact_claims = [
        {"claim_ref": claim["claim_ref"],
         "claim": str(claim.get("allegation_text") or claim.get("claim") or claim)[:600]}
        for claim in claims
    ]
    notebook = new_notebook([claim["claim_ref"] for claim in claims])

    # 1) Read the parts in order; each one updates the notebook.
    for number, part in enumerate(parts, start=1):
        label = f"part {number} of {len(parts)}"
        if progress:
            progress(f"Reading the ledger: {label}…", number, len(parts))
        prompt = READ_PART_PROMPT.replace("{claims_json}", json.dumps(compact_claims, ensure_ascii=False)) \
                                 .replace("{notebook_json}", json.dumps(notebook_view(notebook, by_id), ensure_ascii=False)) \
                                 .replace("{instructions}", instructions or "None provided.") \
                                 .replace("{part_label}", label) \
                                 .replace("{ledger_json}", json.dumps(part, ensure_ascii=False))
        updates = _call_text_llm(prompt).get("updates") or []
        merge_part_updates(notebook, updates, {str(r.get("record_id")) for r in part}, label)

    # 2) Final verdict per group of claims, from the complete notebook.
    summary = ledger_summary(ledger)
    groups = [claims[i:i + CLAIMS_PER_ANALYSIS] for i in range(0, len(claims), CLAIMS_PER_ANALYSIS)]
    if progress:
        progress("Writing the accounting positions…", 0, len(groups))

    def cited(claim):
        page = notebook[claim["claim_ref"]]
        order = ("contradicting", "supporting", "partially_supporting", "unresolved")
        ids = [x for group in order for entry in page[group] for x in entry["record_ids"]]
        return list(dict.fromkeys(ids))[:MAX_FINAL_RECORDS_PER_CLAIM]

    def finalise(group):
        ids = list(dict.fromkeys(x for claim in group for x in cited(claim)))
        records = [by_id[x] for x in ids if x in by_id]
        pages = {claim["claim_ref"]: notebook[claim["claim_ref"]] for claim in group}
        prompt = _claims_prompt(group, records, instructions, summary, pages)
        if len(prompt) > MAX_SINGLE_PROMPT_CHARS and len(group) > 1:
            return [evaluation for claim in group for evaluation in finalise([claim])]
        evaluations = _call_text_llm(prompt).get("claim_evaluations") or []
        refs = [claim["claim_ref"] for claim in group]
        for index, evaluation in enumerate(evaluations):
            if isinstance(evaluation, dict) and evaluation.get("claim_ref") not in refs and len(evaluations) == len(refs):
                evaluation["claim_ref"] = refs[index]
        return evaluations

    evaluations: list = []
    with ThreadPoolExecutor(max_workers=ANALYSIS_WORKERS) as pool:
        for result in pool.map(finalise, groups):
            evaluations.extend(result)

    # 3) Nothing found while reading may be dropped by the final step.
    for evaluation in evaluations:
        page = notebook.get(evaluation.get("claim_ref")) if isinstance(evaluation, dict) else None
        if not page:
            continue
        present = {str(x) for group in ("supporting_evidence", "partially_supporting_evidence",
                                         "contradicting_evidence", "unresolved_evidence")
                   for entry in (evaluation.get(group) or []) if isinstance(entry, dict)
                   for x in entry.get("record_ids") or []}
        for group in NOTEBOOK_GROUPS:
            for entry in page[group]:
                missing = [x for x in entry["record_ids"] if x not in present]
                if missing:
                    evaluation.setdefault(f"{group}_evidence", []).append(
                        {"record_ids": missing, "explanation": entry["explanation"]})
                    present.update(missing)

    run_metadata.update({
        "method": "read_in_parts",
        "ledger_parts": len(parts),
        "claim_groups": len(groups),
        "records_cited": len({x for page in notebook.values() for group in NOTEBOOK_GROUPS
                              for entry in page[group] for x in entry["record_ids"]}),
    })
    return evaluations


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

