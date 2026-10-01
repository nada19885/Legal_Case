"""
Where the text is: boxes, lines and zones on a cleaned page image.
Location: lib/python/legal_platform/layout_boxes.py

Pure OpenCV, no reading and no model. On a page prepared by
image_tables.prepare_page (letters about 24 px tall), all sizes below are
measured in letter heights, so they hold for any page:

  layout(gray)        the whole step: words, lines, zones, then whole boxes.
  find_boxes(gray)    one box per word / number / short phrase. Printed rules
                      (solid or dotted, thin and several lines long) and
                      solid blocks (redactions) are removed first, a box
                      never crosses a column rule, and lines that touch are
                      cut apart at the faintest rows between them.
  group_lines(boxes)  boxes sharing a baseline form a line.
  find_zones(lines)   consecutive lines that hold several widely spaced
                      boxes aligned with each other form a TABLE zone; other
                      lines form TEXT zones (paragraphs).
  column_guides(...)  for a table zone: the x-ranges where its rows' boxes
                      line up, i.e. the columns, found from alignment alone.
  merge_boxes(...)    the words of one table cell, or of one text line up to
                      a wide gap, joined into one box, so nothing is read in
                      pieces.

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

from .image_tables import _line_masks, ink_height, text_ink


MAX_BOX_WIDTH = 28             # letter heights: longer lines are read in pieces
MIN_RULE_LENGTH = 8            # letter heights: shorter straight strokes are not rules


@dataclass
class Box:
    id: int
    x0: int
    y0: int
    x1: int
    y1: int
    line: int = -1
    kind: str = "text"          # text | figure (stamp, logo, signature)
    parts: int = 1              # word pieces joined into this box

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
    """Typical letter height on the page (grain and specks do not count)."""
    return ink_height(ink) or 20.0


def find_boxes(gray: np.ndarray, digital: bool = False) -> Tuple[List[Box], dict]:
    """Every word / number / short phrase on the page as a box, top to
    bottom, right to left within a line; plus measurements used later.
    `digital` is True for screenshots (see image_tables.prepare_page)."""
    height, width = gray.shape
    ink = text_ink(gray, digital)
    first_h = text_height(ink)
    # Rules are found in the same dark ink as the text: a faint watermark's
    # tall letters are not column rules.
    horizontal, vertical = _line_masks(gray, first_h, ink=ink)
    horizontal, vertical = _thin(horizontal, first_h, False), _thin(vertical, first_h, True)
    rules = cv2.bitwise_or(horizontal, vertical)
    text = cv2.subtract(ink, rules)
    # Solid blocks (a redaction bar, a filled logo) are not text, and must
    # not join the text touching them into one big box.
    core = max(3, int(0.6 * first_h))
    solid = cv2.morphologyEx(text, cv2.MORPH_OPEN, np.ones((core, core), np.uint8))
    text = cv2.subtract(text, cv2.dilate(solid, np.ones((5, 5), np.uint8)))
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
    pieces = []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if h > 1.7 * char_h:
            # Lines touching through a descender, a watermark or a stamp:
            # cut at the blank rows between them.
            pieces += _split_lines(text, joined, (int(x), int(y), int(w), int(h)), char_h)
        else:
            pieces.append((int(x), int(y), int(w), int(h), int(area)))
    boxes: List[Box] = []
    for x, y, w, h, area in pieces:
        if h < 0.45 * char_h or w < 0.3 * char_h or area < 0.5 * char_h * char_h:
            continue
        if w > 0.97 * width:
            continue
        # A tall thin stroke (the edge of the paper, a fold, a short rule)
        # is not text.
        if h > 2 * char_h and w < 0.8 * char_h:
            continue
        # Text on the desk or the floor around the paper is not the document.
        pad = int(char_h)
        around = gray[max(0, y - pad):min(height, y + h + pad), max(0, x - pad):min(width, x + w + pad)]
        if not digital and float(np.percentile(around, 75)) < 120:
            continue
        # A shaded field or a redaction with nothing written in it.
        inside = gray[y:y + h, x:x + w]
        if float(np.mean(inside < np.median(inside) - 45)) < 0.02:
            continue
        kind = "figure" if h > 3.5 * char_h and w > 3 * char_h else "text"
        boxes.append(Box(0, int(x), int(y), int(x + w), int(y + h), kind=kind))
    info = {"char_height": round(char_h, 1), "raw_boxes": len(boxes),
            "rules": _segments(vertical, height, char_h)}
    return _number(boxes, char_h), info


def _split_lines(text: np.ndarray, joined: np.ndarray, rect: Tuple[int, int, int, int],
                 char_h: float) -> List[Tuple[int, int, int, int, int]]:
    """A tall box cut into its text lines at the rows (almost) free of ink.
    Thin bands (dots and marks above or below a line) stay with the nearest
    line. A box with no such rows (a stamp, a logo) is kept whole."""
    x, y, w, h = rect
    ink = text[y:y + h, x:x + w] > 0
    profile = ink.sum(axis=1)
    # Rows with (almost) no ink: a faint watermark stroke or one touching
    # descender may still cross the gap between two lines.
    empty = profile <= max(1, 0.1 * np.percentile(profile, 90))
    bands, start = [], None
    for row, blank in enumerate(list(empty) + [True]):
        if not blank and start is None:
            start = row
        elif blank and start is not None:
            bands.append([start, row])
            start = None
    if len(bands) < 2:
        return [(x, y, w, h, int(np.count_nonzero(joined[y:y + h, x:x + w])))]
    # Fold thin bands (dots, diacritics, a stray mark) into the closest line.
    while len(bands) > 1:
        thin = [i for i, (a, b) in enumerate(bands) if b - a < 0.5 * char_h]
        if not thin:
            break
        i = thin[0]
        before = bands[i][0] - bands[i - 1][1] if i > 0 else 10 ** 9
        after = bands[i + 1][0] - bands[i][1] if i + 1 < len(bands) else 10 ** 9
        j = i - 1 if before <= after else i + 1
        bands[min(i, j)] = [min(bands[i][0], bands[j][0]), max(bands[i][1], bands[j][1])]
        del bands[max(i, j)]
    if len(bands) < 2:
        return [(x, y, w, h, int(np.count_nonzero(joined[y:y + h, x:x + w])))]
    out = []
    for a, b in bands:
        columns = np.nonzero(ink[a:b].any(axis=0))[0]
        if not len(columns):
            continue
        pad = int(0.35 * char_h)
        x0, x1 = max(0, x + int(columns[0]) - pad), min(x + w, x + int(columns[-1]) + 1 + pad)
        y0, y1 = y + a, y + b
        out.append((x0, y0, x1 - x0, y1 - y0, int(np.count_nonzero(joined[y0:y1, x0:x1]))))
    return out


def _thin(mask: np.ndarray, char_h: float, vertical: bool) -> np.ndarray:
    """Keep the thin strokes of a rule mask: a printed rule is a thin line,
    the stroke of a large watermark or logo letter is thick."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count < 2:
        return mask
    length = stats[1:, cv2.CC_STAT_HEIGHT if vertical else cv2.CC_STAT_WIDTH].astype(float)
    thickness = stats[1:, cv2.CC_STAT_AREA] / np.maximum(1, length)
    keep = np.zeros(count, dtype=bool)
    # The masks are widened by a few pixels to re-join broken rules. A rule
    # also runs past several lines of text: letters that happen to line up
    # on three or four consecutive lines are not a rule.
    keep[1:] = (thickness <= max(8, 0.45 * char_h) + 4) & (length >= MIN_RULE_LENGTH * char_h)
    return np.where(keep[labels], mask, 0).astype(np.uint8)


