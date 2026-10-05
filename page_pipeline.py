"""
Reading a case PDF page by page: the PDF's own text where it is reliable,
the vision model where the page is a picture, then one consolidated text.
Location: lib/python/legal_platform/page_pipeline.py

  1. inspect     Each page: its text layer (quality clean / damaged / none),
                 the share of the page covered by embedded pictures, and the
                 pictures themselves.
  2. route       native      reliable text, no significant pictures: the text
                             (with PyMuPDF tables as markdown) is used as is;
                             no vision call. Arabic pages get one text-model
                             pass that may repair words only.
                 native+vlm  reliable text around embedded pictures: the text
                             is kept and each picture is read by the VLM.
                 vlm         scans, photos, screenshots, damaged text layers:
                             the page image is read by the VLM (the text layer,
                             if any, is passed as a hint).
  3. kind        Each picture is classified: photo (camera shot), scan,
                 screenshot; with flags low_resolution, table_heavy, mixed.
  4. views       photo:      A perspective-corrected, evened, sharpened
                             B the same geometry, local contrast, denoised
                 scan:       original + cleaned (deskewed, evened, scaled)
                 screenshot: original + lightly sharpened
                 A picture too large for the model is read in parts.
  5. reading     The VLM transcribes every view with the case context as a
                 hint, tables as markdown, "?" for what it cannot read. Money
                 tables get an extra reading of dates and amounts on enlarged
                 bands.
  6. merge       The text LLM merges the candidates into one text: words may
                 be repaired; numbers are only taken from a candidate, never
                 invented or calculated; disagreements are listed as
                 uncertain. Every number of the merged text is then checked
                 against the candidates; one found in none is listed too.
                 Markdown tables are tidied (rows split by wrapped text are
                 joined back).

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
from .arabic_text import fix_visual_arabic

VisionCall = Callable[[str, bytes], str]
TextLLM = Callable[[str, dict], dict]

RENDER_DPI = 250
MAX_CALL_PIXELS = 3_000_000        # a larger picture is reduced by the model, so it is sent in parts
MIN_LETTER_HEIGHT = 15             # px a letter keeps after any reduction; otherwise split into parts
CONTEXT_CHARS = 4000
MIN_PICTURE_SHARE = 0.04           # an embedded picture smaller than this share of the page is decoration
PICTURE_SHARE_FOR_VLM = 0.15       # reliable text + pictures covering this much -> the pictures are read too
PICTURE_SHARE_IS_IMAGE = 0.6       # pictures covering this much: the page is an image (scan with OCR layer)
PHOTO_VIEWS = 2

_ARABIC = re.compile(r"[ء-ي]")


# ---------------------------------------------------------------------------
# 1. Pages
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


def _table_markdown(rows: List[List[Any]]) -> str:
    rows = [[re.sub(r"\s+", " ", str(cell or "")).replace("|", "/").strip() for cell in row] for row in rows if row]
    rows = [r for r in rows if any(r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def native_text(page: Any) -> Tuple[str, List[str]]:
    """The page's own text in reading order, its tables (PyMuPDF) as
    markdown in place, Arabic stored in drawing order put back in reading
    order. Returns (text, tables)."""
    tables, boxes = [], []
    try:
        for table in page.find_tables().tables:
            markdown = _table_markdown(table.extract())
            if markdown:
                tables.append(markdown)
                boxes.append((tuple(table.bbox), markdown))
    except Exception:
        boxes = []

    def inside(block) -> bool:
        cx, cy = (block[0] + block[2]) / 2, (block[1] + block[3]) / 2
        return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b, _ in boxes)

    items = []
    for block in page.get_text("blocks", sort=True):
        if block[6] == 0 and str(block[4]).strip() and not inside(block):
            items.append((block[1], block[0], str(block[4]).strip()))
    items += [(box[1], box[0], markdown) for box, markdown in boxes]
    items.sort(key=lambda item: (round(item[0], 0), item[1]))
    text = "\n\n".join(fix_visual_arabic(text) if not text.startswith("|") else text for _, _, text in items)
    return text.strip(), tables


def page_count(data: bytes) -> int:
    if not data.startswith(b"%PDF"):
        return 1
    import fitz
    with fitz.open(stream=data, filetype="pdf") as document:
        return document.page_count


def text_layers(data: bytes) -> Dict[int, str]:
    """Every page's raw text layer (cheap): neighbouring-page context."""
    if not data.startswith(b"%PDF"):
        return {}
    import fitz
    with fitz.open(stream=data, filetype="pdf") as document:
        return {index + 1: document.load_page(index).get_text("text").strip() for index in range(document.page_count)}


