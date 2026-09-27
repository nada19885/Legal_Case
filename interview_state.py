import json
from datetime import datetime, timezone

from .ids import random_id
from .storage import append_rows


# Uses audit_events so no additional CSV dataset is required.
def persist_interview_state(
    case_id: str,
    decision_payload: dict,
    actor: str = "",
) -> str:
    event_id = random_id("AUD")

    row = {
        "audit_event_id": event_id,
        "case_id": case_id,
        "entity_type": "case_interview_state",
        "entity_id": case_id,
        "action": "interview_assessed",
        "old_value_json": "{}",
        "new_value_json": json.dumps(
            decision_payload,
            ensure_ascii=False,
        ),
        "actor": actor,
        "event_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "reason": (
            "Adaptive LLM completeness "
            "assessment after a case interaction."
        ),
    }

    append_rows(
        "audit_events",
        [row],
    )

    return event_id
