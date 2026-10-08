"""
Multi-view reading of financial pages, consolidated fact by fact.
Location: lib/python/legal_platform/financial_reader.py

Phase 1 of the verified financial extraction:

  1. views       The page as three pictures: the original, a lightly
                 enhanced copy (even light, straightened, letters enlarged)
                 and a sharpened grey copy. The original stays the source
                 of truth.
  2. layout      One look at the page: is it financial, what kind, the
                 currency, and each table's column headers in order.
  3. reading     Every view is read on its own, in horizontal strips of a
                 limited number of text lines (a whole dense page would be
                 shrunk by the model until digits blur). Each view is asked
                 in a different answer format, so the readings are less
                 likely to repeat the same mistake. The model transcribes;
                 it never calculates or corrects.
  4. alignment   The rows of the three readings are matched like a text
                 diff (dates, amounts, descriptions), not by row number, so
                 a skipped or split row does not shift everything after it.
  5. consensus   Every cell is decided on its own from the raw readings
                 (digit scripts unified, separators kept as read):
                 agreed / majority / disagree.
  6. arithmetic  Header words and the running balance decide the money
                 columns; where the readings disagree, a reading that makes
                 the balance chain hold is preferred; the chain is checked
                 row by row (statement_reader.reconcile).
  7. status      A fact is "verified" only when the views agree and, for
                 money in a statement, the arithmetic holds. Everything
                 else is "needs_check" (phase 2 re-reads it from a crop of
                 the original page; what stays uncertain goes to the user).

Every fact keeps its raw reading from each view, for audit.
The vision model is passed in as vision(prompt, png) -> text.
"""

from __future__ import annotations

import difflib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from . import image_tables as it
from .statement_reader import _json, column_role, parse_amount, reconcile, table_decimals

VisionCall = Callable[[str, bytes], str]

VIEW_NAMES = ("original", "enhanced", "sharpened")
STRIP_LINES = 18               # text lines per strip; a strip overlaps the next by one line
MAX_CALL_PIXELS = 2_500_000    # larger pictures are reduced before they are sent
MONEY_ROLES = ("debit", "credit", "balance", "amount")


# ---------------------------------------------------------------------------
# 1. Views
# ---------------------------------------------------------------------------
def make_views(image: np.ndarray, names: Tuple[str, ...] = VIEW_NAMES) -> Dict[str, np.ndarray]:
    """The page as independent pictures. 'original' is untouched (only a
    very small image is enlarged); 'enhanced' is image_tables.prepare_page
    (photos straightened and evened out, letters ~24 px); 'sharpened' is the
    enhanced page with an unsharp mask."""
    views: Dict[str, np.ndarray] = {}
    original = image
    if max(image.shape[:2]) < 1000:
        original = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    if "original" in names:
        views["original"] = original
    if "enhanced" in names or "sharpened" in names:
        enhanced = it.prepare_page(image).read
        if "enhanced" in names:
            views["enhanced"] = enhanced
        if "sharpened" in names:
            blur = cv2.GaussianBlur(enhanced, (0, 0), 1.2)
            views["sharpened"] = cv2.addWeighted(enhanced, 1.6, blur, -0.6, 0)
    return views


def _gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image


