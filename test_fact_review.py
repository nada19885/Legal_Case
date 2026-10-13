"""
Checks for the editable fact table (financial_facts.py).

Run from the repository root:  python test_fact_review.py
Pure functions only: fact rows with traceability, user edits layered on the
extraction, user-added and deleted facts, and the guard that never applies
an edit to a different fact.
"""

import importlib.util
import json
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent
sys.modules.setdefault("dataiku", types.ModuleType("dataiku"))
if "legal_platform" not in sys.modules:
    spec = importlib.util.spec_from_file_location("legal_platform", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules["legal_platform"] = package
    spec.loader.exec_module(package)

from legal_platform import financial_facts as ff          # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


TABLE = "| Date | Description | Amount | Balance |\n|---|---|---|---|\n| 22/10 | ATM | -300.00 | 250.09 |"
output = {"facts": [
    {"fact_key": "F1", "fact_type": "withdrawal", "date": "22/10/2024", "description": "ATM withdrawal",
     "amount": "-300.00", "balance": "250.09", "currency": "SAR", "status": "EXTRACTED",
     "source_text": "22/10 ATM -300.00 250.09", "supporting_table": TABLE},
    {"fact_key": "F2", "fact_type": "deposit", "date": "18/10/2024", "description": "transfer",
     "amount": "250.00", "status": "UNCERTAIN", "source_text": "18/10 transfer [?: 250.00 | 350.00]",
     "review": {"question": "250 or 350?", "reason": "the readings differ", "alternatives": ["350.00"]}},
]}
rows = ff.build_fact_rows("PAGE1", "DOC1", 26, output, meta={"document_name": "statement.pdf",
                                                            "extraction_source": "vlm"})
stored = json.loads(rows[0]["fields_json"])
check("each fact keeps its document, extraction source and table row",
      stored["document_name"] == "statement.pdf" and stored["extraction_source"] == "vlm"
      and stored["supporting_table"] == TABLE and stored["fingerprint"])


def resolution(row_id, action, fields=None, fingerprint="", at="2026-10-05T10:00:00"):
    payload = {"action": action, "fields": fields or {}, "explanation": ""}
    if fingerprint:
        payload["fingerprint"] = fingerprint
    return {"row_id": row_id, "field_name": ff.RESOLUTION_FIELD, "corrected_value": json.dumps(payload),
            "corrected_by": "nada", "corrected_at": at}


table = ff.build_fact_table(rows)
check("the table holds every fact, uncertain ones included, with the reason",
      len(table) == 2 and table[1]["status"] == ff.UNCERTAIN and table[1]["review"]["question"] == "250 or 350?")
check("rows are traceable to page and document", table[0]["page_number"] == 26
      and table[0]["document_name"] == "statement.pdf" and table[0]["supporting_table"] == TABLE)

fingerprint = stored["fingerprint"]
edits = ff.latest_resolutions([resolution(rows[0]["row_id"], "correct", {"description": "ATM cash withdrawal",
                                                                          "amount": "-300.00"}, fingerprint)])
edited = ff.build_fact_table(rows, None, edits)[0]
check("a user edit changes the shown value and keeps what the AI read",
      edited["description"] == "ATM cash withdrawal" and edited["original_values"] == {"description": "ATM withdrawal"}
      and edited["status"] == ff.USER_CORRECTED and edited["edited_by"] == "nada")
check("a field the user re-typed unchanged is not counted as edited", edited["corrected_fields"] == ["description"])

stale = ff.latest_resolutions([resolution(rows[0]["row_id"], "correct", {"amount": "-999.00"}, "another-reading")])
guarded = ff.build_fact_table(rows, None, stale)[0]
check("an edit made on a different extraction of the fact is never applied silently",
      guarded["amount"] == "-300.00" and guarded["status"] == ff.UNCERTAIN and guarded["stale_review"])

deleted = ff.build_fact_table(rows, None, ff.latest_resolutions([resolution(rows[1]["row_id"], "ignore")]))[1]
check("a deleted fact stays in the table, marked deleted, out of the ledger",
      deleted["deleted"] and ff.build_fact_ledger(rows, None, ff.latest_resolutions(
          [resolution(rows[1]["row_id"], "ignore")]))[0][0]["row_id"] == rows[0]["row_id"])

added = ff.user_fact_row("PAGE1", "DOC1", 26, {"fact_type": "opening_balance", "balance": "0.09",
                                              "description": "opening balance"}, "statement.pdf", "nada")
with_added = ff.build_fact_table(rows + [added])
check("a fact added by the user is in the table and the ledger as the user's value",
      with_added[-1]["added_by_user"] and with_added[-1]["status"] == ff.USER_CORRECTED
      and any(e["row_id"] == added["row_id"] for e in ff.build_fact_ledger(rows + [added])[0]))
check("uncertain facts are withheld from the ledger until confirmed",
      ff.build_fact_ledger(rows)[1] == 1
      and ff.build_fact_ledger(rows, None, ff.latest_resolutions([resolution(rows[1]["row_id"], "confirm")]))[1] == 0)

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
