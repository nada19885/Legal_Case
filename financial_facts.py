"""
Atomic financial facts.
Location: lib/python/legal_platform/financial_facts.py

A financial page is broken into ATOMIC FACTS: one independent piece of
financial information each ("financing amount = SAR 1,000,000", "paid
amount = SAR 300,000", "remaining balance = SAR 700,000"). A fact fills
only the fields the page supports; everything else stays None.

Every fact carries a status:

  EXTRACTED       the document states the value explicitly
  CALCULATED      derived arithmetically from other facts on the page
                  (recomputed here; a mismatch makes it UNCERTAIN)
  INFERRED        the meaning was interpreted from context
  UNCERTAIN       something is there but its meaning/value is ambiguous
                  -> needs the user
  MISSING         information the document should contain but does not
                  (recorded as a gap, never asked about)
  USER_CONFIRMED  the user accepted the fact as extracted
  USER_CORRECTED  the user changed it (directly or via an explanation)
  IGNORED         the user excluded it from the ledger

Only UNCERTAIN facts are sent to the user. A value that simply is not on
the page stays None: the user is not asked about it.

Facts are stored one per row in fin_line_items (fields_json holds the
fact), so no dataset schema changes are needed. Rows written by the older
transaction-row extraction are read as "transaction" facts.

Pure functions only (no Dataiku access).
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from .arabic_text import fix_structure, fix_visual_arabic
from .financial_fields import effective_value, parse_fields, pending_fields
from .ids import stable_id

SCHEMA = "atomic_fact_v1"

FACT_FIELDS = (
    "fact_type",
    "date",
    "description",
    "amount",
    "currency",
    "debit",
    "credit",
    "balance",
    "amount_due",
    "paid_amount",
    "remaining_amount",
    "account_number",
    "transaction_reference",
    "counterparty",
)
AMOUNT_FIELDS = ("amount", "debit", "credit", "balance", "amount_due", "paid_amount", "remaining_amount")
TEXT_FIELDS = ("description", "counterparty", "account_number", "transaction_reference")
# Order used to pick "the" number of a fact (display, timeline, calculations).
PRIMARY_VALUE_ORDER = ("amount", "paid_amount", "remaining_amount", "amount_due", "balance", "debit", "credit")

EXTRACTED = "EXTRACTED"
CALCULATED = "CALCULATED"
INFERRED = "INFERRED"
UNCERTAIN = "UNCERTAIN"
MISSING = "MISSING"
USER_CONFIRMED = "USER_CONFIRMED"
USER_CORRECTED = "USER_CORRECTED"
IGNORED = "IGNORED"

MODEL_STATUSES = (EXTRACTED, CALCULATED, INFERRED, UNCERTAIN, MISSING)
LEDGER_STATUSES = (EXTRACTED, CALCULATED, INFERRED, MISSING, USER_CONFIRMED, USER_CORRECTED)

FACT_TYPES = (
    "transaction", "payment", "installment", "deposit", "withdrawal", "transfer",
    "financing_amount", "outstanding_balance", "remaining_balance", "amount_due",
    "opening_balance", "closing_balance", "balance", "fee", "interest", "penalty",
    "credit_limit", "claimed_amount", "other",
)

RESOLUTION_FIELD = "__resolution__"
RESOLVE_ACTIONS = ("confirm", "correct", "ignore")
PROPOSAL_ACTION = "proposal"

_EMPTY = {"", "null", "none", "n/a", "na", "-", "—", "nan", "unknown"}
_TOLERANCE = Decimal("0.01")


# -----------------------------------------------------------------------------
# Value helpers
# -----------------------------------------------------------------------------
def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return str(value)
    text = str(value).strip()
    return None if text.lower() in _EMPTY else text


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def parse_amount(value: Any) -> Optional[Decimal]:
    """Read a money amount exactly as printed, or return None.

    Handles thousands separators (1,000,000 / 1.000.000 / 1 000 000),
    decimal comma or point, Arabic-Indic digits and separators, currency
    text, and negatives written as -500, 500- or (500). A form that can be
    read two ways (e.g. "1.000": one thousand or one?) returns None so the
    fact goes to the user instead of being guessed.
    """
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    text = _clean(value)
    if text is None:
        return None
    text = text.translate(_DIGITS).replace("٬", ",").replace("٫", ".").replace("\u00a0", " ")
    negative = text.strip().startswith("(") and text.strip().endswith(")")
    compact = re.sub(r"[^\d,.\- ]", "", text).strip()
    if compact.startswith("-") or compact.endswith("-"):
        negative = True
    compact = compact.replace("-", "").strip()
    if re.search(r"\d\s+\d", compact):
        if not re.fullmatch(r"\d{1,3}( \d{3})+([.,]\d+)?", compact):
            return None
        compact = compact.replace(" ", "")
    compact = compact.replace(" ", "")
    if not compact or not re.search(r"\d", compact):
        return None

    commas, dots = compact.count(","), compact.count(".")
    if commas and dots:
        decimal_sep = "," if compact.rfind(",") > compact.rfind(".") else "."
        thousands = "." if decimal_sep == "," else ","
        integer, _, fraction = compact.rpartition(decimal_sep)
        if not re.fullmatch(r"\d{1,3}(\%s\d{3})*" % thousands, integer) or not fraction.isdigit():
            return None
        number = integer.replace(thousands, "") + "." + fraction
    elif commas or dots:
        sep = "," if commas else "."
        parts = compact.split(sep)
        if len(parts) > 2:
            if not (1 <= len(parts[0]) <= 3 and all(len(p) == 3 for p in parts[1:])):
                return None
            number = "".join(parts)
        else:
            head, tail = parts
            if not head.isdigit() or not tail.isdigit():
                return None
            if len(tail) == 3:
                # "300,000" is thousands; "1.000" could be either -> ask.
                if sep == ",":
                    number = head + tail
                else:
                    return None
            else:
                number = head + "." + tail
    else:
        number = compact
    try:
        amount = Decimal(number)
    except InvalidOperation:
        return None
    return -amount if negative else amount


def format_amount(value: Decimal) -> str:
    return f"{value:,.2f}"


def _snake(value: Any) -> Optional[str]:
    text = _clean(value)
    if text is None:
        return None
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or None


def _currency(value: Any) -> Optional[str]:
    text = _clean(value)
    if text is None:
        return None
    upper = f" {text.upper()} "
    # Other countries' riyals (and dollars) are kept exactly as written.
    if any(word in upper for word in ("QATAR", "OMAN", "YEMEN", "IRAN", "قطري", "عماني", "يمني", "إيراني", "ايراني")):
        return text.upper()
    for code, markers in (
        ("USDT", ("USDT", "TETHER")),
        ("USD", ("USD", "US$", "دولار أمريكي", "US DOLLAR")),
        ("EUR", ("EUR", "€", "يورو")),
        ("SAR", ("SAR", "ر.س", "ريال", " SR ", "RIYAL", "RIAL")),
    ):
        if any(marker in upper for marker in markers):
            return code
    return text.upper()


def primary_value(fact: dict) -> tuple[Optional[str], Optional[Decimal]]:
    """(field, value) of the number that best represents the fact."""
    for name in PRIMARY_VALUE_ORDER:
        amount = parse_amount(fact.get(name))
        if amount is not None:
            return name, amount
    return None, None


def normalise_status(value: Any) -> str:
    text = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {"EXPLICIT": EXTRACTED, "STATED": EXTRACTED, "DERIVED": CALCULATED, "COMPUTED": CALCULATED,
               "INTERPRETED": INFERRED, "AMBIGUOUS": UNCERTAIN, "UNCLEAR": UNCERTAIN, "ABSENT": MISSING}
    text = aliases.get(text, text)
    return text if text in MODEL_STATUSES else ""


# -----------------------------------------------------------------------------
# LLM output -> fact rows
# -----------------------------------------------------------------------------
def _normalise_fact(raw: dict) -> tuple[dict, dict, list[str]]:
    """(fact fields, raw amount text, problems that make the fact uncertain)."""
    fact: dict = {}
    raw_amounts: dict = {}
    problems: list[str] = []
    for name in FACT_FIELDS:
        value = raw.get(name)
        if name in AMOUNT_FIELDS:
            text = _clean(value)
            if text is None:
                fact[name] = None
                continue
            raw_amounts[name] = text
            amount = parse_amount(value)
            if amount is None:
                fact[name] = text
                problems.append(f"{name.replace('_', ' ')} '{text}' is not a readable number")
            else:
                fact[name] = format_amount(amount)
        elif name == "fact_type":
            fact[name] = _snake(value)
        elif name == "currency":
            fact[name] = _currency(value)
        else:
            fact[name] = fix_visual_arabic(_clean(value))
    return fact, raw_amounts, problems


def _review_block(raw: Any) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    alternatives = raw.get("alternatives") or []
    if not isinstance(alternatives, list):
        alternatives = [alternatives]
    return {
        "question": _clean(raw.get("question")) or "",
        "suggestion": _clean(raw.get("suggestion")) or "",
        "reason": _clean(raw.get("reason")) or "",
        "alternatives": [str(a).strip() for a in alternatives if _clean(a)],
    }


def _calculation_inputs(calculation: dict) -> list[tuple[str, Optional[str]]]:
    inputs = []
    for item in calculation.get("inputs") or []:
        if isinstance(item, dict):
            inputs.append((str(item.get("fact_key") or item.get("key") or ""), _clean(item.get("field"))))
        else:
            inputs.append((str(item), None))
    return inputs


def check_calculation(fact: dict, calculation: dict, facts_by_key: dict) -> dict:
    """Recompute a CALCULATED fact from the facts it names.

    Returns {"ok", "expected", "stated", "field", "message"}. ok is False
    whenever the result cannot be reproduced: unknown operation, missing
    or non-numeric inputs, or a result that differs by more than 0.01.
    """
    operation = str(calculation.get("operation") or "").strip().lower()
    result_field = _clean(calculation.get("result_field"))
    if result_field not in AMOUNT_FIELDS:
        result_field, _ = primary_value(fact)
    stated = parse_amount(fact.get(result_field)) if result_field else None
    check = {"ok": False, "expected": None, "stated": format_amount(stated) if stated is not None else None,
             "field": result_field, "message": ""}

    values = []
    for key, field in _calculation_inputs(calculation):
        source = facts_by_key.get(key)
        if source is None:
            check["message"] = f"Input fact '{key}' was not found on the page."
            return check
        value = parse_amount(source.get(field)) if field else primary_value(source)[1]
        if value is None:
            check["message"] = f"Input fact '{key}' has no numeric value."
            return check
        values.append(value)

    if not values or stated is None:
        check["message"] = "The calculation has no inputs or no stated result to verify."
        return check

    try:
        if operation in {"add", "sum", "plus"}:
            expected = sum(values, Decimal(0))
        elif operation in {"subtract", "minus", "difference"}:
            expected = values[0] - sum(values[1:], Decimal(0))
        elif operation in {"multiply", "product"}:
            expected = Decimal(1)
            for value in values:
                expected *= value
        elif operation in {"divide", "division"} and len(values) == 2 and values[1] != 0:
            expected = values[0] / values[1]
        else:
            check["message"] = f"Unsupported calculation '{operation or 'none'}'."
            return check
    except (InvalidOperation, ArithmeticError) as error:
        check["message"] = f"Calculation failed: {error}"
        return check

    check["expected"] = format_amount(expected)
    check["ok"] = abs(expected - stated) <= _TOLERANCE
    if not check["ok"]:
        check["message"] = (
            f"Recomputed {result_field.replace('_', ' ')} is {format_amount(expected)}, "
            f"but the stated value is {format_amount(stated)}."
        )
    return check


def build_fact_rows(page_id: str, case_document_id: str, page_number: int, output: dict,
                    created_at: str = "") -> list[dict]:
    """Normalise the LLM's facts for one page into fin_line_items rows.

    * fields not supported by the page stay None;
    * an unknown status, an unreadable number, a value with no fact_type,
      or a calculation that does not reproduce -> UNCERTAIN;
    * facts with no value at all are dropped unless they record a MISSING
      piece of information.
    """
    raw_facts = [f for f in (output or {}).get("facts") or [] if isinstance(f, dict)]
    prepared = []
    for index, raw in enumerate(raw_facts):
        fact, raw_amounts, problems = _normalise_fact(raw)
        status = normalise_status(raw.get("status"))
        review = _review_block(raw.get("review"))
        key = str(raw.get("fact_key") or f"F{index + 1}")
        has_value = any(fact.get(name) for name in FACT_FIELDS if name != "fact_type")

        if status != MISSING and not has_value:
            continue
        if not status:
            problems.append(f"The model returned an unrecognised status '{raw.get('status')}'.")
        if status != MISSING and has_value and not fact.get("fact_type"):
            problems.append("The meaning of this value (its fact type) was not determined.")
        if fact.get("fact_type") and fact["fact_type"] not in FACT_TYPES:
            fact["fact_type_label"] = fact["fact_type"]

        prepared.append({
            "key": key, "fact": fact, "raw": raw_amounts, "status": status or UNCERTAIN,
            "problems": problems, "review": review,
            "calculation": raw.get("calculation") if isinstance(raw.get("calculation"), dict) else None,
            "source_text": fix_visual_arabic(_clean(raw.get("source_text")) or ""),
        })

    facts_by_key = {item["key"]: item["fact"] for item in prepared}
    rows = []
    for item in prepared:
        calculation = item["calculation"]
        if item["status"] == CALCULATED:
            if calculation is None:
                item["problems"].append("Marked as calculated but no calculation was given to verify.")
            else:
                check = check_calculation(item["fact"], calculation, facts_by_key)
                calculation = dict(calculation, check=check)
                if not check["ok"]:
                    item["problems"].append(check["message"])

        status = item["status"]
        review = item["review"]
        if item["problems"] and status != MISSING:
            status = UNCERTAIN
            review = dict(review)
            review["reason"] = "; ".join(filter(None, [review.get("reason"), *item["problems"]]))

        fields_json = {
            "schema": SCHEMA,
            "fact_key": item["key"],
            "fact": item["fact"],
            "raw": item["raw"],
            "status": status,
            "review": review,
            "calculation": calculation,
            "source_text": item["source_text"][:1000],
        }
        rows.append({
            "row_id": stable_id("FACT", page_id, f"{page_number}_{item['key']}"),
            "page_id": page_id,
            "case_document_id": case_document_id,
            "page_number": page_number,
            "cluster_key": f"FACT_{page_number}_{item['key']}",
            "fields_json": json.dumps(fields_json, ensure_ascii=False),
            "row_status": status,
            "has_conflict": status == UNCERTAIN,
            "created_at": created_at,
        })
    return rows


# -----------------------------------------------------------------------------
# Reading stored rows
# -----------------------------------------------------------------------------
def _stored(row: dict) -> dict:
    raw = row.get("fields_json", "{}")
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def is_fact_row(row: dict) -> bool:
    return _stored(row).get("schema") == SCHEMA


def _legacy_fact(row: dict, corrections: dict) -> dict:
    """Read a row from the older transaction-row extraction as a fact."""
    fields = parse_fields(row)
    open_fields = pending_fields(row, corrections)

    def value(name):
        effective = effective_value(row, name, corrections)
        if effective["value"] is not None:
            return effective["value"]
        return str((fields.get(name) or {}).get("value", "") or "") or None

    fact = {name: None for name in FACT_FIELDS}
    fact.update({
        "fact_type": "transaction",
        "date": _clean(value("date")),
        "description": _clean(value("description")),
        "currency": _currency(value("currency")),
        "transaction_reference": _clean(value("reference_number")),
        "counterparty": _clean(value("party_source")),
    })
    amount = parse_amount(value("amount"))
    if amount is not None:
        fact["amount"] = format_amount(amount)
        direction = str(value("debit_or_credit") or "").lower()
        if direction in {"debit", "credit"}:
            fact[direction] = format_amount(abs(amount))
    balance = parse_amount(value("running_balance"))
    if balance is not None:
        fact["balance"] = format_amount(balance)

    reasons = [str((fields.get(name) or {}).get("reason", "") or "") for name in open_fields]
    return {
        "fact": fact,
        "status": UNCERTAIN if open_fields else EXTRACTED,
        "review": {
            "question": f"Please check: {', '.join(name.replace('_', ' ') for name in open_fields)}." if open_fields else "",
            "suggestion": "",
            "reason": "; ".join(r for r in reasons if r),
            "alternatives": [],
        },
        "calculation": None,
        "source_text": str((fields.get("_row") or {}).get("source_text", "") or ""),
        "legacy": True,
    }


def fact_from_row(row: dict, corrections: Optional[dict] = None) -> dict:
    stored = _stored(row)
    if stored.get("schema") == SCHEMA:
        fact = {name: stored.get("fact", {}).get(name) for name in FACT_FIELDS}
        base = {
            "fact": fact,
            "status": stored.get("status") or UNCERTAIN,
            "review": stored.get("review") or {},
            "calculation": stored.get("calculation"),
            "source_text": stored.get("source_text") or "",
            "legacy": False,
        }
    else:
        base = _legacy_fact(row, corrections or {})
    # Facts stored before visual-order Arabic was fixed at extraction.
    for name in TEXT_FIELDS:
        base["fact"][name] = fix_visual_arabic(base["fact"].get(name))
    base["source_text"] = fix_visual_arabic(base["source_text"])
    base["review"] = fix_structure(base["review"])
    return base


def _resolution_payload(correction_row: dict) -> dict:
    try:
        payload = json.loads(correction_row.get("corrected_value") or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    payload.setdefault("by", correction_row.get("corrected_by", ""))
    payload.setdefault("at", correction_row.get("corrected_at", ""))
    return payload


def latest_resolutions(correction_rows: list[dict]) -> dict:
    """row_id -> {"final": latest confirm/correct/ignore, "proposal": latest
    explanation-based proposal}. correction_rows must be in time order."""
    result: dict = {}
    for row in correction_rows:
        if str(row.get("field_name", "")) != RESOLUTION_FIELD:
            continue
        payload = _resolution_payload(row)
        action = payload.get("action")
        slot = result.setdefault(str(row.get("row_id", "")), {})
        if action in RESOLVE_ACTIONS:
            slot["final"] = payload
            slot.pop("proposal", None)
        elif action == PROPOSAL_ACTION:
            slot["proposal"] = payload
    return result


def effective_fact(row: dict, corrections: Optional[dict] = None, resolutions: Optional[dict] = None) -> dict:
    """The fact as the ledger should see it after the user's decisions."""
    base = fact_from_row(row, corrections)
    resolution = (resolutions or {}).get(str(row.get("row_id", ""))) or {}
    final = resolution.get("final")
    fact = dict(base["fact"])
    status = base["status"]
    corrected = []
    note = ""

    if final:
        action = final.get("action")
        note = str(final.get("explanation") or "")
        if action == "ignore":
            status = IGNORED
        elif action == "confirm":
            status = USER_CONFIRMED
        elif action == "correct":
            for name, value in (final.get("fields") or {}).items():
                if name in FACT_FIELDS and fact.get(name) != value:
                    fact[name] = value
                    corrected.append(name)
            status = USER_CORRECTED

    return {
        **base,
        "row_id": str(row.get("row_id", "")),
        "page_id": str(row.get("page_id", "")),
        "case_document_id": str(row.get("case_document_id", "")),
        "page_number": row.get("page_number", ""),
        "fact": fact,
        "status": status,
        "corrected_fields": corrected,
        "user_note": note,
        "resolved_by": (final or {}).get("by", ""),
        "proposal": None if final else resolution.get("proposal"),
    }


