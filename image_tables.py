"""
Photographed and scanned pages: clean the image, then find its tables.
Location: lib/python/legal_platform/image_tables.py

Pure image processing (OpenCV + NumPy), no model calls:

  prepare_page(image)      any page (screenshot, scan, phone photo) scaled so
                           its letters are TARGET_TEXT_HEIGHT px tall; photos
                           and scans also straightened and evened out, and
                           light text on dark bands turned dark on light.
                           Gives a smoothed copy for finding text and an
                           unsmoothed one for reading it.
  clean_page(image)        the older cleaning (fixed page width) used by
                           statement_reader: straighten the page (perspective
                           + tilt), even out shadows, raise contrast.
  find_tables(clean)       every table region on the page, each with its own
                           column boundaries (from the printed vertical lines,
                           or from the blank gaps between columns) and its
                           header band.
  text_rows(clean, ...)    the text lines inside a column or region, so each
                           transaction row can be cut out and read on its own.
  crop(...) / to_png(...)  pieces of the cleaned page for the vision model and
                           for the review screen.

Reading the cut-out pieces and checking the arithmetic happen elsewhere
(see statement_reader.py); this module only measures the page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np

TARGET_WIDTH = 2000          # px: enough for small statement digits
MIN_TABLE_AREA = 0.04        # a table covers at least 4% of the page
MIN_TABLE_COLUMNS = 3
TARGET_TEXT_HEIGHT = 24      # px: typical letter height after prepare_page
MAX_SCALE = 4.0
MAX_PIXELS = 16_000_000      # a larger page is scaled less (memory and time)


@dataclass
class Table:
    box: Tuple[int, int, int, int]                 # x0, y0, x1, y1 on the cleaned page
    columns: List[Tuple[int, int]]                 # (x0, x1) left to right
    header: Optional[Tuple[int, int]] = None       # (y0, y1) of the header band
    body: Optional[Tuple[int, int]] = None         # (y0, y1) below the header
    source: str = "lines"                          # lines | gaps
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 1. Cleaning
# ---------------------------------------------------------------------------
def decode(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The image could not be decoded.")
    return image


def _order_corners(points: np.ndarray) -> np.ndarray:
    points = points.reshape(4, 2).astype("float32")
    total, diff = points.sum(axis=1), np.diff(points, axis=1).ravel()
    return np.array([points[np.argmin(total)], points[np.argmin(diff)],
                     points[np.argmax(total)], points[np.argmax(diff)]], dtype="float32")


def _page_outline(gray: np.ndarray) -> Optional[np.ndarray]:
    """Corners of the sheet of paper when the photo shows its edges
    (the page is brighter than the table or floor around it)."""
    height, width = gray.shape
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    # The sheet must fill most of the photo but not touch every border
    # (then the photo is already cropped to the page).
    if area < 0.4 * width * height or area > 0.97 * width * height:
        return None
    approx = cv2.approxPolyDP(largest, 0.02 * cv2.arcLength(largest, True), True)
    return _order_corners(approx) if len(approx) == 4 else None


def _warp(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    tl, tr, br, bl = corners
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32")
    return cv2.warpPerspective(image, cv2.getPerspectiveTransform(corners, target), (width, height),
                               flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _skew_angle(gray: np.ndarray) -> float:
    """Tilt in degrees: the angle at which the rows of ink (text lines and
    table rules) line up best, i.e. the horizontal ink profile is sharpest.
    Searched coarse to fine within +-6 degrees on a reduced copy."""
    ink = cv2.adaptiveThreshold(cv2.medianBlur(gray, 3), 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                cv2.THRESH_BINARY_INV, 31, 15)
    factor = min(1.0, 1200 / max(ink.shape))
    small = cv2.resize(ink, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    height, width = small.shape
    centre = (width / 2, height / 2)

    def sharpness(angle: float) -> float:
        matrix = cv2.getRotationMatrix2D(centre, angle, 1.0)
        rotated = cv2.warpAffine(small, matrix, (width, height), flags=cv2.INTER_NEAREST,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        rows = rotated.sum(axis=1, dtype=np.float64)
        return float(np.sum(np.diff(rows) ** 2))

    if not small.any():
        return 0.0
    best = max(np.arange(-6, 6.01, 0.5), key=sharpness)
    best = max(np.arange(best - 0.5, best + 0.51, 0.1), key=sharpness)
    # No real tilt: keep the page as it is rather than resample it.
    return float(round(best, 2)) if abs(sharpness(best) - sharpness(0.0)) > 0.02 * sharpness(0.0) else 0.0


def _rotate(image: np.ndarray, angle: float) -> np.ndarray:
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(image, matrix, (width, height), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def _even_light(gray: np.ndarray) -> np.ndarray:
    """Divide out the slowly varying background (shadows, a lamp's
    gradient) so paper is uniformly white and ink uniformly dark."""
    size = max(31, (min(gray.shape) // 15) | 1)
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (size, size)))
    normalised = cv2.divide(gray, background, scale=255)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(normalised)


def _fitted_lines(mask: np.ndarray, vertical: bool, min_length: float) -> List[Tuple[float, float, float, float]]:
    """Each long printed rule as (slope, intercept, start, end): x = slope*y +
    intercept for vertical rules, y = slope*x + intercept for horizontal ones."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    lines = []
    for label in range(1, count):
        x, y, w, h = stats[label, :4]
        length = h if vertical else w
        if length < min_length:
            continue
        ys, xs = np.nonzero(labels[y:y + h, x:x + w] == label)
        ys, xs = ys + y, xs + x
        if len(xs) < 20:
            continue
        if vertical:
            slope, intercept = np.polyfit(ys, xs, 1)
            lines.append((float(slope), float(intercept), float(ys.min()), float(ys.max())))
        else:
            slope, intercept = np.polyfit(xs, ys, 1)
            lines.append((float(slope), float(intercept), float(xs.min()), float(xs.max())))
    return lines


