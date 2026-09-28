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
from legal_platform.financial_forensics import normalise_claim_evaluation
from legal_platform import financial_facts as facts
from legal_platform.arabic_text import fix_structure, fix_visual_arabic, is_visual_order
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

# --- claims vs evidence: model output is checked before it is stored -----
evaluated = normalise_claim_evaluation({
    "claim": "The customer never received 12,450 SAR",
    "result": "partially supported",
    "evidence_record_ids": ["R1", "INVENTED"],
    "financial_evidence_found": [{"record_id": "R2"}],
    "missing_evidence": ["Receipt for the transfer", "", "none"],
    "contradictions": [
        {"description": "Statement shows the credit on 25 March", "record_ids": ["R1", "FAKE"]},
        "Balance does not match",
        {"description": ""},
    ],
}, known_ids={"R1", "R2"})
check("claim gets an id", evaluated["claim_id"] == "CLM_001")
check("result wording normalised", evaluated["result"] == "PARTIALLY_SUPPORTED")
check("only ledger records kept as evidence (incl. evidence_found ids)", evaluated["evidence_record_ids"] == ["R1", "R2"])
check("invented ids set apart", evaluated["unverified_record_ids"] == ["INVENTED", "FAKE"])
check("missing evidence cleaned to a list of text", evaluated["missing_evidence"] == ["Receipt for the transfer"])
check("contradictions structured, empty ones dropped",
      evaluated["contradictions"] == [
          {"description": "Statement shows the credit on 25 March", "record_ids": ["R1"]},
          {"description": "Balance does not match", "record_ids": []},
      ])
odd = normalise_claim_evaluation({"claim": "x", "result": "probably true"}, known_ids=set(), index=4)
check("unknown result is not reinterpreted", odd["result"] == "NOT_VERIFIABLE" and odd["result_raw"] == "probably true"
      and odd["claim_id"] == "CLM_005")

# --- atomic financial facts -------------------------------------------------
for text, expected in [("1,000,000", "1000000"), ("300,000", "300000"), ("12,450.00 SAR", "12450.00"),
                       ("1.234,56", "1234.56"), ("(500.00)", "-500.00"), ("١٢٬٤٥٠٫٠٠", "12450.00"),
                       ("1 000 000", "1000000"), ("SAR 540,000", "540000")]:
    check(f"amount '{text}' read exactly", facts.parse_amount(text) == Decimal(expected))
check("ambiguous '1.000' is not guessed", facts.parse_amount("1.000") is None)
check("non-number is not read", facts.parse_amount("about a million") is None)

page_output = {"facts": [
    {"fact_key": "F1", "fact_type": "financing_amount", "amount": "1,000,000", "currency": "ريال", "status": "EXTRACTED"},
    {"fact_key": "F2", "fact_type": "payment", "paid_amount": "300,000", "currency": "SAR", "status": "EXTRACTED"},
    {"fact_key": "F3", "fact_type": "remaining_balance", "remaining_amount": "700,000", "status": "CALCULATED",
     "calculation": {"operation": "subtract", "inputs": ["F1", "F2"], "result_field": "remaining_amount"}},
    {"fact_key": "F4", "fact_type": "remaining_balance", "remaining_amount": "650,000", "status": "CALCULATED",
     "calculation": {"operation": "subtract", "inputs": ["F1", "F2"]}},
    {"fact_key": "F5", "fact_type": "outstanding_balance", "amount": "250,000", "status": "UNCERTAIN",
     "review": {"question": "Balance or installment?", "suggestion": "Outstanding balance", "reason": "Header unreadable",
                "alternatives": ["installment", "debit"]}},
    {"fact_key": "F6", "fact_type": "payment", "description": "Payment date not stated", "status": "MISSING"},
    {"fact_key": "F7", "amount": "5,000", "status": "EXTRACTED"},
    {"fact_key": "F8", "fact_type": "fee", "amount": "one hundred", "status": "EXTRACTED"},
    {"fact_key": "F9", "fact_type": "fee", "amount": "50", "status": "PROBABLY"},
    {"fact_key": "F10", "status": "EXTRACTED"},
]}
fact_rows = facts.build_fact_rows("P1", "D1", 3, page_output)
by_key = {json.loads(r["fields_json"])["fact_key"]: r for r in fact_rows}
check("fact with no values dropped", "F10" not in by_key)
check("explicit value -> EXTRACTED; currency read, not assumed", by_key["F1"]["row_status"] == "EXTRACTED"
      and json.loads(by_key["F1"]["fields_json"])["fact"]["currency"] == "SAR")