def load_page(data: bytes, number: int, dpi: int = RENDER_DPI) -> dict:
    """One page: {page, image, text_layer, native_text, native_tables,
    picture_share, pictures: [(name, image, (y0, y1))], regions}. Opens the
    PDF itself, so pages can be loaded from several threads."""
    if not data.startswith(b"%PDF"):
        image = _decode(data)
        return {"page": 1, "image": image, "text_layer": "", "native_text": "", "native_tables": [],
                "picture_share": 1.0, "pictures": [], "regions": [("whole page", image)]}
    import fitz
    with fitz.open(stream=data, filetype="pdf") as document:
        page = document.load_page(number - 1)
        zoom = dpi / 72.0
        image = _decode(page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes("png"))
        area = page.rect.width * page.rect.height
        rects = []
        for info in page.get_images(full=True):
            for rect in page.get_image_rects(info[0]):
                rect = rect & page.rect
                if rect.width * rect.height >= MIN_PICTURE_SHARE * area:
                    rects.append((rect.x0, rect.y0, rect.x1, rect.y1))
        merged = sorted(_merge_rects(rects, gap=0.01 * page.rect.height), key=lambda r: (r[1], r[0]))
        share = min(1.0, sum((r[2] - r[0]) * (r[3] - r[1]) for r in merged) / area) if area else 0.0
        pictures = []
        for index, (x0, y0, x1, y1) in enumerate(merged, 1):
            crop = image[max(0, int(y0 * zoom)):int(y1 * zoom), max(0, int(x0 * zoom)):int(x1 * zoom)]
            if crop.size:
                pictures.append((f"picture {index}", crop, (y0, y1)))
        text = page.get_text("text").strip()
        own, tables = native_text(page) if text else ("", [])
    regions: List[Tuple[str, np.ndarray]] = [("whole page", image)]
    if len(pictures) >= 2 and len(text.split()) < 20:
        regions = [(name, crop) for name, crop, _ in pictures]
    return {"page": number, "image": image, "text_layer": text, "native_text": own, "native_tables": tables,
            "picture_share": round(share, 3), "pictures": pictures, "regions": regions}


def pdf_pages(data: bytes, filename: str = "", pages: Optional[List[int]] = None,
              dpi: int = RENDER_DPI) -> List[dict]:
    """Every page (or the listed ones) loaded with load_page."""
    return [load_page(data, number, dpi) for number in range(1, page_count(data) + 1)
            if not pages or number in pages]


# ---------------------------------------------------------------------------
# 2. Route
# ---------------------------------------------------------------------------
# Characters that never occur in normal Arabic text: a PDF font with a broken
# character map (its numbers are usually stored reversed as well).
_BROKEN_GLYPHS = re.compile(r"[ʄʈȊɢɲ؈ݍݏݝࢭڲ٭ڈٰܵ]")


def text_layer_quality(text: str) -> str:
    """'none', 'clean' (its numbers are exact) or 'damaged' (broken glyphs:
    its numbers may be reversed or scrambled, only its words are a hint)."""
    if not text or len(text.split()) < 5:
        return "none"
    broken = len(_BROKEN_GLYPHS.findall(text))
    return "damaged" if broken >= 3 or broken > 0.002 * len(text) else "clean"


def hint_text(text: str, quality: str) -> str:
    """The text layer as it may be shown to the models: a damaged layer has
    its digits masked, so a reversed number can never be copied from it."""
    if quality == "damaged":
        return re.sub(r"[0-9٠-٩۰-۹]", "#", text)
    return text


def route(page: dict) -> str:
    """native / native+vlm / vlm (see the module docstring)."""
    if text_layer_quality(page.get("text_layer", "")) != "clean" or not page.get("native_text"):
        return "vlm"
    share = float(page.get("picture_share") or 0.0)
    if share >= PICTURE_SHARE_IS_IMAGE:
        return "vlm"
    if share >= PICTURE_SHARE_FOR_VLM and page.get("pictures"):
        return "native+vlm"
    return "native"


# ---------------------------------------------------------------------------
# 3. Kind
# ---------------------------------------------------------------------------
def _ruling_lines(gray: np.ndarray) -> Tuple[int, int, float]:
    """(horizontal lines, vertical lines, share of the height they span)."""
    small = cv2.resize(gray, None, fx=min(1.0, 1400 / max(gray.shape)), fy=min(1.0, 1400 / max(gray.shape)),
                       interpolation=cv2.INTER_AREA)
    binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    h, w = binary.shape
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // 6), 1)))
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, h // 12))))
    count_h, _, stats_h, _ = cv2.connectedComponentsWithStats(horizontal)
    count_v = cv2.connectedComponentsWithStats(vertical)[0]
    if count_h > 1:
        top = stats_h[1:, cv2.CC_STAT_TOP]
        span = float(top.max() - top.min()) / h
    else:
        span = 0.0
    return count_h - 1, count_v - 1, span


