from datetime import datetime, timezone

from .ids import random_id
from .storage import append_rows
from .config import (
    FACT_CANDIDATES_DATASET,
    FACTS_DATASET,
)


def add_fact_candidate(
    case_id,
    fact_text,
    source_type,
    source_id="",
    party="",
    fact_type="",
    quote="",
    confidence=0.7,
    page_number="",
):
    fact_candidate_id = random_id(
        "FCAND"
    )

    row = {
        "fact_candidate_id": (
            fact_candidate_id
        ),
        "case_id": case_id,
        "source_type": source_type,
        "case_document_id": (
            source_id
            if source_type == "document"
            else ""
        ),
        "page_number": page_number,
        "message_id": (
            source_id
            if source_type == "chat"
            else ""
        ),
        "fact_text": fact_text,
        "fact_date": "",
        "party": party,
        "fact_type": fact_type,
        "evidence_quote": (
            quote or fact_text
        ),
        "confidence": confidence,
        "candidate_status": "pending",
        "created_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }

    append_rows(
        FACT_CANDIDATES_DATASET,
        [row],
    )

    return row


def approve_fact(
    candidate,
    approved_by="",
):
    fact_id = random_id(
        "FACT"
    )

    row = {
        "fact_id": fact_id,
        "case_id": candidate[
            "case_id"
        ],
        "fact_text": candidate[
            "fact_text"
        ],
        "fact_date": candidate.get(
            "fact_date",
            "",
        ),
        "party": candidate.get(
            "party",
            "",
        ),
        "fact_type": candidate.get(
            "fact_type",
            "",
        ),
        "source_type": candidate.get(
            "source_type",
            "",
        ),
        "case_document_id": (
            candidate.get(
                "case_document_id",
                "",
            )
        ),
        "page_number": candidate.get(
            "page_number",
            "",
        ),
        "message_id": candidate.get(
            "message_id",
            "",
        ),
        "evidence_quote": (
            candidate.get(
                "evidence_quote",
                "",
            )
        ),
        "verification_status": (
            "approved"
        ),
        "approved_by": approved_by,
        "approved_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }

    append_rows(
        FACTS_DATASET,
        [row],
    )

    return row