def _number(boxes: List[Box], char_h: float) -> List[Box]:
    """Number the boxes in reading order: text line by line, then figures."""
    lines = group_lines(boxes, char_h)
    ordered = [box for line in lines for box in line]
    for number, box in enumerate(ordered, start=1):
        box.id = number
    figures = [b for b in boxes if b.kind == "figure"]
    for number, box in enumerate(figures, start=len(ordered) + 1):
        box.id = number
    return ordered + figures


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
    # The body rows decide the columns; a title or an information line
    # sitting just above the table (fewer, differently placed items) does not.
    table_lines = [line for line in zone.lines if len(line) >= 3]
    if table_lines:
        most = max(len(line) for line in table_lines)
        table_lines = [line for line in table_lines if len(line) >= max(3, 0.6 * most)]
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


def _segments(vertical: np.ndarray, height: int, char_h: Optional[float]) -> List[Tuple[float, float, float]]:
    from .image_tables import _fitted_lines, _position
    shortest = MIN_RULE_LENGTH * char_h if char_h else 0.08 * height
    return [(round(_position(l, (l[2] + l[3]) / 2), 1), l[2], l[3])
            for l in _fitted_lines(vertical, True, shortest)]


def vertical_rules(gray: np.ndarray, char_h: Optional[float] = None) -> List[float]:
    """x-positions of the long vertical rules printed on the page."""
    _, vertical = _line_masks(gray, char_h)
    return [x for x, _, _ in _segments(vertical, gray.shape[0], char_h)]


