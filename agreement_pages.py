"""
The contract's own pages without their text: the letterhead, logos, stamps,
signatures, lines and borders stay where they are, the text is removed, so
the contract view can write the reviewed text (with its changes) on the
real page.
Location: lib/python/legal_platform/agreement_pages.py

blank_page(pdf_bytes, page_number) -> (png_bytes, layout) or (None, layout)
  layout: {"available": bool, "width", "height" (points),
           "text_box": [left, top, right, bottom] as shares of the page,
           "font": usual text size as a share of the page width}
Only pages with real (digital) text can be cleared; on a scanned page the
text and the logos are one picture, so "available" is false and the
contract view keeps its plain sheet for that page.

page_backgrounds(case_id, documents, pages) caches every page's PNG and
layout in the case documents folder (/cases/<case>/blank_pages/).
"""

from __future__ import annotations

import json
import statistics
from typing import Any, Optional

from .config import CASE_DOCUMENT_FOLDER_ID

BLANK_DIR = "blank_pages"
RENDER_DPI = 110
MIN_TEXT_WORDS = 5            # fewer words: the page's text is in its picture (a scan)


def blank_page(pdf_bytes: bytes, page_number: int, dpi: int = RENDER_DPI) -> tuple[Optional[bytes], dict]:
    import fitz

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        if not 1 <= page_number <= document.page_count:
            return None, {"available": False}
        page = document[page_number - 1]
        width, height = float(page.rect.width), float(page.rect.height)
        layout = {"available": False, "width": width, "height": height}
        spans = [span for block in page.get_text("dict").get("blocks", []) if block.get("type") == 0
                 for line in block.get("lines", []) for span in line.get("spans", []) if span.get("text", "").strip()]
        if sum(len(span["text"].split()) for span in spans) < MIN_TEXT_WORDS:
            return None, layout

        boxes = [fitz.Rect(span["bbox"]) for span in spans]
        box = fitz.Rect(boxes[0])
        for rect in boxes[1:]:
            box |= rect
        # Same margin on both sides (the narrower one): short or right-aligned
        # lines do not make the text area narrower than the page's.
        margin = max(0.0, min(box.x0 / width, 1 - box.x1 / width))
        layout.update({
            "available": True,
            "text_box": [round(margin, 4), round(max(0.0, box.y0 / height), 4),
                         round(1 - margin, 4), round(min(1.0, box.y1 / height), 4)],
            "font": round(statistics.median(float(span.get("size") or 11) for span in spans) / width, 5),
        })

        for rect in boxes:                       # the text only: no fill, pictures and lines kept
            page.add_redact_annot(rect, fill=False)
        try:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                                  text=fitz.PDF_REDACT_TEXT_REMOVE)
        except (TypeError, AttributeError):      # older PyMuPDF: no graphics / text options
            page.apply_redactions(images=getattr(fitz, "PDF_REDACT_IMAGE_NONE", 0))
        png = page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")
    return png, layout


def _records(value: Any) -> list[dict]:
    if value is None:
        return []
    if hasattr(value, "fillna") and hasattr(value, "to_dict"):
        return value.fillna("").to_dict("records")
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _path(case_id: str, page_id: str, suffix: str) -> str:
    return f"/cases/{case_id}/{BLANK_DIR}/{page_id}.{suffix}"


def _read(folder, path: str) -> Optional[bytes]:
    try:
        with folder.get_download_stream(path) as stream:
            return stream.read()
    except Exception:
        return None


def page_backgrounds(case_id: str, documents: Any, pages: Any) -> dict:
    """page_id -> layout for every page of the case's PDFs; the PNGs are
    made once and kept in the folder."""
    import dataiku

    folder = dataiku.Folder(CASE_DOCUMENT_FOLDER_ID)
    paths = {str(d.get("case_document_id") or ""): str(d.get("folder_path") or "") for d in _records(documents)}
    pdfs: dict = {}
    out = {}
    for row in _records(pages):
        page_id = str(row.get("page_id") or row.get("case_document_page_id") or "")
        document_id = str(row.get("case_document_id") or "")
        if not page_id:
            continue
        cached = _read(folder, _path(case_id, page_id, "json"))
        if cached:
            try:
                out[page_id] = json.loads(cached.decode("utf-8"))
                continue
            except ValueError:
                pass
        layout = {"available": False}
        try:
            if document_id not in pdfs:
                data = _read(folder, paths.get(document_id, "")) if paths.get(document_id) else None
                pdfs[document_id] = data if data and data[:4] == b"%PDF" else None
            if pdfs[document_id]:
                png, layout = blank_page(pdfs[document_id], int(float(row.get("page_number") or 0)))
                if png:
                    folder.upload_data(_path(case_id, page_id, "png"), png)
        except Exception as error:
            print(f"[contract page] page {page_id} could not be cleared: {error!r}")
            layout = {"available": False}
        folder.upload_data(_path(case_id, page_id, "json"), json.dumps(layout).encode("utf-8"))
        out[page_id] = layout
    return out


def page_background_png(case_id: str, page_id: str) -> Optional[bytes]:
    import dataiku
    return _read(dataiku.Folder(CASE_DOCUMENT_FOLDER_ID), _path(case_id, page_id, "png"))
