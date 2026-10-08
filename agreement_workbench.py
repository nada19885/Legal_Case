from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any, Callable

import pandas as pd

from .agreement_analysis import review_large_agreement
from .agreement_consolidation import consolidate_page_structures
from .agreement_page_extraction import normalize_pages, structure_agreement_pages
from .agreement_llm import agreement_complete_json
from .storage import append_rows, case_rows

AGREEMENT_TYPES = [
    "nda", "banking_agreement", "vendor_agreement", "customer_agreement",
    "employment_agreement", "consultancy_agreement", "outsourcing_agreement",
    "data_processing_agreement", "software_licence_agreement",
    "procurement_agreement", "partnership_agreement", "other_agreement",
]

RELATIONSHIP_TYPES = [
    "bank_financial_institution", "bank_vendor", "bank_customer",
    "financial_institution_technology_provider", "institution_service_provider",
    "employer_employee", "company_consultant", "supplier_customer",
    "institution_institution", "other_relationship",
]

CLASSIFICATION_PROMPT = """
You classify agreement packages. Use only the supplied compact page material.
Do not infer facts that are not present. The package may contain a master agreement,
NDA, schedules, annexes, amendments, service levels, or other related documents.
Return JSON only with:
{
  "agreement_type": one allowed agreement type,
  "relationship_type": one allowed relationship type,
  "represented_party_guess": string,
  "counterparty_guess": string,
  "document_title": string,
  "package_document_types": [strings],
  "confidence": number from 0 to 1,
  "reasons": [short strings],
  "uncertainties": [short strings]
}
Allowed agreement types: nda, banking_agreement, vendor_agreement,
customer_agreement, employment_agreement, consultancy_agreement,
outsourcing_agreement, data_processing_agreement, software_licence_agreement,
procurement_agreement, partnership_agreement, other_agreement.
Allowed relationships: bank_financial_institution, bank_vendor, bank_customer,
financial_institution_technology_provider, institution_service_provider,
employer_employee, company_consultant, supplier_customer,
institution_institution, other_relationship.
"""

AGREEMENT_STATE_DATASET = "agreement_workflow_state"


def _records(frame: Any, limit: int = 10000) -> list[dict]:
    if isinstance(frame, pd.DataFrame):
        return frame.head(limit).fillna("").to_dict("records")
    if isinstance(frame, list):
        return frame[:limit]
    return []


