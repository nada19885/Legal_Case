"""
Checks for the legal analysis (case_analysis.py): many issues and a large
authority pool are analysed in small calls.

Run from the repository root:  python test_case_analysis.py
The model is a stand-in; this checks what each call carries, how answers
are put back together, and what happens when an answer is unusable.
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

from legal_platform import case_analysis as ca          # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


# 13 issues, 12 hits each from two questions, every node a long article.
ISSUES = [{"issue_id": f"ISS{n}", "issue_title": f"المسألة {n}: تجميد الحساب {n}",
           "issue_description": "هل يحق للبنك تجميد الحساب بعد بلاغ احتيال " * 8, "priority": "high",
           "source_page_ids": [f"FACT{n}"], "approved": True} for n in range(1, 14)]
NODES = {}
RESULTS = []
for n in range(1, 14):
    questions = []
    for q in range(2):
        hits, expanded = [], []
        for h in range(12):
            node_id = f"KB_{n}_{q}_{h}"
            NODES[node_id] = {"node_id": node_id, "heading_path": "نظام مراقبة البنوك > المادة " + str(h),
                              "canonical_text": "نص المادة " * 300, "source_url": "", "language": "ar"}
            hits.append({"node_id": node_id, "score": 1 - h / 20})
            expanded.append(dict(NODES[node_id], _expansion_type="retrieved"))
        parent = f"KB_{n}_{q}_parent"
        NODES[parent] = {"node_id": parent, "heading_path": "الباب", "canonical_text": "باب " * 200}
        expanded.append(dict(NODES[parent], _expansion_type="parent"))
        questions.append({"query": f"q{q}", "hits": hits, "expanded_nodes": expanded})
    RESULTS.append({"issue_id": f"ISS{n}", "issue_title": "", "questions": [], "results": questions})
FACTS = [{"fact_id": f"FACT{n}", "fact_text": f"واقعة {n}: تم تجميد مبلغ 250 ريال بتاريخ 18-10-2024 " * 6,
          "status": "stated", "approved": n % 2 == 0} for n in range(1, 200)]
EVIDENCE = [{"evidence_id": f"EV{n}", "title": "كشف حساب", "status": "requested"} for n in range(1, 50)]

calls = []


def answer_for(issue, cite):
    return {"issue_id": issue["issue_id"], "issue_title": issue["issue_title"],
            "applicable_rules": [{"proposition": "يجوز التجميد", "node_ids": cite}],
            "our_position": "البنك التزم بالتعليمات", "opponent_position": "العميل يطالب",
            "response": "الرد", "conclusion": "Supported", "residual_risk": "منخفض"}


def model(prompt, payload, expect_keys, drop=(), fail=(), summary=True):
    calls.append((prompt, payload, expect_keys))
    if "issues" in expect_keys:
        ids = [issue["issue_id"] for issue in payload["issues"]]
        if any(i in fail for i in ids):
            raise ValueError("The LLM did not return a JSON object.")
        return {"issues": [answer_for(issue, issue["retrieved_authority_ids"][:2] + ["KB_INVENTED"])
                           for issue in payload["issues"] if issue["issue_id"] not in drop or len(ids) == 1]}
    if not summary:
        raise RuntimeError("endpoint busy")
    return {"overall_posture": "Moderate", "executive_summary": "موقف البنك متوسط."}


progress = []
result = ca.analyse_case({"case_name": "Huda v BSF"}, FACTS, ISSUES, EVIDENCE, list(NODES.values()),
                         issue_results=RESULTS, progress=lambda d, t: progress.append((d, t)), llm=model)
issue_calls = [c for c in calls if "issues" in c[2]]
sizes = [len(json.dumps(c[1], ensure_ascii=False, separators=(",", ":"))) for c in issue_calls]
first = next(c for c in issue_calls if c[1]["issues"][0]["issue_id"] == "ISS1")
print(f"    {len(issue_calls)} calls of {min(sizes)}-{max(sizes)} characters")
check("every call stays under the size limit", max(sizes) <= ca.MAX_PAYLOAD_CHARS)
check("a few issues per call", all(len(c[1]["issues"]) <= ca.ISSUES_PER_CALL for c in issue_calls)
      and len(issue_calls) == 7)
check("each call carries only the authorities retrieved for its own issues",
      all({n["node_id"].split("_")[1] for n in c[1]["authority_nodes"]}
          <= {i["issue_id"][3:] for i in c[1]["issues"]} for c in issue_calls))
check("each issue gets its best hits from every question",
      first[1]["issues"][0]["retrieved_authority_ids"][:4] == ["KB_1_0_0", "KB_1_1_0", "KB_1_0_1", "KB_1_1_1"])
check("the facts linked to an issue are sent with it",
      any(f["fact_id"] == "FACT1" for f in first[1]["facts"]))
check("the analysis prompt runs without hidden reasoning", first[0].startswith("/no_think"))
check("every issue is analysed, in the register's order",
      [i["issue_id"] for i in result["issues"]] == [i["issue_id"] for i in ISSUES])
check("conclusions are normalised", all(i["conclusion"] == "supported" for i in result["issues"]))
check("a citation of a node that was not supplied is dropped",
      all("KB_INVENTED" not in r["node_ids"] for i in result["issues"] for r in i["applicable_rules"])
      and all(i["has_authority"] for i in result["issues"]))
check("the posture and summary come from the summary call",
      result["overall_posture"] == "moderate" and result["executive_summary"] == "موقف البنك متوسط.")
check("the authority count is what was actually supplied",
      result["knowledge_base_authority_count"] == len({n["node_id"] for c in issue_calls for n in c[1]["authority_nodes"]}))
check("progress is reported up to every issue", progress[0] == (0, 13) and progress[-1] == (13, 13))

calls.clear()
again = ca.analyse_case({}, FACTS, ISSUES[:4], EVIDENCE, list(NODES.values()), issue_results=RESULTS[:4],
                        llm=lambda p, d, k: model(p, d, k, drop={"ISS2"}))
singles = [c for c in calls if "issues" in c[2] and len(c[1]["issues"]) == 1]
check("an issue left out of a group's answer is asked again on its own",
      len(singles) == 1 and singles[0][1]["issues"][0]["issue_id"] == "ISS2"
      and not again["issues"][1].get("analysis_failed"))

calls.clear()
partial = ca.analyse_case({}, FACTS, ISSUES[:4], EVIDENCE, list(NODES.values()), issue_results=RESULTS[:4],
                          llm=lambda p, d, k: model(p, d, k, fail={"ISS3"}, summary=False))
check("an issue that cannot be analysed is marked, the others are kept",
      partial["issues"][2]["analysis_failed"] and partial["issues"][2]["conclusion"] == "unresolved"
      and partial["issues"][3]["conclusion"] == "supported")
check("without the summary call the posture comes from the issue conclusions",
      partial["overall_posture"] == "strong" and "1 issue(s) could not be analysed" in partial["executive_summary"])

try:
    ca.analyse_case({}, FACTS, ISSUES[:2], EVIDENCE, list(NODES.values()), issue_results=RESULTS[:2],
                    llm=lambda p, d, k: model(p, d, k, fail={"ISS1", "ISS2"}))
    raised = False
except RuntimeError as error:
    raised = "could not be completed" in str(error)
check("when no issue can be analysed the run fails with the reason", raised)

calls.clear()
pooled = ca.analyse_case({}, FACTS, ISSUES[:3], EVIDENCE, list(NODES.values())[:30], llm=model)
check("without per-issue research the calls still carry a bounded pool",
      len(pooled["issues"]) == 3 and all(len(c[1]["authority_nodes"]) <= ca.AUTHORITIES_PER_ISSUE
                                          for c in calls if "issues" in c[2]))

unnamed = ca.analyse_case({}, [], [{"issue_title": "A"}, {"issue_title": "B"}], [], [], llm=model)
check("issues without ids are matched back by a reference",
      [i["issue_title"] for i in unnamed["issues"]] == ["A", "B"]
      and not unnamed["issues"][0]["has_authority"])

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