# ---------------------------------------------------------------------------
# Whole cells and whole line segments
# ---------------------------------------------------------------------------
def _ruled_between(left: Box, right: Box, rules: List[Tuple[float, float, float]]) -> bool:
    top, bottom = min(left.y0, right.y0), max(left.y1, right.y1)
    return any(left.x1 - 2 <= x <= right.x0 + 2 and y0 < bottom and y1 > top for x, y0, y1 in rules)


def _guide(box: Box, columns: List[Tuple[int, int]]) -> int:
    for index, (c0, c1) in enumerate(columns):
        if c0 - 2 <= box.cx <= c1 + 2:
            return index
    return -1


def merge_boxes(zones: List[Zone], char_h: float,
                rules: Optional[List[Tuple[float, float, float]]] = None) -> List[Box]:
    """Join the pieces of one text into one box, so a word, a number or a
    cell is never read in parts: in a TABLE zone, neighbouring boxes on a
    line inside the same column; in a TEXT zone, the words of a line up to
    a wide gap (a gap that separates two items, like "Account: 123" and
    "Currency: SAR"). Never across a printed rule, and a long line is cut
    at a word gap into pieces short enough to read at full size."""
    merged: List[Box] = []
    for zone in zones:
        limit = (2.5 if zone.kind == "table" else 2.0) * char_h
        # Columns from alignment alone (printed rules are checked with their
        # real extent below, so a rule under the table does not split the
        # title above it).
        guides = column_guides(zone, char_h) if zone.kind == "table" else []
        new_lines = []
        for line in zone.lines:
            pieces = sorted(line, key=lambda b: b.x0)
            out = [Box(0, pieces[0].x0, pieces[0].y0, pieces[0].x1, pieces[0].y1, parts=1)]
            for box in pieces[1:]:
                last = out[-1]
                gap = box.x0 - last.x1
                # A space between two words of this text size joins them
                # whatever the columns; a wider gap only inside one column.
                word_space = gap <= 0.3 * min(last.h, box.h)
                same_column = (not guides or _guide(Box(0, last.x1 - 1, last.y0, last.x1, last.y1), guides)
                               == _guide(Box(0, box.x0, box.y0, box.x0 + 1, box.y1), guides))
                same_cell = (gap <= limit and box.x1 - last.x0 <= MAX_BOX_WIDTH * char_h
                             and not _ruled_between(last, box, rules or [])
                             and (word_space or same_column))
                if same_cell:
                    last.x1, last.y0, last.y1 = max(last.x1, box.x1), min(last.y0, box.y0), max(last.y1, box.y1)
                    last.parts += 1
                else:
                    out.append(Box(0, box.x0, box.y0, box.x1, box.y1, parts=1))
            new_lines.append(out)
            merged.extend(out)
        zone.lines = new_lines
    return merged


def layout(gray: np.ndarray, digital: bool = False) -> Tuple[List[Box], List[Zone], dict]:
    """Boxes (whole cells / line segments, numbered in reading order), the
    zones they form, and measurements: the full box-finding step."""
    words, info = find_boxes(gray, digital)
    char_h = info["char_height"]
    rules = info.pop("rules")
    text_words = [b for b in words if b.kind == "text"]
    lines = group_lines(text_words, char_h)
    zones = find_zones(lines, char_h, gray.shape[1], [x for x, _, _ in rules])
    boxes = merge_boxes(zones, char_h, rules)
    figures = [Box(0, b.x0, b.y0, b.x1, b.y1, kind="figure") for b in words if b.kind == "figure"]
    boxes = _number(boxes + figures, char_h)
    # Zones keep their lines in reading order with the new numbers.
    for zone in zones:
        zone.lines = [sorted(line, key=lambda b: b.id) for line in zone.lines]
    info.update(word_boxes=len(text_words), boxes=len(boxes), rules=len(rules))
    return boxes, zones, info


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
