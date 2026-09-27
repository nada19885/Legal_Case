from __future__ import annotations

import json
from datetime import date
from typing import Any

from .completeness import (
    build_case_state,
    format_interviewer_reply,
)
from .models import MatterFilters
from .review_pipeline import assess_case_completeness_multi_request
from .research_package import research_approved_issues
from .case_analysis import analyse_case
from .strategy import generate_defence_strategy
from .financial_classification import classify_case_pages
from .config import (
    COMPLETENESS_MAX_PAGE_SUMMARIES,
    COMPLETENESS_MAX_LATEST_PAGE_SUMMARIES,
    COMPLETENESS_MAX_SUMMARY_CHARS,
    COMPLETENESS_MAX_PARTIES,
    COMPLETENESS_MAX_FACTS,
    COMPLETENESS_MAX_ISSUES,
    COMPLETENESS_MAX_EVENTS,
    COMPLETENESS_MAX_EVIDENCE,
    COMPLETENESS_MAX_DOCUMENTS,
    COMPLETENESS_MAX_MESSAGES,
    COMPLETENESS_MAX_MESSAGE_CHARS,
    COMPLETENESS_MAX_LEGAL_RESEARCH,
    COMPLETENESS_MAX_TOTAL_CHARS,
)

USABLE_PAGE_STATUSES = {"completed", "completed_review_required"}

# These keys must never enter completeness/review prompts.
FORBIDDEN_TEXT_KEYS = {
    "page_text",
    "document_text",
    "full_text",
    "extracted_text",
    "transcription",
    "raw_content",
    "content_base64",
    "image_base64",
    "conversation_history",
}


def _records(value: Any) -> list[dict]:
    if value is None:
        return []
    if hasattr(value, "to_dict"):
        try:
            return value.fillna("").to_dict(orient="records")
        except (TypeError, AttributeError):
            try:
                return value.to_dict(orient="records")
            except TypeError:
                pass
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _text(value: Any, limit: int) -> str:
    result = str(value or "").strip()
    if len(result) <= limit:
        return result
    return result[:limit].rstrip() + "…"


def _json_list(value: Any, limit: int = 8) -> list:
    if isinstance(value, list):
        return value[:limit]
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        return []
    return parsed[:limit] if isinstance(parsed, list) else []


def _pick(record: dict, names: tuple[str, ...], default: Any = "") -> Any:
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return default


def _compact_pages(pages: Any, max_pages: int | None = None) -> list[dict]:
    output: list[dict] = []
    records = sorted(
        _records(pages),
        key=lambda row: (
            str(row.get("case_document_id", "")),
            int(row.get("page_number", 0) or 0),
        ),
    )
    for page in records:
        status = str(page.get("processing_status", "") or "").strip().lower()
        if status not in USABLE_PAGE_STATUSES:
            continue

        summary = _text(page.get("page_summary", ""), COMPLETENESS_MAX_SUMMARY_CHARS)
        if not summary:
            # Never use the full transcription. A short deterministic fallback
            # assembled from already-extracted structured fields is acceptable.
            fragments = []
            for key in (
                "claims_json",
                "facts_json",
                "evidence_items_json",
                "legal_references_json",
            ):
                fragments.extend(str(item) for item in _json_list(page.get(key), 4))
            summary = _text("; ".join(fragments), COMPLETENESS_MAX_SUMMARY_CHARS)
        if not summary:
            continue

        output.append({
            "page_id": str(page.get("page_id", "") or ""),
            "case_document_id": str(page.get("case_document_id", "") or ""),
            "page_number": page.get("page_number", ""),
            "document_type": _text(page.get("document_type", ""), 120),
            "document_language": _text(page.get("document_language", ""), 30),
            "page_summary": summary,
            "parties": _json_list(page.get("parties_json"), 8),
            "dates": _json_list(page.get("dates_json"), 8),
            "amounts": _json_list(page.get("amounts_json"), 8),
            "case_numbers": _json_list(page.get("case_numbers_json"), 8),
            "claims": _json_list(page.get("claims_json"), 6),
            "facts": _json_list(page.get("facts_json"), 8),
            "legal_references": _json_list(page.get("legal_references_json"), 6),
            "evidence_items": _json_list(page.get("evidence_items_json"), 6),
            "signatures_or_stamps": _json_list(page.get("signatures_or_stamps_json"), 4),
            "processing_status": status,
        })
    return output if max_pages is None else output[-max_pages:]