def _intersect(vertical: Tuple[float, float, float, float], horizontal: Tuple[float, float, float, float]) -> np.ndarray:
    a, b = vertical[0], vertical[1]          # x = a*y + b
    c, d = horizontal[0], horizontal[1]      # y = c*x + d
    y = (c * b + d) / (1 - a * c)
    return np.array([a * y + b, y], dtype="float32")


def _table_frame(gray: np.ndarray) -> Optional[np.ndarray]:
    """Corners of the largest ruled table: the outermost long vertical rules
    and the outermost horizontal rules running between them. Used as the
    reference rectangle when the photo is cropped to the page."""
    height, width = gray.shape
    horizontal, vertical = _line_masks(gray)
    verticals = [line for line in _fitted_lines(vertical, True, 0.3 * height)
                 if 0.02 * width < line[0] * (line[2] + line[3]) / 2 + line[1] < 0.98 * width]
    if len(verticals) < 2:
        return None
    middle = lambda line: line[0] * (line[2] + line[3]) / 2 + line[1]
    left, right = min(verticals, key=middle), max(verticals, key=middle)
    span = middle(right) - middle(left)
    if span < 0.4 * width:
        return None
    horizontals = [line for line in _fitted_lines(horizontal, False, 0.4 * span)
                   if line[3] - line[2] >= 0.7 * span
                   and line[2] <= middle(left) + 0.15 * span and line[3] >= middle(right) - 0.15 * span]
    if len(horizontals) < 2:
        return None
    centre = lambda line: line[0] * (line[2] + line[3]) / 2 + line[1]
    top, bottom = min(horizontals, key=centre), max(horizontals, key=centre)
    if centre(bottom) - centre(top) < 0.15 * height:
        return None
    return np.array([_intersect(left, top), _intersect(right, top),
                     _intersect(right, bottom), _intersect(left, bottom)], dtype="float32")