# -----------------------------------------------------------------------------
# Ledger and review queue
# -----------------------------------------------------------------------------
def ledger_entry(item: dict) -> dict:
    fact = item["fact"]
    field, value = primary_value(fact)
    direction = "debit" if fact.get("debit") else "credit" if fact.get("credit") else ""
    entry = {
        "row_id": item["row_id"],
        "page_id": item["page_id"],
        "case_document_id": item["case_document_id"],
        "page_number": item["page_number"],
        **fact,
        "value": format_amount(value) if value is not None else None,
        "value_field": field,
        "status": item["status"],
        "corrected_fields": item.get("corrected_fields", []),
        "user_note": item.get("user_note", ""),
        "source_text": item.get("source_text", ""),
        # Names older consumers (timeline, pleading context) read.
        "debit_or_credit": direction,
        "reference_number": fact.get("transaction_reference") or "",
        "row_status": item["status"],
    }
    if entry["amount"] is None and value is not None:
        entry["amount"] = format_amount(value)
    return entry


def _sort_key(entry: dict) -> tuple:
    date = str(entry.get("date") or "")
    digits = re.sub(r"[^0-9]", "", date)
    try:
        page = int(float(entry.get("page_number") or 0))
    except (TypeError, ValueError):
        page = 0
    return (0 if digits else 1, date, str(entry.get("case_document_id", "")), page)


