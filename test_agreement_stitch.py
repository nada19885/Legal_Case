"""
Checks for joining the agreement's page structures into clauses
(agreement_consolidation.stitch_page_structures / consolidate_page_structures).

Run from the repository root:  python test_agreement_stitch.py
"""

import importlib.util
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

from legal_platform import agreement_consolidation as ac          # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


def fragment(number, heading, text, starts_before=False, goes_on=False):
    return {"clause_number": number, "heading": heading, "text": text, "category": "term_and_termination",
            "continues_from_previous_page": starts_before, "continues_on_next_page": goes_on,
            "exceptions_or_carve_outs": []}


pages = [
    {"page_id": "P2", "document_id": "D1", "page_number": 2, "clause_fragments": [
        fragment("", "", "written notice to the Bank.", starts_before=True),
        fragment("8", "Fees", "Fees are due monthly.")],
     "definitions_introduced": [{"term": "Bank", "definition": "BSF"}]},
    {"page_id": "P1", "document_id": "D1", "page_number": 1, "clause_fragments": [
        fragment("1", "Definitions", "Bank means BSF."),
        fragment("7", "Termination", "The Customer may terminate by giving", goes_on=True)],
     "definitions_introduced": [{"term": "Bank", "definition": "Banque Saudi Fransi"}]},
    {"page_id": "P3", "document_id": "D1", "page_number": 3, "clause_fragments": [
        fragment("", "", "and any late fee.")]},
    {"page_id": "A1", "document_id": "D2", "page_number": 1, "clause_fragments": [
        fragment("", "", "Annex text that says it continues.", starts_before=True)]},
]
stitched = ac.stitch_page_structures(pages)
clauses = stitched["clauses"]
check("fragments are joined in page order into whole clauses",
      [c["clause_number"] for c in clauses] == ["1", "7", "8", "", ""])
check("a clause running onto the next page keeps both parts and both pages",
      clauses[1]["full_text"] == "The Customer may terminate by giving\nwritten notice to the Bank."
      and clauses[1]["source_page_ids"] == ["P1", "P2"])
check("a page starting without a number does not join a clause that ended",
      clauses[3]["full_text"] == "and any late fee." and clauses[3]["source_page_ids"] == ["P3"])
check("a clause never runs into another document", clauses[4]["source_page_ids"] == ["A1"]
      and any("starts in the middle" in note for note in stitched["missing_or_unclear_sections"]))
check("the clause text is exactly the page structures' text", clauses[2]["full_text"] == "Fees are due monthly.")

calls = []
ac.agreement_complete_json = lambda prompt, payload, operation="": calls.append(operation) or {
    "dependency_graph": [{"source_clause_id": "CL_0002", "target_clause_id": "CL_0001"}], "package_summary": "ok"}
progress = []
maps, clause_map = ac.consolidate_page_structures(pages, {"represented_party": "BSF"},
                                                  lambda d, t, n: progress.append((d, t)))
check("only the package summary uses the model (no per-chunk calls)", calls == ["agreement package synthesis"])
check("clause ids, page spans and related clauses are set",
      clause_map["clauses"][1]["clause_id"] == "CL_0002"
      and clause_map["clauses"][1]["completeness_status"] == "spans_multiple_pages"
      and clause_map["clauses"][0]["related_clause_ids"] == ["CL_0002"])
check("a term defined twice is kept once, with all its pages",
      [d["term"] for d in clause_map["definitions"]] == ["Bank"]
      and clause_map["definitions"][0]["source_page_ids"] == ["P1", "P2"])
check("progress is reported", progress == [(1, 1)] and len(maps) == 1)

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
