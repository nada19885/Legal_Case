
import json
from decimal import Decimal

from legal_platform.financial_deterministic_extraction import (
    LineItemCandidate,
    extract_candidates_from_text,
    normalize_amount_for_matching,
    normalize_date_for_matching,
)
from legal_platform.financial_reconciliation import reconcile_page

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        failures.append(label)


# --- amount normalization: matching-only, must not care about formatting --
check("amount 1,234.56 -> 1234.56", normalize_amount_for_matching("1,234.56") == Decimal("1234.56"))
check("amount 1.234,56 (EU style) -> 1234.56", normalize_amount_for_matching("1.234,56") == Decimal("1234.56"))
check("amount (500.00) -> -500.00 (parens = negative)", normalize_amount_for_matching("(500.00)") == Decimal("-500.00"))
check("amount with SAR suffix -> 12450.00", normalize_amount_for_matching("12,450.00 SAR") == Decimal("12450.00"))
check(
    "amount with Arabic-Indic digits -> 12450.00",
    normalize_amount_for_matching("١٢٬٤٥٠٫٠٠") == Decimal("12450.00"),
)
check("garbage amount -> None", normalize_amount_for_matching("n/a") is None)

# --- date normalization: only resolve when genuinely unambiguous ----------
check("date 25/03/2024 -> 2024-03-25 (25>12 disambiguates)", normalize_date_for_matching("25/03/2024") == "2024-03-25")
check("date 03/25/2024 -> 2024-03-25 (25>12 on other side)", normalize_date_for_matching("03/25/2024") == "2024-03-25")
check("date 03/04/2024 -> None (ambiguous DD/MM vs MM/DD)", normalize_date_for_matching("03/04/2024") is None)
check("date 03/04/24 -> None (2-digit year ambiguous)", normalize_date_for_matching("03/04/24") is None)

# --- deterministic line extraction from raw OCR text -----------------------
sample_text = (
    "Statement of account\n"
    "25/03/2024  Transfer to ABC Trading   12,450.00 SAR   debit\n"
    "26/03/2024  Deposit from customer      5,000.00 SAR   credit  ref: TRX-99871\n"
    "unrelated line with no financial data\n"
)
candidates = extract_candidates_from_text("PAGE1", "DOC1", 1, sample_text)
check("2 candidate rows found from sample text", len(candidates) == 2)
check("row 1 amount captured", "12,450.00" in candidates[0].amount_exact_text)
check("row 1 debit detected", candidates[0].debit_or_credit == "debit")
check("row 2 credit detected", candidates[1].debit_or_credit == "credit")
check("row 2 reference captured", candidates[1].reference_number == "TRX-99871")

# --- full reconciliation: all 4 sources agree -> verified -------------------
deterministic = [
    LineItemCandidate(
        page_id="P1", case_document_id="D1", page_number=1, line_index=0,
        raw_line="", extraction_method="deterministic_regex",
        date_exact_text="25/03/2024", amount_exact_text="12,450.00",
        currency_exact_text="SAR", debit_or_credit="debit",
        description="Transfer to ABC Trading",
    )
]
llm_primary = {"line_items": [{
    "date_exact_text": "25/03/2024", "amount_exact_text": "12,450.00",
    "currency_exact_text": "SAR", "debit_or_credit": "debit",
    "description": "Transfer to ABC Trading", "party_source": "ABC Trading",
}]}
llm_secondary = {"line_items": [{
    "date_exact_text": "25/03/2024", "amount_exact_text": "12,450.00",
    "currency_exact_text": "SAR", "debit_or_credit": "debit",
    "description": "Transfer to ABC Trading", "party_source": "ABC Trading",
}]}
rows = reconcile_page("P1", "D1", 1, deterministic, [], llm_primary, llm_secondary)
check("1 reconciled row produced (agreement case)", len(rows) == 1)
check("agreement case -> row_status = verified", rows[0]["row_status"] == "verified")
fields = json.loads(rows[0]["fields_json"])
check("amount field status = verified", fields["amount"]["status"] == "verified")