check("fields the page does not support stay null", json.loads(by_key["F2"]["fields_json"])["fact"]["date"] is None)
check("correct calculation -> CALCULATED (recomputed)", by_key["F3"]["row_status"] == "CALCULATED"
      and json.loads(by_key["F3"]["fields_json"])["calculation"]["check"]["ok"])
f4 = json.loads(by_key["F4"]["fields_json"])
check("wrong calculation -> UNCERTAIN with the recomputed value",
      by_key["F4"]["row_status"] == "UNCERTAIN" and "700,000.00" in f4["review"]["reason"])
check("ambiguous value -> UNCERTAIN with its review block",
      by_key["F5"]["row_status"] == "UNCERTAIN" and json.loads(by_key["F5"]["fields_json"])["review"]["alternatives"] == ["installment", "debit"])
check("missing information -> MISSING, not a question", by_key["F6"]["row_status"] == "MISSING" and not by_key["F6"]["has_conflict"])
check("value with no meaning (fact type) -> UNCERTAIN", by_key["F7"]["row_status"] == "UNCERTAIN")
check("unreadable number -> UNCERTAIN", by_key["F8"]["row_status"] == "UNCERTAIN")
check("unknown status -> UNCERTAIN", by_key["F9"]["row_status"] == "UNCERTAIN")

fact_ledger, fact_withheld = facts.build_fact_ledger(fact_rows)
check("ledger: extracted, calculated and missing facts; uncertain withheld",
      sorted(e["status"] for e in fact_ledger) == ["CALCULATED", "EXTRACTED", "EXTRACTED", "MISSING"] and fact_withheld == 5)
check("ledger value uses the fact's own field", next(e for e in fact_ledger if e["fact_type"] == "payment" and e["value"])["value"] == "300,000.00")

def decision(row, action, **payload):
    return {"row_id": row["row_id"], "field_name": facts.RESOLUTION_FIELD,
            "corrected_value": json.dumps({"action": action, **payload}), "corrected_by": "attorney"}

resolutions = facts.latest_resolutions([
    decision(by_key["F4"], "confirm"),
    decision(by_key["F5"], "proposal", fields={"fact_type": "installment"}, explanation="third installment"),
    decision(by_key["F7"], "ignore"),
    decision(by_key["F8"], "correct", fields={"amount": "100.00"}, explanation="one hundred riyals"),
])
fact_ledger, fact_withheld = facts.build_fact_ledger(fact_rows, {}, resolutions)
statuses = {e["row_id"]: e["status"] for e in fact_ledger}
check("confirm -> USER_CONFIRMED", statuses.get(by_key["F4"]["row_id"]) == "USER_CONFIRMED")
check("ignore -> left out of the ledger", by_key["F7"]["row_id"] not in statuses)
corrected = next(e for e in fact_ledger if e["row_id"] == by_key["F8"]["row_id"])
check("correct -> USER_CORRECTED with the new value and the note",
      corrected["status"] == "USER_CORRECTED" and corrected["amount"] == "100.00" and corrected["user_note"] == "one hundred riyals")
check("a proposal alone keeps the fact waiting", by_key["F5"]["row_id"] not in statuses and fact_withheld == 2)
review = facts.build_fact_review_items(fact_rows, {}, resolutions, {"P1": {"label": "loan.pdf — page 3", "page_text": "..."}})
check("review queue lists remaining uncertain facts with the proposal",
      sorted(i["fact"]["fact_type"] or "" for i in review) == ["fee", "outstanding_balance"]
      and next(i for i in review if i["fact"]["fact_type"] == "outstanding_balance")["proposal"]["explanation"] == "third installment")
check("a later confirm replaces the proposal", facts.latest_resolutions([
    decision(by_key["F5"], "proposal", fields={}), decision(by_key["F5"], "confirm")])[by_key["F5"]["row_id"]].get("proposal") is None)

clean, errors = facts.validate_fact_fields({"amount": "12,500", "fact_type": "Third Installment", "currency": "riyal", "bogus": 1})
check("user fields validated", clean == {"amount": "12,500.00", "fact_type": "third_installment", "currency": "SAR"} and not errors)
check("other countries' riyals kept as written", facts.validate_fact_fields({"currency": "Qatari riyal"})[0]["currency"] == "QATARI RIYAL")
check("user amount must be a number", facts.validate_fact_fields({"amount": "abc"})[1])

legacy_rows = build_rows_from_reconstruction("P1", "D1", 1, reconstruction)
legacy_ledger, legacy_withheld = facts.build_fact_ledger(legacy_rows)
check("old transaction rows read as transaction facts",
      len(legacy_ledger) == 1 and legacy_ledger[0]["fact_type"] == "transaction"
      and legacy_ledger[0]["debit"] == "12,450.00" and legacy_withheld == 2)

