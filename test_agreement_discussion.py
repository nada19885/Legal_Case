"""
Checks that the agreement discussion sends a bounded request
(agreement_workbench.discussion_material / discuss_agreement).

Run from the repository root:  python test_agreement_discussion.py
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

from legal_platform import agreement_workbench as aw          # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


clauses = [{"clause_id": f"CL_{n:04d}", "clause_number": str(n), "heading": h, "category": "other",
            "full_text": t * 3, "source_page_ids": ["P1"]}
           for n, (h, t) in enumerate([("التمهيد", "رغب الطرف الثاني في تكليف المحامي "),
                                       ("الأتعاب", "اتفق الطرفان على أن تكون أتعاب المحاماة 2000 ريال "),
                                       ("إنهاء العقد", "للطرف الأول الحق في إنهاء العقد بإخطار عشرة أيام ")] * 4, start=1)]
nodes = [{"node_id": f"KB_{n}", "heading_path": "نظام المحاماة > المادة " + str(n),
          "canonical_text": "نص المادة " * 400, "embedding": [0.1] * 300, "metadata": {"x": "y" * 500}}
         for n in range(70)]
reviews = [{"clause_id": c["clause_id"], "risk_level": "medium", "review_status": "final",
            "legal_finding_ar": "ملاحظة " * 300, "commercial_finding_en": "note " * 300,
            "authority_node_ids": ["KB_65"] if c["clause_number"] == "8" else [],
            "edits": [{"original": "x" * 2000}], "weaknesses": ["w" * 2000]} for c in clauses]
question = "ما المخاطر في البند 8 إنهاء العقد؟"

old_size = len(json.dumps({"clauses": clauses, "clause_reviews": reviews, "knowledge_base_authorities": nodes},
                          ensure_ascii=False))
sent = []
aw.agreement_complete_json = lambda prompt, payload, operation="": sent.append(payload) or {
    "answer_ar": "...", "clause_ids": ["CL_0008"], "authority_node_ids": ["KB_65", "KB_INVENTED"],
    "support_status": "supported"}
answer = aw.discuss_agreement(question, {"represented_party": "BSF"}, {"clauses": clauses}, {"clause_reviews": reviews}, nodes)
size = len(json.dumps(sent[0], ensure_ascii=False))
print(f"    before: {old_size} characters; now: {size}")
check("the request stays small", size < 30000)
check("the clause the question names comes first", sent[0]["clauses"][0]["clause_id"] == "CL_0008")
check("the authority cited by a clause review is sent first",
      sent[0]["knowledge_base_authorities"][0]["node_id"] == "KB_65")
check("authorities are sent without embeddings or metadata, text shortened",
      set(sent[0]["knowledge_base_authorities"][0]) == {"node_id", "heading_path", "text", "source_url"}
      and len(sent[0]["knowledge_base_authorities"][0]["text"]) <= 700)
check("clause reviews are sent without the page edits", all("edits" not in r for r in sent[0]["clause_reviews"]))
check("the answer still keeps only citations that were supplied",
      answer.get("authority_node_ids") == ["KB_65"])

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