def _png(image: np.ndarray, max_pixels: int = MAX_CALL_PIXELS) -> bytes:
    height, width = image.shape[:2]
    factor = min(1.0, (max_pixels / float(height * width)) ** 0.5)
    if factor < 1.0:
        image = cv2.resize(image, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    return it.to_png(image)


# ---------------------------------------------------------------------------
# 2. Strips
# ---------------------------------------------------------------------------
def line_bands(image: np.ndarray) -> List[Tuple[int, int]]:
    """Text lines as (y0, y1): runs of rows that hold text ink. Printed
    rules (solid or dotted) are removed first, and bands much shorter than
    a letter (dots, specks) do not count as lines."""
    gray = _gray(image)
    ink = it.text_ink(gray, it.is_digital(gray))
    letter = it.ink_height(ink) or 20.0
    horizontal, vertical = it._line_masks(gray, letter, ink=ink)
    ink = cv2.subtract(ink, cv2.bitwise_or(horizontal, vertical))
    profile = (ink > 0).sum(axis=1)
    threshold = max(2, 0.01 * gray.shape[1])
    bands, start = [], None
    for y, value in enumerate(list(profile) + [0]):
        if value > threshold and start is None:
            start = y
        elif value <= threshold and start is not None:
            if y - start >= 0.4 * letter:
                bands.append((start, y))
            start = None
    return bands


def strips(image: np.ndarray, lines_per_strip: int = STRIP_LINES) -> List[Tuple[int, int]]:
    """(y0, y1) of horizontal strips holding about `lines_per_strip` text
    lines each, cut in the blank space between lines; each strip repeats the
    last line of the one before (a row cut at an edge is read whole in one
    of them). A short page is one strip."""
    height = image.shape[0]
    bands = line_bands(image)
    if len(bands) <= lines_per_strip + lines_per_strip // 3:
        return [(0, height)]
    out = []
    first = 0
    while first < len(bands):
        last = min(len(bands), first + lines_per_strip) - 1
        if len(bands) - 1 - last < lines_per_strip // 3:      # do not leave a tiny last strip
            last = len(bands) - 1
        y0 = 0 if first == 0 else max(0, (bands[first - 1][1] + bands[first][0]) // 2)
        y1 = height if last == len(bands) - 1 else min(height, (bands[last][1] + bands[last + 1][0]) // 2)
        out.append((y0, y1))
        if last == len(bands) - 1:
            break
        first = last                                          # one line of overlap
    return out


# ---------------------------------------------------------------------------
# 3. Prompts and reading
# ---------------------------------------------------------------------------
LAYOUT_PROMPT = """
Look at this document page and describe its layout. Do not transcribe the
rows. Return JSON only:
{
  "financial": true or false (the page shows amounts of money: transactions,
               balances, payments, an invoice, a transfer, a financial table),
  "kind": "bank statement | transfer list | invoice | receipt | contract | letter | other",
  "currency": "the currency shown, as printed, or empty",
  "tables": [{"columns": ["each column header exactly as printed, in reading
               order (for an Arabic table: from right to left)"]}]
}
A header printed on two lines is one column. List every table on the page.
""".strip()

_RULES = """
Rules:
- Copy every character exactly as printed: digits, Arabic-Indic digits stay
  Arabic-Indic, thousands and decimal separators, signs and brackets.
- Never calculate, correct, complete or guess. Use "" for an empty cell and
  "?" for a character you cannot read.
- One entry per row of the table. A description that wraps onto a second
  line belongs to its row.
- A row cut by the top or bottom edge of the image: leave it out unless
  every value of it is fully visible.
- "type" is transaction, opening (opening / previous balance), closing,
  total, or other.
- Also copy any account number, IBAN, customer name, period, statement
  date or currency printed outside the table as "context".
""".strip()

READ_PROMPTS = {
    "json_rows": """
Transcribe the table rows visible in this image (part {part} of a page).
{columns}
Return JSON only:
{{"rows": [{{"table": 1, "type": "transaction", "cells": ["value of column 1", "value of column 2", ...]}}],
  "context": {{"<field name>": "<value as printed>"}}}}
Each "cells" list follows the column order given above.
""",
    "lines": """
Transcribe the table rows visible in this image (part {part} of a page).
{columns}
Answer as plain text, one line per row, the cells separated by " | ", in the
column order given above:
T<table number> | <type> | <cell 1> | <cell 2> | ...
After the rows, one line per context field:
CONTEXT | <field name> | <value as printed>
""",
    "json_named": """
Transcribe the table rows visible in this image (part {part} of a page).
{columns}
Return JSON only:
{{"rows": [{{"table": 1, "type": "transaction", "values": {{"<column header>": "<value as printed>", ...}}}}],
  "context": {{"<field name>": "<value as printed>"}}}}
Use the column headers given above as the keys.
""",
}
VIEW_STYLES = {"original": "json_rows", "enhanced": "lines", "sharpened": "json_named"}


def _columns_text(tables: List[dict]) -> str:
    if not tables:
        return "Use the table's own column order, from the header row."
    parts = []
    for number, table in enumerate(tables, start=1):
        names = ", ".join(f'"{c}"' for c in table["columns"])
        parts.append(f"Table {number} columns, in reading order: [{names}]")
    return "\n".join(parts)


def read_prompt(style: str, tables: List[dict], part: str) -> str:
    return READ_PROMPTS[style].format(columns=_columns_text(tables), part=part).strip() + "\n\n" + _RULES


def parse_reading(style: str, answer: str, tables: List[dict]) -> Tuple[List[dict], Dict[str, str]]:
    """Rows as {"table": i, "type": t, "cells": [raw values in column order]}
    and context {field: raw}, whatever the answer format."""
    rows: List[dict] = []
    context: Dict[str, str] = {}
    widths = [len(t["columns"]) for t in tables] or [0]

    def fit(cells: List[str], table: int) -> List[str]:
        width = widths[table] if table < len(widths) and widths[table] else len(cells)
        cells = [str(c if c is not None else "").strip() for c in cells]
        return (cells + [""] * width)[:width]

    def table_index(value: Any) -> int:
        digits = re.sub(r"\D", "", str(value or "1"))
        return max(0, min(len(widths) - 1, int(digits or 1) - 1))

    if style == "lines":
        text = re.sub(r"<think>.*?</think>", "", str(answer or ""), flags=re.S)
        for line in text.splitlines():
            parts = [p.strip() for p in line.strip().strip("`").split("|")]
            if len(parts) >= 3 and parts[0].upper() == "CONTEXT":
                context[parts[1]] = " | ".join(parts[2:])
            elif len(parts) >= 3 and re.fullmatch(r"[Tt]\s*\d+", parts[0]):
                table = table_index(parts[0])
                rows.append({"table": table, "type": parts[1].lower() or "transaction",
                             "cells": fit(parts[2:], table)})
        return rows, context

    data = _json(answer)
    for raw in data.get("rows") or []:
        if not isinstance(raw, dict):
            continue
        table = table_index(raw.get("table"))
        if style == "json_named" and isinstance(raw.get("values"), dict):
            values = raw["values"]
            names = tables[table]["columns"] if table < len(tables) else list(values)
            keyed = {re.sub(r"\s+", " ", str(k)).strip(): v for k, v in values.items()}
            cells = [keyed.get(re.sub(r"\s+", " ", name).strip(), "") for name in names]
            if not any(cells) and values:             # headers renamed by the model: keep its order
                cells = list(values.values())
        else:
            cells = raw.get("cells") if isinstance(raw.get("cells"), list) else []
        rows.append({"table": table, "type": str(raw.get("type") or "transaction").lower(),
                     "cells": fit(cells, table)})
    for name, value in (data.get("context") or {}).items() if isinstance(data.get("context"), dict) else []:
        if value not in (None, ""):
            context[str(name)] = str(value)
    return rows, context


# ---------------------------------------------------------------------------
# 4. Comparing raw readings
# ---------------------------------------------------------------------------
_DIGIT_SCRIPTS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٬٫", "01234567890123456789,.")


def canon(raw: Any) -> str:
    """A raw reading in a comparable form: digit scripts unified (Arabic-
    Indic and Persian digits, Arabic separators to their Latin equivalents),
    spaces and case ignored. Separators themselves are kept, so a comma read
    as a point is still a difference."""
    text = str(raw or "").translate(_DIGIT_SCRIPTS)
    text = re.sub(r"[‎‏؜ـ]", "", text)        # direction marks, tatweel
    return re.sub(r"\s+", "", text).lower()


def _has_digit(text: str) -> bool:
    return bool(re.search(r"\d", text))


def row_similarity(a: dict, b: dict) -> float:
    """0-1: how surely two readings are the same row. Cells with digits
    (dates, amounts, references) weigh double; text is compared loosely."""
    if a["table"] != b["table"]:
        return 0.0
    score = weight = 0.0
    for x, y in zip(a["cells"], b["cells"]):
        cx, cy = canon(x), canon(y)
        if not cx and not cy:
            continue
        w = 2.0 if _has_digit(cx) or _has_digit(cy) else 1.0
        weight += w
        if cx == cy:
            score += w
        elif cx and cy and not (_has_digit(cx) or _has_digit(cy)):
            score += w * max(0.0, difflib.SequenceMatcher(None, cx, cy).ratio() - 0.2) / 0.8
        elif cx and cy:
            # One digit misread still points to the same row.
            score += w * 0.6 * difflib.SequenceMatcher(None, cx, cy).ratio()
    return score / weight if weight else 0.0


def merge_strips(strip_rows: List[List[dict]]) -> List[dict]:
    """One view's rows from its strips, the line repeated at each overlap
    kept once."""
    rows: List[dict] = []
    for part in strip_rows:
        start = 0
        for index, row in enumerate(part[:3]):
            if any(row_similarity(row, previous) >= 0.8 for previous in rows[-3:]):
                start = index + 1
        rows.extend(part[start:])
    return rows


def align(readings: Dict[str, List[dict]], threshold: float = 0.5) -> List[Dict[str, dict]]:
    """Rows of several readings matched into slots {view: row}, in page
    order, like a diff: a row missing from one reading leaves a gap there
    instead of shifting every row after it."""
    slots: List[Dict[str, dict]] = []
    for view, rows in readings.items():
        if not slots:
            slots = [{view: row} for row in rows]
            continue
        n, m = len(slots), len(rows)
        score = np.zeros((n + 1, m + 1))
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                similarity = max(row_similarity(r, rows[j - 1]) for r in slots[i - 1].values())
                match = score[i - 1, j - 1] + (similarity - threshold if similarity >= threshold else -1e9)
                score[i, j] = max(match, score[i - 1, j], score[i, j - 1])
        merged: List[Dict[str, dict]] = []
        i, j = n, m
        while i > 0 or j > 0:
            if i > 0 and j > 0:
                similarity = max(row_similarity(r, rows[j - 1]) for r in slots[i - 1].values())
                if similarity >= threshold and np.isclose(score[i, j], score[i - 1, j - 1] + similarity - threshold):
                    merged.append(dict(slots[i - 1], **{view: rows[j - 1]}))
                    i, j = i - 1, j - 1
                    continue
            if i > 0 and (j == 0 or score[i, j] == score[i - 1, j]):
                merged.append(slots[i - 1])
                i -= 1
            else:
                merged.append({view: rows[j - 1]})
                j -= 1
        slots = list(reversed(merged))
    return slots


def vote(candidates: Dict[str, str], views: List[str]) -> dict:
    """One cell decided from its raw readings: the most common comparable
    form wins; the raw text kept is the one read from the earliest view
    (the original first). A view that has no reading of the row counts as
    a dissent."""
    present = {v: str(candidates[v]) for v in views if v in candidates}
    groups: Dict[str, List[str]] = {}
    for view in views:
        if view in present:
            groups.setdefault(canon(present[view]), []).append(view)
    if not groups:
        return {"raw": "", "readings": {}, "agreement": "missing"}
    best = max(groups, key=lambda k: (len(groups[k]), -views.index(groups[k][0])))
    count = len(groups[best])
    if count == len(views):
        agreement = "agreed"
    elif count * 2 > len(views):
        agreement = "majority"
    elif len(views) == 1:
        agreement = "single"
    else:
        agreement = "disagree"
    return {"raw": present[groups[best][0]], "readings": {v: present[v] for v in views if v in present},
            "agreement": agreement, "candidates": [present[g[0]] for g in groups.values()]}


# ---------------------------------------------------------------------------
# 5. Arithmetic
# ---------------------------------------------------------------------------
def _roles(headers: List[str], rows: List[dict], decimals: int) -> Tuple[List[str], List[str]]:
    """A role per column: header words first; money columns then decided by
    the running balance (layout_reader.arithmetic_roles)."""
    from .layout_reader import arithmetic_roles, _looks_amount, _looks_date
    roles: List[str] = []
    for index, header in enumerate(headers):
        role = column_role(header)
        values = [canon(r["cells"][index]["raw"]) for r in rows if index < len(r["cells"]) and r["cells"][index]["raw"]]
        if role == "other" and values:
            if sum(_looks_amount(v) for v in values) >= 0.6 * len(values):
                role = "amount"
            elif sum(_looks_date(v) for v in values) >= 0.6 * len(values):
                role = "date"
        name, count = role, 2
        while name in roles:
            name, count = f"{role}_{count}", count + 1
        roles.append(name)
    shaped = [{"cells": {roles[i]: {"text": canon(cell["raw"])} for i, cell in enumerate(r["cells"])}}
              for r in rows if r["type"] == "transaction"]
    mapping, note = arithmetic_roles(shaped, decimals)
    if mapping:
        roles = [mapping.get(role, role) for role in roles]
    return roles, [note] if note else []


def _money(row: dict, role: str, decimals: int) -> Optional[Decimal]:
    cell = row["by_role"].get(role)
    return parse_amount(canon(cell["raw"]), decimals) if cell else None


def _fits(previous: Optional[Decimal], debit: Optional[Decimal], credit: Optional[Decimal],
          amount: Optional[Decimal], balance: Optional[Decimal]) -> bool:
    if previous is None or balance is None:
        return False
    if amount is not None and debit is None and credit is None:
        return previous + amount == balance or previous - abs(amount) == balance or previous + abs(amount) == balance
    return previous - (debit or Decimal(0)) + (credit or Decimal(0)) == balance


def _resolve_by_balance(rows: List[dict], decimals: int) -> None:
    """Where the views disagree on a money cell, prefer the reading that
    makes this row (and, for a balance, the next row) add up."""
    transactions = [r for r in rows if r["type"] == "transaction"]
    for index, row in enumerate(transactions):
        previous = _money(transactions[index - 1], "balance", decimals) if index else None
        following = transactions[index + 1] if index + 1 < len(transactions) else None
        for role in MONEY_ROLES:
            cell = row["by_role"].get(role)
            if not cell or cell["agreement"] in ("agreed", "missing") or len(cell.get("candidates", [])) < 2:
                continue
            fitting = []
            for candidate in cell["candidates"]:
                values = {r: _money(row, r, decimals) for r in MONEY_ROLES}
                values[role] = parse_amount(canon(candidate), decimals)
                ok = _fits(previous, values["debit"], values["credit"], values["amount"], values["balance"])
                if role == "balance" and following is not None:
                    nxt = {r: _money(following, r, decimals) for r in MONEY_ROLES}
                    ok = ok or _fits(values["balance"], nxt["debit"], nxt["credit"], nxt["amount"], nxt["balance"])
                if ok:
                    fitting.append(candidate)
            if len(fitting) == 1 and canon(fitting[0]) != canon(cell["raw"]):
                cell["first_choice"] = cell["raw"]
                cell["raw"] = fitting[0]
                cell["resolved"] = "the running balance holds with this reading"
            elif len(fitting) == 1:
                cell["resolved"] = "the running balance holds with this reading"


def _check_statement(rows: List[dict], decimals: int) -> Dict[str, int]:
    """Running-balance check on the consensus; each money cell gets its
    arithmetic result."""
    transactions = [r for r in rows if r["type"] == "transaction"]
    opening = next((r for r in rows if r["type"] == "opening"), None)
    opening_balance = _money(opening, "balance", decimals) if opening else None
    if opening_balance is None and opening is not None:
        opening_balance = next((parse_amount(canon(c["raw"]), decimals) for c in opening["cells"]
                                if parse_amount(canon(c["raw"]), decimals) is not None), None)
    shaped = []
    for row in transactions:
        item = {r: _money(row, r, decimals) for r in MONEY_ROLES}
        if item["amount"] is not None and item["debit"] is None and item["credit"] is None:
            item["debit" if item["amount"] < 0 else "credit"] = abs(item["amount"])
        shaped.append(item)
    checked = reconcile(shaped, decimals, opening_balance)
    for row, result in zip(transactions, checked):
        row["arithmetic"] = result["status"]
        row["notes"] = [n for n in result.get("notes") or [] if "First balance" not in n]
        for field in ("debit", "credit", "balance"):
            if f"{field}_as_read" in result and field in row["by_role"]:
                row["by_role"][field]["arithmetic_value"] = str(result[field]) if result[field] is not None else ""
    return {status: sum(1 for r in transactions if r.get("arithmetic") == status)
            for status in ("reconciled", "repaired", "first", "unconfirmed", "no_balance")}


# ---------------------------------------------------------------------------
# 6. The page
# ---------------------------------------------------------------------------
def _fact(cell: dict, role: str, decimals: int, row_arithmetic: Optional[str]) -> dict:
    """A consolidated cell as a fact with its status."""
    raw = cell.get("raw", "")
    is_money = role.startswith(MONEY_ROLES) or role.startswith("other_amount")
    normalized = None
    if is_money and raw:
        value = parse_amount(canon(raw), decimals)
        normalized = str(value) if value is not None else None
    elif raw and _has_digit(canon(raw)):
        normalized = canon(raw)
    arithmetic = "n/a"
    if is_money and row_arithmetic:
        arithmetic = {"reconciled": "ok", "first": "ok", "repaired": "repaired",
                      "unconfirmed": "unconfirmed", "no_balance": "n/a"}.get(row_arithmetic, "n/a")
    reasons = []
    if cell.get("agreement") not in ("agreed", None) and raw:
        reasons.append(f"views {cell['agreement']}")
    if is_money and raw and normalized is None:
        reasons.append("not a readable amount")
    if arithmetic in ("repaired", "unconfirmed") and raw:
        reasons.append(f"running balance {arithmetic}")
    if cell.get("resolved") and cell.get("agreement") != "agreed":
        reasons = [r for r in reasons if not r.startswith("views")] + ["views differ; balance picks one"]
    fact = {"raw": raw, "normalized": normalized, "readings": cell.get("readings", {}),
            "agreement": cell.get("agreement", "missing"), "arithmetic": arithmetic,
            "status": "needs_check" if reasons else "verified", "reasons": reasons}
    for key in ("first_choice", "resolved", "arithmetic_value"):
        if cell.get(key):
            fact[key] = cell[key]
    return fact


def _consolidate_context(contexts: Dict[str, Dict[str, str]], views: List[str]) -> Dict[str, dict]:
    """Context fields named alike across views, voted like cells."""
    names: Dict[str, str] = {}
    for context in contexts.values():
        for name in context:
            names.setdefault(re.sub(r"[\s_]+", " ", name).strip().lower(), name)
    out = {}
    for key, name in names.items():
        candidates = {view: value for view, context in contexts.items() for n, value in context.items()
                      if re.sub(r"[\s_]+", " ", n).strip().lower() == key}
        cell = vote(candidates, views)
        if cell["raw"]:
            out[name] = _fact(cell, "context", 2, None)
    return out


def read_financial_page(image_bytes: bytes, vision: VisionCall, views: Tuple[str, ...] = VIEW_NAMES,
                        lines_per_strip: int = STRIP_LINES, parallel: int = 3, debug: bool = False) -> Dict[str, Any]:
    """Read one page image in several views and consolidate it fact by fact."""
    timings: Dict[str, float] = {}
    started = time.time()
    image = it.decode(image_bytes)
    pictures = make_views(image, views)
    names = [v for v in views if v in pictures]
    timings["views"] = round(time.time() - started, 1)

    started = time.time()
    layout_view = "enhanced" if "enhanced" in pictures else names[0]
    layout_answer = vision(LAYOUT_PROMPT, _png(pictures[layout_view]))
    layout = _json(layout_answer)
    tables = [{"columns": [str(c) for c in (t.get("columns") or [])]} for t in layout.get("tables") or []
              if isinstance(t, dict)]
    timings["layout"] = round(time.time() - started, 1)
    result: Dict[str, Any] = {"financial": bool(layout.get("financial")), "kind": layout.get("kind", ""),
                              "currency": layout.get("currency", ""), "views": names,
                              "columns": [t["columns"] for t in tables], "timings": timings}
    if debug:
        result["debug"] = {"layout_answer": layout_answer, "pictures": {}, "answers": {}}
    if not result["financial"]:
        return result

    # Every view, strip by strip, each view in its own answer format.
    jobs = []
    for view in names:
        cuts = strips(pictures[view], lines_per_strip)
        for number, (y0, y1) in enumerate(cuts, start=1):
            jobs.append((view, number, len(cuts), pictures[view][y0:y1], (y0, y1, pictures[view].shape[0])))
    started = time.time()

    def run(job):
        view, number, total, picture, _ = job
        style = VIEW_STYLES.get(view, "json_rows")
        prompt = read_prompt(style, tables, f"{number} of {total}")
        try:
            return job, vision(prompt, _png(picture)), ""
        except Exception as error:               # one failed read leaves a gap, not a crash
            return job, "", f"{type(error).__name__}: {error}"

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        answers = list(pool.map(run, jobs))
    timings["reading"] = round(time.time() - started, 1)

    per_view: Dict[str, List[List[dict]]] = {v: [] for v in names}
    contexts: Dict[str, Dict[str, str]] = {v: {} for v in names}
    errors = []
    for (view, number, total, picture, (y0, y1, height)), answer, error in answers:
        if error:
            errors.append(f"{view} part {number}: {error}")
        rows, context = parse_reading(VIEW_STYLES.get(view, "json_rows"), answer, tables)
        for index, row in enumerate(rows):       # where the row was read: phase 2 crops it from there
            row["where"] = {"strip": number, "pos": index, "of": len(rows), "y0": y0, "y1": y1, "height": height}
        per_view[view].append(rows)
        for name, value in context.items():
            contexts[view].setdefault(name, value)
        if debug:
            result["debug"]["pictures"].setdefault(view, []).append(_png(picture))
            result["debug"]["answers"].setdefault(view, []).append(answer)
    readings = {view: merge_strips(parts) for view, parts in per_view.items()}
    result["passes"] = {view: [{"table": r["table"] + 1, "type": r["type"], "cells": r["cells"]} for r in rows]
                        for view, rows in readings.items()}
    result["errors"] = errors

    # Consolidation, table by table.
    out_tables = []
    count = max([len(tables)] + [r["table"] + 1 for rows in readings.values() for r in rows])
    for index in range(count):
        headers = tables[index]["columns"] if index < len(tables) else []
        by_view = {v: [r for r in rows if r["table"] == index] for v, rows in readings.items()}
        slots = align(by_view)
        width = max([len(headers)] + [len(r["cells"]) for s in slots for r in s.values()])
        headers = (headers + [f"column {i + 1}" for i in range(len(headers), width)])[:width]
        rows = []
        for slot in slots:
            types = vote({v: r["type"] for v, r in slot.items()}, names)
            cells = [vote({v: r["cells"][i] for v, r in slot.items() if i < len(r["cells"])}, names)
                     for i in range(width)]
            rows.append({"type": types["raw"] or "transaction", "cells": cells,
                         "seen_in": [v for v in names if v in slot],
                         "where": {v: r["where"] for v, r in slot.items() if "where" in r}})
        decimals = table_decimals([canon(c["raw"]) for r in rows for c in r["cells"]]) or 2
        roles, notes = _roles(headers, rows, decimals)
        for row in rows:
            row["by_role"] = dict(zip(roles, row["cells"]))
        check = None
        if "balance" in roles and ({"debit", "credit", "amount"} & set(roles)):
            _resolve_by_balance(rows, decimals)
            check = _check_statement(rows, decimals)
        facts_rows = []
        for row in rows:
            facts = {role: _fact(cell, role, decimals, row.get("arithmetic")) for role, cell in row["by_role"].items()
                     if cell.get("raw") or cell.get("readings")}
            missing = [v for v in names if v not in row["seen_in"]]
            if missing:
                for fact in facts.values():
                    if fact["raw"]:
                        fact["status"] = "needs_check"
                        fact["reasons"].append("row not seen in " + ", ".join(missing))
            facts_rows.append({"type": row["type"], "seen_in": row["seen_in"], "where": row["where"],
                               "arithmetic": row.get("arithmetic"), "notes": row.get("notes", []), "facts": facts})
        out_tables.append({"headers": headers, "roles": roles, "decimals": decimals, "check": check,
                           "notes": notes, "rows": facts_rows})
    result["tables"] = out_tables
    result["context"] = _consolidate_context(contexts, names)
    every = [f for t in out_tables for r in t["rows"] for f in r["facts"].values() if f["raw"]] + \
        list(result["context"].values())
    result["summary"] = {"facts": len(every), "verified": sum(f["status"] == "verified" for f in every),
                         "needs_check": sum(f["status"] == "needs_check" for f in every),
                         "calls": 1 + len(jobs)}
    return result


def read_financial_file(data: bytes, filename: str, vision: VisionCall, **options) -> Dict[str, Any]:
    """Every image of a PDF (or one image file), read with read_financial_page."""
    from .layout_reader import sources_from_file
    out = {"file": filename, "pages": []}
    for source in sources_from_file(data, filename):
        entry: Dict[str, Any] = {"page": source.page, "source": source.name, "kind": source.kind}
        try:
            if source.kind == "image":
                entry.update(read_financial_page(source.image, vision, **options))
            else:
                from .layout_reader import _typed_text
                entry["text"] = _typed_text(source.words)
        except Exception as error:
            entry["error"] = f"{type(error).__name__}: {error}"
        out["pages"].append(entry)
    return out


def facts_table(page: Dict[str, Any], table: int = 0) -> List[dict]:
    """A table as flat records for a DataFrame: the consensus value of each
    cell, then its status ('ok' or what needs checking)."""
    records = []
    if table >= len(page.get("tables") or []):
        return records
    for number, row in enumerate(page["tables"][table]["rows"], start=1):
        record: Dict[str, Any] = {"#": number, "type": row["type"]}
        for role, fact in row["facts"].items():
            record[role] = fact["raw"]
        flagged = {role: fact for role, fact in row["facts"].items()
                   if fact["raw"] and fact["status"] not in ("verified", "reverified")}
        changed = [role for role, fact in row["facts"].items() if fact["status"] == "reverified"]
        if flagged:
            record["status"] = "; ".join(
                f"{role}: {fact['status'].replace('_', ' ')} "
                f"({(fact.get('verification') or {}).get('decision') or ', '.join(fact['reasons'])})"
                for role, fact in flagged.items())
        else:
            record["status"] = "verified" + (f" (re-read: {', '.join(changed)})" if changed else "")
        records.append(record)
    return records


def passes_table(page: Dict[str, Any], table: int = 0) -> List[dict]:
    """Every cell side by side as each view read it, for the notebook."""
    records = []
    if table >= len(page.get("tables") or []):
        return records
    data = page["tables"][table]
    for number, row in enumerate(data["rows"], start=1):
        for role, fact in row["facts"].items():
            record = {"row": number, "column": role}
            for view in page["views"]:
                record[view] = fact["readings"].get(view, "—")
            record.update(consensus=fact["raw"], normalized=fact["normalized"], agreement=fact["agreement"],
                          arithmetic=fact["arithmetic"], status=fact["status"])
            records.append(record)
    return records


def to_json(page: Dict[str, Any]) -> str:
    clean = {k: v for k, v in page.items() if k != "debug"}
    return json.dumps(clean, ensure_ascii=False, indent=1, default=str)
