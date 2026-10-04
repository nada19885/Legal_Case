"""
Reading a case PDF page by page: page images, preprocessing by type, VLM
reading of each variant, then LLM consolidation and correction.
Location: lib/python/legal_platform/page_pipeline.py

  1. pages       Every PDF page is rendered as an image (250 dpi). A page made
                 of several separate screenshots / photos is cut into one
                 region per picture, so each is read at full size. An image
                 file is one page.
  2. kind        Each region is classified:
                   photo    phone photo (page edges, shadows, tilt, grain)
                   scan     scanner image (grain, but flat and straight)
                   digital  screenshot or typed page (flat, exact pixels)
  3. variants    photo:   perspective correction + deskew + even lighting +
                          enlargement (image_tables.prepare_page)
                 scan:    original + the same cleaning
                 digital: original + a lightly sharpened, darkened copy
                 A variant too large for the model to see at full size is
                 read in overlapping horizontal parts.
  4. reading     The VLM transcribes every variant, with the page context as a
                 hint only (the PDF's own text layer when the page has one,
                 the document so far): it transcribes what it sees and marks
                 unclear characters with "?".
  5. final       The text LLM merges the readings into one corrected text:
                 words and sentences may be repaired; numbers, dates, IDs and
                 IBANs are only chosen from what was read, never invented;
                 values the readings disagree on are listed as uncertain.

The models are passed in: vision(prompt, png) -> text and
text_llm(system_prompt, payload) -> dict (legal_platform.llm.complete_json).
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from . import image_tables as it

VisionCall = Callable[[str, bytes], str]
TextLLM = Callable[[str, dict], dict]

RENDER_DPI = 250
MAX_CALL_PIXELS = 3_000_000        # a larger picture is reduced by the model, so it is sent in parts
MIN_LETTER_HEIGHT = 15             # px a letter keeps after any reduction; otherwise split into parts
CONTEXT_CHARS = 4000


# ---------------------------------------------------------------------------
# 1. Pages and regions
# ---------------------------------------------------------------------------
def _decode(data: bytes) -> np.ndarray:
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def _merge_rects(rects: List[Tuple[float, float, float, float]], gap: float) -> List[Tuple[float, float, float, float]]:
    """Image rectangles that touch or overlap are one picture (a screenshot
    stored as several strips is not cut apart)."""
    rects = [list(r) for r in rects]
    merged = True
    while merged:
        merged = False
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                a, b = rects[i], rects[j]
                if a[0] - gap <= b[2] and b[0] - gap <= a[2] and a[1] - gap <= b[3] and b[1] - gap <= a[3]:
                    rects[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    del rects[j]
                    merged = True
                    break
            if merged:
                break
    return [tuple(r) for r in rects]


def pdf_pages(data: bytes, filename: str = "", pages: Optional[List[int]] = None,
              dpi: int = RENDER_DPI) -> List[dict]:
    """Every page as {page, image, text_layer, regions: [(name, image)]}."""
    if not data.startswith(b"%PDF"):
        image = _decode(data)
        return [{"page": 1, "image": image, "text_layer": "", "regions": [("whole page", image)]}]
    import fitz
    document = fitz.open(stream=data, filetype="pdf")
    out = []
    try:
        for index in range(document.page_count):
            number = index + 1
            if pages and number not in pages:
                continue
            page = document.load_page(index)
            zoom = dpi / 72.0
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            image = _decode(pixmap.tobytes("png"))
            area = page.rect.width * page.rect.height
            rects = []
            for info in page.get_images(full=True):
                for rect in page.get_image_rects(info[0]):
                    if rect.width * rect.height >= 0.04 * area:
                        rects.append((rect.x0, rect.y0, rect.x1, rect.y1))
            pictures = _merge_rects(rects, gap=0.01 * page.rect.height)
            regions: List[Tuple[str, np.ndarray]] = [("whole page", image)]
            text = page.get_text("text")
            words = len(text.split())
            if len(pictures) >= 2 and words < 20:
                regions = []
                for number_in_page, (x0, y0, x1, y1) in enumerate(sorted(pictures, key=lambda r: (r[1], r[0])), 1):
                    crop = image[max(0, int(y0 * zoom)):int(y1 * zoom), max(0, int(x0 * zoom)):int(x1 * zoom)]
                    if crop.size:
                        regions.append((f"picture {number_in_page}", crop))
            out.append({"page": number, "image": image, "text_layer": text.strip(), "regions": regions})
    finally:
        document.close()
    return out


# ---------------------------------------------------------------------------
# 2. Kind
# ---------------------------------------------------------------------------
def classify(image: np.ndarray) -> Tuple[str, dict]:
    """photo / scan / digital, with the measurements behind the decision."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    if it.is_digital(gray):
        return "digital", {"flat": True}
    small = cv2.resize(gray, None, fx=min(1.0, 800 / max(gray.shape)), fy=min(1.0, 800 / max(gray.shape)),
                       interpolation=cv2.INTER_AREA)
    background = cv2.morphologyEx(small, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    background = cv2.GaussianBlur(background, (51, 51), 0)
    unevenness = float(np.percentile(background, 95) - np.percentile(background, 5))
    edges = it._page_outline(gray) is not None
    tilt = abs(it._skew_angle(gray))
    measures = {"page_edges": edges, "light_unevenness": round(unevenness, 1), "tilt": round(tilt, 2)}
    if edges or unevenness > 35 or tilt > 1.0:
        return "photo", measures
    return "scan", measures


# ---------------------------------------------------------------------------
# 3. Variants
# ---------------------------------------------------------------------------
def _gentle(image: np.ndarray) -> np.ndarray:
    """A screenshot or typed page: thin grey strokes darkened a little and
    edges lightly sharpened; nothing that could erase a dot or a comma."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    letter = it.ink_height(it.text_ink(gray, True)) or 24
    if letter < 22:
        factor = min(3.0, 26 / letter)
        gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    darker = (np.power(gray / 255.0, 1.4) * 255).astype(np.uint8)
    blur = cv2.GaussianBlur(darker, (0, 0), 1.0)
    return cv2.addWeighted(darker, 1.3, blur, -0.3, 0)


def variants(image: np.ndarray, kind: str, photo_variants: int = 1) -> Dict[str, np.ndarray]:
    """The pictures each region is read in, by kind."""
    if kind == "photo":
        prepared = it.prepare_page(image)
        out = {"corrected": prepared.read}
        if photo_variants > 1:
            out["corrected, sharpened"] = _gentle(prepared.read)
        return out
    if kind == "scan":
        return {"original": image, "cleaned": it.prepare_page(image).read}
    return {"original": image, "sharpened": _gentle(image)}


def parts(image: np.ndarray, max_pixels: int = MAX_CALL_PIXELS) -> List[np.ndarray]:
    """The picture as one piece if its letters stay readable once reduced to
    `max_pixels`; otherwise horizontal parts (cut in blank rows, overlapping
    a little) that each fit."""
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    letter = it.ink_height(it.text_ink(gray, it.is_digital(gray))) or 24
    factor = min(1.0, (max_pixels / float(height * width)) ** 0.5)
    if letter * factor >= MIN_LETTER_HEIGHT or height < 4 * letter:
        return [image]
    # Each part keeps letters at MIN_LETTER_HEIGHT after reduction.
    keep = min(1.0, MIN_LETTER_HEIGHT / letter * 1.0)
    part_height = int(max_pixels / (width * keep * keep))
    part_height = max(int(6 * letter), min(height, part_height))
    ink = (it.text_ink(gray, it.is_digital(gray)) > 0).sum(axis=1)
    out, top, overlap = [], 0, int(1.5 * letter)
    while top < height:
        bottom = min(height, top + part_height)
        if bottom < height:                                  # cut in the emptiest row near the end
            window = ink[max(top + part_height // 2, bottom - 3 * int(letter)):bottom]
            if len(window):
                bottom = bottom - len(window) + int(np.argmin(window))
        out.append(image[top:bottom])
        if bottom >= height:
            break
        top = max(top + 1, bottom - overlap)
    return out


def _png(image: np.ndarray, max_pixels: int = MAX_CALL_PIXELS) -> bytes:
    height, width = image.shape[:2]
    factor = min(1.0, (max_pixels / float(height * width)) ** 0.5)
    if factor < 1.0:
        image = cv2.resize(image, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    return it.to_png(image)


# ---------------------------------------------------------------------------
# 4. Reading
# ---------------------------------------------------------------------------
READ_PROMPT = """
Transcribe ALL text in this image exactly as printed, in reading order
(Arabic right to left, English left to right). {part}

Rules:
- Copy every character exactly: digits (Arabic-Indic digits stay
  Arabic-Indic), separators, signs, dates, IDs, IBANs, emails, names.
- Write a character you cannot read clearly as "?". Never guess or complete.
- Do not skip anything: headers, small print, stamps, every table row.
- Render tables as markdown tables, one row per line, same columns as printed.
  Keep checkboxes as ☐ / ☒.
- Do not summarise, explain, translate or correct.

{context}
Return only the transcription.
""".strip()

CONTEXT_BLOCK = """
CONTEXT (a hint only; it may be wrong or garbled; transcribe what YOU SEE in the
image, never copy a value from here that is not visible):
{context}
""".strip()


def _context_text(text_layer: str, document_so_far: str) -> str:
    parts_: List[str] = []
    if text_layer:
        parts_.append("The PDF's own text for this page (may have broken letters or reversed numbers):\n"
                      + text_layer[:CONTEXT_CHARS])
    if document_so_far:
        parts_.append("Headings and document type seen on earlier pages:\n" + document_so_far[:1200])
    return CONTEXT_BLOCK.format(context="\n\n".join(parts_)) if parts_ else ""


def read_variant(picture: np.ndarray, vision: VisionCall, context: str) -> Tuple[str, List[str]]:
    """The text of one variant (its parts joined) and any errors."""
    pieces = parts(picture)
    texts, errors = [], []
    for number, piece in enumerate(pieces, start=1):
        note = (f"This is part {number} of {len(pieces)} of a taller image; parts overlap by a line or two."
                if len(pieces) > 1 else "")
        try:
            answer = vision(READ_PROMPT.format(part=note, context=context), _png(piece))
            texts.append(re.sub(r"<think>.*?</think>", "", str(answer or ""), flags=re.S).strip())
        except Exception as error:
            errors.append(f"part {number}: {type(error).__name__}: {error}")
            texts.append("")
    return ("\n\n".join(t for t in texts if t), errors) if len(pieces) > 1 else (texts[0], errors)


# ---------------------------------------------------------------------------
# 5. Consolidation and correction
# ---------------------------------------------------------------------------
CONSOLIDATE_PROMPT = """
You consolidate the transcriptions of ONE page of a legal / financial case file.
The payload gives several readings of the same page (the same image prepared in
different ways) and, when available, the PDF's own text layer (often garbled:
broken Arabic letters, reversed numbers - use it only as supporting evidence).

