from datetime import datetime, timezone
import json

from .ids import random_id
from .storage import append_rows
from .config import AUDIT_DATASET


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def audit(
    case_id,
    entity_type,
    entity_id,
    action,
    actor="",
    old_value=None,
    new_value=None,
    reason="",
):
    row = {
        "audit_event_id": random_id(
            "AUD"
        ),
        "case_id": case_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "old_value_json": json.dumps(
            old_value or {},
            ensure_ascii=False,
        ),
        "new_value_json": json.dumps(
            new_value or {},
            ensure_ascii=False,
        ),
        "actor": actor,
        "event_at": utc_now(),
        "reason": reason,
    }

    append_rows(
        AUDIT_DATASET,
        [row],
    )

    return row[
        "audit_event_id"
    ]
