"""
The calculator: checking and correcting the numbers of a page by arithmetic.
Location: lib/python/legal_platform/money_check.py

Runs on a page's final text after the readings are merged, whenever the page
holds money figures, for any document:

  1. structure   The text LLM copies the page's money rows into JSON, values
                 exactly as written (no calculation): date, description,
                 amount or debit / credit, balance, amounts mentioned inside
                 the description; opening / closing balance; totals; invoice
                 lines (quantity, unit price, line total), subtotal, tax, total.
  2. check       Code checks everything that can be checked:
                   running balance   previous balance +/- movement = balance
                   totals            debit / credit / amount totals = sum of rows
                   opening->closing  opening + all movements = closing balance
                   description       an amount written in the description =
                                     the row's amount
                   invoice           quantity x unit price = line total;
                                     lines = subtotal; subtotal + tax = total
  3. correct     A value is corrected only when the arithmetic PROVES it:
                   - the corrected value follows from figures that are
                     themselves confirmed by another check (e.g. an amount
                     from two balances that each reconcile with their other
                     neighbour), and
                   - it is a plausible misreading of what was read: the same
                     digits except one or two (2/3, 1/7, 5/6, 0/8 ...), one
                     digit more or less, or the sign.
                 Anything else is listed for review, never changed.
  4. apply       Proven corrections are written into the page text in the
                 value's own style (Arabic-Indic or Latin digits, separators),
                 inside that row only, and recorded with what was read.

The LLM never calculates or chooses a number; all arithmetic is Decimal code.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, List, Optional, Tuple

TextLLM = Callable[[str, dict], dict]

_TO_LATIN = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬−", "01234567890123456789.,-")
_TO_ARABIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


# ---------------------------------------------------------------------------
# Numbers as written
# ---------------------------------------------------------------------------
def to_number(raw: Any) -> Optional[Decimal]:
    """A written amount as an exact Decimal: Arabic-Indic or Latin digits,
    thousands separators, a minus sign or brackets, a currency word around
    it. None when it is not one readable amount."""
    if raw is None:
        return None
    text = str(raw).translate(_TO_LATIN)
    text = re.sub(r"(?i)(sar|jod|kwd|bhd|omr|aed|egp|usd|eur|ريال|دينار|جنيه|درهم|ر\.س|\s)", "", text)
    negative = text.startswith("-") or text.endswith("-") or (text.startswith("(") and text.endswith(")"))
    text = text.strip("()+-")
    if not re.fullmatch(r"\d[\d,]*(\.\d+)?|\d+", text):
        return None
    try:
        value = Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None
    return -value if negative else value


def write_like(value: Decimal, raw: str) -> str:
    """A corrected value written in the style of the value it replaces:
    same digit script, decimal places, thousands separator and sign style."""
    raw = str(raw)
    arabic = bool(re.search(r"[٠-٩]", raw))
    latin_view = raw.translate(_TO_LATIN)
    places = len(latin_view.split(".")[1].rstrip(")- ")) if "." in latin_view else 0
    grouped = "," in latin_view.split(".")[0]
    text = f"{abs(value):,.{places}f}" if grouped else f"{abs(value):.{places}f}"
    if arabic:
        text = text.translate(_TO_ARABIC).replace(",", "٬" if "٬" in raw else ",").replace(
            ".", "٫" if "٫" in raw else ".")
    prefix = re.match(r"^\s*([A-Za-z]{3})\s*", raw)               # "SAR200.00" keeps "SAR"
    if value < 0:
        text = f"({text})" if raw.strip().startswith("(") else "-" + text
    return (prefix.group(1) if prefix else "") + text


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value).translate(_TO_LATIN))


def plausible_misreading(raw: Any, correct: Decimal) -> bool:
    """Could `raw` be `correct` misread? Same digits but one or two, one digit
    added or dropped, or only the sign differs."""
    read, right = _digits(raw), _digits(write_like(correct, str(raw)))
    if read == right:
        return True                                            # sign / separator only
    if len(read) == len(right):
        return sum(a != b for a, b in zip(read, right)) <= 2
    if abs(len(read) - len(right)) == 1:
        longer, shorter = (read, right) if len(read) > len(right) else (right, read)
        return any(longer[:i] + longer[i + 1:] == shorter for i in range(len(longer)))
    return False


# ---------------------------------------------------------------------------
# 1. Structure (LLM: copying only)
# ---------------------------------------------------------------------------
STRUCTURE_PROMPT = """
/no_think
Copy the money figures of this page into JSON. COPY ONLY: every value exactly
as written in the text (same digits, same script, same separators and sign).
Never calculate, never correct, never fill a value that is not written.

