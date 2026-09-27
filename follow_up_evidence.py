from __future__ import annotations

from datetime import datetime, timezone
import re

from .config import EVIDENCE_DATASET
from .ids import random_id
from .storage import append_rows, case_rows


def _normalise(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def persist_follow_up_evidence(
    case_id: str,
    actions: list[dict],
    created_by: str = "",
) -> int:
    existing = case_rows(EVIDENCE_DATASET, case_id)
    signatures = set()

    if not existing.empty:
        for row in existing.to_dict(orient="records"):
            signatures.add((
                _normalise(row.get("evidence_type")),
                _normalise(row.get("description")),
            ))

    rows = []
    for action in actions:
        if action.get("action_type") != "request_evidence":
            continue

        evidence_type = str(action.get("evidence_type", "")).strip()
        description = str(action.get("evidence_description", "")).strip()
        referenced = str(action.get("referenced_in_document", "")).strip()
        reason = str(action.get("reason", "")).strip()

        full_description = description
        if referenced:
            full_description += (
                ("\n" if full_description else "")
                + f"Referenced in document: {referenced}."
            )
        if reason:
            full_description += (
                ("\n" if full_description else "")
                + f"Purpose: {reason}"
            )

        signature = (_normalise(evidence_type), _normalise(full_description))
        if signature in signatures:
            continue
        signatures.add(signature)

        rows.append({
            "evidence_id": random_id("EVID"),
            "case_id": case_id,
            "evidence_title": evidence_type or "Requested evidence",
            "evidence_type": evidence_type,
            "case_document_id": "",
            "page_number": "",
            "message_id": "",
            "description": full_description,
            "authenticity_status": "not_received",
            "completeness_status": "not_received",
            "relevance_status": "requested",
            "reliability_status": "not_assessed",
            "review_status": "requested",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": created_by,
        })

    append_rows(EVIDENCE_DATASET, rows)
    return len(rows)
