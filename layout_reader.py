"""
Position-based extraction for financial and legal pages.
Location: lib/python/legal_platform/layout_reader.py

One pipeline for every page, whatever produced it (typed PDF, scan,
screenshot, phone photo):

  1. sources     A PDF page is split into its typed text (exact words and
                 positions from PyMuPDF) and its embedded images (taken out
                 at their original resolution). An image file is one image.
  2. prepare     Each image is scaled so its letters are a standard height
                 (whatever the image size), and photos / scans are also
                 straightened and evened out; screenshots are only scaled
                 (image_tables.prepare_page).
  3. boxes       OpenCV finds every word and joins the words of one table
                 cell, or of one line of text, into one box, never across a
                 printed rule; boxes form lines and zones: TABLE zones
                 (aligned, widely spaced boxes) and TEXT zones
                 (layout_boxes.layout).
  4. read        Text pages: the vision model transcribes the page as
                 today. Table pages: every box is cut out, numbered, and
                 the vision model reads the numbered pieces (all at the same
                 letter size) - it only reads, it never decides where
                 anything is.
  5. structure   The text model receives every box (number, position, text)
                 and returns the table structure as JSON that names BOX
                 NUMBERS, not values. Its answer is checked (boxes used once,
                 boxes of the table left out are sent back once); with no
                 usable answer the table is built from the positions by code
                 (grid_structure). Our code fills in the text of the boxes,
                 so no model can change or invent a figure.
  6. check       Amounts are parsed with the table's decimal places; which
                 money column is debit / credit / balance is decided by the
                 running balance (headers differ between banks); the balance
                 is checked row by row and what the chain proves is repaired
                 (statement_reader.reconcile).
  7. read again  Money cells that are unreadable or do not add up are read
                 again, enlarged, from the page as is and then from the
                 smoothed page; a new reading is kept only when the
                 arithmetic gets better.

Models are passed in as functions, so everything can be tested without
Dataiku:  vision(prompt, png) -> text   and   text_llm(prompt, payload) -> dict.
"""

from __future__ import annotations

import json
import re
import time
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from . import image_tables as it
from . import layout_boxes as lb
from .statement_reader import (
    ROLE_LABELS, VisionCall, _json, column_role, fmt, parse_amount, reconcile, table_decimals,
)

TextLLM = Callable[[str, dict], dict]

BOXES_PER_SHEET = 40
SHEET_MAX_PIXELS = 1_200_000   # vision models shrink larger images, losing small digits
SHEET_MAX_PIECE_WIDTH = 1100
AMOUNT_ROLES = ("debit", "credit", "balance", "amount")


# ---------------------------------------------------------------------------
# 1. Sources
# ---------------------------------------------------------------------------
@dataclass
class Source:
    """One thing to read on a page: an image, or the page's typed text."""
    page: int
    kind: str                                   # image | typed
    image: Optional[bytes] = None               # original-resolution image bytes
    words: List[Tuple[float, float, float, float, str]] = field(default_factory=list)
    rect: Optional[Tuple[float, float, float, float]] = None   # where it sits on the page (PDF points)
    name: str = ""