Return JSON only:
{
  "kind": "statement | invoice | other",
  "rows": [{
     "date": "as written or empty",
     "description_start": "the first 3-6 words of the row's description, as written",
     "amount": "the row's single amount column value, or empty",
     "debit": "", "credit": "",
     "balance": "the row's balance, or empty",
     "description_amounts": ["any amount written INSIDE the description, as written, e.g. SAR300.00"],
     "quantity": "", "unit_price": "", "line_total": ""
  }],
  "opening_balance": "", "closing_balance": "",
  "total_debit": "", "total_credit": "", "total_amount": "",
  "subtotal": "", "tax": "", "grand_total": ""
}
Rows are in page order; one entry per transaction or invoice line (a
description spread over several lines is one row). Leave a field empty when
the page does not show it.
""".strip()


def structure(text: str, text_llm: TextLLM) -> dict:
    try:
        answer = text_llm(STRUCTURE_PROMPT, {"page_text": text[:12000]})
    except Exception as error:
        return {"rows": [], "error": f"{type(error).__name__}: {error}"}
    if not isinstance(answer, dict):
        return {"rows": []}
    answer["rows"] = [r for r in answer.get("rows") or [] if isinstance(r, dict)]
    return answer


# ---------------------------------------------------------------------------
# 2-3. Checks and proven corrections
# ---------------------------------------------------------------------------
def _movement(row: dict) -> Tuple[Optional[Decimal], str]:
    """The row's signed movement and the field it comes from."""
    debit, credit, amount = to_number(row.get("debit")), to_number(row.get("credit")), to_number(row.get("amount"))
    if debit is not None or credit is not None:
        return (credit or Decimal(0)) - abs(debit or Decimal(0)), "debit" if debit is not None else "credit"
    if amount is not None:
        return amount, "amount"
    return None, ""


def _set(row: dict, field: str, value: Decimal) -> None:
    """A field's new value, written in the style of what was read."""
    raw = str(row.get(field) or "")
    if field == "debit":
        value = abs(value)
    row[field] = write_like(value, raw)