# --- full reconciliation: LLM passes disagree on amount -> needs_review ----
llm_primary_conflict = {"line_items": [{
    "date_exact_text": "25/03/2024", "amount_exact_text": "12,450.00",
    "debit_or_credit": "debit", "description": "Transfer to ABC Trading",
}]}
llm_secondary_conflict = {"line_items": [{
    "date_exact_text": "25/03/2024", "amount_exact_text": "12,459.00",  # digit swap
    "debit_or_credit": "debit", "description": "Transfer to ABC Trading",
}]}
rows_conflict = reconcile_page("P1", "D1", 1, [], [], llm_primary_conflict, llm_secondary_conflict)
check(
    "amount digit-swap between primary/secondary -> merged into ONE flagged row (not 2 silent orphans)",
    len(rows_conflict) == 1,
)
check("amount digit-swap -> row_status = needs_review", rows_conflict[0]["row_status"] == "needs_review")
fields_amount_conflict = json.loads(rows_conflict[0]["fields_json"])
check("amount digit-swap -> amount field itself flagged conflict", fields_amount_conflict["amount"]["status"] == "conflict")
check(
    "amount digit-swap -> both disputed values preserved as candidates",
    {c["value"] for c in fields_amount_conflict["amount"]["candidates"]} == {"12,450.00", "12,459.00"},
)

# --- 3+ same-day singleton candidates -> left separate, NOT auto-merged ----
llm_primary_triple = {"line_items": [{"date_exact_text": "01/02/2024", "amount_exact_text": "100.00"}]}
det_triple = [LineItemCandidate(
    page_id="P1", case_document_id="D1", page_number=1, line_index=0, raw_line="",
    extraction_method="deterministic_regex", date_exact_text="01/02/2024", amount_exact_text="200.00",
)]
native_triple = [LineItemCandidate(
    page_id="P1", case_document_id="D1", page_number=1, line_index=0, raw_line="",
    extraction_method="native_table", date_exact_text="01/02/2024", amount_exact_text="300.00",
)]
rows_triple = reconcile_page("P1", "D1", 1, det_triple, native_triple, llm_primary_triple, {"line_items": []})
check(
    "3 distinct same-day singleton candidates -> left as 3 separate rows (ambiguous, not auto-merged)",
    len(rows_triple) == 3,
)
check(
    "3 distinct same-day singletons -> all stay single_source_low_confidence, none silently marked verified",
    {r["row_status"] for r in rows_triple} == {"single_source_low_confidence"},
)

# Same amount, disagreeing debit/credit -> should land in ONE cluster with a field conflict
llm_primary_dc = {"line_items": [{
    "date_exact_text": "25/03/2024", "amount_exact_text": "12,450.00", "debit_or_credit": "debit",
}]}
llm_secondary_dc = {"line_items": [{
    "date_exact_text": "25/03/2024", "amount_exact_text": "12,450.00", "debit_or_credit": "credit",
}]}
det_dc = [LineItemCandidate(
    page_id="P1", case_document_id="D1", page_number=1, line_index=0, raw_line="",
    extraction_method="deterministic_regex", date_exact_text="25/03/2024",
    amount_exact_text="12,450.00", debit_or_credit="debit",
)]
rows_dc = reconcile_page("P1", "D1", 1, det_dc, [], llm_primary_dc, llm_secondary_dc)
check("debit/credit disagreement -> 1 cluster (matched on amount+date)", len(rows_dc) == 1)
check("debit/credit disagreement -> row flagged needs_review", rows_dc[0]["row_status"] == "needs_review")
fields_dc = json.loads(rows_dc[0]["fields_json"])
check("amount field itself still verified (2 of 3 sources agree)", fields_dc["amount"]["status"] == "verified")
check("debit_or_credit field flagged conflict", fields_dc["debit_or_credit"]["status"] == "conflict")
check("conflict candidates preserved for human review", len(fields_dc["debit_or_credit"]["candidates"]) >= 2)

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")