"""
Case-wide legal issue analysis — cross-checks every identified issue against
the knowledge-base authorities retrieved for it, the case facts and its
evidence.
Location: lib/python/legal_platform/case_analysis.py

The analysis is made in small calls: a few issues per call, each with only
the authorities retrieved for those issues, the facts closest to them and
the evidence list, kept under MAX_PAYLOAD_CHARS. (One call carrying every
issue and every retrieved authority ran to 150,000+ characters, more than
the model reads well, and came back as broken or no JSON.) The calls run
in parallel; an issue whose answer is unusable is asked again on its own;
a last small call writes the case-wide posture and summary from the issue
results. The result has the same shape as before.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import zip_longest
from typing import Any, Callable, Optional

from .config import ANALYSIS_LLM_ID
from .llm import complete_json

ISSUES_PER_CALL = 2
AUTHORITIES_PER_ISSUE = 8
MAX_PAYLOAD_CHARS = 26000
FACT_CHARS = 9000
EVIDENCE_ITEMS = 30
PARALLEL_CALLS = 3
# False: the model answers without hidden reasoning (faster, and its answer
# is never cut off while it is still thinking). True lets it reason first.
ANALYSIS_THINKING = False
CONCLUSIONS = ("supported", "unresolved", "unsupported")
POSTURES = ("strong", "moderate", "weak", "unresolved")

_RULES = r"""
RULES:
- Cite ONLY the authority nodes supplied. Every legal proposition must cite
  the node_id(s) it rests on. Never invent a rule, citation, or node_id.
  Each issue lists the node_ids retrieved for it (retrieved_authority_ids);
  start from those.
- If no supplied authority is genuinely applicable to an issue, say so
  plainly (an empty applicable_rules list) rather than forcing a citation.
- our_position / opponent_position / response must be grounded in the
  supplied facts and evidence; never invent a fact.
- conclusion is one of: supported, unresolved, unsupported.
- Analyze exclusively from BSF's defence perspective — never draft the
  claimant's/customer's case as the recommended position.
""".strip()

ISSUES_PROMPT = r"""
You are a senior legal analyst assisting a qualified attorney who represents
Banque Saudi Fransi (BSF / البنك السعودي الفرنسي) in this dispute.

You receive SOME of the case's legal issues, the case facts most related to
them, its evidence, and the knowledge-base authorities retrieved for these
issues (statutes, regulations, precedents — each with a node_id, its
heading path, and its text). Analyze every supplied issue strictly on this
supplied material.

""" + _RULES + r"""
- Return exactly one entry per supplied issue, with its issue_id unchanged.
- Keep each text field to a few clear sentences.

Return only JSON.

Schema:
{
  "issues": [
    {
      "issue_id": "",
      "issue_title": "",
      "applicable_rules": [
        {"proposition": "", "node_ids": []}
      ],
      "our_position": "",
      "opponent_position": "",
      "response": "",
      "conclusion": "supported|unresolved|unsupported",
      "residual_risk": ""
    }
  ]
}
""".strip()

SUMMARY_PROMPT = r"""
/no_think
You are a senior legal analyst assisting a qualified attorney who represents
Banque Saudi Fransi (BSF / البنك السعودي الفرنسي) in this dispute.

