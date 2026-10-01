"""
Position-based extraction for financial and legal pages.
Location: lib/python/legal_platform/layout_reader.py

One pipeline for every page, whatever produced it (typed PDF, scan,
screenshot, phone photo):

  1. sources     A PDF page is split into its typed text (exact words and
                 positions from PyMuPDF) and its embedded images (taken out
                 at their original resolution). An image file is one image.
  2. clean       Each image is straightened, evened out and enlarged
                 (image_tables.clean_page).
  3. boxes       OpenCV finds a box around every word / number / phrase and
                 groups them into lines and zones: TABLE zones (aligned,
                 widely spaced boxes) and TEXT zones (layout_boxes.py).
  4. read        Text pages: the vision model transcribes the page as
                 today. Table pages: every box is cut out, numbered, and
                 the vision model reads the numbered pieces - it only reads,
                 it never decides where anything is.
  5. structure   The text model receives the page context and every box
                 (number, position, text) and returns the table structure
                 as JSON that names BOX NUMBERS, not values: which boxes are
                 the header, what each column means, which boxes form each
                 row. Our code then fills in the text of those boxes, so no
                 model can change or invent a figure.
  6. check       Amounts are parsed with the table's decimal places; a
                 statement's running balance is checked row by row and what
                 the chain proves is repaired (statement_reader.reconcile).

Models are passed in as functions, so everything can be tested without
Dataiku:  vision(prompt, png) -> text   and   text_llm(prompt, payload) -> dict.
"""

from __future__ import annotations

import json
import re
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
SHEET_ROW_HEIGHT = 56          # px per piece on a reading sheet
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
The image is a list of small pieces cut from a document page. Each piece is
on its own line, after a number in a grey box. The numbers on this sheet are:
{ids}.

Transcribe the text of every piece exactly as printed: digits, separators
(, . / -) and letters exactly; Arabic stays Arabic. Do not correct, complete
or guess. Use "" for a piece with no readable text (a mark, a logo, a stain).

