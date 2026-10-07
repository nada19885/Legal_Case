"""
Checks that Knowledge Bank queries fit in the request URL (retrieval._fit_query),
and that one clause that cannot be reviewed does not stop a contract review.

Run from the repository root:  python test_retrieval_query.py
"""

import importlib.util
import pathlib
import sys
import types
from urllib.parse import quote

ROOT = pathlib.Path(__file__).resolve().parent
sys.modules.setdefault("dataiku", types.ModuleType("dataiku"))
if "legal_platform" not in sys.modules:
    spec = importlib.util.spec_from_file_location("legal_platform", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules["legal_platform"] = package
    spec.loader.exec_module(package)

from legal_platform import retrieval                       # noqa: E402
from legal_platform import agreement_analysis as aa        # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


long_query = "Saudi law. Clause wording: " + "يتعهد ويقر المستفيد بأن المعلومات صحيحة ودقيقة " * 200
fitted = retrieval._fit_query(long_query)
check("a long Arabic query is cut to fit the URL", len(quote(fitted, safe="")) <= retrieval.MAX_ENCODED_QUERY)
check("the cut keeps the start of the query and ends on a whole word",
      fitted.startswith("Saudi law. Clause wording:") and long_query.startswith(fitted)
      and long_query[len(fitted)] == " ")
check("a short query is unchanged", retrieval._fit_query("liability cap") == "liability cap")

clauses = [{"clause_id": f"CL_{n}", "heading": f"H{n}", "full_text": f"text {n}", "source_page_ids": [f"P{n}"]}
           for n in (1, 2, 3)]


def search(unit, profile):
    if unit["target_clause"]["clause_id"] == "CL_2":
        raise RuntimeError("HTTP ERROR 414 URI Too Long")
    return [{"node_id": "N1", "text": "rule"}]


def model(prompt, payload, operation=""):
    if "CL_3" in operation:
        raise RuntimeError("The LLM request failed.")
    if "clause review" in operation:
        clause = payload["clause_context"]["target_clause"]
        return {"clause_id": clause["clause_id"], "risk_level": "low", "authority_node_ids": ["N1"],
                "support_status": "supported", "edits": []}
    return {"executive_summary_en": "ok"}


aa.retrieve_authorities_for_unit = search
aa.agreement_complete_json = model
aa.build_review_units = lambda clause_map: [{"target_clause": c} for c in clause_map["clauses"]]
final, authorities = aa.review_large_agreement({"clauses": clauses}, {"represented_party": "BSF"})
reviews = {r["clause_id"]: r for r in final["clause_reviews"]}
check("every clause has a review, in order", [r["clause_id"] for r in final["clause_reviews"]] == ["CL_1", "CL_2", "CL_3"])
check("a failed knowledge-base search: the clause is still reviewed, without authorities",
      not reviews["CL_2"].get("review_failed") and reviews["CL_2"]["authority_node_ids"] == []
      and reviews["CL_2"]["support_status"] == "unsupported")
check("a clause whose review fails is marked, and the others are kept",
      reviews["CL_3"]["review_failed"] and reviews["CL_3"]["review_status"] == "provisional"
      and reviews["CL_1"]["authority_node_ids"] == ["N1"])

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
