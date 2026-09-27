"""
Text-LLM Reconstruction Engine — Stage 2 of the financial evidence-extraction pipeline.
Location: lib/python/legal_platform/financial_reconciliation.py
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Optional

from .config import (
    FINANCIAL_EXTRACTION_LLM_ID,
    FINANCIAL_LINE_ITEMS_DATASET,
    FINANCIAL_REQUEST_MAX_ATTEMPTS,
    FINANCIAL_RETRY_DELAY_SECONDS,
)
from .financial_fields import FIELD_NAMES, REQUIRED_FIELDS, field_issue
from .ids import stable_id
from .llm import complete_json
from .storage import append_rows

RECONSTRUCTION_SYSTEM_PROMPT = r"""
You are an expert forensic accountant reconciling two independent extractions of a single financial page.

Source A (structural_evidence): Clean native table arrays extracted directly from the PDF code.
Source B (transcription_text): Verbatim OCR transcription from a visual model.

YOUR TASK:
1. Reconstruct the genuine financial transaction rows.
2. Rewrite semantic fields (description, transaction type) into clean, professional terms (e.g., 'Financing installment payment no. 5' instead of fragmented OCR). Do not invent new facts.
3. For exact financial facts (amount, date, reference, balance), PRESERVE THE EXACT NUMBERS.
4. Determine certainty field-by-field:
   - If the sources agree or the data is perfectly clear, set `certain: true`.
   - If the sources conflict (e.g., structural says 12,500 but VLM says 17,500), pick the most likely correct value, set `certain: false`, and explain your reasoning in `reason`.
   - If a value is hard to read, ambiguous, or you had to interpret it, give your best reading, set `certain: false`, and explain what is unclear in `reason`.
5. NEVER GUESS OR DEFAULT A VALUE:
   - If a value is not on the page, return value "" with `certain: false` and say so in `reason`.
   - Currency: use the currency printed on the row, or the account/statement currency printed elsewhere on this page (say where in `reason`). Do NOT assume SAR.
   - debit_or_credit must be exactly "debit" or "credit". If the direction cannot be determined from the page, return "" with `certain: false`.
6. For each row, copy the row exactly as printed on the page into `row_source_text` so a reviewer can check it.

RETURN JSON SCHEMA ONLY:
{
  "transactions": [
    {
      "row_index": 1,
      "date": { "value": "", "certain": true, "reason": "" },
      "description": { "value": "", "certain": true, "reason": "" },
      "amount": { "value": "", "certain": true, "reason": "" },
      "currency": { "value": "", "certain": true, "reason": "" },
      "debit_or_credit": { "value": "debit|credit", "certain": true, "reason": "" },
      "reference_number": { "value": "", "certain": true, "reason": "" },
      "party_source": { "value": "", "certain": true, "reason": "" },
      "running_balance": { "value": "", "certain": true, "reason": "" },
      "row_source_text": ""
    }
  ]
}
""".strip()


def reconstruct_page_transactions(
    structural_evidence: dict,
    transcription_text: str,
    page_number: int,
) -> dict:
    payload = {
        "page_number": page_number,
        "structural_evidence": structural_evidence,
        "transcription_text": transcription_text,
    }

    last_error: Optional[Exception] = None
    for attempt in range(1, int(FINANCIAL_REQUEST_MAX_ATTEMPTS) + 1):
        try:
            return complete_json(
                system_prompt=RECONSTRUCTION_SYSTEM_PROMPT,
                user_payload=payload,
                llm_id=FINANCIAL_EXTRACTION_LLM_ID,
                temperature=0.0,
            )
        except Exception as error:
            last_error = error
            if attempt < int(FINANCIAL_REQUEST_MAX_ATTEMPTS):
                time.sleep(float(FINANCIAL_RETRY_DELAY_SECONDS))
    raise RuntimeError(f"Stage 2 reconstruction failed: {last_error!r}")


def build_rows_from_reconstruction(
    page_id: str,
    case_document_id: str,
    page_number: int,
    reconstruction: dict,
) -> list[dict]:
    """Turn the LLM reconstruction into fin_line_items rows.

    Field statuses:
      verified          the LLM was certain and the value is usable;
      conflict          the LLM was uncertain -> user review, with its
                        suggested value as the only candidate;
      missing_required  a REQUIRED_FIELDS value is absent or unusable
                        -> user review (never defaulted);
      missing           an optional field is absent (not blocking).
    Rows with no value at all are dropped as noise.
    """
    rows: list[dict] = []
    for idx, item in enumerate(reconstruction.get("transactions", []) or []):
        if not isinstance(item, dict):
            continue
        resolved_fields = {}
        for field_name in FIELD_NAMES:
            info = item.get(field_name)
            if not isinstance(info, dict):
                info = {"value": info, "certain": False} if info not in (None, "") else {}
            value = str(info.get("value", "") or "").strip()
            certain = bool(info.get("certain", False))
            reason = str(info.get("reason", "") or "").strip()

            if not value:
                status = "missing_required" if field_name in REQUIRED_FIELDS else "missing"
                candidates = []
                if status == "missing_required" and not reason:
                    reason = "No value was found for this field on the page."
            elif certain:
                status = "verified"
                candidates = []
            else:
                status = "conflict"
                candidates = [{"value": value, "source": "AI Suggested"}]

            resolved_fields[field_name] = {
                "value": value,
                "status": status,
                "candidates": candidates,
                "reason": reason,
            }

            # A certain-but-invalid direction ("unclear", "dr/cr"...) is
            # still a question for the user, not something to infer later.
            if status == "verified" and field_issue(field_name, resolved_fields[field_name]):
                resolved_fields[field_name]["status"] = "conflict"
                resolved_fields[field_name]["candidates"] = [{"value": value, "source": "AI Suggested"}]
                resolved_fields[field_name]["reason"] = reason or "Direction must be debit or credit."

        if not any(resolved_fields[name]["value"] for name in FIELD_NAMES):
            continue

        source_text = str(item.get("row_source_text", "") or item.get("source_quote", "") or "").strip()
        resolved_fields["_row"] = {"source_text": source_text[:1000]}

        needs_review = any(field_issue(name, resolved_fields[name]) for name in FIELD_NAMES)
        row_status = "needs_review" if needs_review else "verified"

        try:
            row_index = int(item.get("row_index", idx))
        except (TypeError, ValueError):
            row_index = idx
        cluster_key = f"ROW_{page_number}_{row_index}"
        row_id = stable_id("FLI", page_id, cluster_key)

        rows.append({
            "row_id": row_id,
            "page_id": page_id,
            "case_document_id": case_document_id,
            "page_number": page_number,
            "cluster_key": cluster_key,
            "fields_json": json.dumps(resolved_fields, ensure_ascii=False),
            "row_status": row_status,
            "has_conflict": row_status == "needs_review",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    return rows


def persist_reconciled_rows(case_id: str, rows: list[dict]) -> int:
    for row in rows:
        row["case_id"] = case_id
    return append_rows(FINANCIAL_LINE_ITEMS_DATASET, rows)