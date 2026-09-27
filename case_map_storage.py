from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re

from .ids import random_id
from .storage import append_rows, case_rows
from .config import (
    CASE_PARTIES_DATASET,
    CASE_EVENTS_DATASET,
    FACT_CANDIDATES_DATASET,
    ISSUE_CANDIDATES_DATASET,
    EVIDENCE_DATASET,
    CASE_CONTRADICTIONS_DATASET,  
)
from .audit import audit


def _now():
    return datetime.now(timezone.utc).isoformat()


def _normalise(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _signature(kind, *values):
    raw = "|".join([_normalise(kind)] + [_normalise(v) for v in values])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _existing(dataset_name, case_id, builder):
    df = case_rows(dataset_name, case_id)
    if df.empty:
        return set()
    return {
        builder(row)
        for row in df.to_dict(orient="records")
    }


def persist_case_map(case_id: str, case_map: dict, actor: str = "") -> dict:
    """
    Merge a full rebuilt case map into append-only CSV datasets.
    Existing candidates are skipped by normalised content signature.
    """
    counts = {
    "parties": 0,
    "events": 0,
    "facts": 0,
    "issues": 0,
    "evidence_requests": 0,
    "contradictions": 0,         
    "duplicates_skipped": 0,
}

    # Parties
    existing = _existing(
        CASE_PARTIES_DATASET,
        case_id,
        lambda r: _signature(
            "party",
            r.get("party_name", ""),
            r.get("party_type", ""),
            r.get("role_in_case", ""),
        ),
    )
    rows = []
    for item in case_map.get("parties", []):
        sig = _signature(
            "party",
            item.get("name", ""),
            item.get("party_type", ""),
            item.get("role_in_case", ""),
        )
        if sig in existing:
            counts["duplicates_skipped"] += 1
            continue
        existing.add(sig)
        rows.append({
            "party_id": random_id("PARTY"),
            "case_id": case_id,
            "party_name": item.get("name", ""),
            "party_type": item.get("party_type", ""),
            "role_in_case": item.get("role_in_case", ""),
            "identifier": "",
            "contact_details_json": "{}",
            "review_status": "candidate",
            "created_at": _now(),
            "created_by": actor,
        })
    append_rows(CASE_PARTIES_DATASET, rows)
    counts["parties"] = len(rows)

    # Events
    existing = _existing(
        CASE_EVENTS_DATASET,
        case_id,
        lambda r: _signature(
            "event",
            r.get("event_date", ""),
            r.get("event_type", ""),
            r.get("event_description", ""),
        ),
    )
    rows = []
    for item in case_map.get("events", []):
        sig = _signature(
            "event",
            item.get("event_date", ""),
            item.get("event_type", ""),
            item.get("description", ""),
        )
        if sig in existing:
            counts["duplicates_skipped"] += 1
            continue
        existing.add(sig)
        rows.append({
            "event_id": random_id("EVENT"),
            "case_id": case_id,
            "event_date": item.get("event_date", ""),
            "event_type": item.get("event_type", ""),
            "event_description": item.get("description", ""),
            "party_ids_json": json.dumps(item.get("party_names", []), ensure_ascii=False),
            "source_type": "document",
            "source_id": json.dumps(item.get("source_page_ids", []), ensure_ascii=False),
            "review_status": "candidate",
            "created_at": _now(),
            "created_by": actor,
        })
    append_rows(CASE_EVENTS_DATASET, rows)
    counts["events"] = len(rows)

    # Facts
    existing = _existing(
        FACT_CANDIDATES_DATASET,
        case_id,
        lambda r: _signature(
            "fact",
            r.get("fact_text", ""),
            r.get("fact_date", ""),
            r.get("party", ""),
        ),
    )
    rows = []
    for item in case_map.get("facts", []):
        sig = _signature(
            "fact",
            item.get("fact_text", ""),
            item.get("fact_date", ""),
            item.get("party", ""),
        )
        if sig in existing:
            counts["duplicates_skipped"] += 1
            continue
        existing.add(sig)
        rows.append({
            "fact_candidate_id": random_id("FCAND"),
            "case_id": case_id,
            "source_type": "document",
            "case_document_id": "",
            "page_number": "",
            "message_id": "",
            "fact_text": item.get("fact_text", ""),
            "fact_date": item.get("fact_date", ""),
            "party": item.get("party", ""),
            "fact_type": item.get("fact_type", ""),
            "evidence_quote": item.get("evidence_quote", ""),
            "confidence": item.get("confidence", 0.0),
            "candidate_status": item.get("status", "pending"),
            "created_at": _now(),
            "source_page_ids_json": json.dumps(
                item.get("source_page_ids", []),
                ensure_ascii=False,
            ),
        })
    append_rows(FACT_CANDIDATES_DATASET, rows)
    counts["facts"] = len(rows)

    # Issues
    existing = _existing(
        ISSUE_CANDIDATES_DATASET,
        case_id,
        lambda r: _signature(
            "issue",
            r.get("issue_title", ""),
            r.get("issue_description", ""),
        ),
    )
    rows = []
    for item in case_map.get("potential_issues", []):
        sig = _signature(
            "issue",
            item.get("issue_title", ""),
            item.get("issue_description", ""),
        )
        if sig in existing:
            counts["duplicates_skipped"] += 1
            continue
        existing.add(sig)
        rows.append({
            "issue_candidate_id": random_id("ICAND"),
            "case_id": case_id,
            "issue_title": item.get("issue_title", ""),
            "issue_description": item.get("issue_description", ""),
            "targeted_questions_json": json.dumps(
                item.get("targeted_legal_questions", []),
                ensure_ascii=False,
            ),
            "supporting_fact_ids_json": json.dumps(
                item.get("supporting_page_ids", []),
                ensure_ascii=False,
            ),
            "missing_information_json": "[]",
            "priority": item.get("priority", "medium"),
            "candidate_status": "pending",
            "created_at": _now(),
        })
    append_rows(ISSUE_CANDIDATES_DATASET, rows)
    counts["issues"] = len(rows)

    # Evidence requests
    existing = _existing(
        EVIDENCE_DATASET,
        case_id,
        lambda r: _signature(
            "evidence",
            r.get("evidence_type", ""),
            r.get("description", ""),
            r.get("purpose", ""),
        ),
    )
    rows = []
    for item in case_map.get("missing_evidence", []):
        sig = _signature(
            "evidence",
            item.get("evidence_type", ""),
            item.get("description", ""),
            item.get("purpose", ""),
        )
        if sig in existing:
            counts["duplicates_skipped"] += 1
            continue
        existing.add(sig)
        rows.append({
            "evidence_id": random_id("EVID"),
            "case_id": case_id,
            "evidence_title": item.get("evidence_type", "Requested evidence"),
            "evidence_type": item.get("evidence_type", ""),
            "case_document_id": "",
            "page_number": "",
            "message_id": "",
            "description": item.get("description", ""),
            "authenticity_status": "not_received",
            "completeness_status": "not_received",
            "relevance_status": "requested",
            "reliability_status": "not_assessed",
            "review_status": "requested",
            "created_at": _now(),
            "created_by": actor,
            "purpose": item.get("purpose", ""),
            "priority": item.get("priority", "medium"),
        })
    append_rows(EVIDENCE_DATASET, rows)
    counts["evidence_requests"] = len(rows)
    
    # Contradictions
    existing = _existing(
        CASE_CONTRADICTIONS_DATASET,
        case_id,
        lambda r: _signature(
            "contradiction",
            r.get("description", ""),
            r.get("clarification_required", ""),
        ),
    )
    rows = []
    for item in case_map.get("contradictions", []):
        sig = _signature(
            "contradiction",
            item.get("description", ""),
            item.get("clarification_required", ""),
        )
        if sig in existing:
            counts["duplicates_skipped"] += 1
            continue
        existing.add(sig)
        rows.append({
            "contradiction_id": random_id("CONTRA"),
            "case_id": case_id,
            "description": item.get("description", ""),
            "clarification_required": item.get("clarification_required", ""),
            "source_page_ids_json": json.dumps(
                item.get("source_page_ids", []),
                ensure_ascii=False,
            ),
            "review_status": "candidate",
            "created_at": _now(),
            "created_by": actor,
        })
    append_rows(CASE_CONTRADICTIONS_DATASET, rows)
    counts["contradictions"] = len(rows)

    audit(
        case_id=case_id,
        entity_type="case_map",
        entity_id=case_id,
        action="case_map_merged",
        actor=actor,
        new_value={"counts": counts, "case_map": case_map},
    )
    return counts

def load_case_contradictions(case_id: str) -> list[dict]:
    """Reads back all persisted contradictions for the case."""
    df = case_rows(CASE_CONTRADICTIONS_DATASET, case_id)
    if df.empty:
        return []
    return df.to_dict(orient="records")
