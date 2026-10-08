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
      [s["kind"] for s in page2["segments"]][:2] == ["text", "insert"]
      and page2["segments"][0]["text"].endswith("Payments are due monthly") and markup["edits"]["C7-E3"]["page_id"] == "P2")
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

# --- The contract as one document, and its Word file -------------------------
import io                                                              # noqa: E402
import zipfile                                                         # noqa: E402
import xml.etree.ElementTree as ET                                     # noqa: E402
from legal_platform.agreement_markup import contract_document          # noqa: E402
from legal_platform.agreement_docx import contract_docx                # noqa: E402

CONTRACT = ("عقد تقديم خدمات محاماة\n\nالمادة الأولى: الأتعاب\nاتفق الطرفان على أتعاب قدرها 2000 ريال تستحق:\n"
            "- 1000 ريال عند صدور الحكم.\n- 1000 ريال عند كسب الدعوى.\n\n| البند | المبلغ |\n|---|---|\n"
            "| الدفعة الأولى | 1000 |\n\nإنهاء العقد\n3.1- للطرف الأول إنهاء العقد بإخطار مدته عشرة أيام\n"
            "ولا يستحق أي أتعاب.")
contract_pages = [{"page_id": "Q1", "case_document_id": "D1", "page_number": 1, "page_text": CONTRACT},
                  {"page_id": "Q2", "case_document_id": "D1", "page_number": 2, "page_text": "المادة الرابعة: النزاعات\nتحال النزاعات إلى محاكم جدة."}]
contract_edits = clean_edits([
    {"type": "replace", "original": "1000 ريال عند كسب الدعوى", "replacement": "1000 ريال عند صدور حكم نهائي لصالح الموكل",
     "reason_ar": "تحديد معنى كسب الدعوى"},
    {"type": "replace", "original": "بإخطار مدته عشرة أيام ولا", "replacement": "بإخطار كتابي مدته ثلاثون يوماً ولا",
     "reason_en": "Longer notice"},
    {"type": "add", "original": "تحال النزاعات إلى محاكم جدة", "replacement": "بعد محاولة التسوية الودية خلال 15 يوماً."},
    {"type": "delete", "original": "الدفعة الأولى", "reason_en": "inside the table"},
    {"type": "replace", "original": "not in this contract", "replacement": "x"}], "C1")
contract = contract_document(contract_pages, [{"case_document_id": "D1", "original_filename": "c.pdf"}],
                             [{"clause_id": "C1", "clause_number": "1", "source_page_ids": ["Q1"], "edits": contract_edits}],
                             {"clauses": [{"heading": "إنهاء العقد"}]})
blocks = contract["blocks"]
kinds = [b["type"] for b in blocks]
text_of = lambda b: "".join(r["text"] for r in b.get("runs") or [])
check("the contract's first line is its title", blocks[0]["type"] == "heading" and blocks[0]["level"] == 1)
check("clause titles become headings (by wording and by the clause map)",
      [text_of(b) for b in blocks if b["type"] == "heading"][1:] == ["المادة الأولى: الأتعاب", "إنهاء العقد", "المادة الرابعة: النزاعات"])
check("bullet lines become list items without their dash", kinds.count("item") == 2
      and text_of([b for b in blocks if b["type"] == "item"][0]).startswith("1000 ريال عند صدور"))
table = next(b for b in blocks if b["type"] == "table")
check("a markdown table becomes a table with its header row",
      table["rows"][0]["header"] and ["".join(r["text"] for r in c) for c in table["rows"][1]["cells"]] == ["الدفعة الأولى", "1000"])
check("a page break of the original is marked", {"type": "page", "page_number": 2} in blocks)
wrapped = next(b for b in blocks if b["type"] == "paragraph" and text_of(b).startswith("3.1"))
check("a change running over a wrapped line stays one change in one paragraph",
      [r["kind"] for r in wrapped["runs"]].count("mark") == 1 and "\n" in text_of(wrapped))
check("an addition goes after its sentence", any(r["kind"] == "insert" for b in blocks for r in b.get("runs") or []))
check("a change inside a table cell is placed in the cell",
      any(r["kind"] == "mark" for row in table["rows"] for cell in row["cells"] for r in cell))
check("changes whose words are not in the text are listed apart", contract["unplaced"] == ["C1-E5"] and contract["changes"] == 4)

docx_bytes = contract_docx(contract, "عقد تقديم خدمات محاماة", "ar")
package = zipfile.ZipFile(io.BytesIO(docx_bytes))
NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
body = ET.fromstring(package.read("word/document.xml"))


