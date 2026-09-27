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

# Other extraction schemas name the same fields differently. They are read
# as the canonical field when the canonical one has no value.
FIELD_ALIASES = {
    "date": ("transaction_date", "value_date", "posting_date"),
    "description": ("transaction_description", "narrative", "details"),
    "reference_number": ("reference", "ref_number"),
    "running_balance": ("balance",),
}
DEBIT_COLUMNS = ("debit_amount", "debit")
CREDIT_COLUMNS = ("credit_amount", "credit")
_ZERO = {"0", "0.0", "0.00", "-", "—", "none", "nan"}


def _has_value(info: Any) -> bool:
    return isinstance(info, dict) and str(info.get("value", "") or "").strip() != ""


def _nonzero(info: Any) -> bool:
    return _has_value(info) and str(info.get("value")).strip().lower() not in _ZERO


def _canonical(fields: dict) -> dict:
    """Map alias names onto the canonical fields.

    Separate debit/credit amount columns are read as the statement shows
    them: a value in exactly one of the two columns gives the amount and
    its direction. A row with values in both columns (or neither) is left
    without an amount, so it goes to the user instead of being guessed.
    """
    out = dict(fields)
    for canonical, aliases in FIELD_ALIASES.items():
        if not _has_value(out.get(canonical)):
            for alias in aliases:
                if _has_value(fields.get(alias)):
                    out[canonical] = fields[alias]
                    break

    if not _has_value(out.get("amount")):
        debit = next((fields[c] for c in DEBIT_COLUMNS if _nonzero(fields.get(c))), None)
        credit = next((fields[c] for c in CREDIT_COLUMNS if _nonzero(fields.get(c))), None)
        if (debit is None) != (credit is None):
            source, direction = (debit, "debit") if debit is not None else (credit, "credit")
            out["amount"] = source
            if not _has_value(out.get("debit_or_credit")):
                out["debit_or_credit"] = {
                    "value": direction,
                    "status": source.get("status", "verified"),
                    "certain": source.get("certain", True),
                    "reason": f"Taken from the {direction} column of the statement.",
                }
    return out


def parse_fields(row: dict) -> dict:
    raw = row.get("fields_json", "{}") if isinstance(row, dict) else "{}"
    if isinstance(raw, dict):
        parsed = raw
    else:
        try:
            parsed = json.loads(raw or "{}")
        except (TypeError, ValueError):
            return {}
    return _canonical(parsed) if isinstance(parsed, dict) else {}


def field_issue(field_name: str, info: Any) -> str:
    """"" when the extracted value is usable as-is, otherwise why not."""
    info = info if isinstance(info, dict) else {}
    value = str(info.get("value", "") or "").strip()
    status = str(info.get("status", "") or "")

    if status == "conflict" or str(info.get("certain", "")).strip().lower() == "false":
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
