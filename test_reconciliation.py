"""
Checks for the financial extraction, review and workflow-status logic.

Run from the repository root:  python test_reconciliation.py
Inside Dataiku the real `dataiku` package and `legal_platform` library are
used; outside it a minimal stand-in is installed so the pure logic can be
tested without a Dataiku instance (or PyMuPDF).
"""

import importlib.util
import json
import pathlib
import sys
import types
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parent

for optional in ("dataiku", "fitz"):
    try:
        __import__(optional)
    except ImportError:
        sys.modules[optional] = types.ModuleType(optional)

try:
    import legal_platform  # noqa: F401
except ImportError:
    spec = importlib.util.spec_from_file_location(
        "legal_platform", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules["legal_platform"] = package
    spec.loader.exec_module(package)

import pandas as pd

from legal_platform.financial_deterministic_extraction import (
    LineItemCandidate,  # noqa: F401
    extract_candidates_from_text,
    normalize_amount_for_matching,
    normalize_date_for_matching,
)
from legal_platform.financial_corrections import build_review_items
from legal_platform.financial_extraction_pipeline import sanitize_extracted_line_items
from legal_platform.financial_fields import effective_value, pending_fields
from legal_platform.financial_normalizer import build_normalized_ledger, normalize_currency
from legal_platform.financial_reconciliation import build_rows_from_reconstruction
from legal_platform import workflow
from legal_platform.case_register import build_case_register, normalise_text, prioritise_pages_for_summary

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

# --- reconstruction -> rows: certainty decides what needs the user ---------
def field(value, certain=True, reason=""):
    return {"value": value, "certain": certain, "reason": reason}


reconstruction = {"transactions": [
    {   # 0: fully certain
        "row_index": 0,
        "date": field("2024/03/25"), "amount": field("12,450.00"), "currency": field("SAR"),
        "debit_or_credit": field("debit"), "description": field("Transfer to ABC Trading"),
        "reference_number": field("TRX-1"), "party_source": field(""), "running_balance": field(""),
        "row_source_text": "25/03/2024 Transfer to ABC Trading 12,450.00 SAR",
    },
    {   # 1: amount uncertain, currency not on the page
        "row_index": 1,
        "date": field("2024/03/26"), "amount": field("17,500.00", False, "OCR reads 17,500, table reads 12,500"),
        "currency": field("", False, "No currency printed"), "debit_or_credit": field("credit"),
        "description": field("Deposit"), "reference_number": field(""), "party_source": field(""),
        "running_balance": field(""), "row_source_text": "26/03/2024 Deposit 17,500.00",
    },
    {   # 2: direction marked certain but not debit/credit
        "row_index": 2,
        "date": field("2024/03/27"), "amount": field("100.00"), "currency": field("SAR"),
        "debit_or_credit": field("unclear"), "description": field("Fee"),
    },
    {   # 3: empty noise row
        "row_index": 3,
    },
]}
rows = build_rows_from_reconstruction("P1", "D1", 1, reconstruction)
check("empty reconstruction rows are dropped", len(rows) == 3)
check("certain row -> verified", rows[0]["row_status"] == "verified")
check("uncertain amount -> needs_review", rows[1]["row_status"] == "needs_review")
f1 = json.loads(rows[1]["fields_json"])
check("uncertain amount -> conflict with AI suggestion as candidate",
      f1["amount"]["status"] == "conflict" and f1["amount"]["candidates"][0]["value"] == "17,500.00")
check("missing currency -> missing_required (never defaulted)", f1["currency"]["status"] == "missing_required")
check("row source text kept as evidence", f1["_row"]["source_text"].startswith("26/03/2024"))
check("'unclear' direction -> needs_review", rows[2]["row_status"] == "needs_review")
check("row ids are stable", rows[0]["row_id"] == build_rows_from_reconstruction("P1", "D1", 1, reconstruction)[0]["row_id"])

# --- sanitising keeps rows that need a human -------------------------------
zero_row = build_rows_from_reconstruction("P1", "D1", 1, {"transactions": [{
    "row_index": 9, "date": field("2024/03/28"), "amount": field("0.00"), "currency": field("SAR"),
    "debit_or_credit": field("debit"), "description": field("Opening balance"),
}]})
missing_amount = build_rows_from_reconstruction("P1", "D1", 1, {"transactions": [{
    "row_index": 10, "date": field("2024/03/29"), "amount": field("", False),
    "currency": field("SAR"), "debit_or_credit": field("debit"), "description": field("Transfer"),
}]})
kept, discarded = sanitize_extracted_line_items(zero_row + missing_amount + rows)
check("verified zero-amount row discarded as noise", discarded == 1)
check("row with missing amount kept for review", any(r["row_id"] == missing_amount[0]["row_id"] for r in kept))

# --- pending fields, corrections and the ledger -----------------------------
check("row 1 pending fields = amount + currency", pending_fields(rows[1], {}) == ["amount", "currency"])
check("pending field has no usable value", effective_value(rows[1], "amount", {})["value"] is None)

ledger, withheld = build_normalized_ledger(rows, {})
check("only the fully certain row enters the ledger", len(ledger) == 1 and withheld == 2)
check("ledger entry keeps its row_id for traceability", ledger[0]["row_id"] == rows[0]["row_id"])
check("ledger entry normalises amount", ledger[0]["amount"] == "12,450.00")

corrections = {
    rows[1]["row_id"]: {
        "amount": {"corrected_value": "12,500.00"},
        "currency": {"corrected_value": "SAR"},
    },
}
check("row 1 resolved once both fields are answered", pending_fields(rows[1], corrections) == [])
ledger, withheld = build_normalized_ledger(rows, corrections)
row1 = next(e for e in ledger if e["row_id"] == rows[1]["row_id"])
check("human correction used in the ledger, not the AI suggestion", row1["amount"] == "12,500.00")
check("ledger marks corrected fields", row1["corrected_fields"] == ["amount", "currency"]
      and row1["row_status"] == "verified_with_corrections")
check("row 2 still withheld", withheld == 1)

check("unknown currency is kept as written, not replaced by SAR", normalize_currency("AED") == "AED")
check("empty currency is not defaulted to SAR", normalize_currency("") == "")

# Legacy rows (extracted before required-field checks) with a missing amount
legacy = {"row_id": "L1", "page_id": "P1", "fields_json": json.dumps({
    "date": {"value": "2024-01-01", "status": "verified"},
    "amount": {"value": "", "status": "missing"},
    "currency": {"value": "SAR", "status": "verified"},
    "debit_or_credit": {"value": "debit", "status": "verified"},
})}
check("legacy row missing a required field is pending", pending_fields(legacy, {}) == ["amount"])

# --- other extraction schemas (transaction_date, debit/credit columns) -----
alt_row = {"row_id": "ALT1", "page_id": "P1", "fields_json": json.dumps({
    "transaction_date": {"value": "2024-04-02", "certain": True},
    "transaction_description": {"value": "POS purchase", "certain": True},
    "debit_amount": {"value": "250.00", "certain": True},
    "credit_amount": {"value": "0.00", "certain": True},
    "currency": {"value": "SAR", "certain": True},
})}
check("alias fields satisfy the required fields", pending_fields(alt_row, {}) == [])
alt_ledger, alt_withheld = build_normalized_ledger([alt_row], {})
check("debit column gives amount and direction in the ledger",
      alt_withheld == 0 and alt_ledger[0]["amount"] == "250.00" and alt_ledger[0]["debit_or_credit"] == "debit"
      and alt_ledger[0]["date"] == "2024-04-02" and alt_ledger[0]["description"] == "POS purchase")
both_columns = {"row_id": "ALT2", "page_id": "P1", "fields_json": json.dumps({
    "transaction_date": {"value": "2024-04-03", "certain": True},
    "debit_amount": {"value": "10.00", "certain": True},
    "credit_amount": {"value": "20.00", "certain": True},
    "currency": {"value": "SAR", "certain": True},
})}
check("values in both debit and credit columns go to the user",
      set(pending_fields(both_columns, {})) == {"amount", "debit_or_credit"})
uncertain_flag = {"row_id": "ALT3", "page_id": "P1", "fields_json": json.dumps({
    "date": {"value": "2024-04-04"}, "amount": {"value": "99.00", "certain": False, "reason": "smudged"},
    "currency": {"value": "SAR"}, "debit_or_credit": {"value": "credit"},
})}
check("certain: false is treated as uncertain", pending_fields(uncertain_flag, {}) == ["amount"])

# --- review items carry the evidence the user needs -------------------------
pages = {"P1": {"label": "statement.pdf — page 1",
                "page_text": "Header\n25/03/2024 Transfer to ABC Trading 12,450.00 SAR\n26/03/2024 Deposit 17,500.00\nFooter"}}
items = build_review_items(rows, corrections={}, pages_by_id=pages)
check("one review item per row with open fields", len(items) == 2)
item = next(i for i in items if i["row_id"] == rows[1]["row_id"])
amount_item = next(f for f in item["fields"] if f["field"] == "amount")
check("review item has the LLM suggestion and reasoning",
      amount_item["suggested_value"] == "17,500.00" and "17,500" in amount_item["reason"])
check("missing field is labelled missing", next(f for f in item["fields"] if f["field"] == "currency")["issue"] == "missing")
check("review item has the page excerpt around the row", "26/03/2024 Deposit" in item["page_excerpt"])
check("review item has the source page label", item["page_label"] == "statement.pdf — page 1")
partial = {rows[1]["row_id"]: {"amount": {"corrected_value": "12,500.00"}}}
item_after = next(i for i in build_review_items(rows, partial, pages) if i["row_id"] == rows[1]["row_id"])
check("answered fields drop out of the review item", [f["field"] for f in item_after["fields"]] == ["currency"])

# --- workflow state: merges never drop other stages' results ----------------
base = workflow.blank_workflow_state()
after_accounting = workflow.merge_state(base, {"accounting_status": "needs_review"},
                                        {"accounting": workflow.stage_patch(workflow.WAITING, detail="review_items")})
after_analysis = workflow.merge_state(after_accounting, {"analysis": {"issues": []}},
                                      {"analysis": workflow.stage_patch(workflow.COMPLETED)})
check("merge keeps earlier keys", after_analysis["accounting_status"] == "needs_review")
check("merge keeps other stage records", after_analysis["stages"]["accounting"]["status"] == workflow.WAITING)
check("completed stage gets finished_at", bool(after_analysis["stages"]["analysis"].get("finished_at")))
running = workflow.merge_state(after_analysis, stages={"analysis": workflow.stage_patch(workflow.RUNNING, job_id="J1")})
check("running keeps the last finished_at", running["stages"]["analysis"]["finished_at"] == after_analysis["stages"]["analysis"]["finished_at"])
check("running records its job id", running["stages"]["analysis"]["job_id"] == "J1")
done = workflow.merge_state(running, stages={"analysis": workflow.stage_patch(workflow.COMPLETED)})
check("job id cleared once the stage stops running", "job_id" not in done["stages"]["analysis"])

audits = pd.DataFrame([
    {"entity_type": "case_workflow", "event_at": "2024-01-01T00:00:00", "new_value_json": json.dumps({"analysis": {"v": 1}})},
    {"entity_type": "case_workflow", "event_at": "2024-01-02T00:00:00", "new_value_json": json.dumps({"analysis": {"v": 2}, "strategy": True})},
])
restored = workflow.restore_workflow_state(audits)
check("restore reads the newest workflow row", restored["analysis"] == {"v": 2})
check("restore repairs the legacy strategy=True value", restored["strategy"] is None)


def overview(**facts):
    base_facts = {"has_documents": True, "has_summary": True, "gate_passed": True, "has_analysis": False,
                  "has_memo": False, "accounting": {"status": "not_started"}, "stages": {}, "active_jobs": {}}
    base_facts.update(facts)
    result = workflow.build_stage_overview(base_facts)
    return result, {s["key"]: s for s in result["stages"]}


result, by_key = overview(accounting={"status": "needs_review", "pending_count": 3})
check("pending review items -> accounting waiting_for_user", by_key["accounting"]["status"] == workflow.WAITING)
check("waiting stage is the next action", result["next_stage"] == "accounting" and result["waiting"] == ["accounting"])
check("pleading blocked until analysis and accounting are done",
      by_key["pleading"]["status"] == workflow.BLOCKED and set(by_key["pleading"]["blocked_by"]) == {"analysis", "accounting"})

result, by_key = overview(active_jobs={"analysis": {"job_id": "J1", "progress": {"phase": "researching_law", "detail": "…"}}})
check("live job -> running with its phase", by_key["analysis"]["status"] == workflow.RUNNING
      and by_key["analysis"]["phase"] == "researching_law")

result, by_key = overview(stages={"analysis": {"status": "running", "job_id": "gone"}})
check("running record without a live job -> error (interrupted)", by_key["analysis"]["status"] == workflow.ERROR)

result, by_key = overview(stages={"accounting": {"status": "error", "error": "LLM timeout"}})
check("stored error is shown with its message", by_key["accounting"]["status"] == workflow.ERROR
      and by_key["accounting"]["error"] == "LLM timeout")

result, by_key = overview(
    has_analysis=True, has_memo=True, accounting={"status": "forensic_complete"},
    stages={"analysis": {"finished_at": "2024-02-01"}, "accounting": {"finished_at": "2024-03-01"},
            "pleading": {"finished_at": "2024-02-15"}},
)
check("pleading older than the accounting analysis -> stale", by_key["pleading"]["status"] == workflow.STALE
      and by_key["pleading"]["stale_because"] == "accounting")

result, by_key = overview(has_memo=True, has_analysis=True, accounting={"status": "not_started"})
check("pleading whose accounting was cleared -> stale", by_key["pleading"]["status"] == workflow.STALE)

# --- case register: one consolidated view across documents ---------------
check("normalisation ignores case, punctuation and Arabic diacritics",
      normalise_text("The Bank froze the account.") == normalise_text("the bank FROZE the account")
      and normalise_text("أُجْرِيَ التحويل") == normalise_text("اجري التحويل"))

register = build_case_register({
    "parties": [
        {"party_name": "Banque Saudi Fransi", "role_in_case": "Respondent", "party_type": "bank"},
        {"party_name": "Ahmed Ali", "role_in_case": "Claimant", "party_type": "individual"},
        {"party_name": "banque saudi fransi", "role_in_case": "Respondent", "party_type": "bank"},  # from doc 2
    ],
    "events": [
        {"event_date": "2024-05-01", "event_description": "Account frozen", "source_id": json.dumps(["P2"])},
        {"event_date": "2024-03-25", "event_description": "Transfer of 12,450 SAR", "source_id": json.dumps(["P1"])},
        {"event_date": "", "event_description": "Complaint filed"},
        {"event_date": "2024-05-01", "event_description": "Account frozen.", "source_id": json.dumps(["P7"])},
    ],
    "facts": [{"fact_id": "F-APPROVED", "fact_text": "The transfer was executed on 25 March 2024."}],
    "fact_candidates": [
        {"fact_candidate_id": "C1", "fact_text": "The transfer was executed on 25 March 2024",
         "candidate_status": "stated", "source_page_ids_json": json.dumps(["P1"])},
        {"fact_candidate_id": "C2", "fact_text": "The customer never authorised the transfer",
         "candidate_status": "alleged", "party": "Ahmed Ali", "source_page_ids_json": json.dumps(["P3"])},
        {"fact_candidate_id": "C3", "fact_text": "The customer never authorised the transfer!",
         "candidate_status": "alleged", "source_page_ids_json": json.dumps(["P9"])},
    ],
    "issue_candidates": [
        {"issue_candidate_id": "I1", "issue_title": "Unauthorised transfer liability", "priority": "high"},
        {"issue_candidate_id": "I2", "issue_title": "Limitation period", "priority": "low"},
    ],
    "evidence": [{"evidence_id": "E1", "evidence_title": "Bank statement", "description": "March statement"}],
    "contradictions": [{"description": "Two different transfer dates", "clarification_required": "Which date?"}],
    "documents": [{"case_document_id": "D1"}, {"case_document_id": "D2"}],
    "pages": [{"page_id": "P1", "page_text": "x"}, {"page_id": "P2", "page_text": ""}],
}, page_labels={"P1": "stmt.pdf — page 1", "P3": "claim.pdf — page 1"})

check("duplicate parties from two documents merged", register["counts"]["parties"] == 2)
check("claimant listed before respondent", register["parties"][0]["name"] == "Ahmed Ali")
check("duplicate events merged and their source pages combined",
      register["counts"]["events"] == 3
      and next(e for e in register["events"] if e["description"].startswith("Account"))["source_page_ids"] == ["P2", "P7"])
check("events ordered chronologically, undated last",
      [e["date"] for e in register["events"]] == ["2024-03-25", "2024-05-01", ""])
fact = next(f for f in register["facts"] if "executed" in f["fact_text"])
check("approved fact takes precedence over the matching candidate",
      fact["fact_id"] == "F-APPROVED" and fact["approved"] and fact["source_page_ids"] == ["P1"])
check("allegations kept separate from stated facts",
      [a["fact_text"] for a in register["allegations"]] == ["The customer never authorised the transfer"])
check("allegation keeps its status for the legal analysis", register["allegations"][0]["status"] == "alleged")
check("merged allegation keeps pages from both documents", register["allegations"][0]["source_page_ids"] == ["P3", "P9"])
check("high-priority issues first", register["issues"][0]["issue_title"] == "Unauthorised transfer liability")
check("page labels attached", register["allegations"][0]["page_labels"][0] == "claim.pdf — page 1")
check("sources counted", register["sources"] == {"documents": 2, "pages": 2, "usable_pages": 1})
same = build_case_register({"parties": [{"party_name": "Ahmed Ali", "role_in_case": "Claimant"}]})
changed = build_case_register({"parties": [{"party_name": "Ahmed Ali", "role_in_case": "Claimant"},
                                           {"party_name": "Witness", "role_in_case": "witness"}]})
check("fingerprint changes when the register changes", same["fingerprint"] != changed["fingerprint"])
check("fingerprint is stable", same["fingerprint"] == build_case_register(
    {"parties": [{"party_name": "Ahmed Ali", "role_in_case": "Claimant"}]})["fingerprint"])

ordered = prioritise_pages_for_summary([
    {"page_id": "A", "page_number": 1, "claims_json": "[]"},
    {"page_id": "B", "page_number": 2, "claims_json": json.dumps(["claim"]), "facts_json": "[]"},
    {"page_id": "C", "page_number": 3, "facts_json": json.dumps(["f1", "f2"])},
])
check("pages with claims come first for the attorney review", [p["page_id"] for p in ordered] == ["B", "C", "A"])

result, by_key = overview(
    has_analysis=True, register_fingerprint="new",
    stages={"analysis": {"status": "completed", "register_fingerprint": "old", "finished_at": "2024-01-01"}},
)
check("analysis built on an older register -> stale", by_key["analysis"]["status"] == workflow.STALE
      and by_key["analysis"]["stale_because"] == "documents")

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")