def _compact_messages(messages: Any) -> list[dict]:
    output = []
    for row in _records(messages):
        output.append({
            "message_id": str(row.get("message_id", "") or ""),
            "role": _text(row.get("role", ""), 30),
            "message_text": _text(
                _pick(row, ("message_text", "content", "text")),
                COMPLETENESS_MAX_MESSAGE_CHARS,
            ),
            "created_at": str(row.get("created_at", "") or ""),
        })
    return output


def _compact_documents(documents: Any) -> list[dict]:
    output = []
    for row in _records(documents):
        output.append({
            "case_document_id": str(row.get("case_document_id", "") or ""),
            "filename": _text(_pick(row, ("filename", "file_name", "name")), 220),
            "document_type": _text(row.get("document_type", ""), 100),
            "processing_status": _text(row.get("processing_status", ""), 60),
            "page_count": row.get("page_count", ""),
            "created_at": str(row.get("created_at", "") or ""),
        })
    return output


def _compact_parties(parties: Any) -> list[dict]:
    output = []
    for row in _records(parties):
        output.append({
            "party_id": str(row.get("party_id", "") or ""),
            "name": _text(_pick(row, ("party_name", "name")), 180),
            "role": _text(_pick(row, ("party_role", "role")), 100),
            "party_type": _text(row.get("party_type", ""), 80),
            "source_page_id": str(row.get("source_page_id", "") or ""),
        })
    return output


def _compact_facts(rows: Any) -> list[dict]:
    output = []
    for row in _records(rows):
        output.append({
            "fact_id": str(_pick(row, ("fact_id", "fact_candidate_id"))),
            "fact": _text(
                _pick(row, ("fact_text", "description", "fact", "statement")),
                500,
            ),
            "status": _text(row.get("status", ""), 60),
            "source_page_id": str(row.get("source_page_id", "") or ""),
        })
    return output


def _compact_issues(rows: Any) -> list[dict]:
    output = []
    for row in _records(rows):
        output.append({
            "issue_id": str(_pick(row, ("issue_id", "issue_candidate_id"))),
            "issue": _text(
                _pick(row, ("issue_text", "description", "issue", "title")),
                500,
            ),
            "status": _text(row.get("status", ""), 60),
            "source_page_id": str(row.get("source_page_id", "") or ""),
        })
    return output


def _compact_evidence(rows: Any) -> list[dict]:
    output = []
    for row in _records(rows):
        output.append({
            "evidence_id": str(row.get("evidence_id", "") or ""),
            "title": _text(_pick(row, ("title", "name", "evidence_name")), 180),
            "evidence_type": _text(_pick(row, ("evidence_type", "type")), 100),
            "description": _text(row.get("description", ""), 400),
            "status": _text(row.get("status", ""), 60),
            "source_page_id": str(row.get("source_page_id", "") or ""),
        })
    return output


def _compact_research(rows: Any) -> list[dict]:
    output = []
    for row in _records(rows):
        output.append({
            "authority_id": str(_pick(row, ("authority_id", "node_id", "id"))),
            "title": _text(_pick(row, ("title", "heading", "name")), 180),
            "citation": _text(_pick(row, ("citation", "reference")), 180),
            "summary": _text(_pick(row, ("summary", "text", "content")), 500),
        })
    return output


def _compact_case_record(case_record: Any) -> dict:
    row = case_record if isinstance(case_record, dict) else {}
    allowed = (
        "case_id", "case_name", "case_status", "status", "case_type",
        "jurisdiction", "preferred_language", "matter_date", "customer_type",
        "regulated_entity_type", "product_type", "intake_mode",
    )
    result = {}
    for key in allowed:
        if key in row:
            result[key] = _text(row.get(key), 250)
    return result


def _sanitize_state(value: Any, key: str = "") -> Any:
    """Remove hidden large text fields introduced by build_case_state()."""
    if key.lower() in FORBIDDEN_TEXT_KEYS:
        return None
    if isinstance(value, dict):
        output = {}
        for child_key, child_value in value.items():
            if str(child_key).lower() in FORBIDDEN_TEXT_KEYS:
                continue
            clean = _sanitize_state(child_value, str(child_key))
            if clean is not None:
                output[child_key] = clean
        return output
    if isinstance(value, list):
        return [_sanitize_state(item, key) for item in value]
    if isinstance(value, str):
        # Individual strings in review state should never be enormous.
        return _text(value, 1500)
    return value


def _json_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":")))