You receive the result of the legal analysis of each issue of the case
(BSF's defence perspective). Write the case-wide view:
- overall_posture: BSF's position across all issues: strong, moderate, weak,
  or unresolved.
- executive_summary: one short paragraph for the attorney: where BSF is
  strong, where it is exposed, and what is still open. Use only what the
  issue results say; never invent a fact, rule or citation. Write in the
  language the issue results are written in.

Return only JSON:
{"overall_posture": "strong|moderate|weak|unresolved", "executive_summary": ""}
""".strip()


def _issues_prompt() -> str:
    return ISSUES_PROMPT if ANALYSIS_THINKING else "/no_think\n" + ISSUES_PROMPT


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _compact_node(node: dict, text_chars: int) -> dict:
    node = node or {}
    return {
        "node_id": str(node.get("node_id", "")),
        "heading_path": _text(node.get("heading_path", ""), 200),
        "text": _text(node.get("canonical_text", "") or node.get("text", ""), text_chars),
        "source_url": str(node.get("source_url", "") or ""),
        "language": str(node.get("language", "") or ""),
    }


def _compact_issue(issue: dict, ref: str, authority_ids: list[str]) -> dict:
    issue = issue or {}
    return {
        "issue_id": ref,
        "issue_title": _text(issue.get("issue_title", ""), 200),
        "issue_description": _text(issue.get("issue_description", ""), 600),
        "priority": str(issue.get("priority", "") or ""),
        "retrieved_authority_ids": authority_ids,
    }


def _compact_fact(fact: dict, text_chars: int = 400) -> dict:
    fact = fact or {}
    return {
        "fact_id": str(fact.get("fact_id", "") or fact.get("fact_candidate_id", "")),
        "fact_text": _text(fact.get("fact_text", ""), text_chars),
        "status": str(fact.get("status", "") or ""),
    }


def _compact_evidence(evidence: list[dict]) -> list[dict]:
    compact = []
    for item in (evidence or [])[:EVIDENCE_ITEMS]:
        item = item or {}
        compact.append({
            "evidence_id": str(item.get("evidence_id", "")),
            "title": _text(item.get("title", "") or item.get("evidence_type", ""), 180),
            "status": str(item.get("status", "") or ""),
        })
    return compact


# -----------------------------------------------------------------------------
# What each call carries
# -----------------------------------------------------------------------------
def authorities_by_issue(issue_results: Optional[list], limit: int = AUTHORITIES_PER_ISSUE) -> list[list[str]]:
    """For each researched issue (research_package issue_results, in issue
    order), the node_ids retrieved for it, best first: the search hits of
    its questions taken in turn (each question's best hit first), then the
    provisions the knowledge graph linked to them (parent, definitions,
    references)."""
    out = []
    for item in issue_results or []:
        per_question, linked = [], []
        for result in (item or {}).get("results") or []:
            hits = [str(hit.get("node_id")) for hit in result.get("hits") or [] if hit.get("node_id")]
            for node in result.get("expanded_nodes") or []:
                node_id = str(node.get("node_id") or "")
                if not node_id:
                    continue
                if node.get("_expansion_type") == "retrieved":
                    if node_id not in hits:
                        hits.append(node_id)
                else:
                    linked.append(node_id)
            per_question.append(hits)
        ranked = [node_id for row in zip_longest(*per_question) for node_id in row if node_id]
        out.append(list(dict.fromkeys(ranked + linked))[:limit])
    return out


_WORD = re.compile(r"\w{3,}")


def _words(value: Any) -> set:
    return {word.lower() for word in _WORD.findall(str(value or ""))}


def _facts_for(batch: list[dict], facts: list[dict], budget: int, text_chars: int) -> list[dict]:
    """The facts closest to these issues within a character budget: linked
    to them, approved, sharing words with them, in that order of weight;
    returned in case order."""
    issue_words = set()
    linked = set()
    for issue in batch:
        issue_words |= _words(issue.get("issue_title")) | _words(issue.get("issue_description"))
        linked |= {str(x) for x in issue.get("source_page_ids") or []}
    scored = []
    for index, fact in enumerate(facts or []):
        fact = fact or {}
        score = len(_words(fact.get("fact_text")) & issue_words)
        fact_ids = {str(fact.get("fact_id") or "")} | {str(x) for x in fact.get("source_page_ids") or []}
        if linked & fact_ids:
            score += 5
        if fact.get("approved"):
            score += 2
        scored.append((-score, index))
    chosen, used = [], 0
    for _, index in sorted(scored):
        compact = _compact_fact(facts[index], text_chars)
        if not compact["fact_text"]:
            continue
        size = len(compact["fact_text"]) + 60
        if used + size > budget:
            continue
        chosen.append(index)
        used += size
    return [_compact_fact(facts[index], text_chars) for index in sorted(chosen)]


def _payload(case_record, batch, refs, node_lists, nodes_by_id, facts, evidence) -> tuple[dict, list[str]]:
    """The request for one call, shrunk until it fits MAX_PAYLOAD_CHARS;
    and the node_ids it carries."""
    # The issues' lists taken in turn, so that a shrunk request still has
    # the best authorities of every issue.
    node_ids = list(dict.fromkeys(node_id for row in zip_longest(*node_lists) for node_id in row
                                  if node_id and node_id in nodes_by_id))
    payload = {}
    for node_chars, fact_budget, fact_chars, node_count in (
        (700, FACT_CHARS, 400, len(node_ids)), (450, FACT_CHARS * 2 // 3, 300, len(node_ids)),
        (300, FACT_CHARS // 2, 250, len(node_ids)), (250, FACT_CHARS // 3, 200, AUTHORITIES_PER_ISSUE),
    ):
        carried = node_ids[:node_count]
        payload = {
            "representation_mandate": {
                "represented_party": "Banque Saudi Fransi (BSF) / البنك السعودي الفرنسي",
                "instruction": "Analyze exclusively from BSF's defence perspective.",
            },
            "case": {
                "case_name": (case_record or {}).get("case_name", ""),
                "workflow_type": (case_record or {}).get("workflow_type", ""),
            },
            "issues": [_compact_issue(issue, ref, [i for i in ids if i in carried])
                       for issue, ref, ids in zip(batch, refs, node_lists)],
            "facts": _facts_for(batch, facts, fact_budget, fact_chars),
            "evidence": _compact_evidence(evidence),
            "authority_nodes": [_compact_node(nodes_by_id[node_id], node_chars) for node_id in carried],
        }
        if len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) <= MAX_PAYLOAD_CHARS:
            break
    return payload, [node["node_id"] for node in payload["authority_nodes"]]


# -----------------------------------------------------------------------------
# Reading the answers
# -----------------------------------------------------------------------------
def _usable(answer: Any) -> bool:
    return isinstance(answer, dict) and any(
        str(answer.get(key) or "").strip() for key in ("our_position", "response", "conclusion"))


def _match_answers(result: Any, refs: list[str]) -> dict:
    """ref -> the model's answer for that issue (by issue_id; by position
    when the ids were changed but the count is right)."""
    answers = result.get("issues") if isinstance(result, dict) else None
    answers = [a for a in answers if isinstance(a, dict)] if isinstance(answers, list) else []
    by_ref = {}
    for answer in answers:
        ref = str(answer.get("issue_id") or "").strip()
        if ref in refs and ref not in by_ref:
            by_ref[ref] = answer
    if not by_ref and len(answers) == len(refs):
        by_ref = dict(zip(refs, answers))
    return {ref: answer for ref, answer in by_ref.items() if _usable(answer)}


def _issue_result(answer: dict, issue: dict, ref: str, allowed_ids: set) -> dict:
    out = dict(answer)
    out["issue_id"] = str(issue.get("issue_id") or ref)
    out["issue_title"] = str(answer.get("issue_title") or issue.get("issue_title") or "")
    for key in ("our_position", "opponent_position", "response", "residual_risk"):
        out[key] = str(out.get(key) or "")
    conclusion = str(out.get("conclusion") or "").strip().lower()
    out["conclusion"] = conclusion if conclusion in CONCLUSIONS else "unresolved"
    rules = out.get("applicable_rules")
    out["applicable_rules"] = [rule for rule in rules if isinstance(rule, dict)] if isinstance(rules, list) else []
    single = {"issues": [out]}
    keep_retrieved_rules(single, allowed_ids)
    return single["issues"][0]


def _failed_issue(issue: dict, ref: str, error: str) -> dict:
    return {
        "issue_id": str(issue.get("issue_id") or ref),
        "issue_title": str(issue.get("issue_title") or ""),
        "applicable_rules": [],
        "our_position": "",
        "opponent_position": "",
        "response": "",
        "conclusion": "unresolved",
        "residual_risk": "This issue could not be analysed automatically (the model's answer could not be "
                         "read). Run the legal analysis again.",
        "has_authority": False,
        "analysis_failed": True,
        "analysis_error": error[:300],
    }


def _posture(issues: list[dict]) -> str:
    """The case-wide posture from the issue conclusions (used when the
    summary call fails)."""
    counts = Counter(issue.get("conclusion") for issue in issues if not issue.get("analysis_failed"))
    total = sum(counts.values())
    if not total:
        return "unresolved"
    if counts["supported"] == total:
        return "strong"
    if counts["unsupported"] * 2 > total:
        return "weak"
    if counts["supported"] * 2 >= total:
        return "moderate"
    return "unresolved"


def _fallback_summary(issues: list[dict]) -> str:
    counts = Counter(issue.get("conclusion") for issue in issues if not issue.get("analysis_failed"))
    failed = sum(1 for issue in issues if issue.get("analysis_failed"))
    text = "{} issue(s) analysed: {} supported, {} unresolved, {} unsupported.".format(
        sum(counts.values()), counts["supported"], counts["unresolved"], counts["unsupported"])
    if failed:
        text += " {} issue(s) could not be analysed; run the analysis again.".format(failed)
    return text


def keep_retrieved_rules(analysis: dict, allowed_ids: set) -> None:
    """Keep only rule citations whose node ids were actually retrieved,
    drop rules left without any, and mark each issue with has_authority."""
    for issue in analysis.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        rules = []
        for rule in issue.get("applicable_rules") or []:
            if not isinstance(rule, dict):
                continue
            ids = [str(x) for x in rule.get("node_ids") or [] if str(x) in allowed_ids]
            if ids:
                rules.append({**rule, "node_ids": ids})
        issue["applicable_rules"] = rules
        issue["has_authority"] = bool(rules)


def issue_has_authority(issue: Any) -> bool:
    """True when the issue cites at least one retrieved authority node.
    Analyses saved before has_authority existed are judged by their rules."""
    if not isinstance(issue, dict):
        return False
    if "has_authority" in issue:
        return bool(issue["has_authority"])
    return any(isinstance(rule, dict) and rule.get("node_ids") for rule in issue.get("applicable_rules") or [])


def _default_llm(prompt: str, payload: dict, expect_keys: tuple) -> dict:
    return complete_json(system_prompt=prompt, user_payload=payload, llm_id=ANALYSIS_LLM_ID,
                         temperature=0.0, expect_keys=expect_keys)


def analyse_case(
    case_record: dict,
    facts: list[dict],
    issues: list[dict],
    evidence: list[dict],
    authority_nodes: list[dict],
    issue_results: Optional[list] = None,
    progress: Optional[Callable[[int, int], None]] = None,
    llm: Optional[Callable[[str, dict, tuple], dict]] = None,
) -> dict:
    """Analyse every identified issue against the authorities retrieved for
    it, the case facts and evidence, a few issues per call (see the module
    note).

    `issue_results`: research_package's per-issue results (same order as
    `issues`); without them each issue gets the first authorities of the
    pool. `progress(done, total)` is called as issues are analysed.

    Returns the JSON the Analysis tab (Legal.js renderAnalysisTab) renders
    directly: overall_posture, executive_summary, issues (one card each, in
    the order of `issues`), knowledge_base_authority_count.
    """
    if not issues:
        raise ValueError("No case issues are available for analysis.")
    llm = llm or _default_llm
    issues = [issue or {} for issue in issues]
    nodes_by_id = {}
    for node in authority_nodes or []:
        node_id = str((node or {}).get("node_id", "") or "")
        if node_id and node_id not in nodes_by_id:
            nodes_by_id[node_id] = node
    linked = authorities_by_issue(issue_results)
    pool = list(nodes_by_id)[:AUTHORITIES_PER_ISSUE]
    node_lists = [[i for i in (linked[n] if n < len(linked) else pool) if i in nodes_by_id]
                  for n in range(len(issues))]

    refs, seen = [], set()
    for number, issue in enumerate(issues, start=1):
        ref = str(issue.get("issue_id") or issue.get("issue_candidate_id") or "") or "ISSUE_{}".format(number)
        if ref in seen:
            ref = "{}_{}".format(ref, number)
        seen.add(ref)
        refs.append(ref)

    results: dict = {}
    errors: dict = {}
    supplied: set = set()

    def run(indexes: list[int]) -> tuple[list[int], dict, set, str]:
        batch = [issues[i] for i in indexes]
        batch_refs = [refs[i] for i in indexes]
        payload, carried = _payload(case_record, batch, batch_refs, [node_lists[i] for i in indexes],
                                    nodes_by_id, facts or [], evidence or [])
        size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        try:
            answers = _match_answers(llm(_issues_prompt(), payload, ("issues",)), batch_refs)
            error = ""
        except Exception as failure:
            answers, error = {}, "{}: {}".format(type(failure).__name__, failure)
        print("[legal analysis] issues={} authorities={} payload_chars={} analysed={}{}".format(
            ",".join(batch_refs), len(carried), size, len(answers), " error=" + error[:200] if error else ""))
        return indexes, answers, set(carried), error

    def run_all(groups: list[list[int]]) -> None:
        if not groups:
            return
        with ThreadPoolExecutor(max_workers=min(PARALLEL_CALLS, len(groups))) as pool_executor:
            futures = [pool_executor.submit(run, group) for group in groups]
            for future in as_completed(futures):
                indexes, answers, carried, error = future.result()
                for index in indexes:
                    answer = answers.get(refs[index])
                    if answer is not None:
                        results[index] = _issue_result(answer, issues[index], refs[index], carried)
                        supplied.update(carried)
                    else:
                        errors[index] = error or "the answer had no usable result for this issue"
                if progress:
                    try:
                        progress(len(results), len(issues))
                    except Exception:
                        pass

    order = list(range(len(issues)))
    if progress:
        try:
            progress(0, len(issues))
        except Exception:
            pass
    run_all([order[i:i + ISSUES_PER_CALL] for i in range(0, len(order), ISSUES_PER_CALL)])
    # An issue missing from its group's answer is asked again on its own.
    missing = [i for i in order if i not in results]
    if missing and ISSUES_PER_CALL > 1:
        print("[legal analysis] asking again, one issue per call: {}".format(",".join(refs[i] for i in missing)))
        run_all([[i] for i in missing])

    if not results:
        first = next(iter(errors.values()), "no answer")
        raise RuntimeError("The legal analysis could not be completed: {}".format(first))

    analysed = [results[i] if i in results else _failed_issue(issues[i], refs[i], errors.get(i, ""))
                for i in order]

    posture, summary = _posture(analysed), _fallback_summary(analysed)
    try:
        overview = llm(SUMMARY_PROMPT, {"issues": [{
            "issue_title": issue["issue_title"],
            "conclusion": issue["conclusion"],
            "has_authority": issue.get("has_authority", False),
            "our_position": _text(issue.get("our_position"), 500),
            "residual_risk": _text(issue.get("residual_risk"), 300),
        } for issue in analysed if not issue.get("analysis_failed")]}, ("overall_posture", "executive_summary"))
        reported = str((overview or {}).get("overall_posture") or "").strip().lower()
        if reported in POSTURES:
            posture = reported
        if str((overview or {}).get("executive_summary") or "").strip():
            summary = str(overview["executive_summary"]).strip()
    except Exception as failure:
        print("[legal analysis] the summary call failed ({}); posture and summary computed from the issues"
              .format(failure))

    return {
        "overall_posture": posture,
        "executive_summary": summary,
        "issues": analysed,
        # Deterministic, not LLM-reported: the frontend metric must match
        # what was actually supplied, not a number the model might miscount.
        "knowledge_base_authority_count": len(supplied),
    }