def classify(image: np.ndarray) -> Tuple[str, dict]:
    """photo / scan / screenshot, with the measurements behind the decision
    and flags: low_resolution, table_heavy, mixed (a table plus text)."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    digital = it.is_digital(gray)
    letter = it.ink_height(it.text_ink(gray, digital)) or 0.0
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    lines_h, lines_v, span = _ruling_lines(gray)
    flags = []
    if (letter and letter < 10) or sharpness < 30:
        flags.append("low_resolution")
    if (lines_h >= 3 and lines_v >= 2) or lines_h >= 6:
        flags.append("table_heavy")
        if span < 0.6:
            flags.append("mixed")
    measures = {"letter_height": round(float(letter), 1), "sharpness": round(sharpness, 1),
                "ruling_lines": [lines_h, lines_v], "flags": flags}
    if digital:
        return "screenshot", measures
    small = cv2.resize(gray, None, fx=min(1.0, 800 / max(gray.shape)), fy=min(1.0, 800 / max(gray.shape)),
                       interpolation=cv2.INTER_AREA)
    background = cv2.morphologyEx(small, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    background = cv2.GaussianBlur(background, (51, 51), 0)
    unevenness = float(np.percentile(background, 95) - np.percentile(background, 5))
    edges = it._page_outline(gray) is not None
    tilt = abs(it._skew_angle(gray))
    measures.update({"page_edges": edges, "light_unevenness": round(unevenness, 1), "tilt": round(tilt, 2)})
    if edges or unevenness > 35 or tilt > 1.0:
        return "photo", measures
    return "scan", measures


# ---------------------------------------------------------------------------
# 4. Views
# ---------------------------------------------------------------------------
def _sharpen(gray: np.ndarray, amount: float = 0.5, sigma: float = 1.0) -> np.ndarray:
    blur = cv2.GaussianBlur(gray, (0, 0), sigma)
    return cv2.addWeighted(gray, 1 + amount, blur, -amount, 0)


def _gentle(image: np.ndarray) -> np.ndarray:
    """A screenshot or typed page: thin grey strokes darkened a little and
    edges lightly sharpened; nothing that could erase a dot or a comma."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    letter = it.ink_height(it.text_ink(gray, True)) or 24
    if letter < 22:
        factor = min(3.0, 26 / letter)
        gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
    darker = (np.power(gray / 255.0, 1.4) * 255).astype(np.uint8)
    return _sharpen(darker, 0.3)


def _local_contrast(gray: np.ndarray) -> np.ndarray:
    """Photo view B: local contrast (CLAHE), light denoising, a different
    sharpening. No thresholding: it can erase decimal points."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    denoised = cv2.fastNlMeansDenoising(clahe, None, h=5, templateWindowSize=7, searchWindowSize=21)
    return _sharpen(denoised, 0.8, 1.5)


def variants(image: np.ndarray, kind: str, photo_views: int = PHOTO_VIEWS) -> Dict[str, np.ndarray]:
    """The views each picture is read in, by kind."""
    if kind == "photo":
        prepared = it.prepare_page(image).read
        out = {"corrected": _sharpen(prepared, 0.4)}
        if photo_views > 1:
            out["contrast"] = _local_contrast(prepared)
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
# 5. Reading
# ---------------------------------------------------------------------------
TABLE_RULES = """
- Tables: write each table as a markdown table that keeps what the table
  means: a header row with the column names as printed, then ONE row per
  entry (one transaction, one invoice line, one instalment...).
  When an entry's text wraps over several lines inside its cell, keep it in
  that ONE cell and join the lines with <br>; never start a new row for a
  wrapped line. Every row starts and ends with | and has exactly as many
  cells as the header; an empty cell stays empty (| |). Never move a value
  into another column and never add a column the table does not have.
  Opening / closing balances and totals keep their own rows. When a part
  starts in the middle of a table, repeat the header row first.
""".strip()

READ_PROMPT = """
Transcribe ALL text in this image exactly as printed, in reading order
(Arabic right to left, English left to right). {part}

Rules:
- Copy every character exactly: digits (Arabic-Indic digits stay
  Arabic-Indic), separators, signs, dates, IDs, IBANs, emails, names.
- Write a character you cannot read clearly as "?". Never guess, complete
  or correct a value, even one that looks wrong.
- Do not skip anything: headers, small print, stamps, every table row.
{table_rules}
- Keep checkboxes as ☐ / ☒.
- Do not summarise, explain or translate.