grouped = normalise_claim_evaluation({
    "parent_claim": "Customer paid SAR 500,000 and owes nothing", "claim": "Customer paid SAR 500,000",
    "claimed_amount": "500000", "substantiated_amount": "350,000", "result": "partially_supported",
    "partially_supporting_evidence": [{"record_ids": ["R1"], "explanation": "Only 350,000 on page 11"}],
    "contradicting_evidence": [{"record_ids": ["R2", "FAKE"], "explanation": "Balance still due"}],
    "unresolved_evidence": [{"record_ids": ["R3"], "explanation": "Inferred meaning"}],
    "accounting_position": "Records substantiate SAR 350,000 of SAR 500,000.",
}, known_ids={"R1", "R2", "R3"})
check("atomic claim keeps its parent claim", grouped["parent_claim"].startswith("Customer paid SAR 500,000 and"))
check("claimed / substantiated amounts normalised", grouped["claimed_amount"] == "500,000.00" and grouped["substantiated_amount"] == "350,000.00")
check("evidence groups kept with ledger ids only",
      grouped["partially_supporting_evidence"][0]["record_ids"] == ["R1"]
      and grouped["contradicting_evidence"][0]["record_ids"] == ["R2"]
      and grouped["unresolved_evidence"][0]["record_ids"] == ["R3"] and grouped["unverified_record_ids"] == ["FAKE"])
check("evidence resting only on invented records is dropped", normalise_claim_evaluation(
    {"supporting_evidence": [{"record_ids": ["FAKE"], "explanation": "made up"}]}, known_ids={"R1"})["supporting_evidence"] == [])
check("flat views kept for the pleading", grouped["evidence_record_ids"] == ["R1"]
      and grouped["contradictions"] == [{"description": "Balance still due", "record_ids": ["R2"]}])

# --- Arabic stored in visual (drawing) order --------------------------------
visual_line = ("Pay) /6.00 لىأ قيبطت( عملا طاقم ربع عفد ىدم ةقاطب يسيئرلا يدوعسلا كنبلا / TEA TIME RESTAURANT "
               "\\Apple / 611**# مقرلا - Pay App /SA /POS#63122666 /SNB")
fixed_line = fix_visual_arabic(visual_line)
check("reversed Arabic detected", is_visual_order(visual_line))
check("Arabic words restored to reading order", "البنك السعودي الرئيسي بطاقة مدى دفع عبر" in fixed_line)
check("English runs keep their own order", "TEA TIME RESTAURANT" in fixed_line and "Pay App /SA /POS#63122666 /SNB" in fixed_line)
check("brackets and masked numbers kept as printed", "(تطبيق" in fixed_line and fixed_line.endswith("Pay)") and "611**#" in fixed_line)
check("fees line restored", fix_visual_arabic("ةفاضملا ةميقلا ةبيرض :موسرلا ليصافت - موسر")
      == "رسوم - تفاصيل الرسوم: ضريبة القيمة المضافة")
check("common banking words detected", fix_visual_arabic("12,450.00 لاير ليوحت") == "تحويل ريال 12,450.00")
for untouched in ["رسوم - تفاصيل الرسوم: ضريبة القيمة المضافة", "تحويل 12,450.00 ريال", "TEA TIME RESTAURANT",
                  "البنك السعودي الرئيسي بطاقة مدى"]:
    check(f"text already in reading order left alone: {untouched[:20]}", fix_visual_arabic(untouched) == untouched)
check("fix is idempotent", fix_visual_arabic(fixed_line) == fixed_line)
check("nested structures fixed", fix_structure({"rows": [["موسر", 5]]}) == {"rows": [["رسوم", 5]]})

stored_reversed = facts.build_fact_rows("P9", "D9", 1, {"facts": [
    {"fact_key": "F1", "fact_type": "fee", "amount": "6.00", "status": "EXTRACTED",
     "description": "ةفاضملا ةميقلا ةبيرض :موسرلا ليصافت - موسر"}]})
check("fact descriptions stored in reading order",
      json.loads(stored_reversed[0]["fields_json"])["fact"]["description"].startswith("رسوم - تفاصيل"))
old_row = dict(stored_reversed[0])
old_fields = json.loads(old_row["fields_json"])
old_fields["fact"]["description"] = "ةفاضملا ةميقلا ةبيرض :موسرلا ليصافت - موسر"
old_row["fields_json"] = json.dumps(old_fields, ensure_ascii=False)
check("facts stored earlier are fixed when read", facts.build_fact_ledger([old_row])[0][0]["description"].startswith("رسوم - تفاصيل"))

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")