def _enforce_state_limit(state: dict, max_chars: int) -> dict:
    """Trim lower-priority lists until the complete review state is bounded."""
    if _json_chars(state) <= max_chars:
        return state

    # Common locations used by completeness.build_case_state().
    paths = [
        ("recent_messages",),
        ("messages",),
        ("latest_document_pages",),
        ("document_pages",),
        ("pages",),
        ("legal_research",),
        ("evidence",),
        ("events",),
        ("fact_candidates",),
        ("approved_facts",),
        ("issue_candidates",),
        ("approved_issues",),
    ]

    def get_list(container: dict, path: tuple[str, ...]):
        current: Any = container
        for part in path[:-1]:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        if isinstance(current, dict) and isinstance(current.get(path[-1]), list):
            return current[path[-1]]
        return None

    while _json_chars(state) > max_chars:
        changed = False
        for path in paths:
            items = get_list(state, path)
            if items:
                items.pop(0)
                changed = True
                break
        if not changed:
            break
    return state


def assess_next_step(
    case_record,
    messages,
    documents,
    pages,
    facts,
    fact_candidates,
    parties,
    issues,
    issue_candidates,
    evidence,
    legal_research=None,
    previous_state=None,
    latest_documents=None,
    latest_pages=None,
):
    compact_pages = _compact_pages(pages, None)
    compact_latest_pages = _compact_pages(
        latest_pages or [],
        None,
    )
    compact_messages = _compact_messages(messages)

    # Prefer approved records; retain candidates separately because the
    # completeness reviewer may need to ask for validation or missing proof.
    compact_facts = _compact_facts(facts)
    compact_fact_candidates = _compact_facts(fact_candidates)
    compact_issues = _compact_issues(issues)
    compact_issue_candidates = _compact_issues(issue_candidates)

    print(
        "[completeness compact input] pages={} latest_pages={} messages={} "
        "facts={} fact_candidates={} issues={} issue_candidates={} "
        "full_page_text_sent=false".format(
            len(compact_pages),
            len(compact_latest_pages),
            len(compact_messages),
            len(compact_facts),
            len(compact_fact_candidates),
            len(compact_issues),
            len(compact_issue_candidates),
        )
    )

    state = build_case_state(
        case_record=_compact_case_record(case_record),
        messages=compact_messages,
        document_pages=compact_pages,
        documents=_compact_documents(documents),
        approved_facts=compact_facts,
        fact_candidates=compact_fact_candidates,
        parties=_compact_parties(parties),
        approved_issues=compact_issues,
        issue_candidates=compact_issue_candidates,
        evidence=_compact_evidence(evidence),
        legal_research=_compact_research(legal_research or []),
        previous_interview_state=_sanitize_state(previous_state or {}),
        latest_documents=_compact_documents(latest_documents or []),
        latest_document_pages=compact_latest_pages,
    )

    state = _sanitize_state(state)
    state_chars = _json_chars(state)

    print(
        "[automatic completeness multi-request] total_payload_chars={} "
        "full_compact_state_preserved=true full_page_text_sent=false".format(
            state_chars,
        )
    )

    decision = assess_case_completeness_multi_request(state)
    return {
        "decision": decision,
        "reply": format_interviewer_reply(decision),
    }


def run_legal_analysis(case_record, facts, issues, evidence, actor=""):
    case_id = str(case_record.get("case_id", ""))
    matter_date = _parse_date(case_record.get("matter_date"))
    filters = MatterFilters(
        language=case_record.get("preferred_language", "ar") or "ar",
        matter_date=matter_date,
        customer_type=case_record.get("customer_type") or None,
        regulated_entity_type=case_record.get("regulated_entity_type") or None,
        product_type=case_record.get("product_type") or None,
        current_only=not bool(matter_date),
    )
    research = research_approved_issues(
        case_id=case_id,
        issues=_records(issues),
        filters=filters,
        created_by=actor,
    )
    analysis = analyse_case(
        case_record=case_record,
        facts=_records(facts),
        issues=_records(issues),
        evidence=_records(evidence),
        authority_nodes=research["authority_nodes"],
    )
    return {"research": research, "analysis": analysis}


def run_defence_plan(case_record, analysis, facts, evidence, authority_nodes):
    return generate_defence_strategy(
        case_record=case_record,
        analysis=analysis,
        facts=_records(facts),
        evidence=_records(evidence),
        authority_nodes=_records(authority_nodes),
    )


def run_accounting_classification(case_id: str, page_ids: list[str], actor: str = ""):
    return classify_case_pages(case_id, page_ids, actor=actor)