def check_and_correct(data: dict) -> dict:
    """Run every check, make the proven corrections, list the rest.
    Returns {checks, corrections, unresolved, rows}."""
    rows = [dict(r) for r in data.get("rows") or []]
    checks: List[dict] = []
    corrections: List[dict] = []
    unresolved: List[dict] = []

    def correct(index: Optional[int], field: str, read: str, value: Decimal, reason: str, where: str) -> bool:
        if not plausible_misreading(read, value):
            unresolved.append({"row": index, "field": field, "read": read,
                               "arithmetic_says": write_like(value, read), "reason": reason +
                               " (too different from what was read to be a misreading: not changed)"})
            return False
        corrections.append({"row": index, "field": field, "where": where, "read": read,
                            "corrected": write_like(value, read), "reason": reason})
        return True

    # Running balance -------------------------------------------------------------
    opening = to_number(data.get("opening_balance"))
    closing = to_number(data.get("closing_balance"))
    balances = [to_number(r.get("balance")) for r in rows]
    moves = [_movement(r) for r in rows]
    # A single amount column printed without signs: the balance shows the direction.
    unsigned = all(m is None or f != "amount" or m >= 0 for m, f in moves) and \
        any(f == "amount" for _, f in moves)

    def before_of(i: int) -> Optional[Decimal]:
        return opening if i == 0 else balances[i - 1]

    def holds(i: int) -> Optional[bool]:
        before, (move, field), after = before_of(i), moves[i], balances[i]
        if before is None or move is None or after is None:
            return None
        if unsigned and field == "amount":
            return before + move == after or before - move == after
        return before + move == after

    def confirmed_after(i: int) -> bool:
        """Row i's balance is confirmed from the other side: the next row
        reconciles from it, or it is the last row and equals the closing balance."""
        if i + 1 < len(rows):
            return holds(i + 1) is True
        return closing is not None and balances[i] == closing

    def confirmed_before(i: int) -> bool:
        return opening is not None if i == 0 else (i - 1 == 0 and opening is None and balances[0] is not None) \
            or holds(i - 1) is True

    if sum(b is not None for b in balances) >= 2:
        for i in range(len(rows)):
            result = holds(i)
            if result is None:
                continue
            checks.append({"check": "running balance", "row": i, "ok": result})
            if result:
                continue
            before, (move, field), after = before_of(i), moves[i], balances[i]
            needed = after - before
            where = rows[i].get("description_start", "")
            # (a) the movement was misread: the balances on both sides are confirmed.
            if field and confirmed_before(i) and confirmed_after(i):
                if field == "amount":
                    value = abs(needed) if unsigned else needed
                elif field == "debit" and needed < 0:
                    value = abs(needed)
                elif field == "credit" and needed > 0:
                    value = needed
                else:
                    value = None
                if value is not None and correct(i, field, str(rows[i].get(field)), value,
                                                 f"running balance: {before} -> {after} needs a movement of {needed:+}",
                                                 where):
                    _set(rows[i], field, value)
                    moves[i] = _movement(rows[i])
                    checks[-1]["ok"] = holds(i) is True
                    continue
            # (b) the balance was misread: the next row reconciles from the computed balance.
            step = move if not (unsigned and field == "amount") else None
            if step is not None and i + 1 < len(rows) and moves[i + 1][0] is not None \
                    and balances[i + 1] is not None and before + step + moves[i + 1][0] == balances[i + 1]:
                computed = before + step
                if correct(i, "balance", str(rows[i].get("balance")), computed,
                           f"running balance: {before} {step:+} = {computed}, confirmed by the next row", where):
                    _set(rows[i], "balance", computed)
                    balances[i] = computed
                    checks[-1]["ok"] = True
                    continue
            unresolved.append({"row": i, "field": "balance / amount", "read": f"{before} {move:+} -> {after}",
                               "reason": "the running balance does not add up and no single proven "
                                         "misreading explains it"})

    # Amounts written inside descriptions = the row's (checked) amount ------------------
    for i, row in enumerate(rows):
        move, field = _movement(row)
        if move is None:
            continue
        fixed = []
        for raw in row.get("description_amounts") or []:
            value = to_number(raw)
            if value is None:
                continue
            ok = abs(value) == abs(move)
            checks.append({"check": "amount in description", "row": i, "ok": ok})
            if ok:
                fixed.append(raw)
                continue
            row_confirmed = holds(i) is not False                    # the row's own amount is not in doubt
            if row_confirmed and correct(i, "description_amount", str(raw), abs(move),
                                         f"the row's amount is {abs(move)}", row.get("description_start", "")):
                fixed.append(write_like(abs(move), str(raw)))
            else:
                fixed.append(raw)
        row["description_amounts"] = fixed

    # Totals ------------------------------------------------------------------------------
    debits = [abs(m) for m, f in (_movement(r) for r in rows) if m is not None and m < 0]
    credits = [m for m, f in (_movement(r) for r in rows) if m is not None and m > 0]
    for name, values, sign in (("total_debit", debits, -1), ("total_credit", credits, 1)):
        total = to_number(data.get(name))
        if total is None or not values:
            continue
        ok = abs(total) == sum(values)
        checks.append({"check": name.replace("_", " "), "ok": ok})
        if not ok:
            chain_ok = all(c["ok"] for c in checks if c["check"] == "running balance")
            if chain_ok and correct(None, name, str(data.get(name)), sum(values) * (1 if total >= 0 else -1),
                                    f"the rows add up to {sum(values)} and every row reconciles", "totals"):
                data = dict(data, **{name: write_like(sum(values) * (1 if total >= 0 else -1), str(data[name]))})
            elif not chain_ok:
                unresolved.append({"row": None, "field": name, "read": str(data.get(name)),
                                   "reason": f"the rows add up to {sum(values)}"})
    total_amount = to_number(data.get("total_amount"))
    amounts = [to_number(r.get("amount")) for r in rows if to_number(r.get("amount")) is not None]
    if total_amount is not None and amounts and not debits and not credits:
        ok = total_amount == sum(amounts)
        checks.append({"check": "total amount", "ok": ok})
        if not ok:
            unresolved.append({"row": None, "field": "total_amount", "read": str(data.get("total_amount")),
                               "reason": f"the rows add up to {sum(amounts)}"})

    # Opening + movements = closing ----------------------------------------------------------
    all_moves = [m for m, _ in (_movement(r) for r in rows) if m is not None]
    if opening is not None and closing is not None and all_moves:
        checks.append({"check": "opening + movements = closing", "ok": opening + sum(all_moves) == closing})
        if opening + sum(all_moves) != closing:
            unresolved.append({"row": None, "field": "closing_balance", "read": str(data.get("closing_balance")),
                               "reason": f"opening {opening} + movements {sum(all_moves)} = {opening + sum(all_moves)}"})

    # Invoices ----------------------------------------------------------------------------------
    lines = []
    for i, row in enumerate(rows):
        quantity, price, line = (to_number(row.get(k)) for k in ("quantity", "unit_price", "line_total"))
        if quantity is not None and price is not None and line is not None:
            ok = quantity * price == line
            checks.append({"check": "quantity x price", "row": i, "ok": ok})
            if not ok:
                unresolved.append({"row": i, "field": "line_total", "read": str(row.get("line_total")),
                                   "reason": f"{quantity} x {price} = {quantity * price}"})
        if line is not None:
            lines.append(line)
    subtotal, tax, grand = (to_number(data.get(k)) for k in ("subtotal", "tax", "grand_total"))
    if subtotal is not None and lines:
        checks.append({"check": "lines = subtotal", "ok": sum(lines) == subtotal})
        if sum(lines) != subtotal:
            unresolved.append({"row": None, "field": "subtotal", "read": str(data.get("subtotal")),
                               "reason": f"the lines add up to {sum(lines)}"})
    if subtotal is not None and tax is not None and grand is not None:
        checks.append({"check": "subtotal + tax = total", "ok": subtotal + tax == grand})
        if subtotal + tax != grand:
            unresolved.append({"row": None, "field": "grand_total", "read": str(data.get("grand_total")),
                               "reason": f"{subtotal} + {tax} = {subtotal + tax}"})

    return {"checks": checks, "corrections": corrections, "unresolved": unresolved, "rows": rows}