def version(accept: bool) -> str:
    out = []

    def walk(node, inside_ins=False, inside_del=False):
        tag = node.tag.replace(NS, "")
        inside_ins = inside_ins or tag == "ins"
        inside_del = inside_del or tag == "del"
        if tag == "t" and (accept or not inside_ins):
            out.append(node.text or "")
        if tag == "delText" and not accept:
            out.append(node.text or "")
        for child in node:
            walk(child, inside_ins, inside_del)
    walk(body)
    return "".join(out)


rejected, accepted = version(False), version(True)
check("the Word file holds every part of a .docx", {"[Content_Types].xml", "word/document.xml", "word/styles.xml",
                                                    "word/comments.xml"} <= set(package.namelist()))
check("every change is a tracked change (insertions and deletions)",
      len(body.findall(f".//{NS}ins")) == 3 and len(body.findall(f".//{NS}del")) == 3)
check("rejecting all changes gives back the contract's own words",
      "1000 ريال عند كسب الدعوى" in rejected and "بإخطار مدته عشرة أيام" in rejected and "ثلاثون" not in rejected)
check("accepting all changes gives the proposed wording",
      "عند صدور حكم نهائي لصالح الموكل" in accepted and "عند كسب الدعوى." not in accepted
      and "بعد محاولة التسوية الودية" in accepted)
check("each reason is a Word comment", package.read("word/comments.xml").decode("utf-8").count("<w:comment ") == 3)
check("Arabic paragraphs are right-to-left", body.find(f".//{NS}bidi") is not None)
check("the changes not found are listed at the end", "تعديلات مقترحة أخرى" in accepted and "not in this contract" in accepted)

# --- Changes worked out from a clause's proposed wording ---------------------
from legal_platform.agreement_markup import derive_edits                # noqa: E402

CLAUSE10 = ("تتم تسوية أي خلافات بشكل ،ودّي وفي حالة تعذر ذلك خلال (15) ،يوم يحال الخالف إلى املحاكم املختصة في "
            "مدينة جدة وفق أحكام نظام املرافعات الشرعية في اململكة العربية السعودية.")
REVIEW10 = {"clause_id": "CL_0010", "risk_level": "medium",
            "proposed_wording_ar": "تتم تسوية أي خلافات بشكل ودي وفي حالة تعذر ذلك خلال (30) يوماً، يحال الخلاف إلى "
                                   "المحاكم المختصة في مدينة جدة وفق أحكام نظام المرافعات الشرعية في المملكة العربية "
                                   "السعودية، ولا يمنع ذلك الطرفين من الاتفاق كتابةً على تمديد هذه المدة.",
            "proposed_wording_en": "Any disputes shall be resolved amicably within (30) days ...",
            "recommended_change_en": "Extend the amicable settlement period to 30 days."}
derived = derive_edits(REVIEW10, CLAUSE10)
check("a proposed wording gives only the words that differ",
      [(e["type"], e["original"], e["replacement"]) for e in derived]
      == [("replace", "15", "30"),
          ("add", "العربية السعودية.", "ولا يمنع ذلك الطرفين من الاتفاق كتابةً على تمديد هذه المدة")])
check("the PDF's letter-order damage is not taken for a change", len(derived) == 2)
check("the clause's recommended change is the reason", derived[0]["reason_en"].startswith("Extend"))
check("an instruction with blanks is not a wording", derive_edits(
    {"clause_id": "C9", "proposed_wording_ar": "إضافة إشارة إلى المادة ___ من النظام"}, "تكون جميع املراسالت") == [])
check("a wording in another language than the clause is not used", derive_edits(
    {"clause_id": "C9", "proposed_wording_en": "All notices in writing."}, "تكون جميع املراسالت على العناوين") == [])
rewrite = derive_edits({"clause_id": "C7", "proposed_wording_ar": "على المحامي أداء عمله وفق الأصول المهنية المعتمدة."},
                       "يلتزم الطرف الأول ببذل العناية الالزمة")
check("a full rewrite replaces the whole clause", len(rewrite) == 1 and rewrite[0]["original"] == "يلتزم الطرف الأول ببذل العناية الالزمة")

PAGE_TWO = ("املادة الثامنة: إنهاء العقد: للطرف الأول الحق في إنهاء العقد بموجب إخطار ال تقل مدته عن عشرة أيام.\n\n"
            "املادة العاشرة: حل النزاعات: " + CLAUSE10 + "\n\n2\n\n[picture 1] [picture 2]")
derived_contract = contract_document(
    [{"page_id": "R2", "case_document_id": "D9", "page_number": 2, "page_text": PAGE_TWO}], [], [REVIEW10],
    {"clauses": [{"clause_id": "CL_0010", "heading": "حل النزاعات", "full_text": CLAUSE10},
                 {"clause_id": "CL_0008", "heading": "إنهاء العقد"}]})