Return JSON only: {{"boxes": {{"<number>": "<text>", ...}}}}
""".strip()


def _sheet(gray: np.ndarray, boxes: List[lb.Box]) -> np.ndarray:
    """One reading sheet: each box cut out (with a margin), scaled to a
    common height, after its number on a grey label."""
    rows = []
    label_w = 110
    for box in boxes:
        piece = it.crop(gray, box.x0, box.y0, box.x1, box.y1, pad=6)
        scale = (SHEET_ROW_HEIGHT - 10) / max(1, piece.shape[0])
        piece = cv2.resize(piece, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        piece = piece[:, :SHEET_MAX_PIECE_WIDTH]
        row = np.full((SHEET_ROW_HEIGHT, label_w + 20 + piece.shape[1]), 255, np.uint8)
        row[5:5 + piece.shape[0], label_w + 20:] = piece
        cv2.rectangle(row, (4, 8), (label_w, SHEET_ROW_HEIGHT - 8), 200, -1)
        cv2.putText(row, str(box.id), (14, SHEET_ROW_HEIGHT - 18), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2, cv2.LINE_AA)
        cv2.line(row, (0, SHEET_ROW_HEIGHT - 1), (row.shape[1], SHEET_ROW_HEIGHT - 1), 225, 1)
        rows.append(row)
    width = max(r.shape[1] for r in rows)
    return np.vstack([np.pad(r, ((0, 0), (0, width - r.shape[1])), constant_values=255) for r in rows])


def _sheet_groups(boxes: List[lb.Box]) -> List[List[lb.Box]]:
    """Boxes split into sheets small enough for the vision model to see at
    full size (wide pieces make a sheet wide, so fewer fit)."""
    groups: List[List[lb.Box]] = []
    current: List[lb.Box] = []
    widest = 0
    for box in boxes:
        width = 130 + min(SHEET_MAX_PIECE_WIDTH, int((box.w + 12) * (SHEET_ROW_HEIGHT - 10) / max(1, box.h + 12)))
        if current and (len(current) >= BOXES_PER_SHEET or
                        max(widest, width) * SHEET_ROW_HEIGHT * (len(current) + 1) > SHEET_MAX_PIXELS):
            groups.append(current)
            current, widest = [], 0
        current.append(box)
        widest = max(widest, width)
    if current:
        groups.append(current)
    return groups


def read_boxes(gray: np.ndarray, boxes: List[lb.Box], vision: VisionCall,
               images: Optional[list] = None) -> Dict[int, str]:
    """Text of every box, read in sheets of numbered pieces."""
    texts: Dict[int, str] = {}
    readable = [b for b in boxes if b.kind == "text"]
    for group in _sheet_groups(readable):
        sheet = _sheet(gray, group)
        prompt = READ_BOXES_PROMPT.format(ids=", ".join(str(b.id) for b in group))
        answer = vision(prompt, it.to_png(sheet))
        found = _json(answer).get("boxes") or {}
        if images is not None:
            images.append({"name": f"reading sheet (boxes {group[0].id}-{group[-1].id})",
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
You receive the page context and every piece of text found on the page as a
BOX: its number, its position (x0, x1 from the left edge, y from the top, in
pixels; the page is {width} px wide) and its text. Column hints K1, K2 ...
are x-ranges where boxes line up; boxes also carry the hint they fall in.
Arabic tables run right to left: the first column is on the right.

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
- Every row is one transaction / line item. A description that wraps onto
  the next lines belongs to the row above it: list all its boxes.
- A cell split into several boxes lists all of them, in reading order.
- A row's boxes are on (about) the same line; on a curled photo the left
  side can sit slightly higher or lower, so use the column hints and the
  order of rows, not exact y alone.
- Watermarks, stamps, logos and page furniture belong to no row.
- Opening/closing balance and total lines go in "totals", not "rows".
- If a column has no header, give it the role its contents show.
""".strip()


def _box_rows(boxes: List[lb.Box], texts: Dict[int, str], zones: List[lb.Zone]) -> Tuple[list, list]:
    hints = []
    for zone in zones:
        if zone.kind == "table":
            for index, (c0, c1) in enumerate(zone.columns, start=1):
                hints.append({"hint": f"K{index}", "x0": c0, "x1": c1, "y0": zone.box[1], "y1": zone.box[3]})
    rows = []
    for box in boxes:
        if box.kind != "text" or not texts.get(box.id):
            continue
        hint = next((h["hint"] for h in hints if h["x0"] - 4 <= box.cx <= h["x1"] + 4
                     and h["y0"] - 4 <= box.cy <= h["y1"] + 4), "")
        rows.append({"box": box.id, "x0": box.x0, "x1": box.x1, "y": int(box.cy), "line": box.line,
                     "hint": hint, "text": texts[box.id]})
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


def build_tables(structure: dict, texts: Dict[int, str], boxes: List[lb.Box]) -> Tuple[List[dict], dict]:
    """Fill the model's box numbers with the text read from those boxes,
    map header words to roles (our dictionary wins over the model), parse
    amounts and run the checks."""
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
        roles = [c["role"] for c in columns]
        rows = []
        for raw_row in raw.get("rows") or []:
            if not isinstance(raw_row, dict):
                continue
            row = {"cells": {}}
            for role, ids in raw_row.items():
                value, used = _join(ids, texts, by_id)
                row["cells"][str(role)] = {"text": value, "boxes": used}
            rows.append(row)
        table = {"kind": raw.get("kind") or "other", "columns": columns, "rows": rows,
                 "totals": raw.get("totals") or []}
        present = {role for row in rows for role in row["cells"]}
        amount_roles = [r for r in AMOUNT_ROLES if r in present]
        decimals = table_decimals([row["cells"][r]["text"] for row in rows for r in amount_roles
                                   if r in row["cells"]]) or 2
        table["decimals"] = decimals
        for row in rows:
            for role in amount_roles:
                if role in row["cells"]:
                    row[role] = parse_amount(row["cells"][role]["text"], decimals)
                    if row["cells"][role]["text"] and row[role] is None:
                        row.setdefault("notes", []).append(
                            f"{role} '{row['cells'][role]['text']}' is not a readable amount.")
        if "balance" in present and ({"debit", "credit", "amount"} & present):
            for row in rows:
                amount = row.get("amount")
                if amount is not None and row.get("debit") is None and row.get("credit") is None:
                    row["debit" if amount < 0 else "credit"] = abs(amount)
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
        table["roles"] = roles
        tables.append(table)
    return tables, context