# ---------------------------------------------------------------------------
# 4. Writing the corrections into the text
# ---------------------------------------------------------------------------
def _row_spans(text: str, rows: List[dict]) -> List[Tuple[int, int]]:
    """Where each row sits in the page text: from its date / description to
    the next row's start."""
    starts, cursor = [], 0
    for row in rows:
        position = -1
        for key in ("date", "description_start"):
            needle = str(row.get(key) or "").strip()
            if needle:
                found = text.find(needle[:40], cursor)
                if found >= 0:
                    position = found
                    break
        starts.append(position if position >= 0 else cursor)
        cursor = max(cursor, starts[-1] + 1)
    ends = starts[1:] + [len(text)]
    return list(zip(starts, ends))


def apply(text: str, data: dict, result: dict, mark: bool = False) -> Tuple[str, List[dict]]:
    """The page text with the proven corrections written in place; each
    correction records whether it was found in the text."""
    rows = data.get("rows") or []
    spans = _row_spans(text, rows)
    applied = []
    for correction in result["corrections"]:
        read, new = correction["read"], correction["corrected"]
        if correction["row"] is None:                           # a total: after the last row
            start, end = (spans[-1][0] if spans else 0), len(text)
        else:
            start, end = spans[correction["row"]] if correction["row"] < len(spans) else (0, len(text))
        segment = text[start:end]
        replacement = new + (f" [calculated; read {read}]" if mark else "")
        if read and read in segment:
            text = text[:start] + segment.replace(read, replacement, 1) + text[end:]
            shift = len(replacement) - len(read)
            spans = [(s + (shift if s > start else 0), e + (shift if e > start else 0)) for s, e in spans]
            applied.append(dict(correction, applied=True))
        else:
            applied.append(dict(correction, applied=False))
    return text, applied


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
def run(text: str, text_llm: TextLLM, mark: bool = False) -> dict:
    """Structure the page's money figures, check them, apply what the
    arithmetic proves. Returns {text, corrections, unresolved, checks, data}."""
    data = structure(text, text_llm)
    if not data.get("rows"):
        return {"text": text, "corrections": [], "unresolved": [], "checks": [], "data": data,
                "note": data.get("error") or "no money rows to check"}
    result = check_and_correct(data)
    new_text, applied = apply(text, data, result, mark)
    return {"text": new_text, "corrections": applied, "unresolved": result["unresolved"],
            "checks": result["checks"], "data": data,
            "summary": {"checks": len(result["checks"]), "passed": sum(c["ok"] for c in result["checks"]),
                        "corrected": sum(c["applied"] for c in applied), "unresolved": len(result["unresolved"])}}
