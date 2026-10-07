"""
Checks for the contract review marks on the agreement pages
(agreement_markup.py and agreement_analysis.clean_edits).

Run from the repository root:  python test_agreement_markup.py
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

from legal_platform.agreement_markup import mark_pages          # noqa: E402
from legal_platform.agreement_analysis import clean_edits       # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


edits = clean_edits([
    {"type": "replace", "original": "The Customer may terminate this Agreement without notice.",
     "replacement": "The Customer may terminate this Agreement by giving 30 days' written notice.",
     "reason_en": "Termination without notice exposes the Bank."},
    {"type": "delete", "original": "The Bank waives all claims.", "reason_en": "Never waive claims."},
    {"type": "add", "original": "Payments are due monthly.", "replacement": "Late payments bear a fee of 2%."},
    {"type": "replace", "original": "", "replacement": "nothing to replace"},
    {"type": "replace", "original": "same", "replacement": "same"},
    "not a dict",
], "C7")
check("only usable edits are kept, each with an id", [e["edit_id"] for e in edits] == ["C7-E1", "C7-E2", "C7-E3"])
check("a deletion has no replacement", edits[1]["type"] == "delete" and edits[1]["replacement"] == "")

PAGE1 = ("7.1 Term. This Agreement starts on signature.\n7.2 The Customer may terminate this\n"
         "Agreement   without notice. The Bank waives all claims.")
PAGE2 = "8. Payments are due monthly. Interest is fixed."
ARABIC = "يلتزم العميل بسداد الرسوم شهرياً في موعدها. يحق للبنك إنهاء الاتفاقية دون إشعار."
pages = [{"page_id": "P2", "case_document_id": "D1", "page_number": 2, "page_text": PAGE2},
         {"page_id": "P1", "case_document_id": "D1", "page_number": 1, "page_text": PAGE1},
         {"page_id": "P3", "case_document_id": "D2", "page_number": 1, "page_text": ARABIC}]
documents = [{"case_document_id": "D1", "original_filename": "agreement.pdf"},
             {"case_document_id": "D2", "original_filename": "annex.pdf"}]
arabic_edits = clean_edits([{"type": "replace", "original": "يحق للبنـك إنهاءُ الاتفاقية دون إشعار",
                             "replacement": "يحق للبنك إنهاء الاتفاقية بإشعار مدته ثلاثون يوماً"},
                            {"type": "delete", "original": "بسداد الرسوم شهرياً في موعدها"},
                            {"type": "replace", "original": "words that are on no page",
                             "replacement": "x"}], "C9")
reviews = [{"clause_id": "C7", "risk_level": "high", "source_page_ids": ["P1"], "edits": edits},
           {"clause_id": "C9", "risk_level": "medium", "source_page_ids": [], "edits": arabic_edits}]
markup = mark_pages(pages, documents, reviews)

check("pages are in reading order with their file names",
      [(p["document_name"], p["page_number"]) for p in markup["pages"]]
      == [("agreement.pdf", 1), ("agreement.pdf", 2), ("annex.pdf", 1)])
page1 = markup["pages"][0]
check("the page text is kept whole", "".join(s["text"] for s in page1["segments"]) == PAGE1)
marks = [s for s in page1["segments"] if s["kind"] == "mark"]
check("a sentence is found despite a line break and extra spaces",
      marks[0]["edit_id"] == "C7-E1" and marks[0]["text"].startswith("The Customer may terminate this\nAgreement"))
check("a deletion is marked on its words", marks[1]["edit_id"] == "C7-E2" and marks[1]["text"] == "The Bank waives all claims")
page2 = markup["pages"][1]
check("an addition is placed after its sentence on another page of the clause",
      [s["kind"] for s in page2["segments"]][:3] == ["text", "text", "insert"]
      and page2["segments"][1]["text"] == "Payments are due monthly" and markup["edits"]["C7-E3"]["page_id"] == "P2")
page3 = markup["pages"][2]
check("Arabic words are found despite tatweel and diacritics",
      any(s["kind"] == "mark" and s["edit_id"] == "C9-E1" for s in page3["segments"]))
check("a change whose words are on no page is listed apart, not placed", markup["unplaced"] == ["C9-E3"])
check("a word ending in a diacritic is matched before the next word",
      any(s["kind"] == "mark" and s["edit_id"] == "C9-E2" for s in page3["segments"]))
check("each change knows its clause risk", markup["edits"]["C7-E1"]["risk_level"] == "high")
check("pages count their changes", [p["changes"] for p in markup["pages"]] == [2, 1, 2])
check("no review edits: plain pages", mark_pages(pages, documents, [{"clause_id": "X"}])["pages"][0]["segments"]
      == [{"text": PAGE1, "edit_id": "", "kind": "text"}])

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