def _warp_page_by(gray: np.ndarray, corners: np.ndarray) -> Optional[np.ndarray]:
    """Warp the whole page so the quadrilateral `corners` becomes an upright
    rectangle (a flat sheet photographed at an angle is one plane, so the
    same correction straightens everything printed on it)."""
    tl, tr, br, bl = corners
    # Already an upright rectangle (a scan, a screenshot): nothing to correct.
    if max(abs(tl[0] - bl[0]), abs(tr[0] - br[0]), abs(tl[1] - tr[1]), abs(bl[1] - br[1])) < 6:
        return None
    rect_w = float(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    rect_h = float(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    if rect_w < 50 or rect_h < 50:
        return None
    target = np.array([tl, tl + [rect_w, 0], tl + [rect_w, rect_h], tl + [0, rect_h]], dtype="float32")
    matrix = cv2.getPerspectiveTransform(corners, target)
    height, width = gray.shape
    frame = cv2.perspectiveTransform(
        np.array([[[0, 0], [width, 0], [width, height], [0, height]]], dtype="float32"), matrix)[0]
    x_min, y_min = frame.min(axis=0)
    x_max, y_max = frame.max(axis=0)
    shift = np.array([[1, 0, -x_min], [0, 1, -y_min], [0, 0, 1]], dtype="float64")
    out_w, out_h = int(x_max - x_min), int(y_max - y_min)
    if out_w > 3 * width or out_h > 3 * height:
        return None        # implausible: the frame was not a real rectangle
    return cv2.warpPerspective(gray, shift @ matrix, (out_w, out_h), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=255)


def clean_page(image: np.ndarray) -> Tuple[np.ndarray, dict]:
    """Straightened, evenly lit, enlarged greyscale page, and what was done."""
    info: dict = {"original_size": [int(image.shape[1]), int(image.shape[0])]}
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()

    corners = _page_outline(gray)
    if corners is not None:
        gray = _warp(gray, corners)
        info["perspective"] = "page edges"

    scale = TARGET_WIDTH / gray.shape[1]
    if abs(scale - 1) > 0.05:
        gray = cv2.resize(gray, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
        info["scale"] = round(scale, 3)

    gray = _even_light(gray)

    if corners is None:
        frame = _table_frame(gray)
        warped = _warp_page_by(gray, frame) if frame is not None else None
        if warped is not None:
            gray = warped
            info["perspective"] = "table frame"

    angle = _skew_angle(gray)
    if abs(angle) > 0.15:
        gray = _rotate(gray, angle)
        info["deskew_degrees"] = round(angle, 2)

    gray = cv2.fastNlMeansDenoising(gray, None, h=7, templateWindowSize=7, searchWindowSize=21)
    info["size"] = [int(gray.shape[1]), int(gray.shape[0])]
    return gray, info


# ---------------------------------------------------------------------------
# 1b. Preparing any page: screenshots and photos, scaled by text size
# ---------------------------------------------------------------------------
@dataclass
class Prepared:
    find: np.ndarray        # cleaned (smoothed) page, for finding the boxes
    read: np.ndarray        # same geometry, not smoothed, for reading the text
    info: dict
    digital: bool           # a screenshot / exported image rather than a photo or scan


def ink_height(ink: np.ndarray) -> float:
    """Typical letter height in a binary ink image, at any scale: the
    median height of letter-like marks weighted by their ink, so grain and
    specks (many, but tiny) do not count. 0 when there is no text."""
    count, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    if count < 2:
        return 0.0
    height, width = ink.shape
    h, w, area = stats[1:, cv2.CC_STAT_HEIGHT], stats[1:, cv2.CC_STAT_WIDTH], stats[1:, cv2.CC_STAT_AREA]
    keep = (h >= 4) & (h <= 0.1 * height) & (w <= 3 * h + 4) & (w <= 0.2 * width) & (area >= 6)
    h, area = h[keep], area[keep]
    if len(h) < 5:
        return 0.0
    order = np.argsort(h)
    cumulative = np.cumsum(area[order])
    return float(h[order][np.searchsorted(cumulative, cumulative[-1] / 2)])


def text_ink(gray: np.ndarray, digital: bool = False) -> np.ndarray:
    """Ink of the text. A screenshot has no grain, so anything clearly
    darker than its surroundings is ink (grey labels included). On a photo
    or scan the page is smoothed first and ink must also be dark in absolute
    terms, so grain and faint shading are not taken for text."""
    if digital:
        return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    smooth = cv2.medianBlur(gray, 3)
    local = cv2.adaptiveThreshold(smooth, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    level, _ = cv2.threshold(smooth, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = (smooth < min(200, level + 25)).astype(np.uint8) * 255
    return cv2.bitwise_and(local, dark)


def is_digital(gray: np.ndarray) -> bool:
    """A screenshot or an exported image: nearly everywhere a pixel equals
    its neighbours (flat backgrounds of any shade), and one background
    shade dominates. Photos and scans carry grain, which JPEG only partly
    smooths away."""
    sample = gray[::2, ::2]
    kernel = np.ones((3, 3), np.uint8)
    spread = cv2.dilate(sample, kernel).astype(np.int16) - cv2.erode(sample, kernel)
    mode = int(np.bincount(sample.ravel(), minlength=256).argmax())
    background = float(np.mean(np.abs(sample.astype(np.int16) - mode) <= 2))
    return float(np.mean(spread <= 1)) >= 0.7 and background >= 0.3


def _invert_dark_parts(gray: np.ndarray, digital: bool) -> Tuple[np.ndarray, List[str]]:
    """Light text on a dark background (a dark-mode screenshot, a header
    bar printed in a dark colour) becomes dark text on light, like the rest."""
    done: List[str] = []
    sample = gray[::2, ::2]
    if int(np.bincount(sample.ravel(), minlength=256).argmax()) < 100:
        return 255 - gray, ["whole page (dark background)"]
    height, width = gray.shape
    char_h = ink_height(text_ink(gray, digital)) or 12
    dark = (gray < 100).astype(np.uint8) * 255
    size = max(3, int(1.5 * char_h))
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (size, size)))
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = gray
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if h < 1.2 * char_h or w < 4 * char_h or h > 0.35 * height:
            continue
        if cv2.contourArea(contour) < 0.85 * w * h:
            continue                     # not a filled rectangle
        if not digital and (x <= 1 or y <= 1 or x + w >= width - 1 or y + h >= height - 1):
            continue                     # the desk around a photographed page
        inside = gray[y:y + h, x:x + w]
        light = float(np.mean(inside > 170))
        # Mostly dark, with some light text in it (bold dark text on a light
        # shade is not a dark band).
        if float(np.median(inside)) < 100 and 0.02 <= light <= 0.5:
            if out is gray:
                out = gray.copy()
            out[y:y + h, x:x + w] = 255 - inside
            done.append(f"dark band at y={y}")
    return out, done


def _text_scale(gray: np.ndarray, digital: bool) -> float:
    measured = ink_height(text_ink(gray, digital))
    if not measured:
        return min(MAX_SCALE, TARGET_WIDTH / gray.shape[1]) if gray.shape[1] < TARGET_WIDTH else 1.0
    return TARGET_TEXT_HEIGHT / measured


def _resize(gray: np.ndarray, scale: float) -> np.ndarray:
    if abs(scale - 1) <= 0.05:
        return gray
    return cv2.resize(gray, None, fx=scale, fy=scale,
                      interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)


def prepare_page(image: np.ndarray) -> Prepared:
    """Any page image made ready for finding and reading text.

    The page is scaled so its letters are about TARGET_TEXT_HEIGHT pixels
    tall whatever the image size (a large screenshot with small text is
    enlarged, never shrunk). Screenshots are only scaled: they are already
    sharp and straight, and smoothing them would blur thin strokes like
    decimal points. Photos and scans are also straightened (page edges,
    table frame, tilt) and evened out; the smoothed copy is used to find
    the boxes and the unsmoothed one to read them."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    digital = is_digital(gray)
    info: dict = {"original_size": [int(gray.shape[1]), int(gray.shape[0])],
                  "source": "screenshot / digital" if digital else "photo / scan"}
    gray, inverted = _invert_dark_parts(gray, digital)
    if inverted:
        info["inverted"] = inverted

    if not digital:
        corners = _page_outline(gray)
        if corners is not None:
            gray = _warp(gray, corners)
            info["perspective"] = "page edges"

    # Scale by text size, measured twice: blurred small text measures a
    # little short, so the first estimate is checked on the scaled page.
    limit = min(MAX_SCALE, (MAX_PIXELS / max(1, gray.shape[0] * gray.shape[1])) ** 0.5)
    scale = min(limit, max(0.4, _text_scale(gray, digital)))
    check = ink_height(text_ink(_resize(gray, scale), digital))
    if check and not 0.8 * TARGET_TEXT_HEIGHT <= check <= 1.25 * TARGET_TEXT_HEIGHT:
        scale = min(limit, max(0.4, scale * TARGET_TEXT_HEIGHT / check))
    gray = _resize(gray, scale)
    info["scale"] = round(scale, 3)

    if not digital:
        gray = _even_light(gray)
        frame = _table_frame(gray) if "perspective" not in info else None
        warped = _warp_page_by(gray, frame) if frame is not None else None
        if warped is not None:
            gray = warped
            info["perspective"] = "table frame"

    angle = _skew_angle(gray)
    if abs(angle) > 0.15:
        gray = _rotate(gray, angle)
        info["deskew_degrees"] = round(angle, 2)

    find = gray if digital else cv2.fastNlMeansDenoising(gray, None, h=7, templateWindowSize=7, searchWindowSize=21)
    info["size"] = [int(gray.shape[1]), int(gray.shape[0])]
    return Prepared(find=find, read=gray, info=info, digital=digital)


# ---------------------------------------------------------------------------
# 2. Tables
# ---------------------------------------------------------------------------
def _ink(gray: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)


def _line_masks(gray: np.ndarray, char_h: Optional[float] = None,
                ink: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Printed horizontal and vertical rules. With the letter height known,
    the sizes follow the text (a rule is several letters long, so a tall
    letter or a stack of 'l's is never taken for one); otherwise they
    follow the page size."""
    ink = _ink(gray) if ink is None else ink
    height, width = gray.shape
    if char_h:
        across = int(max(5 * char_h, min(width // 25, 12 * char_h)))
        down = int(max(3 * char_h, min(height // 30, 8 * char_h)))
        gap = max(5, int(0.5 * char_h))
    else:
        across, down, gap = width // 25, height // 30, 11
    horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (across, 1)))
    # Dotted or dashed column rules: join the dots first (a short vertical
    # closing does not merge stacked text lines, which are further apart).
    dotted = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, gap)))
    vertical = cv2.morphologyEx(dotted, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, down)))
    # Re-join line pieces broken by faint print or the photo.
    horizontal = cv2.dilate(horizontal, cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3)))
    vertical = cv2.dilate(vertical, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15)))
    return horizontal, vertical


