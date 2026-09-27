"""
Field-level rules shared by financial extraction, user review and the ledger.
Location: lib/python/legal_platform/financial_fields.py

One definition of "this value still needs a human" so that extraction,
the pending-review queue and the normalized ledger can never disagree:

  * a field the LLM marked uncertain ("conflict") is pending;
  * a REQUIRED field with no value is pending (the system must not fill it
    in by default, e.g. assume SAR or guess debit/credit);
  * debit_or_credit must be exactly "debit" or "credit";
  * a human correction resolves the field, whatever it was.

Pure functions only (no Dataiku access), so they can be unit-tested.
"""

from __future__ import annotations

import json
from typing import Any

FIELD_NAMES = (
    "date",
    "amount",
    "currency",
    "debit_or_credit",
    "description",
    "reference_number",
    "party_source",
    "running_balance",
)

# Values the accounting analysis cannot do without. Missing -> ask the user.
REQUIRED_FIELDS = ("date", "amount", "currency", "debit_or_credit")

# Field statuses written by extraction that mean "not usable yet".
PENDING_STATUSES = {"conflict", "missing_required"}

ISSUE_UNCERTAIN = "uncertain"
ISSUE_MISSING = "missing"

DIRECTION_VALUES = {"debit", "credit"}


def parse_fields(row: dict) -> dict:
    raw = row.get("fields_json", "{}") if isinstance(row, dict) else "{}"
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def field_issue(field_name: str, info: Any) -> str:
    """"" when the extracted value is usable as-is, otherwise why not."""
    info = info if isinstance(info, dict) else {}
    value = str(info.get("value", "") or "").strip()
    status = str(info.get("status", "") or "")

    if status == "conflict":
        return ISSUE_UNCERTAIN
    if not value:
        return ISSUE_MISSING if (field_name in REQUIRED_FIELDS or status == "missing_required") else ""
    if field_name == "debit_or_credit" and value.lower() not in DIRECTION_VALUES:
        return ISSUE_UNCERTAIN
    return ""


def row_corrections(row: dict, corrections_by_row: dict) -> dict:
    return (corrections_by_row or {}).get(str(row.get("row_id", "")), {}) or {}


def pending_fields(row: dict, corrections_by_row: dict) -> list[str]:
    """Fields of this row that still need a human answer."""
    fields = parse_fields(row)
    corrected = row_corrections(row, corrections_by_row)
    return [
        name for name in FIELD_NAMES
        if name not in corrected and field_issue(name, fields.get(name))
    ]


def effective_value(row: dict, field_name: str, corrections_by_row: dict) -> dict:
    """The value downstream stages may use for one field.

    A human correction wins. Otherwise the extracted value is used only if
    it has no open issue; a pending field returns value None so that no
    caller can silently fall back to the LLM's suggestion.
    """
    corrected = row_corrections(row, corrections_by_row)
    if field_name in corrected:
        return {
            "value": str(corrected[field_name].get("corrected_value", "") or ""),
            "status": "verified_human",
            "source": "human",
        }

    info = parse_fields(row).get(field_name) or {}
    issue = field_issue(field_name, info)
    if issue:
        return {"value": None, "status": "pending_review", "source": None, "issue": issue}

    value = str(info.get("value", "") or "")
    return {
        "value": value,
        "status": info.get("status", "verified") if value else "missing",
        "source": "extraction",
    }
