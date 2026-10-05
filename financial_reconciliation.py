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


# =============================================================================
# ATOMIC FINANCIAL FACTS (current extraction)
# =============================================================================
ATOMIC_FACTS_SYSTEM_PROMPT = r"""
You are a forensic accountant reviewing ONE page of a legal case file.

ATOMIC FINANCIAL FACTS are the smallest independently verifiable financial facts that YOU find in an actual
financial / accounting record: bank or account statements, transaction histories, ledgers, balance reports,
debit / credit records, payment and transfer records or confirmations, financing and loan statements, repayment /
amortization schedules, instalment histories, outstanding-balance records, settlement and reconciliation
statements, financial statements, balance sheets, income and cash-flow statements, trial balances, journal
entries, invoices and receipts.

What emails, letters, correspondence, fraud-investigation messages, statements of claim, complaints, pleadings,
memoranda, case summaries, witness statements, narratives or legal arguments SAY about money is NOT a fact, even
with amounts, dates, account numbers, IBANs, balances, payments, transfers, deductions or frozen amounts. It is a
FINANCIAL CLAIM: something to verify against the records. Example: an email "The customer transferred SAR 250 to
BSF" gives NO fact; it gives the claim "The customer transferred SAR 250 to BSF".
Decision rule for every value: did I find it in an accounting record on this page? Yes -> fact. No -> claim.

STEP 1 - SECTIONS. Split the page into its logical sections (an email header, its body, a pasted transaction
record, a signature, a statement table...). Label each:
- "accounting_evidence": an accounting record (give its source_type);
- "claim": what a party, lawyer, employee or document asserts about money;
- "context": anything else (headers, signatures, disclaimers, legal text).
STEP 2 - FACTS only from "accounting_evidence" sections. Each fact names its section.
STEP 3 - CLAIMS: every financial statement made in "claim" sections, word for word, for the accountant to verify.
Never turn a claim into a fact.

You receive:
- transcription_text: the page's consolidated text. It comes from the PDF's own text when that was reliable
  (page_route "native" / "native+vlm") or from vision-model readings of the page image (page_route "vlm").
  Tables are markdown, one row per entry. A value written [?: A | B] was read differently by the readers: such
  a fact is UNCERTAIN, with A and B as alternatives.
- structural_evidence: text and tables read directly from the PDF (may be empty for scanned pages).
- page_classification: what the page was classified as (financial = an accounting record; mixed = narrative
  with an accounting record section inside).
Arabic text in structural_evidence can be garbled (letters reversed or wrong glyphs, a known PDF issue).
For Arabic wording, prefer transcription_text; use structural_evidence mainly for numbers and table layout.
Write every description in normal Arabic/English reading order.
Never correct, round or recalculate a printed number because it looks unusual: copy it, and use UNCERTAIN
when you doubt it.

WHAT AN ATOMIC FACT IS
One independent piece of financial information. Never combine several amounts in one fact.
A loan statement showing "financed SAR 1M, paid SAR 300K, SAR 700K outstanding" becomes THREE facts:
  financing_amount = 1,000,000 SAR; payment (paid_amount) = 300,000 SAR; remaining_balance (remaining_amount) = 700,000 SAR.
Each row of a statement or ledger table is one fact (fact_type "transaction", with debit/credit/balance as printed).
Ignore institutional boilerplate: paid-up capital, CR/VAT numbers, P.O. boxes, phone numbers, barcodes, page footers.

FIELDS (fill ONLY what the record supports; use null for everything else)
fact_type: one of transaction, payment, installment, deposit, withdrawal, transfer, financing_amount,
  outstanding_balance, remaining_balance, amount_due, opening_balance, closing_balance, balance, fee,
  interest, penalty, credit_limit, claimed_amount, other
date, description, amount, currency, debit, credit, balance, amount_due, paid_amount, remaining_amount,
account_number, transaction_reference, counterparty
source_type: the kind of record the fact comes from (bank_statement, account_statement, transaction_record,
  ledger, loan_statement, repayment_schedule, invoice, receipt, transfer_confirmation, balance_sheet, ...)
- Copy numbers exactly as printed (keep separators); do not convert or round.
- currency: only if printed on the row or stated for the account/statement on this page. Never assume SAR.
- Do NOT fill a field just because the column exists. A value not on the page is null, and that is fine.

STATUS (exactly one per fact)
- EXTRACTED: the record states the value explicitly.
- CALCULATED: you derived it arithmetically from other facts on this page. Give "calculation":
  {"operation": "add|subtract|multiply|divide", "inputs": ["<fact_key>", ...], "result_field": "<field>"}.
  Inputs are the fact_keys of facts in your output. The system recomputes it.
- INFERRED: the value is printed in the record but its meaning (fact_type, direction) comes from context, and you are confident.
- UNCERTAIN: something is in the record but you cannot confidently tell its value or meaning.
  Give your best interpretation in the fields AND a "review" block.
- MISSING: information the record clearly should contain but does not (e.g. a payment with no date).
  Put what is missing in "description"; leave values null.

NEVER GUESS. If you are not confident, use UNCERTAIN rather than EXTRACTED or INFERRED.

REVIEW BLOCK (only for UNCERTAIN)
"review": {"question": "what the reviewer must decide", "suggestion": "your best interpretation in words",
           "reason": "why you are unsure", "alternatives": ["other plausible meanings"]}

For every fact, copy the exact text it came from into "source_text". For a fact read from a table, also copy
its table row exactly as in transcription_text into "supporting_table" (the header row, the separator row and
the fact's row, as markdown); otherwise null.

RETURN JSON ONLY:
{
  "sections": [
    {"section": 1, "label": "context", "source_type": null, "starts_with": "From: ... Subject: ..."},
    {"section": 2, "label": "claim", "source_type": null, "starts_with": "Please continue freezing ..."},
    {"section": 3, "label": "accounting_evidence", "source_type": "transaction_record", "starts_with": "Date: 29/08/2025 ..."}
  ],
  "facts": [
    {
      "fact_key": "F1",
      "section": 3,
      "source_type": "transaction_record",
      "fact_type": "deposit",
      "date": "29/08/2025", "description": "Credit",
      "amount": "250", "currency": "SAR",
      "debit": null, "credit": "250", "balance": "250",
      "amount_due": null, "paid_amount": null, "remaining_amount": null,
      "account_number": null, "transaction_reference": "TX82921", "counterparty": null,
      "status": "EXTRACTED",
      "source_text": "...",
      "supporting_table": null,
      "calculation": null,
      "review": null
    }
  ],
  "financial_claims": [
    {"statement": "Please continue freezing the amount of SAR 250.", "made_by": "Al Rajhi Bank fraud team (email)",
     "amounts": ["SAR 250"], "requires_accounting_verification": true}
  ]
}
""".strip()