def build_fact_ledger(rows: list[dict], corrections: Optional[dict] = None,
                      resolutions: Optional[dict] = None) -> tuple[list[dict], int]:
    """(ledger entries, facts withheld because they await the user).

    The ledger holds every fact whose status is final (extracted,
    calculated, inferred, missing, user-confirmed, user-corrected);
    UNCERTAIN facts are withheld until resolved, IGNORED ones are left out.
    """
    ledger, withheld = [], 0
    for row in rows:
        item = effective_fact(row, corrections, resolutions)
        if item["status"] == UNCERTAIN:
            withheld += 1
        elif item["status"] in LEDGER_STATUSES:
            ledger.append(ledger_entry(item))
    ledger.sort(key=_sort_key)
    return ledger, withheld


def count_uncertain(rows: list[dict], corrections: Optional[dict] = None,
                    resolutions: Optional[dict] = None) -> int:
    """Number of facts still waiting for the user (cheap: no page text)."""
    return sum(1 for row in rows if effective_fact(row, corrections, resolutions)["status"] == UNCERTAIN)


def _page_excerpt(page_text: str, needles: list[str], width: int = 260) -> str:
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


def build_fact_review_items(rows: list[dict], corrections: Optional[dict], resolutions: Optional[dict],
                            pages_by_id: dict) -> list[dict]:
    """One review item per UNCERTAIN fact, with the evidence to decide it:
    the AI's interpretation and reason, the text as printed, the page
    context, any failed calculation check, and a pending proposal made
    from the user's explanation."""
    items = []
    for row in rows:
        item = effective_fact(row, corrections, resolutions)
        if item["status"] != UNCERTAIN:
            continue
        page = pages_by_id.get(item["page_id"]) or {}
        fact = item["fact"]
        raw = _stored(row).get("raw") or {}
        needles = [item["source_text"][:60], *raw.values(), *(fact.get(n) or "" for n in AMOUNT_FIELDS)]
        items.append({
            "row_id": item["row_id"],
            "page_id": item["page_id"],
            "page_number": item["page_number"],
            "page_label": page.get("label", ""),
            "fact": fact,
            "review": item["review"],
            "calculation": item.get("calculation"),
            "source_text": item["source_text"],
            "page_excerpt": fix_visual_arabic(_page_excerpt(page.get("page_text", ""), needles)),
            "proposal": item.get("proposal"),
            "legacy": item["legacy"],
        })

    def order(entry):
        try:
            page = int(float(entry.get("page_number") or 0))
        except (TypeError, ValueError):
            page = 0
        return (str(entry.get("page_label", "")), page, entry["row_id"])

    return sorted(items, key=order)


def validate_fact_fields(fields: dict) -> tuple[dict, list[str]]:
    """Clean user-entered fact fields: amounts must be numbers, fact_type
    is snake_case, unknown keys are dropped. Returns (clean, errors)."""
    clean, errors = {}, []
    for name, value in (fields or {}).items():
        if name not in FACT_FIELDS:
            continue
        if name in AMOUNT_FIELDS:
            text = _clean(value)
            if text is None:
                clean[name] = None
                continue
            amount = parse_amount(value)
            if amount is None:
                errors.append(f"{name.replace('_', ' ')}: '{text}' is not a number")
            else:
                clean[name] = format_amount(amount)
        elif name == "fact_type":
            clean[name] = _snake(value)
        elif name == "currency":
            clean[name] = _currency(value)
        else:
            clean[name] = _clean(value)
    return clean, errors
