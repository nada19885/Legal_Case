"""
Page-scoped PyMuPDF structural extractor — Stage 1a of the financial
evidence-extraction pipeline.
Location: lib/python/legal_platform/financial_structural_extraction.py

Adapted from a generic RAG PDF extractor, scoped down to a single page and
stripped of VLM image-captioning: Stage 1b's own whole-page VLM pass already
covers what is visually on the page, so this module only supplies the PDF's
native, machine-readable layer — text, tables, positions and headings. It
does not OCR; a scanned/image-only page simply has nothing to report here,
and Stage 2 must be able to reconstruct from the VLM evidence alone in
that case.
"""

from __future__ import annotations

import re
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF

SPACE_RE = re.compile(r"[ \t]+")


def _clean_text(value: Any) -> str:
    value = "" if value is None else str(value)
    value = value.replace("\x00", " ").replace("\r", "\n")
    lines = []
    for line in value.split("\n"):
        line = SPACE_RE.sub(" ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _rect_tuple(rect: Any) -> Tuple[float, float, float, float]:
    if rect is None:
        return (0.0, 0.0, 0.0, 0.0)
    if hasattr(rect, "x0"):
        return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))
    vals = list(rect)
    return tuple(float(x) for x in vals[:4])  # type: ignore[return-value]


def _rect_area(rect: Tuple[float, float, float, float]) -> float:
    return max(0.0, rect[2] - rect[0]) * max(0.0, rect[3] - rect[1])


def _intersection_ratio(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    denom = _rect_area(a)
    return area / denom if denom else 0.0


def _body_font_size(page_dict: Dict[str, Any]) -> float:
    weighted: List[float] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = _clean_text(span.get("text", ""))
                if not text:
                    continue
                try:
                    size = float(span.get("size") or 0)
                except Exception:
                    continue
                if size > 0:
                    weighted.extend([size] * max(1, min(len(text), 30)))
    return float(median(weighted)) if weighted else 10.0


def _text_block(block: Dict[str, Any]) -> Tuple[str, float, bool]:
    lines_out: List[str] = []
    sizes: List[float] = []
    bold = False
    for line in block.get("lines", []):
        pieces: List[str] = []
        for span in line.get("spans", []):
            raw = span.get("text", "")
            if raw:
                pieces.append(str(raw))
            try:
                sizes.append(float(span.get("size") or 0))
            except Exception:
                pass
            font = str(span.get("font", "")).lower()
            flags = int(span.get("flags") or 0)
            if "bold" in font or (flags & 16):
                bold = True
        line_text = _clean_text("".join(pieces))
        if line_text:
            lines_out.append(line_text)
    return "\n".join(lines_out), (max(sizes) if sizes else 0.0), bold


def _heading_level(text: str, font_size: float, body_size: float, bold: bool) -> Optional[int]:
    if not text or len(text) > 180:
        return None
    ratio = font_size / max(body_size, 1.0)
    if ratio >= 1.55:
        return 1
    if ratio >= 1.25 and (bold or len(text) <= 100):
        return 2
    return None


def _extract_tables(page: "fitz.Page") -> List[Dict[str, Any]]:
    tables: List[Dict[str, Any]] = []
    if not hasattr(page, "find_tables"):
        return tables
    try:
        finder = page.find_tables()
        found = list(getattr(finder, "tables", []) or [])
    except Exception:
        return tables

    for table in found:
        bbox = _rect_tuple(table.bbox)
        try:
            raw_rows = table.extract() or []
        except Exception:
            raw_rows = []
        rows = [[_clean_text(cell) for cell in row] for row in raw_rows]
        rows = [row for row in rows if any(row)]
        if not rows:
            continue
        tables.append({"bbox": bbox, "rows": rows})
    return tables


def extract_page_structure(pdf_bytes: bytes, page_number: int) -> Dict[str, Any]:
    """PyMuPDF structural extraction for a single 1-indexed PDF page.

    Returns native text (paragraphs/headings, in reading order) and tables
    (as row lists) already present in the PDF's text layer — no OCR, no VLM.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if page_number < 1 or page_number > len(doc):
            return {"paragraphs": [], "tables": [], "has_text_layer": False}

        page = doc.load_page(page_number - 1)
        page_dict = page.get_text("dict")
        body_size = _body_font_size(page_dict)

        table_blocks = _extract_tables(page)
        table_boxes = [t["bbox"] for t in table_blocks]

        candidates: List[Tuple[float, float, Dict[str, Any]]] = []

        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            bbox = _rect_tuple(block.get("bbox"))
            if any(_intersection_ratio(bbox, tb) >= 0.55 for tb in table_boxes):
                continue
            text, font_size, bold = _text_block(block)
            text = _clean_text(text)
            if not text:
                continue
            level = _heading_level(text, font_size, body_size, bold)
            candidates.append((bbox[1], bbox[0], {
                "type": "heading" if level else "paragraph",
                "text": text,
                "heading_level": level,
            }))

        candidates.sort(key=lambda item: (item[0], item[1]))

        paragraphs = []
        current_section = ""
        for _, _, record in candidates:
            if record["type"] == "heading" and (record.get("heading_level") or 1) <= 1:
                current_section = record["text"]
            paragraphs.append({
                "text": record["text"],
                "is_heading": record["type"] == "heading",
                "section": current_section,
            })

        return {
            "paragraphs": paragraphs,
            "tables": [{"rows": t["rows"]} for t in table_blocks],
            "has_text_layer": bool(paragraphs or table_blocks),
        }
    finally:
        doc.close()


__all__ = ["extract_page_structure"]