EVIDENCE_LABEL = "accounting_evidence"


def split_page_output(output: dict, page_type: str = "financial") -> tuple[dict, list[dict], list[str]]:
    """Keep only the facts found in accounting evidence (the model's own
    section labels); on a mixed page a fact must name an accounting-evidence
    section. Returns (output with the kept facts, financial claims, notes on
    what was dropped)."""
    output = dict(output or {})
    sections = {}
    for item in output.get("sections") or []:
        if isinstance(item, dict):
            sections[str(item.get("section", ""))] = item
    kept, dropped = [], []
    for fact in output.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        section = sections.get(str(fact.get("section", "")))
        label = str((section or {}).get("label") or "").strip().lower()
        if section is not None and label != EVIDENCE_LABEL:
            dropped.append(f"{fact.get('fact_key', '?')}: from a {label or 'non-evidence'} section")
            continue
        if section is None and page_type == "mixed":
            dropped.append(f"{fact.get('fact_key', '?')}: not tied to an accounting record section on a mixed page")
            continue
        if not fact.get("source_type") and section is not None:
            fact = dict(fact, source_type=section.get("source_type"))
        kept.append(fact)
    claims = []
    for claim in output.get("financial_claims") or []:
        if isinstance(claim, dict) and str(claim.get("statement") or "").strip():
            claims.append({
                "type": "financial_claim",
                "statement": str(claim["statement"]).strip(),
                "made_by": str(claim.get("made_by") or "").strip(),
                "amounts": [str(a) for a in claim.get("amounts") or [] if str(a).strip()],
                "requires_accounting_verification": True,
            })
    output["facts"] = kept
    return output, claims, dropped


