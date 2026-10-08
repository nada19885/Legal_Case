"""
The contract review shown on the agreement's own pages: each wording edit
of the clause review (agreement_analysis.clean_edits) is found in the
page text, so the screen can show the words to change in red and an
arrow to how they should read.
Location: lib/python/legal_platform/agreement_markup.py

mark_pages(pages, documents, clause_reviews) ->
  {"pages": [{page_id, document_name, page_number, changes,
              segments: [{"text": ..., "edit_id": ""|id, "kind": "text"|"mark"|"insert"}]}],
   "edits": {edit_id: edit + risk_level, clause_number, heading, page_id},
   "unplaced": [edit_id, ...]}
An edit whose words are not found on any page (the model changed them, or
they run across a page break) is listed in "unplaced", never put in the
wrong place.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Arabic diacritics and tatweel, ignored when matching.
_IGNORABLE = "ـًٌٍَُِّْٰ"
_GAP = "[\\s{}]*".format(_IGNORABLE)
_TRIM = " \t\r\n.,;:،؛!?\"'«»()[]"


def _records(value: Any) -> list[dict]:
    if value is None:
        return []
    if hasattr(value, "fillna") and hasattr(value, "to_dict"):
        return value.fillna("").to_dict("records")
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _pattern(words: str) -> Optional[re.Pattern]:
    """A pattern for `words` that tolerates different spacing, line breaks,
    Arabic diacritics / tatweel and letter case."""
    clean = "".join(ch for ch in words if ch not in _IGNORABLE).strip(_TRIM)
    if len(clean) < 3:
        return None
    parts = []
    for token in clean.split():
        parts.append(_GAP.join(re.escape(ch) for ch in token))
    between = "[{}]*\\s+[{}]*".format(_IGNORABLE, _IGNORABLE)
    return re.compile(between.join(parts), re.IGNORECASE)


def _find(text: str, words: str, taken: list) -> Optional[tuple]:
    pattern = _pattern(words)
    if pattern is None:
        return None
    for match in pattern.finditer(text):
        start, end = match.span()
        if all(end <= a or start >= b for a, b in taken):
            return start, end
    return None


def _page_rows(pages: Any, documents: Any) -> tuple[list[dict], dict]:
    names = {str(row.get("case_document_id", "")): str(row.get("original_filename") or row.get("file_name") or "")
             for row in _records(documents)}
    rows = []
    for row in _records(pages):
        page_id = str(row.get("page_id") or row.get("case_document_page_id") or "")
        if page_id:
            rows.append({"page_id": page_id, "document_id": str(row.get("case_document_id") or ""),
                         "page_number": int(float(row.get("page_number") or 0)),
                         "text": str(row.get("page_text") or "")})
    rows.sort(key=lambda r: (r["document_id"], r["page_number"]))
    return rows, names


def _placements(rows: list[dict], clause_reviews: list) -> tuple[dict, dict, list]:
    """Where each edit's words are on the pages: (edits by id, page_id ->
    [(start, end, edit_id, kind)], ids of edits not found). The pages of
    the edit's own clause are searched first. An addition is placed after
    its anchor sentence, which may also carry a change."""
    by_id = {r["page_id"]: r for r in rows}
    edits, placements, unplaced = {}, {r["page_id"]: [] for r in rows}, []
    for review in clause_reviews or []:
        if not isinstance(review, dict):
            continue
        own_pages = [str(x) for x in review.get("source_page_ids") or [] if str(x) in by_id]
        search = own_pages + [r["page_id"] for r in rows if r["page_id"] not in own_pages]
        for edit in review.get("edits") or []:
            if not isinstance(edit, dict) or not edit.get("edit_id"):
                continue
            edit_id = str(edit["edit_id"])
            edits[edit_id] = dict(edit, risk_level=review.get("risk_level", ""),
                                  clause_number=review.get("clause_number", ""),
                                  heading=review.get("heading", ""), page_id="")
            words = edit.get("original") or ""
            kind = "insert" if edit.get("type") == "add" else "mark"
            placed = False
            if words:
                for page_id in search:
                    taken = [] if kind == "insert" else [(a, b) for a, b, _, k in placements[page_id] if k == "mark"]
                    span = _find(by_id[page_id]["text"], words, taken)
                    if span:
                        placements[page_id].append((span[0], span[1], edit_id, kind))
                        edits[edit_id]["page_id"] = page_id
                        placed = True
                        break
            if not placed:
                unplaced.append(edit_id)
    return edits, placements, unplaced


def mark_pages(pages: Any, documents: Any, clause_reviews: list) -> dict:
    rows, names = _page_rows(pages, documents)
    edits, placements, unplaced = _placements(rows, clause_reviews)
    out_pages = []
    for row in rows:
        text, segments, cursor = row["text"], [], 0
        for start, end, edit_id, kind in sorted(placements[row["page_id"]]):
            if kind == "insert":            # the anchor stays as it is; the new words follow it
                if end > cursor:
                    segments.append({"text": text[cursor:end], "edit_id": "", "kind": "text"})
                    cursor = end
                segments.append({"text": "", "edit_id": edit_id, "kind": "insert"})
                continue
            if start > cursor:
                segments.append({"text": text[cursor:start], "edit_id": "", "kind": "text"})
            segments.append({"text": text[start:end], "edit_id": edit_id, "kind": "mark"})
            cursor = end
        if cursor < len(text):
            segments.append({"text": text[cursor:], "edit_id": "", "kind": "text"})
        out_pages.append({"page_id": row["page_id"], "document_name": names.get(row["document_id"], ""),
                          "page_number": row["page_number"], "changes": len(placements[row["page_id"]]),
                          "segments": segments})
    return {"pages": out_pages, "edits": edits, "unplaced": unplaced}


# -----------------------------------------------------------------------------
# The contract as one structured document
# -----------------------------------------------------------------------------
# contract_document(...) ->
#   {"blocks": [block, ...], "edits": {...}, "unplaced": [...], "changes": n}
# block: {"type": "document", "text"}            a file of the package (when several)
#        {"type": "page", "page_number"}         where a page of the original starts
#        {"type": "heading", "level", "runs"}
#        {"type": "paragraph" | "item", "runs"}
#        {"type": "table", "rows": [{"header": bool, "cells": [runs, ...]}]}
# run:   {"text", "kind": "text"} | {"text", "kind": "mark", "edit_id", "last"}
#        | {"text": "", "kind": "insert", "edit_id"}
# A mark's "last" piece is where its new wording is shown.

_HEADING_WORDS = re.compile(
    r"^\s*(#{1,6}\s|المادة|مادة|البند|بند|الفصل|الباب|الملحق|ملحق|التمهيد|تمهيد|"
    r"article\b|clause\b|section\b|schedule\b|annex\b|appendix\b|preamble\b)", re.IGNORECASE)
_ITEM_START = re.compile(r"^\s*([-•*·▪●]\s+|\(\s*[☒☐✓✔xX]?\s*\)\s*)")
_NUMBERED_START = re.compile(
    r"^\s*(-?\(?[0-9٠-٩]+(\.[0-9٠-٩]+)*\s*[\.\-\):–]|\(?[أ-ي]\)\s|"
    r"(أولاً|ثانياً|ثالثاً|رابعاً|خامساً|سادساً|سابعاً|ثامناً|تاسعاً|عاشراً)\s*[:\-–])")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}")


def _norm(text: str) -> str:
    clean = "".join(ch for ch in str(text or "") if ch not in _IGNORABLE)
    clean = re.sub(r"^[\s#\-–:.()0-9٠-٩]+", "", clean)
    return re.sub(r"\s+", " ", clean).strip(_TRIM).casefold()


def _is_heading(line: str, headings: set) -> bool:
    text = line.strip()
    if not text or len(text) > 120 or text.startswith("|"):
        return False
    if text.startswith("#"):
        return True
    norm = _norm(text)
    if norm and any(norm == h or (norm.endswith(h) and len(norm) <= len(h) + 30) for h in headings):
        return True
    return bool(_HEADING_WORDS.match(text)) and len(text) <= 90 and not text.rstrip().endswith((".", "،", ","))


def _runs(text: str, start: int, end: int, marks: list) -> list[dict]:
    """The runs of text[start:end]: plain text, marked words, additions."""
    runs, cursor = [], start
    events = []
    for a, b, edit_id, kind in marks:
        if kind == "insert":
            # after the anchor, or after a change that covers the anchor's end
            position = max([b] + [mb for ma, mb, _, mk in marks if mk == "mark" and ma < b < mb])
            if start < position <= end:
                events.append((position, 1, edit_id, "insert", position))
        elif b > start and a < end:
            events.append((max(a, start), 0, edit_id, "mark", min(b, end)))
    for position, _, edit_id, kind, stop in sorted(events):
        if position > cursor:
            runs.append({"text": text[cursor:position], "kind": "text"})
            cursor = position
        if kind == "insert":
            runs.append({"text": "", "kind": "insert", "edit_id": edit_id})
        elif stop > cursor:
            runs.append({"text": text[cursor:stop], "kind": "mark", "edit_id": edit_id, "last": False})
            cursor = stop
    if cursor < end:
        runs.append({"text": text[cursor:end], "kind": "text"})
    return runs


def _table_cells(text: str, line_start: int, line: str) -> list[tuple[int, int]]:
    cells, position = [], 0
    pieces = line.split("|")
    for index, piece in enumerate(pieces):
        piece_start = position
        position += len(piece) + 1
        if (index == 0 or index == len(pieces) - 1) and not piece.strip():
            continue
        lead = len(piece) - len(piece.lstrip())
        cells.append((line_start + piece_start + lead, line_start + piece_start + len(piece.rstrip())))
    return cells


def _page_blocks(text: str, marks: list, headings: set) -> list[dict]:
    lines, offset = [], 0
    for line in text.split("\n"):
        lines.append((offset, line))
        offset += len(line) + 1
    blocks, paragraph = [], None

    def close():
        nonlocal paragraph
        if paragraph:
            kind, a, b = paragraph
            runs = _runs(text, a, b, marks)
            if any(r["text"].strip() or r["kind"] == "insert" for r in runs):
                blocks.append({"type": kind, "runs": runs})
        paragraph = None

    index = 0
    while index < len(lines):
        start, line = lines[index]
        stripped = line.strip()
        lead = len(line) - len(line.lstrip())
        if not stripped:
            close()
            index += 1
            continue
        if stripped.startswith("|") and stripped.count("|") >= 2:
            close()
            rows = []
            while index < len(lines) and lines[index][1].strip().startswith("|"):
                row_start, row_line = lines[index]
                if _TABLE_SEPARATOR.match(row_line.strip().strip("|")):
                    if rows:
                        rows[-1]["header"] = True
                else:
                    rows.append({"header": False, "cells": [_runs(text, a, b, marks)
                                                            for a, b in _table_cells(text, row_start, row_line)]})
                index += 1
            width = max((len(r["cells"]) for r in rows), default=0)
            for row in rows:
                row["cells"] += [[] for _ in range(width - len(row["cells"]))]
            if rows:
                blocks.append({"type": "table", "rows": rows})
            continue
        if _is_heading(stripped, headings):
            close()
            hashes = len(stripped) - len(stripped.lstrip("#"))
            skip = lead + (hashes + (1 if stripped[hashes:hashes + 1] == " " else 0) if hashes else 0)
            blocks.append({"type": "heading", "level": min(max(hashes, 2), 4) if hashes else 2,
                           "runs": _runs(text, start + skip, start + len(line.rstrip()), marks)})
        elif _ITEM_START.match(stripped):
            close()
            marker = _ITEM_START.match(line).end()
            box = line[:marker].strip()
            paragraph = ("item", start + (lead if box.startswith("(") else marker), start + len(line.rstrip()))
        elif _NUMBERED_START.match(stripped) or paragraph is None:
            close()
            paragraph = ("paragraph", start + lead, start + len(line.rstrip()))
        else:
            paragraph = (paragraph[0], paragraph[1], start + len(line.rstrip()))
        index += 1
    close()
    return blocks


def _all_runs(block: dict):
    if block["type"] == "table":
        for row in block["rows"]:
            for cell in row["cells"]:
                yield from cell
    else:
        yield from block.get("runs") or []


def contract_document(pages: Any, documents: Any, clause_reviews: list, clause_map: Optional[dict] = None) -> dict:
    """The agreement's extracted text as one document, with each wording
    change in place (see the block format above)."""
    rows, names = _page_rows(pages, documents)
    edits, placements, unplaced = _placements(rows, clause_reviews)
    headings = {_norm(c.get("heading")) for c in (clause_map or {}).get("clauses") or []
                if isinstance(c, dict) and len(_norm(c.get("heading"))) >= 3}
    several = len({r["document_id"] for r in rows}) > 1
    blocks, current = [], None
    for row in rows:
        if row["document_id"] != current:           # a new file: its title, no page line
            current = row["document_id"]
            if several:
                blocks.append({"type": "document", "text": names.get(current) or "Document"})
        else:                                       # where the next page of the original starts
            blocks.append({"type": "page", "page_number": row["page_number"]})
        blocks.extend(_page_blocks(row["text"], sorted(placements[row["page_id"]]), headings))

    # The contract's own title: its first short line, when it reads as one.
    first = next((b for b in blocks if b["type"] not in {"document", "page"}), None)
    if first and first["type"] == "paragraph":
        line = "".join(r["text"] for r in first["runs"])
        if "\n" not in line.strip() and len(line.strip()) <= 80 and not line.rstrip().endswith((".", "،", ",", ":")):
            first["type"], first["level"] = "heading", 1

    last = {}
    for block in blocks:
        for run in _all_runs(block):
            if run["kind"] == "mark":
                last[run["edit_id"]] = run
    for run in last.values():
        run["last"] = True
    placed = {r["edit_id"] for b in blocks for r in _all_runs(b) if r["kind"] in {"mark", "insert"}}
    unplaced += [edit_id for edit_id in edits if edit_id not in placed and edit_id not in unplaced]
    return {"blocks": blocks, "edits": edits, "unplaced": unplaced, "changes": len(placed)}
