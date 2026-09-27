import json
from datetime import date

from .models import MatterFilters


def _json_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    text = str(value).strip()

    if not text:
        return []

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _date(value):
    if not value:
        return None

    if isinstance(value, date):
        return value

    try:
        return date.fromisoformat(
            str(value)[:10]
        )
    except Exception:
        return None


def node_is_applicable(
    node: dict,
    filters: MatterFilters,
) -> bool:
    if (
        filters.language
        and str(
            node.get("language", "")
        ) != filters.language
    ):
        return False

    if filters.current_only:
        raw = str(
            node.get("is_current", "")
        ).lower()

        if raw in {
            "false",
            "0",
            "no",
        }:
            return False

    if filters.customer_type:
        allowed = _json_list(
            node.get(
                "customer_types_json"
            )
        )

        if (
            allowed
            and filters.customer_type
            not in allowed
        ):
            return False

    if filters.regulated_entity_type:
        allowed = _json_list(
            node.get(
                "regulated_entity_types_json"
            )
        )

        if (
            allowed
            and filters.regulated_entity_type
            not in allowed
        ):
            return False

    if filters.product_type:
        allowed = _json_list(
            node.get(
                "products_json"
            )
        )

        if (
            allowed
            and filters.product_type
            not in allowed
        ):
            return False

    if filters.matter_date:
        effective = _date(
            node.get("effective_date")
        )

        expiry = _date(
            node.get("expiry_date")
        )

        if (
            effective
            and effective > filters.matter_date
        ):
            return False

        if (
            expiry
            and expiry < filters.matter_date
        ):
            return False

    return True