def extract_page_facts(
    structural_evidence: dict,
    transcription_text: str,
    page_number: int,
    page_route: str = "",
    page_type: str = "financial",
) -> dict:
    """One LLM call: a page -> its sections, the atomic financial facts of
    its accounting evidence, and the financial claims it makes."""
    payload = {
        "page_number": page_number,
        "page_route": page_route,
        "page_classification": page_type,
        "structural_evidence": structural_evidence,
        "transcription_text": transcription_text,
    }
    last_error: Optional[Exception] = None
    for attempt in range(1, int(FINANCIAL_REQUEST_MAX_ATTEMPTS) + 1):
        try:
            return complete_json(
                system_prompt=ATOMIC_FACTS_SYSTEM_PROMPT,
                user_payload=payload,
                llm_id=FINANCIAL_EXTRACTION_LLM_ID,
                temperature=0.0,
            )
        except Exception as error:
            last_error = error
            if attempt < int(FINANCIAL_REQUEST_MAX_ATTEMPTS):
                time.sleep(float(FINANCIAL_RETRY_DELAY_SECONDS))
    raise RuntimeError(f"Atomic fact extraction failed: {last_error!r}")


REINTERPRET_SYSTEM_PROMPT = r"""
A reviewer has explained how an uncertain financial fact should be read. Rewrite that ONE fact
according to the explanation, using the page evidence.

Rules:
- Follow the reviewer's explanation; it overrides your earlier interpretation.
- Change only what the explanation implies. Keep values the explanation does not touch.
- Copy numbers as printed on the page. Use null for anything the page does not show.
- Do not invent dates, references or amounts that are neither on the page nor in the explanation.
- fact_type must be one of: transaction, payment, installment, deposit, withdrawal, transfer,
  financing_amount, outstanding_balance, remaining_balance, amount_due, opening_balance, closing_balance,
  balance, fee, interest, penalty, credit_limit, claimed_amount, other.

RETURN JSON ONLY:
{
  "fields": {"fact_type": "...", "date": null, "description": "...", "amount": null, "currency": null,
             "debit": null, "credit": null, "balance": null, "amount_due": null, "paid_amount": null,
             "remaining_amount": null, "account_number": null, "transaction_reference": null,
             "counterparty": null},
  "summary": "one sentence describing the fact as now understood"
}
""".strip()


def reinterpret_fact(fact: dict, review: dict, source_text: str, page_text: str, explanation: str) -> dict:
    """Rewrite an uncertain fact from the reviewer's explanation. The result
    is only a proposal: the user confirms it before it is used."""
    payload = {
        "current_fact": fact,
        "why_it_was_uncertain": review,
        "source_text": source_text,
        "page_text": (page_text or "")[:6000],
        "reviewer_explanation": explanation,
    }
    result = complete_json(
        system_prompt=REINTERPRET_SYSTEM_PROMPT,
        user_payload=payload,
        llm_id=FINANCIAL_EXTRACTION_LLM_ID,
        temperature=0.0,
    )
    if not isinstance(result, dict) or not isinstance(result.get("fields"), dict):
        raise RuntimeError("The model did not return a rewritten fact.")
    return result


def persist_reconciled_rows(case_id: str, rows: list[dict]) -> int:
    for row in rows:
        row["case_id"] = case_id
    return append_rows(FINANCIAL_LINE_ITEMS_DATASET, rows)