{context}
Return only the transcription.
""".strip()

CONTEXT_BLOCK = """
CONTEXT (a hint only; it may be wrong or garbled; transcribe what YOU SEE in the
image, never copy a value from here that is not visible):
{context}
""".strip()

_CASE_KEYS = ("case_name", "case_type", "customer_name", "client_name", "claimant_name", "defendant_name",
              "product_type", "preferred_language")


def _context_lines(context: Any) -> List[str]:
    """Case context as hint lines: case, document, page, parties, currency,
    neighbouring pages. A plain string is the document so far."""
    if not context:
        return []
    if isinstance(context, str):
        return ["Headings and document type seen on earlier pages:\n" + context[:1200]]
    lines = []
    case = {k: v for k, v in (context.get("case") or {}).items() if k in _CASE_KEYS and str(v or "").strip()}
    if case:
        lines.append("Case: " + "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in case.items()))
    if context.get("document_name"):
        page = f", page {context['page_number']}" if context.get("page_number") else ""
        total = f" of {context['page_count']}" if context.get("page_count") else ""
        lines.append(f"Document: {context['document_name']}{page}{total}")
    if context.get("parties"):
        lines.append("Known parties: " + "; ".join(str(p) for p in context["parties"][:12]))
    if context.get("currency"):
        lines.append(f"Likely currency: {context['currency']}")
    if context.get("financial"):
        lines.append("This page appears to be financial (amounts, balances, a statement or schedule).")
    for key, label in (("previous_page", "Previous page (start)"), ("next_page", "Next page (start)")):
        if context.get(key):
            lines.append(f"{label}:\n{str(context[key])[:600]}")
    if context.get("document_so_far"):
        lines.append("Headings and document type seen on earlier pages:\n" + str(context["document_so_far"])[:1200])
    return lines


def _context_text(text_layer: str, context: Any = None, quality: str = "clean") -> str:
    parts_: List[str] = []
    if text_layer and quality != "none":
        label = ("The PDF's own text for this page. Its numbers are exact copies of the document; "
                 "its Arabic words may have letters swapped:" if quality == "clean" else
                 "The PDF's own text for this page, with garbled letters; its digits are hidden (#) because "
                 "they are stored reversed. Use it for words only and read every number from the image:")
        parts_.append(label + "\n" + hint_text(text_layer, quality)[:CONTEXT_CHARS])
    parts_ += _context_lines(context)
    return CONTEXT_BLOCK.format(context="\n\n".join(parts_)) if parts_ else ""


def _clean_answer(answer: Any) -> str:
    return re.sub(r"<think>.*?</think>", "", str(answer or ""), flags=re.S).strip()


def read_variant(picture: np.ndarray, vision: VisionCall, context: str) -> Tuple[str, List[str]]:
    """The text of one view (its parts joined) and any errors."""
    pieces = parts(picture)
    texts, errors = [], []
    for number, piece in enumerate(pieces, start=1):
        note = (f"This is part {number} of {len(pieces)} of a taller image; parts overlap by a line or two."
                if len(pieces) > 1 else "")
        try:
            answer = vision(READ_PROMPT.format(part=note, context=context, table_rules=TABLE_RULES), _png(piece))
            texts.append(_clean_answer(answer))
        except Exception as error:
            errors.append(f"part {number}: {type(error).__name__}: {error}")
            texts.append("")
    return ("\n\n".join(t for t in texts if t), errors) if len(pieces) > 1 else (texts[0], errors)


NUMBERS_PROMPT = """
This image is one band of a financial document page ({band}). Read ONLY the
lines that contain a date, an amount or a balance, top to bottom, including
small numbers standing alone at the edge of the page (an opening balance, a
total). For each such line write one line:
<date as printed> | <first words of the description> | <every number on the line, as printed, separated by ;>
Copy digits exactly (Arabic-Indic digits stay Arabic-Indic, keep separators,
signs and leading zeros). Each line has its own date: never repeat a date
from another line. Use "?" for a character you cannot read. If the band has
no such line, answer NONE.
""".strip()

_MONEY = re.compile(r"[0-9٠-٩][0-9٠-٩,٬]*[.٫][0-9٠-٩]{2,3}(?![0-9٠-٩])")
_TABLE_LINE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*\|", re.M)


def looks_financial(texts: List[str]) -> bool:
    """A reading with several money figures (1,250.00 / ٣٠٠٫٠٠)."""
    return max((len(_MONEY.findall(t or "")) for t in texts), default=0) >= 3


def numbers_pass(picture: np.ndarray, vision: VisionCall, bands: int = 3) -> Tuple[str, List[str]]:
    """Dates and amounts re-read on enlarged horizontal bands: small,
    isolated figures that a full-page transcription skips are read here."""
    height = picture.shape[0]
    overlap = int(0.06 * height)
    step = height // bands

    def read_band(number: int) -> Tuple[int, str, str]:
        top, bottom = max(0, number * step - overlap), min(height, (number + 1) * step + overlap)
        band = cv2.resize(picture[top:bottom], None, fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC)
        try:
            answer = vision(NUMBERS_PROMPT.format(band=f"band {number + 1} of {bands}, top to bottom"), _png(band))
            return number, _clean_answer(answer), ""
        except Exception as error:
            return number, "", f"numbers band {number + 1}: {type(error).__name__}: {error}"

    with ThreadPoolExecutor(max_workers=bands) as pool:          # the bands are read at the same time
        answers = sorted(pool.map(read_band, range(bands)))
    out = [f"[band {n + 1}]\n{a}" for n, a, _ in answers if a and a.upper() != "NONE"]
    return "\n".join(out), [e for _, _, e in answers if e]


# ---------------------------------------------------------------------------
# 6. Merge
# ---------------------------------------------------------------------------
CONSOLIDATE_PROMPT = """
/no_think
You consolidate the extraction candidates of ONE page of a legal / financial
case file into one clean text of what the page says. The payload gives:
- readings: transcriptions of the page image (the same image prepared in
  different ways); a reading named "numbers" is a focused re-read of dates
  and amounts on enlarged bands: for dates, amounts and balances it is the
  most reliable reading; use it to fill numbers the full readings missed (an
  opening balance, a total) and to correct row dates.
  A reading named "pdf_text" is the PDF's own text of the page (outside its
  pictures); "[picture N]" marks where each picture sits; the readings named
  "picture N / ..." are the content of that picture.