# ---------------------------------------------------------------------------
# The whole page
# ---------------------------------------------------------------------------
def read_image(image_bytes: bytes, vision: VisionCall, text_llm: TextLLM, debug: bool = False,
               force: str = "") -> Dict[str, Any]:
    """Read one image (a page, a screenshot, a photo). force='table' or
    'text' overrides the page-type decision."""
    clean, info = it.clean_page(it.decode(image_bytes))
    images: List[dict] = []
    boxes, box_info = lb.find_boxes(clean)
    char_h = box_info["char_height"]
    lines = lb.group_lines([b for b in boxes if b.kind == "text"], char_h)
    zones = lb.find_zones(lines, char_h, clean.shape[1], lb.vertical_rules(clean))
    kind = force or ("table" if any(z.kind == "table" for z in zones) else "text")
    result: Dict[str, Any] = {"cleaning": info, "boxes": len(boxes), "char_height": char_h, "page_kind": kind,
                              "zones": [{"kind": z.kind, "box": list(z.box), "lines": len(z.lines),
                                         "columns": len(z.columns)} for z in zones]}
    if debug:
        result["images"] = images
        images.append({"name": "cleaned page", "png": it.to_png(clean)})
        images.append({"name": "boxes and zones", "png": it.to_png(lb.draw_boxes(clean, boxes, zones))})

    if kind == "text":
        answer = vision(TRANSCRIBE_PROMPT, it.to_png(clean))
        result["text"] = re.sub(r"<think>.*?</think>", "", answer, flags=re.S).strip()
        return result

    texts = read_boxes(clean, boxes, vision, images if debug else None)
    box_rows, hints = _box_rows(boxes, texts, zones)
    payload = {"page_width": clean.shape[1], "column_hints": hints, "boxes": box_rows}
    structure = text_llm(STRUCTURE_PROMPT.format(width=clean.shape[1]), payload)
    if debug:
        images.append({"name": "structure from the text model", "answer": json.dumps(structure, ensure_ascii=False)})
    tables, context = build_tables(structure if isinstance(structure, dict) else {}, texts, boxes)
    used = {i for t in tables for r in t["rows"] for c in r["cells"].values() for i in c["boxes"]}
    used |= {i for t in tables for c in t["columns"] for i in c["header_boxes"]}
    used |= {i for c in context.values() for i in c["boxes"]}
    text_ids = [i for i in structure.get("text_boxes") or [] if str(i).isdigit()]
    result.update(
        context=context, tables=tables,
        text=" ".join(texts.get(int(i), "") for i in text_ids if texts.get(int(i))),
        unplaced=[{"box": b.id, "text": texts[b.id]} for b in boxes
                  if b.kind == "text" and texts.get(b.id) and b.id not in used and b.id not in {int(i) for i in text_ids}],
        box_texts={str(k): v for k, v in texts.items()},
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
    for number, table in enumerate(result.get("tables") or [], start=1):
        lines.append(f"\n  TABLE {number} ({table['kind']}): " + " | ".join(
            f"{c['header'] or '?'} = {c['role']}" for c in table["columns"]))
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
