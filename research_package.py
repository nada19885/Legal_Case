from __future__ import annotations
from datetime import datetime, timezone
import json

from .ids import random_id
from .models import MatterFilters
from .retrieval import research_issue
from .storage import append_rows
from .config import RESEARCH_PACKAGES_DATASET

def research_approved_issues(
    case_id: str,
    issues: list[dict],
    filters: MatterFilters,
    created_by: str = "",
) -> dict:
    run_id = random_id("RUN")
    issue_results = []
    all_nodes = {}

    for issue in issues:
        issue_id = str(issue.get("issue_id", ""))
        questions = []

        legal_question = str(issue.get("legal_question", "")).strip()
        if legal_question:
            questions.append(legal_question)

        try:
            extra = json.loads(issue.get("targeted_questions_json", "[]"))
            if isinstance(extra, list):
                questions.extend(str(q) for q in extra if str(q).strip())
        except Exception:
            pass

        if not questions:
            questions.append(
                "{}: {}".format(
                    issue.get("issue_title", ""),
                    issue.get("issue_description", ""),
                )
            )

        question_results = []
        for index, question in enumerate(dict.fromkeys(questions), start=1):
            result = research_issue(
                query=question,
                filters=filters,
                research_run_id=run_id,
                case_id=case_id,
                issue_id=issue_id,
                question_id="Q{}".format(index),
                created_by=created_by,
                persist_log=True,
            )
            question_results.append(result)
            for node in result.get("expanded_nodes", []):
                node_id = str(node.get("node_id", ""))
                if node_id:
                    all_nodes[node_id] = node

        issue_results.append({
            "issue_id": issue_id,
            "issue_title": issue.get("issue_title", ""),
            "questions": questions,
            "results": question_results,
        })

    package = {
        "research_package_id": random_id("RPKG"),
        "research_run_id": run_id,
        "case_id": case_id,
        "issue_id": "",
        "targeted_questions_json": json.dumps(
            [q for item in issue_results for q in item["questions"]],
            ensure_ascii=False,
        ),
        "authority_node_ids_json": json.dumps(list(all_nodes.keys()), ensure_ascii=False),
        "definitions_node_ids_json": "[]",
        "exceptions_node_ids_json": "[]",
        "amendments_node_ids_json": "[]",
        "procedural_node_ids_json": "[]",
        "quotation_candidates_json": json.dumps(
            [
                {
                    "node_id": node_id,
                    "heading_path": node.get("heading_path", ""),
                    "text": node.get("canonical_text", ""),
                    "source_url": node.get("source_url", ""),
                }
                for node_id, node in all_nodes.items()
            ],
            ensure_ascii=False,
        ),
        "research_gaps_json": "[]",
        "arabic_source_available": str(
            any(str(n.get("language", "")).lower() == "ar" for n in all_nodes.values())
        ).lower(),
        "date_checked": str(bool(filters.matter_date)).lower(),
        "customer_type_checked": str(bool(filters.customer_type)).lower(),
        "authority_status": "candidate",
        "review_status": "not_reviewed",
        "approved_by": "",
        "approved_at": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    append_rows(RESEARCH_PACKAGES_DATASET, [package])

    return {
        "run_id": run_id,
        "package": package,
        "issue_results": issue_results,
        "authority_nodes": list(all_nodes.values()),
    }