def _positions(profile: np.ndarray, threshold: float, min_gap: int) -> List[int]:
    """Centres of the runs where profile exceeds threshold."""
    centres, start = [], None
    for index, value in enumerate(list(profile) + [0]):
        if value > threshold and start is None:
            start = index
        elif value <= threshold and start is not None:
            centre = (start + index - 1) // 2
            if not centres or centre - centres[-1] >= min_gap:
                centres.append(centre)
            start = None
    return centres


def _columns_from_gaps(ink: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> List[Tuple[int, int]]:
    """Column ranges from the vertical strips that hold no ink (tables
    printed without vertical lines)."""
    profile = (ink[y0:y1, x0:x1] > 0).sum(axis=0)
    empty = profile <= max(1, int(0.004 * (y1 - y0)))
    columns, start, min_gap = [], None, max(12, (x1 - x0) // 120)
    run = 0
    for index, is_empty in enumerate(list(empty) + [True]):
        if not is_empty:
            if start is None:
                start = index
            run = 0
        else:
            run += 1
            if start is not None and (run >= min_gap or index == len(empty)):
                columns.append((x0 + start, x0 + index - run + 1))
                start = None
    return [c for c in columns if c[1] - c[0] > 8]


def _position(line: Tuple[float, float, float, float], at: float) -> float:
    return line[0] * at + line[1]


def _merge_close(values: List[float], distance: float) -> List[float]:
    merged: List[float] = []
    for value in sorted(values):
        if merged and value - merged[-1] < distance:
            merged[-1] = (merged[-1] + value) / 2
        else:
            merged.append(value)
    return merged


def _beside_dark(gray: np.ndarray, line: Tuple[float, float, float, float], gap: int = 25) -> bool:
    """True for a vertical rule with the dark desk on one side: the paper's
    edge, not a table rule."""
    height, width = gray.shape
    rows = np.linspace(line[2], line[3], 25).astype(int)
    left, right = [], []
    for row in rows:
        x = int(_position(line, row))
        if 0 <= x - gap and x + gap < width:
            left.append(gray[row, x - gap])
            right.append(gray[row, x + gap])
    if not left:
        return True
    return min(float(np.median(left)), float(np.median(right))) < 110


def find_tables(gray: np.ndarray) -> List[Table]:
    """Every table region on the page, top to bottom, each with its own
    columns (from its printed vertical rules, else from blank gaps) and
    header band (between its top rule and the next rule)."""
    height, width = gray.shape
    horizontal, vertical = _line_masks(gray)
    border_x, border_y = 0.02 * width, 0.015 * height

    # Rules running along the photo's own border are the desk or the
    # paper's edge, not part of any table: leave them out.
    v_lines = [l for l in _fitted_lines(vertical, True, 0.05 * height)
               if border_x < _position(l, (l[2] + l[3]) / 2) < width - border_x and not _beside_dark(gray, l)]
    h_lines = [l for l in _fitted_lines(horizontal, False, 0.1 * width)
               if border_y < _position(l, (l[2] + l[3]) / 2) < height - border_y]
    canvas = np.zeros_like(gray)
    for slope, intercept, start, end in v_lines:
        cv2.line(canvas, (int(slope * start + intercept), int(start)), (int(slope * end + intercept), int(end)), 255, 9)
    for slope, intercept, start, end in h_lines:
        cv2.line(canvas, (int(start), int(slope * start + intercept)), (int(end), int(slope * end + intercept)), 255, 9)
    contours, _ = cv2.findContours(canvas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    ink = _ink(gray)

    tables: List[Table] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h < MIN_TABLE_AREA * width * height or w < width * 0.3:
            continue
        x1, y1 = x + w, y + h
        mid_y, mid_x = y + h / 2, x + w / 2
        inside_v = [l for l in v_lines if x - 10 <= _position(l, mid_y) <= x1 + 10
                    and l[3] - l[2] >= 0.5 * h and l[2] <= mid_y <= l[3]]
        cuts = _merge_close([_position(l, mid_y) for l in inside_v], distance=max(15, w / 80))
        source = "lines"
        if len(cuts) >= MIN_TABLE_COLUMNS + 1:
            columns = [(int(cuts[i]) + 5, int(cuts[i + 1]) - 5) for i in range(len(cuts) - 1)]
        else:
            columns = _columns_from_gaps(ink, x + 6, x1 - 6, y + 6, y1 - 6)
            source = "gaps"
        inside_h = [l for l in h_lines if l[3] - l[2] >= 0.5 * w and l[2] <= mid_x <= l[3]
                    and y - 10 <= _position(l, mid_x) <= y1 + 10]
        rules = _merge_close([_position(l, mid_x) for l in inside_h], distance=12)
        table = Table(box=(x, y, x1, y1), columns=columns, source=source)
        top, bottom = (rules[0], rules[-1]) if len(rules) >= 2 else (y, y1)
        inner = [r for r in rules if top + 15 < r < bottom - 15]
        if inner and inner[0] - top < 0.25 * (bottom - top):
            table.header = (int(top) + 5, int(inner[0]) - 5)
            body_end = next((r for r in inner[1:] if r - inner[0] > 0.3 * (bottom - top)), bottom)
            table.body = (int(inner[0]) + 5, int(body_end) - 5)
            if body_end != bottom:
                table.box = (x, y, x1, int(body_end))
                tables.append(Table(box=(x, int(body_end), x1, y1), columns=[(x + 6, x1 - 6)],
                                    body=(int(body_end) + 5, int(bottom) - 5), source="box",
                                    notes=["box below a table"]))
        else:
            table.body = (int(top) + 5, int(bottom) - 5)
            table.notes.append("no header rule found")
        tables.append(table)
    tables.sort(key=lambda t: t.box[1])
    return tables


# ---------------------------------------------------------------------------
# 3. Text lines and crops
# ---------------------------------------------------------------------------
def text_rows(gray: np.ndarray, x0: int, x1: int, y0: int, y1: int, min_height: int = 10) -> List[Tuple[int, int]]:
    """(top, bottom) of every text line inside a rectangle, ignoring printed
    rules and light background speckle."""
    ink = _ink(gray)[y0:y1, x0:x1]
    wide, tall = max(20, (x1 - x0) // 2), 60
    rules = cv2.bitwise_or(
        cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (wide, 1))),
        cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, tall))))
    ink = cv2.subtract(ink, cv2.dilate(rules, np.ones((3, 3), np.uint8)))
    profile = (ink > 0).sum(axis=1)
    threshold = max(4, int(0.08 * (x1 - x0)))
    rows, start = [], None
    for index, value in enumerate(list(profile) + [0]):
        if value > threshold and start is None:
            start = index
        elif value <= threshold and start is not None:
            if index - start >= min_height:
                rows.append((y0 + start, y0 + index))
            start = None
    return rows


