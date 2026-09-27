
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .agreement_retrieval import build_review_units, retrieve_authorities_for_unit
from .context_budget import make_char_chunks, select_with_char_budget
from .agreement_llm import agreement_complete_json
from .config import (
    AGREEMENT_CLAUSE_REVIEW_MAX_WORKERS,
    AGREEMENT_SYNTHESIS_MAX_WORKERS,
)

UNIT_REVIEW_PROMPT = """
Review one consolidated agreement clause from the represented party's side.
Use only: the supplied consolidated clause context, attorney instructions, and
supplied knowledge-base authorities. Never use general legal knowledge or outside
law. Commercial/textual findings may come from contract wording. Every legal finding
must cite supplied node_ids. Consider all related clauses, definitions, exceptions,
carve-outs, schedules, and missing dependencies before concluding. If a dependency
is missing, mark the review provisional. Return JSON only:
{
 "clause_id":"", "clause_number":"", "heading":"",
 "risk_level":"low|medium|high|critical",
 "review_status":"final|provisional",
 "commercial_finding_ar":"", "commercial_finding_en":"",
 "legal_finding_ar":"", "legal_finding_en":"",
 "authority_node_ids":[], "support_status":"supported|unsupported|not_legal",
 "weaknesses":[], "affected_related_clause_ids":[], "missing_dependencies":[],
 "recommended_change_ar":"", "recommended_change_en":"",
 "proposed_wording_ar":"", "proposed_wording_en":"",
 "client_question_ar":"", "client_question_en":""
}
If no supplied authority supports a legal conclusion, say insufficient applicable
authority was retrieved and do not fill the gap from model memory.
"""

SYNTHESIS_PROMPT = """
Synthesize clause reviews into a concise package-level contract review. Use only the
supplied clause reviews and package map. Do not add new legal propositions. Deduplicate
repeated risks and recommendations. Return JSON only:
{
 "executive_summary_ar":"", "executive_summary_en":"",
 "critical_points":[], "missing_protections":[], "cross_clause_conflicts":[],
 "clause_reviews":[],
 "negotiation_position":{"non_negotiable":[],"high_priority":[],
 "negotiable":[],"fallback_positions":[],"client_questions":[]},
 "provisional_items":[]
}
"""


def _clean_authority_ids(review: dict, allowed: set[str]) -> None:
    ids = []
    for node_id in review.get("authority_node_ids", []) or []:
        value = str(node_id or "").strip()
        if value in allowed and value not in ids:
            ids.append(value)
    review["authority_node_ids"] = ids
    if review.get("support_status") == "supported" and not ids:
        review["support_status"] = "unsupported"
        review["legal_finding_ar"] = "لم يتم استرجاع سند نظامي كافٍ من قاعدة المعرفة لهذه النتيجة."
        review["legal_finding_en"] = "Insufficient applicable authority was retrieved from the knowledge base for this conclusion."


def review_large_agreement(
    clause_map: dict,
    confirmed_profile: dict,
    instructions: str = "",
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> tuple[dict, list[dict]]:
    units = build_review_units(clause_map)
    if not units:
        raise ValueError("The consolidated agreement map contains no reviewable clauses.")

    def review_one(index: int, unit: dict) -> tuple[int, dict, list[dict]]:
        authorities = retrieve_authorities_for_unit(unit, confirmed_profile)
        context = {
            "confirmed_profile": confirmed_profile,
            "attorney_instructions": instructions,
            "clause_context": unit,
            "knowledge_base_authorities": select_with_char_budget(
                authorities, max_chars=29400
            ),
        }
        clause_id = str(unit.get("target_clause", {}).get("clause_id", ""))
        review = agreement_complete_json(
            UNIT_REVIEW_PROMPT,
            context,
            operation=f"agreement clause review {clause_id or index}",
        )
        allowed = {str(x.get("node_id", "") or "") for x in authorities}
        _clean_authority_ids(review, allowed)
        review["_order"] = index
        return index, review, authorities

    reviews: list[dict] = []
    all_authorities: dict[str, dict] = {}
    workers = max(1, min(int(AGREEMENT_CLAUSE_REVIEW_MAX_WORKERS or 1), len(units)))
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(review_one, index, unit): (index, unit) for index, unit in enumerate(units, start=1)}
        for future in as_completed(futures):
            index, review, authorities = future.result()
            reviews.append(review)
            for node in authorities:
                node_id = str(node.get("node_id", "") or "").strip()
                if node_id:
                    all_authorities[node_id] = node
            completed += 1
            if progress_callback:
                progress_callback(completed, len(units), str(review.get("clause_id", "")))

    reviews.sort(key=lambda item: int(item.pop("_order", 0) or 0))

    review_groups = make_char_chunks(reviews, target_chars=25200, hard_limit_chars=32200)

    def synthesize_group(index: int, group: list[dict]) -> tuple[int, dict]:
        partial = agreement_complete_json(
            SYNTHESIS_PROMPT,
            {
                "package_map": {"package_summary": clause_map.get("package_summary", "")},
                "clause_reviews": group,
            },
            operation=f"agreement review synthesis group {index}",
        )
        return index, partial

    partials: list[tuple[int, dict]] = []
    synth_workers = max(1, min(int(AGREEMENT_SYNTHESIS_MAX_WORKERS or 1), len(review_groups)))
    with ThreadPoolExecutor(max_workers=synth_workers) as executor:
        futures = {executor.submit(synthesize_group, index, group): index for index, group in enumerate(review_groups, start=1)}
        for future in as_completed(futures):
            partials.append(future.result())
    partials.sort(key=lambda item: item[0])
    compact_partials = [item[1] for item in partials]

    # The final request uses partial summaries only. Sending all clause reviews again
    # caused oversized/truncated JSON responses in large packages.
    final = agreement_complete_json(
        SYNTHESIS_PROMPT,
        {
            "package_map": {
                "contract_overview": clause_map.get("contract_overview", {}),
                "package_summary": clause_map.get("package_summary", ""),
                "missing_dependencies": clause_map.get("missing_dependencies", []),
                "cross_document_conflicts": clause_map.get("cross_document_conflicts", []),
            },
            "partial_summaries": compact_partials,
            "instruction": "Merge the partial summaries. Do not repeat every clause review.",
        },
        operation="final agreement review synthesis",
    )
    final["clause_reviews"] = reviews
    return final, list(all_authorities.values())

