"""
Where the text is: boxes, lines and zones on a cleaned page image.
Location: lib/python/legal_platform/layout_boxes.py

Pure OpenCV, no reading and no model. On a cleaned greyscale page:

  find_boxes(gray)    one box per word / number / short phrase. Printed rules
                      (solid or dotted) are removed first and a box never
                      crosses a column rule, so neighbouring cells stay apart.
  group_lines(boxes)  boxes sharing a baseline form a line.
  find_zones(lines)   consecutive lines that hold several widely spaced
                      boxes aligned with each other form a TABLE zone; other
                      lines form TEXT zones (paragraphs).
  column_guides(...)  for a table zone: the x-ranges where its boxes line
                      up (right edges for numbers, left or right edges for
                      text), i.e. the columns, found from alignment alone.

The boxes are later read by the vision model and arranged into JSON by the
text model (see layout_reader.py); nothing here depends on how a bank
draws its tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .image_tables import _ink, _line_masks


@dataclass
class Box:
    id: int
    x0: int
    y0: int
    x1: int
    y1: int
    line: int = -1
    kind: str = "text"          # text | figure (stamp, logo, signature)

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def h(self) -> int:
        return self.y1 - self.y0

    @property
    def w(self) -> int:
        return self.x1 - self.x0


@dataclass
class Zone:
    kind: str                     # table | text
    lines: List[List[Box]]
    box: Tuple[int, int, int, int]
    columns: List[Tuple[int, int]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Boxes
# ---------------------------------------------------------------------------
def text_height(ink: np.ndarray) -> float:
    """Typical character height on the page: the median height of
    glyph-sized marks (grain and specks are too small to count)."""
    count, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    heights = [stats[i, cv2.CC_STAT_HEIGHT] for i in range(1, count)
               if 10 <= stats[i, cv2.CC_STAT_HEIGHT] <= 120 and stats[i, cv2.CC_STAT_AREA] >= 40]
    return float(median(heights)) if heights else 20.0


def _text_ink(gray: np.ndarray) -> np.ndarray:
    """Ink of the text only: smoothed so photo grain does not break letters
    apart, and dark in absolute terms as well as darker than its
    surroundings (faint shading and grain are not ink)."""
    smooth = cv2.medianBlur(gray, 3)
    local = cv2.adaptiveThreshold(smooth, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    level, _ = cv2.threshold(smooth, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = (smooth < min(200, level + 25)).astype(np.uint8) * 255
    return cv2.bitwise_and(local, dark)


def find_boxes(gray: np.ndarray) -> Tuple[List[Box], dict]:
    """Every word / number / short phrase on the page as a box, top to
    bottom, right to left within a line; plus measurements used later."""
    height, width = gray.shape
    ink = _text_ink(gray)
    horizontal, vertical = _line_masks(gray)
    rules = cv2.bitwise_or(horizontal, vertical)
    text = cv2.subtract(ink, rules)
    char_h = text_height(text)
    # Drop specks (grain, dust, dotted-rule remnants): marks far smaller than
    # a dot on an i at this text size.
    count, labels, stats, _ = cv2.connectedComponentsWithStats(text, connectivity=8)
    small = np.zeros(count, dtype=bool)
    small[1:] = stats[1:, cv2.CC_STAT_AREA] < max(4, 0.02 * char_h * char_h)
    text[small[labels]] = 0

    # Join the characters of a word, and words separated by one normal
    # space, but not the wider gaps between table columns.
    joined = cv2.dilate(text, cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(3, int(0.7 * char_h)), max(1, int(0.2 * char_h)))))
    # A box never crosses a printed column rule.
    joined = cv2.subtract(joined, cv2.dilate(vertical, np.ones((1, 5), np.uint8)))

    count, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    boxes: List[Box] = []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if h < 0.45 * char_h or w < 0.3 * char_h or area < 0.5 * char_h * char_h:
            continue
        if w > 0.97 * width:
            continue
        # Text on the desk or the floor around the paper is not the document.
        pad = int(char_h)
        around = gray[max(0, y - pad):min(height, y + h + pad), max(0, x - pad):min(width, x + w + pad)]
        if float(np.percentile(around, 75)) < 120:
            continue
        # A shaded field or a redaction with nothing written in it.
        inside = gray[y:y + h, x:x + w]
        if float(np.mean(inside < np.median(inside) - 45)) < 0.02:
            continue
        kind = "figure" if h > 3.5 * char_h and w > 3 * char_h else "text"
        boxes.append(Box(0, int(x), int(y), int(x + w), int(y + h), kind=kind))
    info = {"char_height": round(char_h, 1), "raw_boxes": len(boxes)}
    lines = group_lines(boxes, char_h)
    ordered = [box for line in lines for box in line]
    for number, box in enumerate(ordered, start=1):
        box.id = number
    figures = [b for b in boxes if b.kind == "figure"]
    for number, box in enumerate(figures, start=len(ordered) + 1):
        box.id = number
    return ordered + figures, info


# ---------------------------------------------------------------------------
# Lines and zones
# ---------------------------------------------------------------------------
def group_lines(boxes: List[Box], char_h: float) -> List[List[Box]]:
    """Text boxes that share a baseline, top to bottom; each line right to
    left (Arabic reading order; for left-to-right text the order is simply
    reversed by the reader)."""
    lines: List[List[Box]] = []
    for box in sorted((b for b in boxes if b.kind == "text"), key=lambda b: b.cy):
        target = None
        for line in lines[-6:]:
            centre = median(b.cy for b in line)
            if abs(box.cy - centre) < 0.55 * max(char_h, min(box.h, median(b.h for b in line))):
                target = line
                break
        if target is None:
            lines.append([box])
        else:
            target.append(box)
    lines.sort(key=lambda line: median(b.cy for b in line))
    for number, line in enumerate(lines):
        line.sort(key=lambda b: -b.x1)
        for box in line:
            box.line = number
    return lines


def _is_table_line(line: List[Box], char_h: float, page_width: int) -> bool:
    """A table line holds 3+ boxes with at least two wide gaps between them."""
    if len(line) < 3:
        return False
    xs = sorted(line, key=lambda b: b.x0)
    gaps = [xs[i + 1].x0 - xs[i].x1 for i in range(len(xs) - 1)]
    wide = sum(1 for g in gaps if g > 1.5 * char_h)
    return wide >= 2 and (xs[-1].x1 - xs[0].x0) > 0.35 * page_width


def find_zones(lines: List[List[Box]], char_h: float, page_width: int,
               rules_x: Optional[List[float]] = None) -> List[Zone]:
    """Consecutive table lines (allowing a few wrapped description lines in
    between) form table zones; the rest form text zones."""
    flags = [_is_table_line(line, char_h, page_width) for line in lines]
    # A short run of non-table lines between table lines is a wrapped
    # description inside the table, not a paragraph.
    table_runs = [i for i, flag in enumerate(flags) if flag]
    for i, flag in enumerate(flags):
        if not flag and table_runs:
            before = any(j < i and i - j <= 6 for j in table_runs)
            after = any(j > i and j - i <= 6 for j in table_runs)
            if before and after and len(lines[i]) <= 5:
                flags[i] = None          # a wrapped line inside a table
    zones: List[Zone] = []
    for line, flag in zip(lines, flags):
        kind = "text" if flag is False else "table"
        if zones and zones[-1].kind == kind and (
                min(b.y0 for b in line) - zones[-1].box[3] < 6 * char_h):
            zones[-1].lines.append(line)
        else:
            zones.append(Zone(kind, [line], (0, 0, 0, 0)))
        boxes = [b for l in zones[-1].lines for b in l]
        zones[-1].box = (min(b.x0 for b in boxes), min(b.y0 for b in boxes),
                         max(b.x1 for b in boxes), max(b.y1 for b in boxes))
    # A "table" of one or two lines is just a line with spaced words.
    for zone in zones:
        if zone.kind == "table" and sum(1 for l in zone.lines if _is_table_line(l, char_h, page_width)) < 3:
            zone.kind = "text"
    for zone in zones:
        if zone.kind == "table":
            zone.columns = column_guides(zone, char_h, rules_x)
    return zones


def column_guides(zone: Zone, char_h: float, rules_x: Optional[List[float]] = None) -> List[Tuple[int, int]]:
    """Columns of a table zone, from alignment alone: the x-ranges covered
    by boxes on many of its table lines, separated by gaps that (almost) no
    line crosses. Right to left."""
    table_lines = [line for line in zone.lines if len(line) >= 3]
    boxes = [b for line in table_lines for b in line]
    if not boxes:
        return []
    x0, x1 = min(b.x0 for b in boxes), max(b.x1 for b in boxes)
    coverage = np.zeros(x1 - x0 + 1, dtype=np.int32)
    for b in boxes:
        coverage[b.x0 - x0:b.x1 - x0 + 1] += 1
    # A gap crossed by one long description on a single line is still a gap.
    occupied = coverage > max(1, int(0.12 * len(table_lines)))
    columns, start, run = [], None, 0
    min_gap = max(4, int(0.6 * char_h))
    for i, used in enumerate(list(occupied) + [False] * (min_gap + 1)):
        if used:
            if start is None:
                start = i
            run = 0
        elif start is not None:
            run += 1
            if run >= min_gap:
                columns.append((x0 + start, x0 + i - run))
                start = None
    # Printed column rules (solid or dotted), when the page has them, are
    # boundaries too: cells on either side can almost touch.
    for rule in sorted(rules_x or []):
        split = []
        for c0, c1 in columns:
            if c0 + char_h < rule < c1 - char_h:
                split += [(c0, int(rule) - 3), (int(rule) + 3, c1)]
            else:
                split.append((c0, c1))
        columns = split
    return sorted(columns, key=lambda c: -c[1])


def vertical_rules(gray: np.ndarray) -> List[float]:
    """x-positions of the long vertical rules printed on the page."""
    from .image_tables import _fitted_lines, _position
    _, vertical = _line_masks(gray)
    height = gray.shape[0]
    return [_position(l, (l[2] + l[3]) / 2) for l in _fitted_lines(vertical, True, 0.08 * height)]


def draw_boxes(gray: np.ndarray, boxes: List[Box], zones: Optional[List[Zone]] = None,
               numbers: bool = True) -> np.ndarray:
    """The page with every box (blue; stamps and logos orange), its number,
    and the zones (tables red, text green), for checking what was found."""
    picture = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for zone in zones or []:
        colour = (0, 0, 220) if zone.kind == "table" else (0, 150, 0)
        x0, y0, x1, y1 = zone.box
        cv2.rectangle(picture, (x0 - 8, y0 - 8), (x1 + 8, y1 + 8), colour, 4)
        for c0, c1 in zone.columns:
            cv2.line(picture, (c0 - 3, y0 - 8), (c0 - 3, y1 + 8), (220, 0, 220), 2)
    for box in boxes:
        colour = (0, 140, 255) if box.kind == "figure" else (220, 80, 0)
        cv2.rectangle(picture, (box.x0, box.y0), (box.x1, box.y1), colour, 2)
        if numbers:
            cv2.putText(picture, str(box.id), (box.x0, max(12, box.y0 - 3)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 0, 200), 1, cv2.LINE_AA)
    return picture
