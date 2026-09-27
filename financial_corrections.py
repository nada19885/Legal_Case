from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from .audit import audit
from .config import (
    FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET,
    FINANCIAL_LINE_ITEMS_DATASET,
)
from .ids import random_id
from .storage import append_rows, case_rows


def list_rows_needing_review(case_id: str) -> list[dict]:
    """Rows (or specific fields within a row) still awaiting a human read of
    the source page image. A row drops off this list once every one of its
    conflicting fields has a correction on file.
    """
    rows_df = case_rows(FINANCIAL_LINE_ITEMS_DATASET, case_id)
    if rows_df.empty:
        return []

    corrected_fields_by_row = _corrected_fields_by_row(case_id)
    pending_rows = rows_df[rows_df["row_status"] == "needs_review"]

    result = []
    for row in pending_rows.to_dict(orient="records"):
        row_id = str(row.get("row_id", ""))
        already_corrected = corrected_fields_by_row.get(row_id, set())
        if _has_uncorrected_conflict(row, already_corrected):
            result.append(row)
    return result


def _corrected_fields_by_row(case_id: str) -> dict[str, set]:
    corrections_df = case_rows(FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET, case_id)
    if corrections_df.empty:
        return {}
    result: dict[str, set] = {}
    for row in corrections_df.to_dict(orient="records"):
        result.setdefault(str(row.get("row_id", "")), set()).add(str(row.get("field_name", "")))
    return result


def _has_uncorrected_conflict(row: dict, corrected_fields: set) -> bool:
    try:
        fields = json.loads(row.get("fields_json", "{}") or "{}")
    except (TypeError, json.JSONDecodeError):
        return True
    conflicting_fields = {name for name, info in fields.items() if info.get("status") == "conflict"}
    return bool(conflicting_fields - corrected_fields)


def submit_correction(
    case_id: str,
    row_id: str,
    field_name: str,
    corrected_value: str,
    corrected_by: str,
    correction_note: str = "",
    reviewed_candidates: Optional[list[dict]] = None,
) -> str:
    """Records a human's read of the source page image for one disputed
    field. This never overwrites fin_line_items.fields_json — the
    original disagreement between extraction methods stays on record, and
    the correction is layered on top, exactly like every other append-only
    entity in this codebase.
    """
    correction_id = random_id("FLICORR")
    row = {
        "correction_id": correction_id,
        "case_id": case_id,
        "row_id": row_id,
        "field_name": field_name,
        "candidates_json": json.dumps(reviewed_candidates or [], ensure_ascii=False),
        "corrected_value": corrected_value,
        "corrected_by": corrected_by,
        "corrected_at": datetime.now(timezone.utc).isoformat(),
        "correction_note": correction_note,
    }
    append_rows(FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET, [row])

    audit(
        case_id=case_id,
        entity_type="financial_line_item",
        entity_id=row_id,
        action="field_corrected",
        actor=corrected_by,
        new_value={"field_name": field_name, "corrected_value": corrected_value},
        reason=correction_note,
    )
    return correction_id


def load_latest_corrections(case_id: str) -> dict[str, dict[str, dict]]:
    """row_id -> field_name -> latest correction row."""
    corrections_df = case_rows(FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET, case_id)
    if corrections_df.empty:
        return {}
    if "corrected_at" in corrections_df.columns:
        corrections_df = corrections_df.sort_values("corrected_at")

    result: dict[str, dict[str, dict]] = {}
    for row in corrections_df.to_dict(orient="records"):
        row_id = str(row.get("row_id", ""))
        field_name = str(row.get("field_name", ""))
        result.setdefault(row_id, {})[field_name] = row  # later rows overwrite earlier ones
    return result


def effective_field_value(
    row: dict,
    field_name: str,
    corrections_by_row: dict[str, dict[str, dict]],
) -> dict:
    """The value stage 4+ should actually use for this field: a human
    correction if one exists, otherwise the reconciled value UNLESS its
    status is still "conflict" (in which case it stays unusable — never
    silently pick one of the disagreeing candidates).
    """
    row_id = str(row.get("row_id", ""))
    corrections = corrections_by_row.get(row_id, {})
    if field_name in corrections:
        correction = corrections[field_name]
        return {"value": correction["corrected_value"], "status": "verified_human", "source": "human"}

    try:
        fields = json.loads(row.get("fields_json", "{}") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {"value": None, "status": "pending_review", "source": None}

    info = fields.get(field_name, {})
    if info.get("status") == "conflict":
        return {"value": None, "status": "pending_review", "source": None}

    return {"value": info.get("value", ""), "status": info.get("status", "missing"), "source": "extraction"}