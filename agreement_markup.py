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


def mark_pages(pages: Any, documents: Any, clause_reviews: list) -> dict:
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
            placed = False
            if words:
                for page_id in search:
                    taken = [(a, b) for a, b, _, _ in placements[page_id]]
                    span = _find(by_id[page_id]["text"], words, taken)
                    if span:
                        kind = "insert" if edit.get("type") == "add" else "mark"
                        placements[page_id].append((span[0], span[1], edit_id, kind))
                        edits[edit_id]["page_id"] = page_id
                        placed = True
                        break
            if not placed:
                unplaced.append(edit_id)

    out_pages = []
    for row in rows:
        text, segments, cursor = row["text"], [], 0
        for start, end, edit_id, kind in sorted(placements[row["page_id"]]):
            if start > cursor:
                segments.append({"text": text[cursor:start], "edit_id": "", "kind": "text"})
            if kind == "insert":            # the anchor stays as it is; the new words follow it
                segments.append({"text": text[start:end], "edit_id": "", "kind": "text"})
                segments.append({"text": "", "edit_id": edit_id, "kind": "insert"})
            else:
                segments.append({"text": text[start:end], "edit_id": edit_id, "kind": "mark"})
            cursor = end
        if cursor < len(text):
            segments.append({"text": text[cursor:], "edit_id": "", "kind": "text"})
        out_pages.append({"page_id": row["page_id"], "document_name": names.get(row["document_id"], ""),
                          "page_number": row["page_number"], "changes": len(placements[row["page_id"]]),
                          "segments": segments})
    return {"pages": out_pages, "edits": edits, "unplaced": unplaced}