def has_ink(gray: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> bool:
    """True when a cell holds text (not just background or a rule)."""
    return bool(text_rows(gray, x0, x1, y0, y1))


def row_anchors(gray: np.ndarray, column: Tuple[int, int], body: Tuple[int, int],
                min_fill: float = 0.45) -> List[Tuple[int, int]]:
    """Text lines in a column that is filled once per row (a date column):
    one per transaction. Fragments of text spilling in from a neighbouring
    column are ignored: a real entry spans most of the column's width."""
    x0, x1 = column
    ink = _ink(gray)
    anchors = []
    for top, bottom in text_rows(gray, x0, x1, body[0], body[1]):
        filled = np.nonzero((ink[top:bottom, x0:x1] > 0).sum(axis=0) > 1)[0]
        if len(filled) and filled[-1] - filled[0] >= min_fill * (x1 - x0):
            anchors.append((top, bottom))
    return anchors


def reading_sheet(gray: np.ndarray, table: Table, labels: List[str], y0: int, y1: int,
                  label_height: int = 70) -> np.ndarray:
    """The part of a table between y0 and y1 with a label bar on top that
    names every column in plain capitals, and strong separators between
    the columns, so a reader cannot attribute a number to the wrong column."""
    x0, x1 = table.box[0], table.box[2]
    body = cv2.cvtColor(crop(gray, x0, y0, x1, y1, pad=0), cv2.COLOR_GRAY2BGR)
    bar = np.full((label_height, body.shape[1], 3), 255, np.uint8)
    for (c0, c1), label in zip(table.columns, labels):
        left, right = c0 - x0, c1 - x0
        size = min(1.4, max(0.6, (right - left) / (28 * max(4, len(label)))))
        (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, size, 3)
        cv2.putText(bar, label, (left + max(4, (right - left - text_w) // 2), (label_height + text_h) // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, size, (0, 0, 180), 3, cv2.LINE_AA)
    sheet = np.vstack([bar, body])
    for c0, c1 in table.columns:
        # On the printed rule itself (columns stop 5 px inside it), thin, so
        # digits printed up against the rule stay visible.
        for edge in (c0 - x0 - 5, c1 - x0 + 5):
            cv2.line(sheet, (edge, 0), (edge, label_height), (200, 0, 0), 3)
            cv2.line(sheet, (edge, label_height), (edge, sheet.shape[0]), (200, 0, 0), 1)
    return sheet


def draw_tables(gray: np.ndarray, tables: List[Table]) -> np.ndarray:
    """The cleaned page with every region (red), header band (green) and
    column boundary (blue) drawn on it, for checking what was found."""
    picture = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for number, table in enumerate(tables, start=1):
        x0, y0, x1, y1 = table.box
        cv2.rectangle(picture, (x0, y0), (x1, y1), (0, 0, 220), 5)
        cv2.putText(picture, f"{number}", (x0 + 8, y0 + 45), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 220), 4)
        if table.header:
            cv2.rectangle(picture, (x0 + 6, table.header[0]), (x1 - 6, table.header[1]), (0, 150, 0), 4)
        if len(table.columns) > 1:
            for c0, c1 in table.columns:
                cv2.line(picture, (c0 - 5, y0), (c0 - 5, y1), (220, 0, 0), 3)
    return picture


def crop(gray: np.ndarray, x0: int, y0: int, x1: int, y1: int, pad: int = 6) -> np.ndarray:
    height, width = gray.shape[:2]
    return gray[max(0, y0 - pad):min(height, y1 + pad), max(0, x0 - pad):min(width, x1 + pad)]


def to_png(image: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("PNG encoding failed.")
    return buffer.tobytes()
