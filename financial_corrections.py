from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from .audit import audit
from .config import (
    FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET,
    FINANCIAL_LINE_ITEMS_DATASET,
)
from .financial_fields import (
    FIELD_NAMES,
    ISSUE_MISSING,
    effective_value,
    field_issue,
    parse_fields,
    pending_fields,
)
from .financial_facts import RESOLUTION_FIELD, latest_resolutions
from .ids import random_id
from .storage import append_rows, case_rows


def list_rows_needing_review(case_id: str) -> list[dict]:
    """Rows with at least one field still awaiting a human answer (an
    uncertain value or a missing required one). A row drops off this list
    once every such field has a correction on file.
    """
    rows_df = case_rows(FINANCIAL_LINE_ITEMS_DATASET, case_id)
    if rows_df.empty:
        return []
    corrections = load_latest_corrections(case_id)
    return [
        row for row in rows_df.to_dict(orient="records")
        if pending_fields(row, corrections)
    ]


def _page_excerpt(page_text: str, needles: list[str], width: int = 260) -> str:
    """The part of the page around the row being reviewed, so the user sees
    the evidence without opening the whole page."""
    text = str(page_text or "")
    if not text:
        return ""
    for needle in needles:
        needle = str(needle or "").strip()
        if len(needle) < 3:
            continue
        position = text.find(needle)
        if position >= 0:
            start = max(0, position - width)
            end = min(len(text), position + len(needle) + width)
            return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")
    return text[: width * 2].strip() + ("…" if len(text) > width * 2 else "")


def build_review_items(rows: list[dict], corrections: dict, pages_by_id: dict) -> list[dict]:
    """One pending-review item per row with open fields.

    Each item carries what the user needs to answer without guessing:
    the transaction as currently understood, the LLM's suggestion and
    reasoning for every open field, the row as printed on the page, and an
    excerpt of the page text around it. pages_by_id maps page_id to
    {"page_text", "label"}.
    """
    items = []
    for row in rows:
        open_fields = pending_fields(row, corrections)
        if not open_fields:
            continue
        fields = parse_fields(row)
        page_id = str(row.get("page_id", ""))
        page = pages_by_id.get(page_id) or {}

        transaction = {}
        for name in FIELD_NAMES:
            effective = effective_value(row, name, corrections)
            info = fields.get(name) or {}
            transaction[name] = {
                "value": effective["value"] if effective["value"] is not None else str(info.get("value", "") or ""),
                "pending": name in open_fields,
                "source": effective.get("source") or "suggestion",
            }

        source_text = str((fields.get("_row") or {}).get("source_text", "") or "")
        open_items = []
        for name in open_fields:
            info = fields.get(name) or {}
            suggested = str(info.get("value", "") or "").strip()
            open_items.append({
                "field": name,
                "issue": field_issue(name, info) or ISSUE_MISSING,
                "suggested_value": suggested,
                "reason": str(info.get("reason", "") or ""),
                "candidates": [
                    {"value": c.get("value"), "source": c.get("source")}
                    for c in (info.get("candidates") or [])
                    if isinstance(c, dict) and str(c.get("value", "") or "").strip()
                ] or ([{"value": suggested, "source": "AI Suggested"}] if suggested else []),
            })

        amount_text = str((fields.get("amount") or {}).get("value", "") or "")
        reference = str((fields.get("reference_number") or {}).get("value", "") or "")
        items.append({
            "row_id": str(row.get("row_id", "")),
            "page_id": page_id,
            "page_number": row.get("page_number"),
            "page_label": page.get("label", ""),
            "transaction": transaction,
            "source_text": source_text,
            "page_excerpt": _page_excerpt(page.get("page_text", ""), [source_text[:60], reference, amount_text]),
            "fields": open_items,
        })

    items.sort(key=lambda item: (str(item.get("page_label", "")), _as_int(item.get("page_number")), item["row_id"]))
    return items


def _as_int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


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
        if field_name == RESOLUTION_FIELD:
            continue  # fact-level decisions, see load_fact_resolutions
        result.setdefault(row_id, {})[field_name] = row  # later rows overwrite earlier ones
    return result


def load_fact_resolutions(case_id: str) -> dict:
    """row_id -> {"final": ..., "proposal": ...}: the user's latest decision
    on each atomic fact (see financial_facts.latest_resolutions)."""
    corrections_df = case_rows(FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET, case_id)
    if corrections_df.empty:
        return {}
    if "corrected_at" in corrections_df.columns:
        corrections_df = corrections_df.sort_values("corrected_at", kind="stable")
    return latest_resolutions(corrections_df.to_dict(orient="records"))


def submit_fact_resolution(
    case_id: str,
    row_id: str,
    action: str,
    fields: Optional[dict] = None,
    explanation: str = "",
    decided_by: str = "",
    summary: str = "",
) -> str:
    """Record the user's decision on one atomic fact: confirm, correct,
    ignore, or an explanation-based proposal awaiting confirmation.

    Stored as its own row in the corrections dataset (field_name
    "__resolution__"); the extracted fact itself is never overwritten, so
    the original reading and every decision stay on record."""
    payload = {
        "action": action,
        "fields": fields or {},
        "explanation": explanation,
        "summary": summary,
    }
    correction_id = random_id("FACTRES")
    append_rows(FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET, [{
        "correction_id": correction_id,
        "case_id": case_id,
        "row_id": row_id,
        "field_name": RESOLUTION_FIELD,
        "candidates_json": "[]",
        "corrected_value": json.dumps(payload, ensure_ascii=False),
        "corrected_by": decided_by,
        "corrected_at": datetime.now(timezone.utc).isoformat(),
        "correction_note": explanation,
    }])
    audit(
        case_id=case_id,
        entity_type="financial_fact",
        entity_id=row_id,
        action=f"fact_{action}",
        actor=decided_by,
        new_value=payload,
        reason=explanation,
    )
    return correction_id


def effective_field_value(
    row: dict,
    field_name: str,
    corrections_by_row: dict[str, dict[str, dict]],
) -> dict:
    """The value stage 4+ should actually use for this field: a human
    correction if one exists, otherwise the extracted value only when it
    has no open issue (see financial_fields.effective_value).
    """
    return effective_value(row, field_name, corrections_by_row)