dblocks = derived_contract["blocks"]
check("a review without exact edits still shows its changes in the contract",
      derived_contract["changes"] == 2 and derived_contract["unplaced"] == [])
check("a short change is placed in its own sentence",
      any(r["kind"] == "mark" and r["text"] == "15" for b in dblocks for r in b.get("runs") or []))
check("the brackets around a changed number stay as they are",
      derived_contract["edits"]["CL_0010-D1"]["replacement"] == "30")
check("a title on the same line as its text becomes a heading",
      [text_of(b) for b in dblocks if b["type"] == "heading"] == ["المادة الثامنة: إنهاء العقد", "المادة العاشرة: حل النزاعات"]
      and text_of(dblocks[1]).startswith("للطرف الأول"))
check("page numbers and picture markers are not shown as contract text",
      not any(text_of(b).strip() in {"2", "[picture 1] [picture 2]"} for b in dblocks))

# --- Advice, rewrites and matching despite the PDF's punctuation ----------------
CLAUSE3 = ("للطرف الأول إنهاء العقد بإخطار مدته عشرة (10) أيام، وللطرف الثاني إنهاء العقد مع سداد كامل الأتعاب "
           "بإخطار مدته عشرة (10) أيام.")
advice_with_quote = derive_edits({"clause_id": "C3", "proposed_wording_ar":
    "يُستحسن إضافة جملة: 'يُطبق أحكام المادة 15 من الصيغ النموذجية في حالة إنهاء العقد' بعد ذكر التزام الطرف الثاني."},
    CLAUSE3)
check("advice quoting a sentence: the sentence is added at the end of the clause",
      advice_with_quote[0]["type"] == "add" and advice_with_quote[0]["replacement"].startswith("يُطبق أحكام المادة 15")
      and advice_with_quote[0]["original"] == CLAUSE3)
plain_advice = derive_edits({"clause_id": "C8", "proposed_wording_ar":
    "يُعدل النص ليُشترط أن يُحتسب دفع الأتعاب بناءً على النسبة الزمنية المنقضية."}, CLAUSE3)
check("advice without a sentence to add is not put in the contract", [e["type"] for e in plain_advice] == ["advice"])
with_node = derive_edits({"clause_id": "C5", "proposed_wording_ar":
    "يتعهد الطرف الثاني بتقديم الوكالات اللازمة المحددة في النظام (NODE_05EA806F15D7F9B14CAE) لتقديم الشكوى."},
    "زود المحامي بكافة المستندات والوكالات الالزمة وتقديم الشكوى")
check("knowledge-base ids are never written into the contract", all("NODE_" not in e["replacement"] for e in with_node))
check("a rewrite replaces the clause whole instead of mixing words",
      len(with_node) == 1 and with_node[0]["type"] == "replace")

NOTICE_PAGE = ("املادة التاسعة: املراسالت\nتكون جميع املراسالت واإلشعارات على العناوين املثبتة في صدر هذا ،العقد وتعد "
               "منتجة آثارها ،النظامية ويلتزم من يغير عنوانه بإشعار الطرف اآلخر كتابة.")
notice = contract_document(
    [{"page_id": "N1", "case_document_id": "D7", "page_number": 1, "page_text": NOTICE_PAGE}], [],
    [{"clause_id": "CL_0009", "proposed_wording_ar": "تُرسل جميع المراسلات إلى العناوين المذكورة في بداية العقد، مع خيار "
                                                     "الإشعار الإلكتروني بموافقة الطرفين."},
     {"clause_id": "CL_0003", "proposed_wording_ar": "يُعدل النص ليُشترط أن يُحتسب دفع الأتعاب بالتناسب."}],
    {"clauses": [{"clause_id": "CL_0009", "heading": "المراسلات", "full_text":
                  "تكون جميع املراسالت واإلشعارات على العناوين املثبتة في صدر هذا العقد وتعد منتجة آثارها النظامية "
                  "ويلتزم من يغير عنوانه بإشعار الطرف اآلخر كتابة"},
                 {"clause_id": "CL_0003", "heading": "مدة العقد", "full_text": CLAUSE3}]})
check("a clause is found although the page has stray commas and letter-order damage",
      notice["edits"]["CL_0009-D1"]["page_id"] == "N1" and "CL_0009-D1" not in notice["unplaced"])
check("advice is listed apart, not placed", notice["unplaced"] == ["CL_0003-D1"]
      and notice["edits"]["CL_0003-D1"]["type"] == "advice")
check("the page text is shown with its ligatures repaired",
      text_of(notice["blocks"][0]).startswith("المادة التاسعة") and "الإشعارات" in "".join(
          r["text"] for b in notice["blocks"] for r in b.get("runs") or []))

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