def _compact_classification_material(pages: Any, max_pages: int = 80) -> list[dict]:
    normalized = normalize_pages(pages)
    if not normalized:
        return []
    # For large packages, sample beginning/end and use stored page summaries in between.
    if len(normalized) <= max_pages:
        selected = normalized
    else:
        head = normalized[:30]
        tail = normalized[-20:]
        step = max(1, (len(normalized) - 50) // 30)
        middle = normalized[30:-20:step][:30]
        seen = set()
        selected = []
        for item in head + middle + tail:
            key = item["page_id"]
            if key not in seen:
                seen.add(key)
                selected.append(item)
    return [{
        "page_id": p["page_id"],
        "document_id": p["document_id"],
        "page_number": p["page_number"],
        "text": (p.get("page_summary") or p.get("page_text", ""))[:3500],
    } for p in selected]


def classify_agreement(pages: Any) -> dict:
    material = _compact_classification_material(pages)
    if not material:
        raise ValueError("No usable extracted agreement text is available.")
    result = agreement_complete_json(
        CLASSIFICATION_PROMPT,
        {"sampled_package_pages": material},
        temperature=0.0,
        operation="agreement classification",
    )
    if result.get("agreement_type") not in AGREEMENT_TYPES:
        result["agreement_type"] = "other_agreement"
    if result.get("relationship_type") not in RELATIONSHIP_TYPES:
        result["relationship_type"] = "other_relationship"
    result["classification_method"] = "token_bounded_package_sampling"
    result["sampled_page_count"] = len(material)
    return result


def extract_clause_map(
    pages: Any,
    confirmed_profile: dict,
    page_progress_callback: Callable[[int, int, str], None] | None = None,
    chunk_progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict:
    """Page-by-page extraction followed by hierarchical contract-wide consolidation."""
    page_structures = structure_agreement_pages(pages, page_progress_callback)
    chunk_maps, clause_map = consolidate_page_structures(
        page_structures,
        confirmed_profile,
        chunk_progress_callback,
    )
    # Persist only the compact package map. Raw OCR pages already remain in the
    # page dataset, and clause records preserve page/fragment traceability. Keeping
    # intermediate page/chunk payloads out of session state avoids oversized rows.
    return {
        **clause_map,
        "processing_metadata": {
            "page_structure_count": len(page_structures),
            "chunk_count": len(chunk_maps),
            "method": "page_by_page_then_hierarchical_consolidation",
        },
    }


def retrieve_agreement_authorities(
    clause_map: dict,
    confirmed_profile: dict,
    limit_per_query: int = 5,
) -> list[dict]:
    # Compatibility helper. The final review retrieves laws per consolidated clause.
    review, authorities = review_large_agreement(
        clause_map,
        confirmed_profile,
        instructions="Authority retrieval only; do not alter attorney instructions.",
    )
    return authorities


def review_agreement(
    clause_map: dict,
    confirmed_profile: dict,
    authority_nodes: list[dict] | None = None,
    instructions: str = "",
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict:
    # authority_nodes is accepted for backward compatibility. Retrieval is intentionally
    # re-run per clause to ensure each legal answer receives only relevant KB material.
    result, retrieved = review_large_agreement(
        clause_map,
        confirmed_profile,
        instructions=instructions,
        progress_callback=progress_callback,
    )
    result["retrieved_authority_nodes"] = retrieved
    result["source_policy"] = "case_contract_and_retrieved_knowledge_base_only"
    return result


def run_agreement_review(
    clause_map: dict,
    confirmed_profile: dict,
    instructions: str = "",
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> tuple[dict, list[dict]]:
    return review_large_agreement(
        clause_map,
        confirmed_profile,
        instructions=instructions,
        progress_callback=progress_callback,
    )


def save_agreement_state(case_id: str, state_type: str, payload: dict, actor: str = "") -> None:
    append_rows(AGREEMENT_STATE_DATASET, [{
        "agreement_state_id": f"AGR-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "case_id": case_id,
        "state_type": state_type,
        "payload_json": json.dumps(payload, ensure_ascii=False, default=str),
        "actor": actor,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }])


def load_agreement_states(case_id: str) -> dict[str, dict]:
    frame = case_rows(AGREEMENT_STATE_DATASET, case_id)
    if frame.empty or "state_type" not in frame.columns:
        return {}
    if "created_at" in frame.columns:
        frame = frame.sort_values("created_at")
    result = {}
    for _, row in frame.iterrows():
        try:
            payload = json.loads(str(row.get("payload_json", "{}") or "{}"))
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            result[str(row.get("state_type", ""))] = payload
    return result

AGREEMENT_DISCUSSION_PROMPT = """
You are a grounded agreement-review assistant. Answer only from:
1. the confirmed agreement profile;
2. the consolidated clause map;
3. the completed clause reviews;
4. the supplied knowledge-base authority nodes.
Do not use general legal knowledge, model memory, or outside law. Every legal
statement must cite supplied authority node_ids. Every contract statement must cite
supplied clause_ids and, when available, source_page_ids. If support is insufficient,
say so clearly. Return JSON only:
{
  "answer_ar":"", "answer_en":"",
  "clause_ids":[], "source_page_ids":[], "authority_node_ids":[],
  "support_status":"supported|partial|insufficient",
  "proposed_change_ar":"", "proposed_change_en":""
}
"""


# The discussion request used to carry every clause, every clause review and
# every retrieved authority in full (172,000 characters for a 2-page
# contract), which the model endpoint refused at once ("The LLM request
# failed."). It now carries what the question needs, within these limits.
DISCUSSION_CLAUSE_CHARS = 9000
DISCUSSION_REVIEW_CHARS = 8000
DISCUSSION_AUTHORITY_CHARS = 7000
_DISCUSSION_WORD = re.compile(r"\w{3,}")


def _discussion_words(value) -> set:
    return {word.lower() for word in _DISCUSSION_WORD.findall(str(value or ""))}


def _within(items: list, limit: int) -> list:
    out, used = [], 0
    for item in items:
        size = len(json.dumps(item, ensure_ascii=False, default=str))
        if out and used + size > limit:
            continue
        out.append(item)
        used += size
    return out


def discussion_material(question, clause_map, review, authority_nodes) -> dict:
    """The clauses, clause reviews and authorities sent with one question:
    those closest to the question first (clauses it names, then shared
    words), cut to short text, within the character limits above."""
    words = _discussion_words(question)
    asked = str(question or "")

    def score(*texts) -> int:
        return len(words & set().union(*(_discussion_words(t) for t in texts)))

    clauses = [c for c in (clause_map or {}).get("clauses", []) or [] if isinstance(c, dict)]
    def clause_rank(item):
        index, clause = item
        named = any(str(clause.get(k) or "") and str(clause.get(k)) in asked for k in ("clause_id", "clause_number"))
        return (-int(named), -score(clause.get("heading"), clause.get("full_text")), index)
    ordered = [c for _, c in sorted(enumerate(clauses), key=clause_rank)]
    picked_clauses = _within([{
        "clause_id": c.get("clause_id", ""), "clause_number": c.get("clause_number", ""),
        "heading": c.get("heading", ""), "category": c.get("category", ""),
        "full_text": str(c.get("full_text", "") or "")[:1500],
        "source_page_ids": c.get("source_page_ids", []) or [],
    } for c in ordered], DISCUSSION_CLAUSE_CHARS)

    position = {c["clause_id"]: n for n, c in enumerate(ordered)}
    reviews = [r for r in (review or {}).get("clause_reviews", []) or [] if isinstance(r, dict)]
    reviews.sort(key=lambda r: position.get(str(r.get("clause_id", "")), len(position)))
    keep = ("clause_id", "risk_level", "review_status", "support_status", "authority_node_ids")
    texts = ("commercial_finding_ar", "commercial_finding_en", "legal_finding_ar", "legal_finding_en",
             "recommended_change_ar", "recommended_change_en")
    picked_reviews = _within([
        {**{k: r.get(k) for k in keep if r.get(k)}, **{k: str(r.get(k))[:400] for k in texts if r.get(k)}}
        for r in reviews], DISCUSSION_REVIEW_CHARS)

    cited = {str(i) for r in picked_reviews for i in r.get("authority_node_ids") or []}
    nodes = [n for n in authority_nodes or [] if isinstance(n, dict) and n.get("node_id")]
    nodes.sort(key=lambda n: (str(n.get("node_id")) not in cited,
                              -score(n.get("heading_path"), n.get("canonical_text") or n.get("text"))))
    seen, unique = set(), []
    for node in nodes:
        if str(node["node_id"]) not in seen:
            seen.add(str(node["node_id"]))
            unique.append({"node_id": str(node["node_id"]), "heading_path": str(node.get("heading_path", "") or "")[:200],
                           "text": str(node.get("canonical_text") or node.get("text") or "")[:700],
                           "source_url": str(node.get("source_url", "") or "")})
    return {"clauses": picked_clauses, "clause_reviews": picked_reviews,
            "knowledge_base_authorities": _within(unique, DISCUSSION_AUTHORITY_CHARS)}


def discuss_agreement(
    question: str,
    confirmed_profile: dict,
    clause_map: dict,
    review: dict,
    authority_nodes: list[dict] | None = None,
) -> dict:
    """Answer an agreement question using the same dedicated Qwen model.

    The answer is grounded in stored agreement material and validated against the
    clause, page, and authority identifiers supplied to the model.
    """
    material = discussion_material(question, clause_map, review, authority_nodes)
    authorities = material["knowledge_base_authorities"]
    result = agreement_complete_json(
        AGREEMENT_DISCUSSION_PROMPT,
        {
            "question": str(question or "").strip(),
            "confirmed_profile": confirmed_profile or {},
            "contract_overview": (clause_map or {}).get("contract_overview", {}),
            "package_summary": (clause_map or {}).get("package_summary", ""),
            "clauses": material["clauses"],
            "dependency_graph": ((clause_map or {}).get("dependency_graph", []) or [])[:60],
            "missing_dependencies": ((clause_map or {}).get("missing_dependencies", []) or [])[:30],
            "clause_reviews": material["clause_reviews"],
            "knowledge_base_authorities": authorities,
        },
        operation="agreement discussion",
    )

    allowed_clauses = {
        str(item.get("clause_id", "") or "")
        for item in (clause_map or {}).get("clauses", []) or []
    }
    allowed_pages = {
        str(page_id)
        for item in (clause_map or {}).get("clauses", []) or []
        for page_id in item.get("source_page_ids", []) or []
    }
    allowed_authorities = {
        str(item.get("node_id", "") or "") for item in authorities
    }

    def clean(values, allowed):
        output = []
        for value in values or []:
            value = str(value or "").strip()
            if value and value in allowed and value not in output:
                output.append(value)
        return output

    result["clause_ids"] = clean(result.get("clause_ids"), allowed_clauses)
    result["source_page_ids"] = clean(result.get("source_page_ids"), allowed_pages)
    result["authority_node_ids"] = clean(result.get("authority_node_ids"), allowed_authorities)

    legal_text = " ".join([
        str(result.get("answer_ar", "")), str(result.get("answer_en", "")),
        str(result.get("proposed_change_ar", "")), str(result.get("proposed_change_en", "")),
    ]).strip()
    if legal_text and not result["authority_node_ids"]:
        result["support_status"] = "partial"
    return result
