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

from .storage import case_rows
from .financial_corrections import load_latest_corrections
from .financial_normalizer import normalize_row_for_ledger
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
Evaluate each customer claim against the available financial records. 

INPUTS:
- Customer Claims: {claims_json}
- Financial Evidence (Normalized Ledger): {ledger_json}
- User Analysis Instructions: {instructions}

METHODOLOGY:
1. Understand each customer claim and determine the exact financial question that needs to be investigated.
2. Read the User Analysis Instructions and use them to determine the requested accounting focus, scope, or methodology.
3. Determine what financial evidence would normally be expected to answer the claim and the requested analysis.
4. Identify the relevant financial evidence from the provided ledger.
5. Perform the requested accounting analysis using the available evidence.
6. Compare the claim against the financial evidence.
7. Clearly identify any discrepancies, missing evidence, unexplained amounts, inconsistencies, or limitations.

HOW TO USE THE USER ANALYSIS INSTRUCTIONS:
- Treat the user's instructions as guidance for what should be investigated.
- The instructions may specify a period, transaction type, amount, calculation, reconciliation, discrepancy, or accounting question to focus on.
- The instructions guide the scope and methodology of the accounting analysis.
- The instructions MUST NOT determine the conclusion.
- Do not assume that a hypothesis stated by the user is true.
- Verify the requested issue independently using the provided financial evidence.
- Do not ignore evidence that contradicts the user's requested hypothesis.
- If the evidence does not support the user's requested hypothesis, state that clearly.
- If no user instructions are provided, perform the normal claim-based accounting analysis.

RULES:
- Use ONLY the provided claims and financial evidence.
- Never invent transactions, amounts, dates, references, calculations, or supporting evidence.
- Every accounting conclusion must be supported by the available financial evidence.
- Do not make legal conclusions such as liability, regulatory violations, or legal entitlement.
- Clearly state limitations when the available ledger cannot fully answer the accounting question.
- Result must be one of: SUPPORTED, PARTIALLY_SUPPORTED, CONTRADICTED, NOT_VERIFIABLE, NO_FINANCIAL_EVIDENCE, NOT_FINANCIAL_CLAIM.
RETURN JSON ONLY:
{
  "claim_evaluations": [
    {
      "claim_id": "CLM_001",
      "claim": "...",
      "financial_question": "...",
      "expected_evidence": "...",
      "financial_evidence_found": [
        {
          "record_id": "...",
          "date": "...",
          "type": "...",
          "amount": 0.0,
          "reference": "..."
        }
      ],
      "comparison": "...",
      "result": "SUPPORTED",
      "accounting_response": "...",
      "limitation": "...",
      "evidence_record_ids": ["..."]
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

    corrections = load_latest_corrections(case_id)
    rows = rows_df.to_dict(orient="records")
    return [normalize_row_for_ledger(row, corrections) for row in rows]


def build_and_save_financial_timeline(case_id: str, normalized_ledger: list[dict]) -> pd.DataFrame:
    """Persists all sorted chronological transactions to the financial timeline dataset."""
    if not normalized_ledger:
        return pd.DataFrame()

    df = pd.DataFrame(normalized_ledger)
    if "date" in df.columns:
        df = df.sort_values(by="date", ascending=True)

    df["case_id"] = str(case_id)
    df["timeline_id"] = [random_id("TIMELINE") for _ in range(len(df))]

    try:
        ds = dataiku.Dataset(FINANCIAL_TIMELINE_DATASET)
        try:
            ex = ds.get_dataframe()
            if not ex.empty and "case_id" in ex.columns:
                ex = ex[ex["case_id"].astype(str) != str(case_id)].copy()
                final_df = pd.concat([ex, df], ignore_index=True)
            else:
                final_df = df
        except Exception:
            final_df = df
        ds.write_with_schema(final_df)
        logger.info(f"Persisted {len(df)} transactions to {FINANCIAL_TIMELINE_DATASET}")
    except Exception as e:
        logger.warning(f"Could not persist timeline dataset: {e}")

    return df


# -----------------------------------------------------------------------------
# CLAIM-BASED SYNTHESIS
# -----------------------------------------------------------------------------
def run_claim_based_accounting_analysis(case_id: str, normalized_ledger: list[dict], customer_claims: list[dict], instructions: str = "") -> dict:
    if not normalized_ledger:
        raise ValueError("No normalized transactions available for forensic analysis.")
    if not customer_claims:
        return {"claim_evaluations": []}

    # Format the ledger to preserve token context
    compact_ledger = [
        {
            "record_id": r.get("row_id"),
            "date": r.get("date"),
            "type": r.get("debit_or_credit"),
            "amount": r.get("amount"),
            "description": str(r.get("description", ""))[:50]
        }
        for r in normalized_ledger
    ]

    prompt = CLAIM_BASED_ACCOUNTING_PROMPT.replace("{claims_json}", json.dumps(customer_claims, ensure_ascii=False)) \
                                          .replace("{ledger_json}", json.dumps(compact_ledger, ensure_ascii=False)) \
                                          .replace("{instructions}", instructions or "None provided.")

    try:
        print("[forensic synthesis] Evaluating customer claims against financial ledger...", flush=True)
        findings_result = _call_text_llm(prompt)
    except Exception as err:
        logger.warning(f"Accounting analysis failed: {err!r}")
        findings_result = {"claim_evaluations": []}

    _persist_forensic_results(case_id, findings_result)
    return findings_result


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
    ds = dataiku.Dataset(FINANCIAL_FINDINGS_DATASET)
    try:
        ex_f = ds.get_dataframe()
        if not ex_f.empty and "case_id" in ex_f.columns:
            ex_f = ex_f[ex_f["case_id"].astype(str) != str(case_id)].copy()
            final_f = pd.concat([ex_f, pd.DataFrame([row])], ignore_index=True)
        else:
            final_f = pd.DataFrame([row])
        ds.write_with_schema(final_f)
    except Exception as e:
        logger.warning(f"Could not persist findings dataset: {e}")


def load_saved_forensic_results(case_id: str) -> dict:
    """Reads back persisted timeline and new claim findings for the case."""
    out = {
        "timeline": [],
        "claim_evaluations": [],
        "discrepancies": [],
        "cross_check_summary": {},
        "accounting_findings": {},
    }
    try:
        ds_t = dataiku.Dataset(FINANCIAL_TIMELINE_DATASET)
        df_t = ds_t.get_dataframe()
        if not df_t.empty and "case_id" in df_t.columns:
            out["timeline"] = df_t[df_t["case_id"].astype(str) == str(case_id)].to_dict(orient="records")
    except Exception:
        pass

    try:
        ds_f = dataiku.Dataset(FINANCIAL_FINDINGS_DATASET)
        df_f = ds_f.get_dataframe()
        if not df_f.empty and "case_id" in df_f.columns:
            matches = df_f[df_f["case_id"].astype(str) == str(case_id)]
            if not matches.empty:
                latest = matches.iloc[-1].to_dict()
                parsed_findings = json.loads(latest.get("accounting_findings_json", "{}") or "{}")
                out["claim_evaluations"] = parsed_findings.get("claim_evaluations", [])
                out["discrepancies"] = parsed_findings.get("discrepancies", [])
                out["cross_check_summary"] = parsed_findings.get("cross_check_summary", {})
                out["accounting_findings"] = parsed_findings.get("accounting_findings", {})
    except Exception:
        pass

    return out