def sources_from_file(data: bytes, filename: str = "") -> List[Source]:
    """Every source on every page of a PDF, or the single image of an image
    file. Images inside a PDF are taken out at their own resolution (not
    re-rendered), so small digits keep all their detail."""
    if not data.startswith(b"%PDF"):
        return [Source(page=1, kind="image", image=data, name=filename or "image")]
    import fitz
    document = fitz.open(stream=data, filetype="pdf")
    sources: List[Source] = []
    try:
        for index in range(document.page_count):
            page = document.load_page(index)
            number = index + 1
            area = page.rect.width * page.rect.height
            words = [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words") if str(w[4]).strip()]
            covered = 0.0
            for position, image in enumerate(page.get_images(full=True)):
                xref = image[0]
                rects = page.get_image_rects(xref)
                if not rects:
                    continue
                rect = rects[0]
                if rect.width * rect.height < 0.03 * area:
                    continue                    # logos, icons, signatures
                extracted = document.extract_image(xref)
                if not extracted or not extracted.get("image"):
                    continue
                covered += rect.width * rect.height
                sources.append(Source(page=number, kind="image", image=extracted["image"],
                                      rect=(rect.x0, rect.y0, rect.x1, rect.y1),
                                      name=f"page {number} image {position + 1}"))
            # Typed text outside the images (an invisible scanner text layer
            # lying on top of a full-page scan is not trusted).
            if words and covered < 0.85 * area:
                sources.append(Source(page=number, kind="typed", words=words, name=f"page {number} text"))
            if not words and covered == 0:
                # A page drawn with vector graphics only: render it.
                pixmap = page.get_pixmap(dpi=250, alpha=False)
                sources.append(Source(page=number, kind="image", image=pixmap.tobytes("png"),
                                      name=f"page {number} (rendered)"))
    finally:
        document.close()
    return sources


# ---------------------------------------------------------------------------
# 4. Reading
# ---------------------------------------------------------------------------
TRANSCRIBE_PROMPT = """
Transcribe all text on this page exactly as printed, in reading order
(Arabic right to left). Keep headings, paragraphs and lists; render any
table as a markdown table. Do not summarise or add anything.
""".strip()

READ_BOXES_PROMPT = """
The image is a list of pieces cut from a document page. Each piece is on
its own row, after a number in a grey box. A piece can be a word, a number,
a whole table cell or a line of text (sometimes two lines), or a stamp.
The numbers on this sheet are:
{ids}.

Transcribe the text of every piece exactly as printed: digits, separators
(, . / - :) and letters exactly, keeping the spaces between words; Arabic
stays Arabic. Do not correct, complete or guess. Text cut off at the edge
of a piece belongs to a neighbouring piece: leave it out. Use "" for a piece
with no readable text (a mark, a logo, a stain).

Return JSON only: {{"boxes": {{"<number>": "<text>", ...}}}}
""".strip()

REREAD_PROMPT = """
The image shows pieces cut from a {what}, each after a number in a grey box.
They are enlarged because the first reading did not add up.
The numbers on this sheet are: {ids}.

Read every character of each piece one by one, exactly as printed: every
digit, the thousands separators and the decimal point, a minus sign or
brackets. Do not correct or complete anything. Use "" if a piece is
unreadable.

Return JSON only: {{"boxes": {{"<number>": "<text>", ...}}}}
""".strip()

SHEET_LETTER_HEIGHT = 30       # px: letter height of every piece on a reading sheet
SHEET_LABEL_WIDTH = 110
FIGURE_MAX_HEIGHT = 10         # letter heights: taller marks (page edges, photos) are not read


def readable(box: lb.Box, char_h: float) -> bool:
    """Text boxes, and stamps / logos small enough to carry text."""
    return box.kind == "text" or (box.h <= FIGURE_MAX_HEIGHT * char_h and box.w >= 1.5 * char_h
                                  and box.w <= 40 * char_h)


def _piece_scale(box: lb.Box, char_h: float, letter: int) -> Tuple[float, int, int]:
    """Scale that gives the piece's letters `letter` px (wide pieces are
    reduced to fit the sheet, stamps capped in height), and its padding."""
    pad_x, pad_y = max(6, int(0.3 * char_h)), max(6, int(0.35 * char_h))
    scale = letter / max(1.0, char_h)
    if box.kind == "figure":
        scale = min(scale, 6 * letter / max(1, box.h + 2 * pad_y))
    scale = min(scale, SHEET_MAX_PIECE_WIDTH / max(1, box.w + 2 * pad_x))
    return scale, pad_x, pad_y


def _piece_size(box: lb.Box, char_h: float, letter: int) -> Tuple[int, int]:
    scale, pad_x, pad_y = _piece_scale(box, char_h, letter)
    return int((box.w + 2 * pad_x) * scale) + SHEET_LABEL_WIDTH + 20, int((box.h + 2 * pad_y) * scale) + 10


def _sheet(gray: np.ndarray, boxes: List[lb.Box], char_h: float = 24.0,
           letter: int = SHEET_LETTER_HEIGHT) -> np.ndarray:
    """One reading sheet: each box cut out with a margin, scaled so all
    letters have the same height, after its number on a grey label."""
    rows = []
    height, width = gray.shape
    for box in boxes:
        scale, pad_x, pad_y = _piece_scale(box, char_h, letter)
        piece = gray[max(0, box.y0 - pad_y):min(height, box.y1 + pad_y),
                     max(0, box.x0 - pad_x):min(width, box.x1 + pad_x)]
        piece = cv2.resize(piece, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
        row_h = max(46, piece.shape[0] + 10)
        row = np.full((row_h, SHEET_LABEL_WIDTH + 20 + piece.shape[1]), 255, np.uint8)
        top = (row_h - piece.shape[0]) // 2
        row[top:top + piece.shape[0], SHEET_LABEL_WIDTH + 20:] = piece
        label_y = row_h // 2
        cv2.rectangle(row, (4, label_y - 15), (SHEET_LABEL_WIDTH, label_y + 15), 200, -1)
        cv2.putText(row, str(box.id), (14, label_y + 10), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2, cv2.LINE_AA)
        cv2.line(row, (0, row_h - 1), (row.shape[1], row_h - 1), 225, 1)
        rows.append(row)
    sheet_w = max(r.shape[1] for r in rows)
    return np.vstack([np.pad(r, ((0, 0), (0, sheet_w - r.shape[1])), constant_values=255) for r in rows])


def _sheet_groups(boxes: List[lb.Box], char_h: float = 24.0,
                  letter: int = SHEET_LETTER_HEIGHT) -> List[List[lb.Box]]:
    """Boxes split into sheets small enough for the vision model to see at
    full size (wide pieces make a sheet wide, so fewer fit)."""
    groups: List[List[lb.Box]] = []
    current: List[lb.Box] = []
    widest = total_h = 0
    for box in boxes:
        width, height = _piece_size(box, char_h, letter)
        height = max(46, height)
        if current and (len(current) >= BOXES_PER_SHEET or
                        max(widest, width) * (total_h + height) > SHEET_MAX_PIXELS):
            groups.append(current)
            current, widest, total_h = [], 0, 0
        current.append(box)
        widest, total_h = max(widest, width), total_h + height
    if current:
        groups.append(current)
    return groups


def read_boxes(gray: np.ndarray, boxes: List[lb.Box], vision: VisionCall,
               images: Optional[list] = None, char_h: float = 24.0, prompt: str = READ_BOXES_PROMPT,
               letter: int = SHEET_LETTER_HEIGHT, what: str = "", label: str = "reading sheet",
               errors: Optional[List[str]] = None) -> Dict[int, str]:
    """Text of every box, read in sheets of numbered pieces."""
    texts: Dict[int, str] = {}
    for group in _sheet_groups([b for b in boxes if readable(b, char_h)], char_h, letter):
        sheet = _sheet(gray, group, char_h, letter)
        try:
            answer = vision(prompt.format(ids=", ".join(str(b.id) for b in group), what=what), it.to_png(sheet))
        except Exception as error:          # one failed sheet leaves its boxes empty, not the page
            if errors is not None:
                errors.append(f"{label} (boxes {group[0].id}-{group[-1].id}): {type(error).__name__}: {error}")
            answer = ""
        found = _json(answer).get("boxes") or {}
        if images is not None:
            images.append({"name": f"{label} (boxes {group[0].id}-{group[-1].id})",
                           "png": it.to_png(sheet), "answer": answer})
        for box in group:
            value = found.get(str(box.id), found.get(box.id))
            texts[box.id] = "" if value is None else str(value).strip()
    return texts


# ---------------------------------------------------------------------------
# 5. Structure
# ---------------------------------------------------------------------------
STRUCTURE_PROMPT = """
You rebuild the structure of one page from a financial or legal case file.
You receive every piece of text found on the page as a BOX: its number, its
position (x0, x1 from the left edge, y from the top, in pixels; the page is
{width} px wide), the line it sits on, and its text. Column hints such as
T1K1, T1K2 ... are x-ranges where the boxes of table area T1 line up; boxes
carry the hint they fall in. Arabic tables run right to left: the first
column is on the right.

Return JSON only:
{{
  "context": {{"<what it is, e.g. account number / IBAN / currency / period /
               bank / customer>": [box numbers]}},
  "tables": [{{
     "kind": "transactions | schedule | invoice | other",
     "columns": [{{"header_boxes": [..], "role": "date | value_date | description |
                  debit | credit | balance | amount | reference | other"}}],
     "rows": [{{"<role>": [box numbers], ...}}],
     "totals": [{{"label_boxes": [..], "<role>": [box numbers]}}]
  }}],
  "text_boxes": [box numbers that are ordinary text, in reading order]
}}

Rules:
- Refer to boxes ONLY by their numbers. Never write a value yourself.
- Use each box once.
- Headers differ from bank to bank and language to language. Decide each
  column's role from its header AND its contents: dates are date /
  value_date; the column whose figures carry on from row to row is the
  balance; money going out is debit, money coming in is credit; one signed
  or unsigned money column is amount; long words are the description;
  codes and numbers without decimals are reference.
- Every row is one transaction / line item. A description that wraps onto
  the next lines belongs to the row above it: list all its boxes.
- A cell split into several boxes lists all of them, in reading order.
- A row's boxes are on (about) the same line; on a curled photo the left
  side can sit slightly higher or lower, so use the column hints and the
  order of rows, not exact y alone.
- Watermarks, stamps, logos and page furniture belong to no row.
- Opening/closing balance and total lines go in "totals", not "rows".
""".strip()

_DATE = re.compile(r"^\d{1,4}\s*[/\-.]\s*\d{1,2}\s*[/\-.]\s*\d{1,4}$")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def _looks_date(text: str) -> bool:
    return bool(_DATE.match(str(text or "").translate(_ARABIC_DIGITS).strip()))


def _looks_amount(text: str) -> bool:
    """A money figure: digits with a decimal part (1,250.00 / 0.300 / (45.00))."""
    value = str(text or "").translate(_ARABIC_DIGITS).strip().replace(" ", "")
    value = re.sub(r"(?i)\s*(cr|dr)$", "", value).strip("()-+")
    return bool(re.fullmatch(r"\d{1,3}(,\d{3})*([.,]\d{1,3})|\d+[.,]\d{1,3}", value))


def _zone_of(box: lb.Box, zones: List[lb.Zone]) -> int:
    for index, zone in enumerate(zones):
        if any(b.id == box.id for line in zone.lines for b in line):
            return index
    return -1


def _box_rows(boxes: List[lb.Box], texts: Dict[int, str], zones: List[lb.Zone]) -> Tuple[list, list]:
    hints = []
    table_number = 0
    for zone in zones:
        if zone.kind == "table":
            table_number += 1
            for index, (c0, c1) in enumerate(zone.columns, start=1):
                hints.append({"hint": f"T{table_number}K{index}", "x0": c0, "x1": c1,
                              "y0": zone.box[1], "y1": zone.box[3]})
    rows = []
    for box in boxes:
        if not texts.get(box.id):
            continue
        hint = next((h["hint"] for h in hints if h["x0"] - 4 <= box.cx <= h["x1"] + 4
                     and h["y0"] - 4 <= box.cy <= h["y1"] + 4), "")
        row = {"box": box.id, "x0": box.x0, "x1": box.x1, "y": int(box.cy), "line": box.line,
               "hint": hint, "text": texts[box.id]}
        if box.kind != "text":
            row["kind"] = "stamp / logo"
        rows.append(row)
    return rows, hints


def _join(ids: Any, texts: Dict[int, str], by_id: Dict[int, lb.Box]) -> Tuple[str, List[int]]:
    """The text of the listed boxes in reading order (top to bottom, right
    to left for Arabic, left to right otherwise) and the ids that exist."""
    found = [by_id[int(i)] for i in (ids if isinstance(ids, list) else [ids])
             if str(i).lstrip("-").isdigit() and int(i) in by_id]
    if not found:
        return "", []
    arabic = any(re.search(r"[؀-ۿ]", texts.get(b.id, "")) for b in found)
    found.sort(key=lambda b: (b.line, -b.x1 if arabic else b.x0))
    return " ".join(t for t in (texts.get(b.id, "") for b in found) if t), [b.id for b in found]


# ---------------------------------------------------------------------------
# Checking the model's structure
# ---------------------------------------------------------------------------
def _ids(value: Any) -> List[int]:
    values = value if isinstance(value, list) else [value]
    return [int(v) for v in values if str(v).strip().lstrip("-").isdigit()]


def clean_structure(structure: Any, boxes: List[lb.Box]) -> Tuple[dict, List[str]]:
    """The model's answer made safe to use: known shapes only, box numbers
    that exist, and every box used once (a box named twice stays where it
    was first used)."""
    known = {b.id for b in boxes}
    used: set = set()
    notes: List[str] = []

    def take(value: Any, where: str) -> List[int]:
        kept = []
        for i in _ids(value):
            if i not in known:
                notes.append(f"box {i} ({where}) does not exist; ignored")
            elif i in used:
                notes.append(f"box {i} used twice; kept where it was first used, dropped from {where}")
            else:
                used.add(i)
                kept.append(i)
        return kept

    structure = structure if isinstance(structure, dict) else {}
    out: dict = {"context": {}, "tables": [], "text_boxes": []}
    for number, raw in enumerate(structure.get("tables") or [], start=1):
        if not isinstance(raw, dict):
            continue
        table = {"kind": str(raw.get("kind") or "other"), "columns": [], "rows": [], "totals": []}
        for column in raw.get("columns") or []:
            if isinstance(column, dict):
                table["columns"].append({"header_boxes": take(column.get("header_boxes") or [], f"table {number} header"),
                                         "role": str(column.get("role") or "other")})
        for index, raw_row in enumerate(raw.get("rows") or [], start=1):
            if isinstance(raw_row, dict):
                row = {str(role): take(ids, f"table {number} row {index}") for role, ids in raw_row.items()}
                if any(row.values()):
                    table["rows"].append(row)
        for raw_total in raw.get("totals") or []:
            if isinstance(raw_total, dict):
                table["totals"].append({str(role): take(ids, f"table {number} totals")
                                        for role, ids in raw_total.items()})
        if table["rows"] or table["columns"]:
            out["tables"].append(table)
    for name, ids in (structure.get("context") or {}).items() if isinstance(structure.get("context"), dict) else []:
        kept = take(ids, f"context '{name}'")
        if kept:
            out["context"][str(name)] = kept
    out["text_boxes"] = take(structure.get("text_boxes") or [], "text")
    return out, notes


def _placed(structure: dict) -> set:
    placed = {i for ids in structure.get("context", {}).values() for i in ids}
    placed |= set(structure.get("text_boxes") or [])
    for table in structure.get("tables") or []:
        placed |= {i for column in table["columns"] for i in column["header_boxes"]}
        placed |= {i for row in table["rows"] + table["totals"] for ids in row.values() for i in ids}
    return placed


def _table_box_ids(boxes: List[lb.Box], texts: Dict[int, str], zones: List[lb.Zone]) -> List[int]:
    """Boxes with text inside the table areas: each should be placed."""
    return [b.id for zone in zones if zone.kind == "table" for line in zone.lines for b in line if texts.get(b.id)]


def grid_structure(zones: List[lb.Zone], texts: Dict[int, str], boxes: List[lb.Box]) -> dict:
    """A structure built by code alone from the positions, used when the
    text model gives no usable answer: each table area's lines become rows
    (a line without a date or an amount continues the row above), boxes go
    to the column they sit in, header lines are the lines above the first
    row, and roles come from the header words or else from the contents
    (amount columns are told apart later by the arithmetic)."""
    out: dict = {"context": {}, "tables": [], "text_boxes": []}
    for zone in zones:
        if zone.kind != "table" or not zone.columns:
            out["text_boxes"] += [b.id for line in zone.lines for b in line if texts.get(b.id)]
            continue
        columns = sorted(zone.columns, key=lambda c: c[0])

        def column(box: lb.Box) -> int:
            return min(range(len(columns)), key=lambda i: 0 if columns[i][0] <= box.cx <= columns[i][1]
                       else min(abs(box.cx - columns[i][0]), abs(box.cx - columns[i][1])))

        def is_data(line: List[lb.Box]) -> bool:
            return any(_looks_date(texts.get(b.id, "")) or _looks_amount(texts.get(b.id, "")) for b in line)

        lines = [[b for b in line if texts.get(b.id)] for line in zone.lines]
        lines = [line for line in lines if line]
        first = next((i for i, line in enumerate(lines) if is_data(line)), None)
        if first is None:
            out["text_boxes"] += [b.id for line in lines for b in line]
            continue
        header_lines = lines[max(0, first - 3):first]
        out["text_boxes"] += [b.id for line in lines[:max(0, first - 3)] for b in line]
        rows: List[Dict[int, List[int]]] = []
        for line in lines[first:]:
            cells: Dict[int, List[int]] = {}
            for b in line:
                cells.setdefault(column(b), []).append(b.id)
            if rows and not is_data(line) and len(cells) <= max(1, len(columns) // 3):
                for index, ids in cells.items():
                    rows[-1].setdefault(index, []).extend(ids)
            else:
                rows.append(cells)
        # Only columns that hold data are columns; a header goes to the data
        # column under it (a left-aligned header above right-aligned figures
        # lines up with neither edge of them).
        by_id = {b.id: b for b in boxes}
        spans: Dict[int, List[int]] = {}
        for row in rows:
            for index, ids in row.items():
                for i in ids:
                    span = spans.setdefault(index, [by_id[i].x0, by_id[i].x1])
                    span[0], span[1] = min(span[0], by_id[i].x0), max(span[1], by_id[i].x1)
        used = sorted(spans)
        renumber = {old: new for new, old in enumerate(used)}
        rows = [{renumber[i]: ids for i, ids in row.items()} for row in rows]
        columns = [tuple(spans[i]) for i in used]

        def header_column(box: lb.Box) -> int:
            overlap = [max(0, min(box.x1, c1) - max(box.x0, c0)) for c0, c1 in columns]
            if max(overlap) > 0:
                return overlap.index(max(overlap))
            return min(range(len(columns)), key=lambda i: abs(box.cx - (columns[i][0] + columns[i][1]) / 2))

        headers: Dict[int, List[int]] = {}
        for line in header_lines:
            for b in line:
                headers.setdefault(header_column(b), []).append(b.id)
        # Roles: header words first, then what the cells contain.
        roles: Dict[int, str] = {}
        for index in range(len(columns)):
            header = " ".join(texts.get(i, "") for i in headers.get(index, []))
            values = [" ".join(texts.get(i, "") for i in row.get(index, [])) for row in rows if row.get(index)]
            role = column_role(header)
            if role == "other" and values:
                if sum(_looks_date(v) for v in values) >= 0.6 * len(values):
                    role = "date" if "date" not in roles.values() else "value_date"
                elif sum(_looks_amount(v) for v in values) >= 0.6 * len(values):
                    role = "amount"
                elif sum(bool(re.search(r"[^\d\s\-/]", v)) for v in values) >= 0.6 * len(values):
                    role = "description"
                else:
                    role = "reference"
            name, count = role, 2
            while name in roles.values():
                name, count = f"{role}_{count}", count + 1
            roles[index] = name
        out["tables"].append({
            "kind": "transactions" if any(r.startswith(("amount", "debit", "credit", "balance")) for r in roles.values())
            else "other",
            "columns": [{"header_boxes": headers.get(i, []), "role": roles[i]} for i in range(len(columns))],
            "rows": [{roles[i]: ids for i, ids in row.items()} for row in rows],
            "totals": []})
    return out


def _structure(text_llm: TextLLM, boxes: List[lb.Box], texts: Dict[int, str], zones: List[lb.Zone],
               width: int, images: Optional[list] = None) -> Tuple[dict, List[str]]:
    """The text model's structure, checked; asked once more when it leaves
    boxes of the table areas out; built from the positions by code when the
    model gives nothing usable."""
    box_rows, hints = _box_rows(boxes, texts, zones)
    payload: Dict[str, Any] = {"page_width": width, "column_hints": hints, "boxes": box_rows}
    expected = _table_box_ids(boxes, texts, zones)
    best, best_coverage, notes = None, -1.0, []
    for attempt in range(2):
        try:
            answer = text_llm(STRUCTURE_PROMPT.format(width=width), payload)
        except Exception as error:                     # a failed call never stops the page
            answer = {}
            notes.append(f"structure call {attempt + 1} failed: {type(error).__name__}: {error}")
        answer, problems = clean_structure(answer, boxes)
        missing = [i for i in expected if i not in _placed(answer)]
        coverage = 1.0 - len(missing) / len(expected) if expected else 1.0
        if images is not None:
            images.append({"name": f"structure from the text model (try {attempt + 1})",
                           "answer": json.dumps(answer, ensure_ascii=False)})
        if coverage > best_coverage:
            best, best_coverage = answer, coverage
            notes = [n for n in notes if n.startswith("structure call")] + problems[:20]
        if (coverage >= 0.9 and (answer["tables"] or not expected)) or attempt == 1:
            break
        payload = dict(payload, previous_answer_problem=(
            ("Your previous answer had no table, but the page has one. " if not answer["tables"] else "")
            + (f"These boxes inside the table area were not placed anywhere: {missing[:80]}. Put each in its "
               "row, header or totals, or in context / text_boxes." if missing else "")))
    if expected and (not best["tables"] or best_coverage < 0.4):
        notes.append("The text model gave no usable table; the table was built from the positions alone.")
        best = grid_structure(zones, texts, boxes)
    notes.append(f"table boxes placed: {round(100 * max(0.0, best_coverage))}%")
    return best, notes


# ---------------------------------------------------------------------------
# Filling values and the checks
# ---------------------------------------------------------------------------
def _amount_keys(rows: List[dict], decimals: Optional[int]) -> List[str]:
    """Columns that hold money: named as such, or mostly money figures."""
    keys = []
    for key in {k for row in rows for k in row["cells"]}:
        values = [row["cells"][key]["text"] for row in rows if row["cells"].get(key, {}).get("text")]
        if key in AMOUNT_ROLES or key.startswith("amount"):
            keys.append(key)
        elif key not in ("date", "value_date", "description", "reference") and values and \
                sum(_looks_amount(v) for v in values) >= 0.7 * len(values):
            keys.append(key)
    return sorted(keys)


def _chain_score(rows: List[dict], movement_keys: Tuple[str, ...], balance_key: str, decimals: int,
                 signed: bool) -> int:
    """How many consecutive rows agree with: previous balance +/- movement =
    balance, if the columns had these meanings."""
    previous, score = None, 0
    for row in rows:
        balance = parse_amount(row["cells"].get(balance_key, {}).get("text"), decimals)
        if balance is None:
            previous = None
            continue
        values = [parse_amount(row["cells"].get(k, {}).get("text"), decimals) for k in movement_keys]
        if previous is not None:
            if len(movement_keys) == 2:                  # (debit, credit)
                debit, credit = (values[0] or Decimal(0)), (values[1] or Decimal(0))
                score += previous - debit + credit == balance
            elif values[0] is not None:                  # one money column
                score += (previous + values[0] == balance) if signed else \
                    (abs(balance - previous) == abs(values[0]))
        previous = balance
    return score


def arithmetic_roles(rows: List[dict], decimals: int) -> Tuple[Dict[str, str], str]:
    """Which money column is the balance, the debit and the credit, decided
    by the running balance rather than by header words (which differ from
    bank to bank). Returns {current key: new key} when the arithmetic
    clearly prefers another reading than the current one, and a note."""
    from itertools import permutations
    keys = _amount_keys(rows, decimals)
    if len(keys) < 2 or len(keys) > 5 or len(rows) < 3:
        return {}, ""
    present = set(keys)

    def score_of(assignment: Dict[str, str]) -> int:
        role = {v: k for k, v in assignment.items()}
        if "debit" in role and "credit" in role:
            return _chain_score(rows, (role["debit"], role["credit"]), role["balance"], decimals, True)
        mover = role.get("amount") or role.get("debit") or role.get("credit")
        return _chain_score(rows, (mover,), role["balance"], decimals, False) if mover else 0

    current = {k: k for k in keys if k in ("debit", "credit", "balance", "amount")}
    current_score = score_of(current) if "balance" in current.values() and len(current) >= 2 else 0
    best, best_score = None, current_score
    for size in (3, 2):
        for chosen in permutations(keys, size):
            roles = ("debit", "credit", "balance") if size == 3 else ("amount", "balance")
            assignment = dict(zip(chosen, roles))
            score = score_of(assignment)
            if score > best_score:
                best, best_score = assignment, score
    if best is None or best_score < max(2, 0.5 * (len(rows) - 1)) or best_score <= current_score + 1:
        return {}, ""
    if all(current.get(k) == v for k, v in best.items()):
        return {}, ""
    mapping = dict(best)
    # Keys that lose their role keep their text under a neutral name.
    for key in present - set(best):
        if key in ("debit", "credit", "balance", "amount"):
            mapping[key] = f"other_amount_{key}"
    note = ("Money columns decided by the running balance: " +
            ", ".join(f"{k} → {v}" for k, v in best.items() if k != v) +
            f" ({best_score} rows agree, against {current_score} with the header reading).")
    return mapping, note


def _direction(row: dict, previous: Optional[Decimal]) -> None:
    """An unsigned single amount becomes a debit or a credit: from DR/CR
    marks, a sign, or the change in the balance."""
    amount, balance = row.get("amount"), row.get("balance")
    text = str(row["cells"].get("amount", {}).get("text") or "").upper()
    if amount is None or row.get("debit") is not None or row.get("credit") is not None:
        return
    if re.search(r"DR\b|مدين", text) or amount < 0:
        side = "debit"
    elif re.search(r"CR\b|دائن", text):
        side = "credit"
    elif previous is not None and balance is not None and previous - abs(amount) == balance:
        side = "debit"
    else:
        side = "credit"
        if previous is None:
            row.setdefault("notes", []).append(
                "No earlier balance on the page: this amount is taken as money in; check the direction.")
    row[side] = abs(amount)


def build_tables(structure: dict, texts: Dict[int, str], boxes: List[lb.Box]) -> Tuple[List[dict], dict]:
    """Fill the structure's box numbers with the text read from those boxes,
    map header words to roles (our dictionary wins over the model), let the
    running balance decide the money columns, parse amounts and run the
    checks."""
    by_id = {b.id: b for b in boxes}
    context = {}
    for name, ids in (structure.get("context") or {}).items():
        value, used = _join(ids, texts, by_id)
        if value:
            context[str(name)] = {"text": value, "boxes": used}

    tables = []
    for raw in structure.get("tables") or []:
        if not isinstance(raw, dict):
            continue
        columns = []
        for column in raw.get("columns") or []:
            if not isinstance(column, dict):
                continue
            header, header_ids = _join(column.get("header_boxes") or [], texts, by_id)
            role = column_role(header)
            if role == "other":
                role = str(column.get("role") or "other")
            columns.append({"header": header, "header_boxes": header_ids, "role": role,
                            "model_role": column.get("role")})
        rows = []
        for raw_row in raw.get("rows") or []:
            if not isinstance(raw_row, dict):
                continue
            row = {"cells": {}}
            for role, ids in raw_row.items():
                value, used = _join(ids, texts, by_id)
                row["cells"][str(role)] = {"text": value, "boxes": used}
            rows.append(row)
        totals = []
        for raw_total in raw.get("totals") or []:
            if isinstance(raw_total, dict):
                total = {"cells": {}}
                for role, ids in raw_total.items():
                    value, used = _join(ids, texts, by_id)
                    if value:
                        total["cells"]["label" if role == "label_boxes" else str(role)] = {"text": value, "boxes": used}
                totals.append(total)
        table = {"kind": raw.get("kind") or "other", "columns": columns, "rows": rows, "totals": totals,
                 "notes": []}
        decimals = table_decimals([c["text"] for row in rows for k, c in row["cells"].items()
                                   if _looks_amount(c["text"])]) or 2
        table["decimals"] = decimals

        mapping, note = arithmetic_roles(rows, decimals)
        if mapping:
            for row in rows:
                row["cells"] = {mapping.get(k, k): v for k, v in row["cells"].items()}
            for column in columns:
                column["role"] = mapping.get(column["role"], column["role"])
            table["notes"].append(note)

        present = {role for row in rows for role in row["cells"]}
        amount_roles = [r for r in sorted(present) if r in AMOUNT_ROLES or r.startswith(("amount", "other_amount"))]
        for row in rows:
            for role in amount_roles:
                if role in row["cells"]:
                    row[role] = parse_amount(row["cells"][role]["text"], decimals)
                    if row["cells"][role]["text"] and row[role] is None:
                        row.setdefault("notes", []).append(
                            f"{role} '{row['cells'][role]['text']}' is not a readable amount.")
        if "balance" in present and ({"debit", "credit", "amount"} & present):
            previous = None
            for row in rows:
                _direction(row, previous)
                previous = row.get("balance") if row.get("balance") is not None else previous
            checked = reconcile(rows, decimals)
            for row, result in zip(rows, checked):
                row.update({k: result.get(k) for k in ("debit", "credit", "balance", "status", "notes")})
                for field in ("debit", "credit", "balance"):
                    if f"{field}_as_read" in result:
                        row[f"{field}_as_read"] = result[f"{field}_as_read"]
            table["check"] = {status: sum(1 for r in rows if r.get("status") == status)
                              for status in ("reconciled", "repaired", "first", "unconfirmed", "no_balance")}
        else:
            for row in rows:
                row.setdefault("status", "read")
        table["roles"] = [c["role"] for c in columns]
        tables.append(table)
    return tables, context


# ---------------------------------------------------------------------------
# Reading again what does not add up
# ---------------------------------------------------------------------------
REREAD_LIMIT = 40


def _doubtful(tables: List[dict]) -> List[int]:
    """Boxes worth a second look: money cells that are not a readable
    amount, and the money cells of rows the arithmetic could not confirm
    (with the balance of the row before, which may be the misread one)."""
    ids: List[int] = []
    for table in tables:
        rows = table["rows"]
        for index, row in enumerate(rows):
            money = [k for k in row["cells"] if k in AMOUNT_ROLES or k.startswith("amount")]
            for key in money:
                cell = row["cells"][key]
                if cell["text"] and row.get(key) is None:
                    ids += cell["boxes"]
            if row.get("status") == "unconfirmed":
                for key in money:
                    ids += row["cells"][key]["boxes"]
                if index > 0:
                    ids += rows[index - 1]["cells"].get("balance", {}).get("boxes", [])
    return list(dict.fromkeys(ids))[:REREAD_LIMIT]


def _quality(tables: List[dict]) -> Tuple[int, int]:
    rows = [r for t in tables for r in t["rows"]]
    good = sum(1 for r in rows if r.get("status") in ("reconciled", "repaired"))
    unreadable = sum(1 for r in rows for k, c in r["cells"].items()
                     if (k in AMOUNT_ROLES or k.startswith("amount")) and c["text"] and r.get(k) is None)
    return good, -unreadable


def _reread(prepared: "it.Prepared", structure: dict, texts: Dict[int, str], boxes: List[lb.Box],
            tables: List[dict], context: dict, vision: VisionCall, char_h: float,
            images: Optional[list]) -> Tuple[Dict[int, str], List[dict], dict, List[dict]]:
    """Read the doubtful money cells again, enlarged, first from the page as
    is and then from the smoothed page (a different picture of the same
    digits); keep a new reading only when the arithmetic gets better."""
    log: List[dict] = []
    by_id = {b.id: b for b in boxes}
    # The second picture: the smoothed page for a photo, a clean black and
    # white version for a screenshot (its smoothed page is the same picture).
    other = ("enlarged, black and white", 255 - it.text_ink(prepared.read, True)) if prepared.digital \
        else ("enlarged, smoothed", prepared.find)
    for name, picture in (("enlarged", prepared.read), other):
        doubtful = [by_id[i] for i in _doubtful(tables) if i in by_id]
        if not doubtful:
            break
        second = read_boxes(picture, doubtful, vision, images, char_h, prompt=REREAD_PROMPT, letter=48,
                            what="bank statement table: amounts and dates", label=f"read again ({name})")
        changed = {i: t for i, t in second.items() if t and t != texts.get(i)}
        if not changed:
            continue
        trial = {**texts, **changed}
        trial_tables, trial_context = build_tables(structure, trial, boxes)
        better = _quality(trial_tables) > _quality(tables)
        log += [{"box": i, "first": texts.get(i, ""), "second": t, "pass": name, "kept": better}
                for i, t in changed.items()]
        if better:
            texts, tables, context = trial, trial_tables, trial_context
    return texts, tables, context, log


# ---------------------------------------------------------------------------
# The whole page
# ---------------------------------------------------------------------------
TRANSCRIBE_MAX_PIXELS = 4_000_000


def read_image(image_bytes: bytes, vision: VisionCall, text_llm: TextLLM, debug: bool = False,
               force: str = "") -> Dict[str, Any]:
    """Read one image (a page, a screenshot, a photo). force='table' or
    'text' overrides the page-type decision."""
    started = time.time()
    timings: Dict[str, float] = {}
    prepared = it.prepare_page(it.decode(image_bytes))
    images: List[dict] = []
    boxes, zones, box_info = lb.layout(prepared.find, prepared.digital)
    timings["image processing"] = round(time.time() - started, 1)
    char_h = box_info["char_height"]
    kind = force or ("table" if any(z.kind == "table" for z in zones) else "text")
    result: Dict[str, Any] = {"cleaning": prepared.info, "boxes": len(boxes), "char_height": char_h,
                              "page_kind": kind,
                              "zones": [{"kind": z.kind, "box": list(z.box), "lines": len(z.lines),
                                         "columns": len(z.columns)} for z in zones],
                              "seconds": timings}
    if debug:
        result["images"] = images
        images.append({"name": "cleaned page", "png": it.to_png(prepared.read)})
        images.append({"name": "boxes and zones", "png": it.to_png(lb.draw_boxes(prepared.read, boxes, zones))})

    if kind == "text":
        page = prepared.read
        factor = min(1.0, (TRANSCRIBE_MAX_PIXELS / (page.shape[0] * page.shape[1])) ** 0.5)
        if factor < 1.0:
            page = cv2.resize(page, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
        started = time.time()
        answer = vision(TRANSCRIBE_PROMPT, it.to_png(page))
        timings["reading"] = round(time.time() - started, 1)
        result["text"] = re.sub(r"<think>.*?</think>", "", answer, flags=re.S).strip()
        return result

    errors: List[str] = []
    started = time.time()
    texts = read_boxes(prepared.read, boxes, vision, images if debug else None, char_h, errors=errors)
    timings["reading"] = round(time.time() - started, 1)
    if errors and not any(texts.values()):
        raise RuntimeError("Every reading sheet failed. " + errors[0])
    started = time.time()
    structure, notes = _structure(text_llm, boxes, texts, zones, prepared.read.shape[1],
                                  images if debug else None)
    timings["structure"] = round(time.time() - started, 1)
    tables, context = build_tables(structure, texts, boxes)
    started = time.time()
    texts, tables, context, reread = _reread(prepared, structure, texts, boxes, tables, context, vision,
                                             char_h, images if debug else None)
    timings["read again"] = round(time.time() - started, 1)
    used = _placed(structure)
    text_ids = [i for i in structure.get("text_boxes") or [] if texts.get(i)]
    result.update(
        context=context, tables=tables,
        text=" ".join(texts[i] for i in text_ids),
        unplaced=[{"box": b.id, "text": texts[b.id]} for b in boxes if texts.get(b.id) and b.id not in used],
        box_texts={str(k): v for k, v in texts.items()},
        structure_notes=notes, re_read=reread, reading_errors=errors,
    )
    return result


def read_file(data: bytes, filename: str, vision: VisionCall, text_llm: TextLLM, debug: bool = False) -> Dict[str, Any]:
    """Every page of a PDF (or one image file), each source read on its own."""
    out = {"file": filename, "sources": []}
    for source in sources_from_file(data, filename):
        entry: Dict[str, Any] = {"page": source.page, "source": source.name, "kind": source.kind}
        try:
            if source.kind == "image":
                entry.update(read_image(source.image, vision, text_llm, debug=debug))
            else:
                entry["text"] = _typed_text(source.words)
        except Exception as error:          # one bad page never stops the file
            entry["error"] = f"{type(error).__name__}: {error}"
        out["sources"].append(entry)
    return out


def _typed_text(words: List[Tuple[float, float, float, float, str]]) -> str:
    """Typed PDF words in line order (positions are exact; tables in typed
    PDFs keep their spacing as ' | ' between distant words)."""
    lines: List[list] = []
    for word in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        centre = (word[1] + word[3]) / 2
        if lines and abs(centre - lines[-1][0]) < 0.5 * (word[3] - word[1]):
            lines[-1][1].append(word)
        else:
            lines.append([centre, [word]])
    rendered = []
    for _, items in lines:
        items.sort(key=lambda w: w[0])
        parts, previous = [], None
        for w in items:
            if previous is not None:
                parts.append(" | " if w[0] - previous[2] > 3 * (w[3] - w[1]) else " ")
            parts.append(w[4])
            previous = w
        rendered.append("".join(parts))
    return "\n".join(rendered)


# ---------------------------------------------------------------------------
# Reports and the notebook runner
# ---------------------------------------------------------------------------
def report(result: Dict[str, Any]) -> str:
    """One page / source as readable text."""
    lines = [f"page kind: {result.get('page_kind', result.get('kind'))}   boxes: {result.get('boxes')}   "
             f"cleaning: {result.get('cleaning')}"]
    if result.get("error"):
        lines.append(f"ERROR: {result['error']}")
    for name, value in (result.get("context") or {}).items():
        lines.append(f"  {name}: {value['text']}")
    for note in result.get("structure_notes") or []:
        lines.append(f"  [structure] {note}")
    for number, table in enumerate(result.get("tables") or [], start=1):
        lines.append(f"\n  TABLE {number} ({table['kind']}): " + " | ".join(
            f"{c['header'] or '?'} = {c['role']}" for c in table["columns"]))
        for note in table.get("notes") or []:
            lines.append(f"  [columns] {note}")
        if table.get("check"):
            lines.append(f"  check: {table['check']}   decimals: {table['decimals']}")
        decimals = table.get("decimals") or 2
        for index, row in enumerate(table["rows"], start=1):
            cells = row["cells"]
            amounts = "  ".join(f"{r}={fmt(row.get(r), decimals)}" for r in AMOUNT_ROLES if row.get(r) is not None)
            lines.append(f"  {index:>3}. {cells.get('date', {}).get('text', ''):<12} {amounts}   [{row.get('status')}]")
            if cells.get("description", {}).get("text"):
                lines.append(f"       {cells['description']['text'][:110]}")
            for note in row.get("notes") or []:
                if "First balance" not in note and "Confirmed by the next" not in note:
                    lines.append(f"       ! {note}")
    kept = [r for r in result.get("re_read") or [] if r["kept"]]
    if result.get("re_read"):
        lines.append(f"\n  read again: {len(result['re_read'])} cell(s), {len(kept)} new reading(s) kept: "
                     + " · ".join(f"box {r['box']}: {r['first']!r} → {r['second']!r}" for r in kept[:15]))
    if result.get("unplaced"):
        lines.append(f"\n  text not placed in any table ({len(result['unplaced'])}): "
                     + " · ".join(u["text"] for u in result["unplaced"][:25]))
    if result.get("text") and not result.get("tables"):
        lines.append("\n" + result["text"][:2500])
    return "\n".join(lines)


def score(result: Dict[str, Any]) -> Dict[str, Any]:
    """One line of numbers per source, for comparing many examples."""
    tables = result.get("tables") or []
    rows = [r for t in tables for r in t["rows"]]
    statuses = [r.get("status") for r in rows]
    return {"kind": result.get("page_kind", result.get("kind")), "boxes": result.get("boxes"),
            "tables": len(tables), "rows": len(rows),
            "reconciled": statuses.count("reconciled") + statuses.count("first"),
            "repaired": statuses.count("repaired"), "unconfirmed": statuses.count("unconfirmed"),
            "re_read_kept": sum(1 for r in result.get("re_read") or [] if r["kept"]),
            "unplaced_text": len(result.get("unplaced") or []), "error": result.get("error", "")}


def dataiku_text_llm(model_id: Optional[str] = None) -> TextLLM:
    from .llm import complete_json
    from .config import TEXT_STRUCTURING_LLM_ID

    def call(prompt: str, payload: dict) -> dict:
        return complete_json(prompt, payload, llm_id=model_id or TEXT_STRUCTURING_LLM_ID, temperature=0.0)
    return call


def run_folder(folder_id: str, vision: VisionCall, text_llm: TextLLM, files: Optional[List[str]] = None,
               debug: bool = False, show: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> List[dict]:
    """Read every PDF / image in a Dataiku managed folder and return one
    score line per source; show(name, result) is called after each source
    (e.g. to print the report and display the pictures in a notebook)."""
    import dataiku
    folder = dataiku.Folder(folder_id)
    names = files or [p for p in folder.list_paths_in_partition()
                      if p.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"))]
    scores = []
    for name in names:
        with folder.get_download_stream(name) as stream:
            data = stream.read()
        result = read_file(data, name, vision, text_llm, debug=debug)
        for source in result["sources"]:
            line = {"file": name, "source": source["source"], **score(source)}
            scores.append(line)
            if show:
                show(f"{name} / {source['source']}", source)
    return scores