- text_layer_quality "clean": the PDF text's NUMBERS are exact copies of the
  document (dates, IDs, amounts, phone numbers): when a reading differs from
  it on a number, use the PDF text's value. Its Arabic words may have
  letters swapped (e.g. "املدعي" for "المدعي"): take words from the readings.
- text_layer_quality "damaged": its digits are hidden (#); words only.
- page_context: the case, document and neighbouring pages (a hint only).

Produce one final, faithful text of the page:
- Keep the page's content and order. Merge compatible candidates, remove
  duplicates, keep every distinct piece of information.
- WORDS: you may fix misread or broken words (Arabic letters split or
  swapped) and join sentences broken across lines, when the candidates or
  the language make the correct word clear. Keep Arabic and English as on the
  page, in normal reading order; do not translate.
- NUMBERS, DATES, AMOUNTS, IDs, IBANs, ACCOUNT and PHONE NUMBERS, EMAILS: never
  invent, calculate or "correct" a value because it looks unusual. Use a
  value exactly as one candidate shows it. When the candidates agree, use it.
  When they differ, write [?: reading A | reading B] in the text and list it
  under "uncertain" with every reading; only choose one when it is clearly
  better supported (the clean PDF text, or a "?" in the other reading), and
  still list it under "uncertain".
- A "?" in a reading means that reader could not see the character: prefer a
  reading that shows it.
{table_rules}
- Do not add anything that is not on the page. Do not summarise.

Return JSON only:
{{
  "text": "the final text of the page",
  "uncertain": [{{"value": "...", "readings": ["..."], "reason": "..."}}],
  "corrections": [{{"from": "as read", "to": "corrected", "why": "..."}}],
  "document_type": "bank statement | statement of claim | court decision | email | letter | invoice | form | other",
  "headings": ["main headings or titles on the page"]
}}
""".format(table_rules=TABLE_RULES).strip()

REPAIR_PROMPT = """
/no_think
The payload holds the PDF's own text of ONE page of a legal / financial case
file. Its numbers and Latin text are exact. Its Arabic words may be damaged
by the PDF export: letters swapped (e.g. "املدعي" for "المدعي", "املبلغ" for
"المبلغ"), split, or in reversed order.

Return the same text with ONLY those Arabic words repaired, when the
language makes the correct word certain. Do not change, add, remove or move
any number, date, ID, amount, name in Latin letters, line or table cell. Keep
markdown tables exactly as they are, cell for cell.

Return JSON only:
{"text": "the repaired text", "corrections": [{"from": "...", "to": "...", "why": "..."}],
 "document_type": "bank statement | statement of claim | court decision | email | letter | invoice | form | other",
 "headings": ["main headings or titles on the page"]}
""".strip()


def consolidate(readings: Dict[str, str], text_layer: str, text_llm: TextLLM, kind: str,
                page_context: str = "") -> dict:
    quality = text_layer_quality(text_layer)
    payload = {"page_kind": kind, "readings": readings, "text_layer_quality": quality,
               "pdf_text_layer": hint_text(text_layer, quality)[:CONTEXT_CHARS] if quality != "none" else "",
               "page_context": page_context}
    best = max(readings.values(), key=len) if readings else ""
    try:
        answer = text_llm(CONSOLIDATE_PROMPT, payload)
    except Exception as error:
        return {"text": best, "uncertain": [], "corrections": [], "document_type": "", "headings": [],
                "error": f"consolidation failed, longest reading kept: {type(error).__name__}: {error}"}
    if not isinstance(answer, dict) or not str(answer.get("text") or "").strip():
        return {"text": best, "uncertain": [], "corrections": [], "document_type": "", "headings": [],
                "error": "the consolidation returned no text; longest reading kept"}
    return {"text": str(answer["text"]).strip(),
            "uncertain": [u for u in answer.get("uncertain") or [] if isinstance(u, dict)],
            "corrections": [c for c in answer.get("corrections") or [] if isinstance(c, dict)],
            "document_type": str(answer.get("document_type") or ""),
            "headings": [str(h) for h in answer.get("headings") or []][:10]}


# --- numbers: every number of the final text must come from a candidate --------
_NUMBER = re.compile(r"[0-9٠-٩۰-۹](?:[0-9٠-٩۰-۹,٬.٫/:\- ]*[0-9٠-٩۰-۹])?")
_TO_ASCII = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _digit_runs(text: str) -> List[str]:
    """The digits of every number in the text (separators dropped)."""
    out = []
    for match in _NUMBER.finditer(text or ""):
        for piece in re.split(r"\s{2,}", match.group(0)):
            digits = re.sub(r"\D", "", piece.translate(_TO_ASCII))
            if digits:
                out.append(digits)
    return out


def unsupported_numbers(final_text: str, sources: List[str]) -> List[str]:
    """Numbers (3+ digits) of the final text that appear in no source."""
    known = set()
    for source in sources:
        known.update(_digit_runs(source))
        known.add(re.sub(r"\D", "", (source or "").translate(_TO_ASCII)))
    out = []
    for match in _NUMBER.finditer(final_text or ""):
        digits = re.sub(r"\D", "", match.group(0).translate(_TO_ASCII))
        if len(digits) < 3 or digits in known or any(digits in k for k in known):
            continue
        if match.group(0) not in out:
            out.append(match.group(0).strip())
    return out


# --- markdown tables: rows split by wrapped text are joined back ---------------
_DATE = re.compile(r"^\s*[0-9٠-٩]{1,4}[/\-.][0-9٠-٩]{1,2}([/\-.][0-9٠-٩]{1,4})?\s*$")
_AMOUNT = re.compile(r"^\s*[-+(]?\s*[A-Za-z؀-ۿ.]*\s*[-+]?[0-9٠-٩][0-9٠-٩,٬]*([.٫][0-9٠-٩]+)?\s*[)A-Za-z؀-ۿ.]*\s*[-+]?\s*$")
_SEPARATOR = re.compile(r"^:?-{2,}:?$")


def _cells(line: str) -> List[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def _tidy_table(lines: List[str]) -> List[str]:
    rows = [_cells(line) for line in lines]
    if len(rows) < 2 or not all(_SEPARATOR.match(c.replace(" ", "")) for c in rows[1] if c):
        return lines
    header, body = rows[0], rows[2:]
    width = len(header)
    if not body:
        return lines

    def column_share(test, index):
        values = [r[index] for r in body if len(r) == width and index < len(r) and r[index]]
        return sum(bool(test(v)) for v in values) / len(values) if values else 0.0

    amount_cols = [i for i in range(width) if column_share(lambda v: _AMOUNT.match(v) and _MONEY.search(v), i) >= 0.6]
    date_cols = [i for i in range(width) if column_share(_DATE.match, i) >= 0.6]
    text_cols = [i for i in range(width) if i not in amount_cols and i not in date_cols]
    if not amount_cols or not text_cols:
        return ["| " + " | ".join(header) + " |", "|" + "---|" * width] + [
            "| " + " | ".join((r + [""] * width)[:max(width, len(r))]) + " |" for r in body]
    description = max(text_cols, key=lambda i: sum(len(r[i]) for r in body if len(r) == width and i < len(r)))

    out_rows: List[List[str]] = []
    for row in body:
        aligned = len(row) == width
        numbers_empty = aligned and all(not row[i] for i in amount_cols + date_cols)
        continuation = out_rows and (numbers_empty or (not aligned and not any(_MONEY.fullmatch(c.strip()) or _DATE.match(c)
                                                                              for c in row if c)))
        if continuation and any(row):
            text = " ".join(c for c in row if c)
            previous = out_rows[-1]
            previous[description] = f"{previous[description]}<br>{text}" if previous[description] else text
            continue
        out_rows.append((row + [""] * width)[:width] if len(row) <= width else row)
    return ["| " + " | ".join(header) + " |", "|" + "---|" * width] + ["| " + " | ".join(r) + " |" for r in out_rows]


def tidy_tables(text: str) -> str:
    """Markdown tables made regular: | at both ends, rows split by wrapped
    text joined back into the row's description cell (only in tables with an
    amount column, and only rows with no date and no amount of their own)."""
    lines = (text or "").split("\n")
    out, block = [], []

    def flush():
        out.extend(_tidy_table(block) if len(block) >= 3 else block)
        block.clear()

    for line in lines:
        if line.count("|") >= 2 or (block and line.strip().startswith("|")):
            block.append(line)
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out)


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
def _native(page: dict, text_llm: TextLLM) -> dict:
    """Route native: the PDF's own text; Arabic words repaired by the text
    model, kept only when every number survives unchanged."""
    text = page["native_text"]
    out = {"text": text, "uncertain": [], "corrections": [], "document_type": "", "headings": [], "llm_calls": 0}
    if not _ARABIC.search(text):
        return out
    out["llm_calls"] = 1
    try:
        answer = text_llm(REPAIR_PROMPT, {"pdf_text": text[:20000]})
    except Exception as error:
        out["error"] = f"word repair failed, PDF text kept: {type(error).__name__}: {error}"
        return out
    repaired = str((answer or {}).get("text") or "").strip() if isinstance(answer, dict) else ""
    if not repaired:
        return out
    if sorted(_digit_runs(repaired)) != sorted(_digit_runs(text)):
        out["error"] = "the word repair changed a number; the PDF text was kept unrepaired"
        return out
    out.update({"text": repaired,
                "corrections": [c for c in answer.get("corrections") or [] if isinstance(c, dict)],
                "document_type": str(answer.get("document_type") or ""),
                "headings": [str(h) for h in answer.get("headings") or []][:10]})
    return out


def _with_picture_marks(page: dict) -> str:
    """The PDF text with [picture N] where each read picture sits."""
    text = page["native_text"]
    marks = "\n".join(f"[{name}]" for name, _, _ in page.get("pictures") or [])
    return f"{text}\n\n{marks}".strip()


def process_page(page: dict, vision: VisionCall, text_llm: TextLLM, context: Any = None,
                 parallel: int = 3, photo_views: int = PHOTO_VIEWS, debug: bool = False,
                 numbers: bool = True) -> dict:
    """One page routed, read and consolidated (see the module docstring).
    `context` is a dict (case, document_name, page_number, page_count,
    parties, currency, previous_page, next_page) or the document so far."""
    started = time.time()
    text_layer = page.get("text_layer", "")
    quality = text_layer_quality(text_layer)
    way = route(page)
    hint_context = "\n\n".join(_context_lines(context))
    errors: List[str] = []
    readings: Dict[str, str] = {}
    regions_out: List[dict] = []
    llm_calls = 0

    if way == "native":
        final = _native(page, text_llm)
        llm_calls += final.pop("llm_calls")
        readings["pdf_text"] = page["native_text"]
        if final.get("error"):
            errors.append(final.pop("error"))
        results: list = []
        jobs: list = []
    else:
        regions = ([(name, crop) for name, crop, _ in page["pictures"]] if way == "native+vlm"
                   else page["regions"])
        reader_context = _context_text(text_layer if way == "vlm" else "", context, quality)
        jobs = []
        for name, image in regions:
            kind, measures = classify(image)
            views = variants(image, kind, photo_views)
            regions_out.append({"region": name, "kind": kind, "flags": measures.get("flags", []),
                                "measures": measures, "variants": list(views)})
            for view, picture in views.items():
                jobs.append((name, kind, view, picture))

        def run(job):
            name, kind, view, picture = job
            text, problems = read_variant(picture, vision, reader_context)
            return job, text, problems

        with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
            results = list(pool.map(run, jobs))

        named = way == "native+vlm" or len(regions) > 1
        for (name, kind, view, picture), text, problems in results:
            key = f"{name} / {view}" if named else view
            readings[key] = text
            errors += [f"{key}: {p}" for p in problems]

        for region in regions_out:                             # what the reading shows refines the flags
            own = [t for (n, _, _, _), t, _ in results if n == region["region"]]
            if (looks_financial(own) or any(_TABLE_LINE.search(t or "") for t in own)) \
                    and "table_heavy" not in region["flags"]:
                region["flags"].append("table_heavy")

        if numbers:                                            # money tables: dates and amounts re-read
            for region in regions_out:
                own = [t for (n, _, _, _), t, _ in results if n == region["region"]]
                if not looks_financial(own):
                    continue
                first = next(p for (n, _, _, p), _, _ in results if n == region["region"])
                text, problems = numbers_pass(first, vision)
                key = f"{region['region']} / numbers" if named else "numbers"
                if text:
                    readings[key] = text
                errors += problems
                region["numbers_pass"] = True

        if way == "native+vlm":
            merged_input = {"pdf_text": _with_picture_marks(page), **readings}
            final = consolidate(merged_input, text_layer, text_llm, "pdf text with pictures", hint_context)
            readings = merged_input
            llm_calls += 1
        elif len(regions) > 1:
            texts, uncertain, corrections, types, headings = [], [], [], [], []
            for region in regions_out:
                own = {k.split(" / ", 1)[1]: v for k, v in readings.items() if k.startswith(region["region"] + " / ")}
                part = consolidate(own, "", text_llm, region["kind"], hint_context)
                llm_calls += 1
                texts.append(f"[{region['region']}]\n{part['text']}")
                uncertain += part["uncertain"]
                corrections += part["corrections"]
                types.append(part["document_type"])
                headings += part["headings"]
                if part.get("error"):
                    errors.append(f"{region['region']}: {part['error']}")
            final = {"text": "\n\n".join(texts), "uncertain": uncertain, "corrections": corrections,
                     "document_type": next((t for t in types if t), ""), "headings": headings}
        else:
            final = consolidate(readings, text_layer, text_llm, regions_out[0]["kind"], hint_context)
            llm_calls += 1
        if final.get("error"):
            errors.append(final.pop("error"))

    final_text = tidy_tables(final["text"])
    uncertain = list(final["uncertain"])
    sources = list(readings.values()) + ([text_layer] if quality == "clean" else [])
    for value in unsupported_numbers(final_text, sources):
        uncertain.append({"value": value, "readings": [],
                          "reason": "this number appears in none of the readings; check it against the page"})

    out = {"page": page["page"], "route": way, "regions": regions_out, "readings": readings,
           "final_text": final_text, "uncertain": uncertain, "corrections": final["corrections"],
           "document_type": final["document_type"], "headings": final["headings"],
           "has_text_layer": bool(text_layer), "text_layer_quality": quality,
           "picture_share": page.get("picture_share", 0.0), "native_tables": len(page.get("native_tables") or []),
           "errors": errors, "vision_calls": len(jobs) + 3 * sum(bool(r.get("numbers_pass")) for r in regions_out),
           "llm_calls": llm_calls, "seconds": round(time.time() - started, 1)}
    if debug:
        out["pictures"] = {(f"{name} / {view}" if (way == "native+vlm" or len(regions_out) > 1) else view): _png(picture)
                           for (name, kind, view, picture), _, _ in results}
    return out


def page_context(base: Optional[dict], number: int, total: int, layers: Dict[int, str]) -> dict:
    """The context for one page: the case context plus its place in the
    document and the start of its neighbouring pages' own text."""
    context = dict(base or {})
    context.update({"page_number": number, "page_count": total,
                    "previous_page": hint_text(layers.get(number - 1, ""), text_layer_quality(layers.get(number - 1, "")))[:600],
                    "next_page": hint_text(layers.get(number + 1, ""), text_layer_quality(layers.get(number + 1, "")))[:600]})
    return context