Produce one final, faithful text of the page:
- Keep the page's content and order; tables stay markdown tables.
- WORDS: you may fix misread or broken words (e.g. Arabic letters split or
  swapped) and join sentences broken across lines, when the readings or the
  language make the correct word clear.
- NUMBERS, DATES, AMOUNTS, IDs, IBANs, ACCOUNT and PHONE NUMBERS, EMAILS: never
  invent or calculate. Use a value exactly as one of the readings shows it.
  When the readings agree, use it. When they differ, choose the reading that is
  clearly best supported (more readings agree, or the text layer confirms it
  after undoing a reversal) and list it under "uncertain" with every reading.
  When you cannot decide, write the value as [?: reading A | reading B] in the
  text and list it under "uncertain".
- A "?" in a reading means that reader could not see the character: prefer a
  reading that shows it.
- Do not add anything that is not on the page. Do not summarise.

Return JSON only:
{
  "text": "the final text of the page",
  "uncertain": [{"value": "...", "readings": ["..."], "reason": "..."}],
  "corrections": [{"from": "as read", "to": "corrected", "why": "..."}],
  "document_type": "bank statement | statement of claim | court decision | email | letter | invoice | form | other",
  "headings": ["main headings or titles on the page"]
}
""".strip()


def consolidate(readings: Dict[str, str], text_layer: str, text_llm: TextLLM, kind: str) -> dict:
    payload = {"page_kind": kind, "readings": readings,
               "pdf_text_layer": text_layer[:CONTEXT_CHARS] if text_layer else ""}
    try:
        answer = text_llm(CONSOLIDATE_PROMPT, payload)
    except Exception as error:
        best = max(readings.values(), key=len) if readings else ""
        return {"text": best, "uncertain": [], "corrections": [], "document_type": "", "headings": [],
                "error": f"consolidation failed, longest reading kept: {type(error).__name__}: {error}"}
    if not isinstance(answer, dict) or not str(answer.get("text") or "").strip():
        best = max(readings.values(), key=len) if readings else ""
        return {"text": best, "uncertain": [], "corrections": [], "document_type": "", "headings": [],
                "error": "the consolidation returned no text; longest reading kept"}
    return {"text": str(answer["text"]).strip(),
            "uncertain": [u for u in answer.get("uncertain") or [] if isinstance(u, dict)],
            "corrections": [c for c in answer.get("corrections") or [] if isinstance(c, dict)],
            "document_type": str(answer.get("document_type") or ""),
            "headings": [str(h) for h in answer.get("headings") or []][:10]}


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------
def process_page(page: dict, vision: VisionCall, text_llm: TextLLM, document_so_far: str = "",
                 parallel: int = 3, photo_variants: int = 1, debug: bool = False) -> dict:
    """One page: every region classified, prepared, read in each variant,
    then the page consolidated."""
    started = time.time()
    context = _context_text(page.get("text_layer", ""), document_so_far)
    jobs = []
    regions_out = []
    for name, image in page["regions"]:
        kind, measures = classify(image)
        pictures = variants(image, kind, photo_variants)
        regions_out.append({"region": name, "kind": kind, "measures": measures, "variants": list(pictures)})
        for variant_name, picture in pictures.items():
            jobs.append((name, kind, variant_name, picture))

    def run(job):
        name, kind, variant_name, picture = job
        text, errors = read_variant(picture, vision, context)
        return job, text, errors

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        results = list(pool.map(run, jobs))

    readings: Dict[str, str] = {}
    errors: List[str] = []
    for (name, kind, variant_name, picture), text, problems in results:
        key = variant_name if len(page["regions"]) == 1 else f"{name} / {variant_name}"
        readings[key] = text
        errors += [f"{key}: {p}" for p in problems]
    if len(page["regions"]) > 1:
        # Several pictures: consolidate each picture's variants, keep page order.
        texts, uncertain, corrections, types, headings = [], [], [], [], []
        for region in regions_out:
            own = {k.split(" / ", 1)[1]: v for k, v in readings.items() if k.startswith(region["region"] + " / ")}
            final = consolidate(own, "", text_llm, region["kind"])
            texts.append(f"[{region['region']}]\n{final['text']}")
            uncertain += final["uncertain"]
            corrections += final["corrections"]
            types.append(final["document_type"])
            headings += final["headings"]
            if final.get("error"):
                errors.append(f"{region['region']}: {final['error']}")
        final = {"text": "\n\n".join(texts), "uncertain": uncertain, "corrections": corrections,
                 "document_type": next((t for t in types if t), ""), "headings": headings}
    else:
        final = consolidate(readings, page.get("text_layer", ""), text_llm, regions_out[0]["kind"])
        if final.get("error"):
            errors.append(final["error"])
    out = {"page": page["page"], "regions": regions_out, "readings": readings, "final_text": final["text"],
           "uncertain": final["uncertain"], "corrections": final["corrections"],
           "document_type": final["document_type"], "headings": final["headings"],
           "has_text_layer": bool(page.get("text_layer")), "errors": errors,
           "vision_calls": len(jobs), "seconds": round(time.time() - started, 1)}
    if debug:
        out["pictures"] = {(f"{name} / {variant_name}" if len(page["regions"]) > 1 else variant_name): _png(picture)
                           for (name, kind, variant_name, picture), _, _ in results}
    return out


def process_pdf(data: bytes, filename: str, vision: VisionCall, text_llm: TextLLM,
                pages: Optional[List[int]] = None, parallel: int = 3, photo_variants: int = 1,
                debug: bool = False, progress: Optional[Callable[[dict], None]] = None) -> List[dict]:
    """Every page of a PDF (or one image file); progress(page_result) is
    called after each page."""
    results = []
    seen: List[str] = []
    for page in pdf_pages(data, filename, pages):
        try:
            result = process_page(page, vision, text_llm, "\n".join(seen[-12:]), parallel, photo_variants, debug)
        except Exception as error:
            result = {"page": page["page"], "error": f"{type(error).__name__}: {error}", "final_text": "",
                      "uncertain": [], "corrections": [], "readings": {}, "regions": []}
        if result.get("document_type"):
            seen.append(f"page {page['page']}: {result['document_type']} - " + "; ".join(result.get("headings", [])[:3]))
        results.append(result)
        if progress:
            progress(result)
    return results


def dataiku_text_llm(model_id: Optional[str] = None) -> TextLLM:
    from .config import TEXT_STRUCTURING_LLM_ID
    from .llm import complete_json

    def call(prompt: str, payload: dict) -> dict:
        return complete_json(prompt, payload, llm_id=model_id or TEXT_STRUCTURING_LLM_ID, temperature=0.0)
    return call
