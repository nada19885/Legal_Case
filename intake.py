from __future__ import annotations

from datetime import datetime, timezone

from .ids import random_id
from .storage import append_rows
from .audit import audit
from .config import (
    CASES_DATASET,
    CASE_MESSAGES_DATASET,
)


VALID_WORKFLOW_TYPES = {
    "litigation",
    "agreement_review",
}

WORKFLOW_ALIASES = {
    "litigation": "litigation",
    "litigation_case": "litigation",
    "litigation case": "litigation",
    "case": "litigation",
    "legal_case": "litigation",
    "agreement": "agreement_review",
    "agreement_review": "agreement_review",
    "agreement review": "agreement_review",
    "contract": "agreement_review",
    "contract_review": "agreement_review",
    "contract review": "agreement_review",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_workflow_type(value: str | None) -> str:
    """Return the canonical persisted workflow value."""
    normalized = str(value or "litigation").strip().lower()
    normalized = WORKFLOW_ALIASES.get(normalized, normalized)

    if normalized not in VALID_WORKFLOW_TYPES:
        raise ValueError(
            "workflow_type must be 'litigation' or 'agreement_review'. "
            f"Received: {value!r}"
        )

    return normalized


def create_case(
    case_name,
    intake_mode="mixed",
    created_by="",
    description="",
    language="ar",
    client_name="",
    matter_type="",
    responsible_attorney="",
    workflow_type="litigation",
):
    """Create either a litigation matter or an agreement-review matter.

    The optional parameters are retained for backward compatibility with older
    versions of the application. The current UI only requires case_name,
    preferred language, and workflow_type.
    """
    cleaned_name = str(case_name or "").strip()
    if not cleaned_name:
        raise ValueError("A file name is required.")

    normalized_workflow = normalize_workflow_type(workflow_type)
    normalized_language = str(language or "ar").strip().lower()
    if normalized_language not in {"ar", "en"}:
        normalized_language = "ar"

    case_id = random_id("CASE")
    timestamp = utc_now()

    row = {
        "case_id": case_id,
        "case_name": cleaned_name,
        "case_description": str(description or "").strip(),
        "intake_mode": str(intake_mode or "mixed").strip() or "mixed",
        "workflow_type": normalized_workflow,
        "client_name": str(client_name or "").strip(),
        "matter_type": str(matter_type or "").strip(),
        "matter_date": "",
        "jurisdiction": "Saudi Arabia",
        "preferred_language": normalized_language,
        "customer_type": "",
        "regulated_entity_type": "",
        "product_type": "",
        "case_status": "intake",
        "facts_complete": "false",
        "issues_approved": "false",
        "research_complete": "false",
        "analysis_approved": "false",
        "strategy_approved": "false",
        "created_at": timestamp,
        "created_by": str(created_by or "").strip(),
        "responsible_attorney": str(responsible_attorney or "").strip(),
        "updated_at": timestamp,
    }

    try:
        append_rows(CASES_DATASET, [row])
    except Exception as error:
        message = str(error)
        if "workflow_type" in message or "schema" in message.lower():
            raise RuntimeError(
                "The Dataiku 'cases' dataset must contain a string column named "
                "'workflow_type'. Add that column, then retry. Allowed values are "
                "'litigation' and 'agreement_review'. Original error: " + message
            ) from error
        raise

    audit(
        case_id,
        "case",
        case_id,
        "created",
        str(created_by or "").strip(),
        new_value=row,
    )

    return case_id


def add_message(
    case_id,
    conversation_id,
    role,
    text,
    created_by="",
    language="ar",
    sequence=0,
):
    message_id = random_id("MSG")

    row = {
        "message_id": message_id,
        "case_id": case_id,
        "conversation_id": conversation_id,
        "message_sequence": sequence,
        "role": role,
        "message_text": text,
        "message_language": language,
        "created_at": utc_now(),
        "created_by": created_by,
        "processing_status": "stored",
    }

    append_rows(CASE_MESSAGES_DATASET, [row])
    return message_id