def process_pdf(data: bytes, filename: str, vision: VisionCall, text_llm: TextLLM,
                pages: Optional[List[int]] = None, parallel: int = 3, photo_views: int = PHOTO_VIEWS,
                debug: bool = False, progress: Optional[Callable[[dict], None]] = None,
                numbers: bool = True, context: Optional[dict] = None) -> List[dict]:
    """Every page of a PDF (or one image file), one after the other;
    progress(page_result) is called after each page."""
    total = page_count(data)
    layers = text_layers(data)
    base = dict(context or {}, document_name=(context or {}).get("document_name") or filename)
    results = []
    for number in range(1, total + 1):
        if pages and number not in pages:
            continue
        try:
            page = load_page(data, number)
            result = process_page(page, vision, text_llm, page_context(base, number, total, layers),
                                  parallel, photo_views, debug, numbers)
        except Exception as error:
            result = {"page": number, "route": "", "error": f"{type(error).__name__}: {error}", "final_text": "",
                      "uncertain": [], "corrections": [], "readings": {}, "regions": [],
                      "errors": [f"{type(error).__name__}: {error}"]}
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


def dataiku_vision(model_id: Optional[str] = None) -> VisionCall:
    from .vlm_adapter import vision_call
    return lambda prompt, png: vision_call(prompt, png, model_id)
