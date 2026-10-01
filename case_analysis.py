"""
Case-wide legal issue analysis — cross-checks every identified issue against
the knowledge-base authority pool retrieved for the case, the case facts and
its evidence.
Location: lib/python/legal_platform/case_analysis.py
"""

from __future__ import annotations

from typing import Any

from .config import ANALYSIS_LLM_ID
from .llm import complete_json

ANALYSIS_PROMPT = r"""
You are a senior legal analyst assisting a qualified attorney who represents
Banque Saudi Fransi (BSF / البنك السعودي الفرنسي) in this dispute.

You receive the case's identified legal issues, its facts, its evidence, and
a knowledge-base authority pool retrieved for this case (statutes,
regulations, precedents — each with a node_id, its heading path, and its
canonical text). Analyze every issue strictly on this supplied material.

RULES:
- Cite ONLY the authority nodes supplied. Every legal proposition must cite
  the node_id(s) it rests on. Never invent a rule, citation, or node_id.
- If no supplied authority is genuinely applicable to an issue, say so
  plainly (an empty applicable_rules list) rather than forcing a citation.
- our_position / opponent_position / response must be grounded in the
  supplied facts and evidence; never invent a fact.
- conclusion is one of: supported, unresolved, unsupported.
- Analyze exclusively from BSF's defence perspective — never draft the
  claimant's/customer's case as the recommended position.
- overall_posture summarises the case across all issues: strong, moderate,
  weak, or unresolved.

Return only JSON.

Schema:
{
  "overall_posture": "strong|moderate|weak|unresolved",
  "executive_summary": "",
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


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _compact_authority_nodes(authority_nodes: list[dict]) -> list[dict]:
    compact = []
    for node in authority_nodes or []:
        node = node or {}
        compact.append({
            "node_id": str(node.get("node_id", "")),
            "heading_path": _text(node.get("heading_path", ""), 200),
            "text": _text(node.get("canonical_text", "") or node.get("text", ""), 900),
            "source_url": str(node.get("source_url", "") or ""),
            "language": str(node.get("language", "") or ""),
        })
    return compact


def _compact_issues(issues: list[dict]) -> list[dict]:
    compact = []
    for issue in issues or []:
        issue = issue or {}
        compact.append({
            "issue_id": str(issue.get("issue_id", "") or issue.get("issue_candidate_id", "")),
            "issue_title": _text(issue.get("issue_title", ""), 200),
            "issue_description": _text(issue.get("issue_description", ""), 600),
            "priority": str(issue.get("priority", "") or ""),
        })
    return compact


def _compact_facts(facts: list[dict]) -> list[dict]:
    compact = []
    for fact in facts or []:
        fact = fact or {}
        compact.append({
            "fact_id": str(fact.get("fact_id", "") or fact.get("fact_candidate_id", "")),
            "fact_text": _text(fact.get("fact_text", ""), 400),
            "status": str(fact.get("status", "") or ""),
        })
    return compact


def _compact_evidence(evidence: list[dict]) -> list[dict]:
    compact = []
    for item in evidence or []:
        item = item or {}
        compact.append({
            "evidence_id": str(item.get("evidence_id", "")),
            "title": _text(item.get("title", "") or item.get("evidence_type", ""), 180),
            "status": str(item.get("status", "") or ""),
        })
    return compact


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


def analyse_case(
    case_record: dict,
    facts: list[dict],
    issues: list[dict],
    evidence: list[dict],
    authority_nodes: list[dict],
) -> dict:
    """One case-wide LLM call analysing every identified issue against the
    retrieved knowledge-base authority pool, facts and evidence.

    Returns the JSON the Analysis tab (Legal.js renderAnalysisTab) renders
    directly (overall_posture, knowledge_base_authority_count,
    executive_summary, per-issue cards), and that
    strategy.generate_defence_strategy later consumes unmodified as
    supporting context for the defence plan.
    """
    if not issues:
        raise ValueError("No case issues are available for analysis.")

    compact_authorities = _compact_authority_nodes(authority_nodes)
    payload = {
        "representation_mandate": {
            "represented_party": "Banque Saudi Fransi (BSF) / البنك السعودي الفرنسي",
            "instruction": "Analyze exclusively from BSF's defence perspective.",
        },
        "case": {
            "case_name": (case_record or {}).get("case_name", ""),
            "workflow_type": (case_record or {}).get("workflow_type", ""),
        },
        "issues": _compact_issues(issues),
        "facts": _compact_facts(facts),
        "evidence": _compact_evidence(evidence),
        "authority_nodes": compact_authorities,
    }

    result = complete_json(
        system_prompt=ANALYSIS_PROMPT,
        user_payload=payload,
        llm_id=ANALYSIS_LLM_ID,
        temperature=0.0,
    )

    if not isinstance(result, dict):
        raise RuntimeError(
            f"Legal analysis LLM returned an unexpected result type: {type(result).__name__}"
        )

    result.setdefault("issues", [])
    result.setdefault("overall_posture", "unresolved")
    result.setdefault("executive_summary", "")
    keep_retrieved_rules(result, {node["node_id"] for node in compact_authorities if node["node_id"]})
    # Deterministic, not LLM-reported: the frontend metric must match what
    # was actually supplied, not a number the model might miscount.
    result["knowledge_base_authority_count"] = len(compact_authorities)
    return result