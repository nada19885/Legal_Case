"""
Synthetic test pages with known content, for the extraction tests.

Each page returns (image as BGR numpy array, truth), where truth lists
every piece of text drawn: {"text", "box": (x0, y0, x1, y1), "kind":
"cell" | "header" | "line", "row", "col"} in the page's own pixels. They
mimic what real case files contain without using any real document:

  email_screenshot()   a crisp screenshot of a forwarded bank email: small
                       text, header lines, a caution banner on a coloured
                       background, Arabic paragraphs, a transfer table with
                       two-line headers, and a signature with | separators.
  photo_statement()    a statement with dotted column rules, blur and grain,
                       like a phone photo.
"""

from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _font(size: int, bold: bool = False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def _text(draw, truth, text, xy, font, kind="line", anchor="la", fill=(25, 25, 25), **extra):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor,
              direction="rtl" if any("؀" <= c <= "ۿ" for c in text) else None)
    box = draw.textbbox(xy, text, font=font, anchor=anchor,
                        direction="rtl" if any("؀" <= c <= "ۿ" for c in text) else None)
    truth.append({"text": text, "box": tuple(int(v) for v in box), "kind": kind, **extra})


TRANSFERS = [
    ("Bank Al Jazira", "SA3550100135315570010000", "100.00", "19:09:21", "17-10-2024", "20241017SARJHI6BOPF11923740575"),
    ("Riyad Bank", "SA2420000004020866489940", "878.00", "19:31:28", "17-10-2024", "20241017SARJHI2BOPF11932771920"),
    ("National Commercial Bank", "SA3610000046800000529802", "347.00", "8:13:30", "18-10-2024", "20241018SARJHI2BOPF10813362827"),
    ("Banque Saudi Fransi", "SA8255000000027634500180", "250.00", "11:11:40", "18-10-2024", "20241018SARJHI2BOPF11111423324"),
    ("Mobile pay", "429204152687", "119.00", "7:11:13", "18-10-2024", "429204152687"),
]
TRANSFER_HEADERS = [("Beneficiary Bank's", "name"), ("Beneficiary's", "IBAN"), ("Original", "Amount"),
                    ("Transaction", "Time"), ("Transaction", "Date"), ("Transaction ID", "")]


def email_screenshot(width: int = 2400, size: int = 15) -> Tuple[np.ndarray, List[dict]]:
    image = Image.new("RGB", (width, 1500), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    truth: List[dict] = []
    f, fb = _font(size), _font(size, bold=True)
    y = 40
    for line in ("From: FraudAlerts <FraudAlerts@alrajhibank.com.sa>",
                 "Sent: Friday, October 18, 2024 1:20 PM",
                 "To: FraudAlerts <FraudAlerts@BankAljazira.com>; Fraudalerts <Fraudalerts@bsf.sa>",
                 "Subject: Fraud alert - hold request"):
        _text(draw, truth, line, (60, y), f)
        y += int(size * 1.6)
    y += 10
    draw.rectangle((50, y - 6, width - 50, y + int(size * 1.5)), fill=(255, 235, 156))
    _text(draw, truth, "CAUTION: This message is originated from an external source. Please use caution.",
          (60, y), f)
    y += int(size * 3)
    for line in ("الزملاء في مكافحة الاحتيال المالي تحية طيبة",
                 "نفيدكم بأن عميل المصرف قد تعرض للاحتيال وتنفيذ حوالة إلى حساب لديكم",
                 "نأمل منكم التكرم بالحجز والتحفظ على المبالغ في حال توفرها"):
        _text(draw, truth, line, (width - 60, y), f, anchor="ra")
        y += int(size * 1.7)
    y += 30
    # Transfer table: thin solid rules, two-line headers.
    columns = [(60, 420), (430, 820), (830, 1020), (1030, 1200), (1210, 1380), (1390, 1900)]
    top = y
    header_h = int(size * 3.4)
    row_h = int(size * 2.0)
    bottom = top + header_h + row_h * len(TRANSFERS)
    draw.rectangle((columns[0][0] - 8, top, columns[-1][1] + 8, top + header_h), fill=(220, 230, 241))
    for index, (first, second) in enumerate(TRANSFER_HEADERS):
        x0, x1 = columns[index]
        _text(draw, truth, first, (x0, top + 6), fb, kind="header", col=index, part=0)
        if second:
            _text(draw, truth, second, (x0, top + 6 + int(size * 1.4)), fb, kind="header", col=index, part=1)
    for r, row in enumerate(TRANSFERS):
        yy = top + header_h + r * row_h + 6
        for index, value in enumerate(row):
            x0, x1 = columns[index]
            if index == 2:
                _text(draw, truth, value, (x1 - 10, yy), f, kind="cell", anchor="ra", row=r, col=index)
            else:
                _text(draw, truth, value, (x0, yy), f, kind="cell", row=r, col=index)
    for yy in [top, top + header_h] + [top + header_h + row_h * (r + 1) for r in range(len(TRANSFERS))]:
        draw.line((columns[0][0] - 8, yy, columns[-1][1] + 8, yy), fill=(120, 120, 120), width=1)
    for x in [c[0] - 8 for c in columns] + [columns[-1][1] + 8]:
        draw.line((x, top, x, bottom), fill=(120, 120, 120), width=1)
    y = bottom + 50
    for line in ("Ghanim Alatwai | Officer Anti-Fraud Joint Operations",
                 "Anti-Fraud Management Division | Compliance Group",
                 "Direct Line +966 (11) 289 8014 | Mobile +966 (53) 887 6045"):
        _text(draw, truth, line, (60, y), f)
        y += int(size * 1.6)
    array = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    return array[:y + 40], truth


STATEMENT = [("01/03/2024", "Opening deposit", "", "5,000.00", "5,000.00"),
             ("03/03/2024", "Card purchase", "120.50", "", "4,879.50"),
             ("05/03/2024", "Transfer fee", "15.00", "", "4,864.50"),
             ("09/03/2024", "Salary", "", "8,250.00", "13,114.50"),
             ("12/03/2024", "Rent payment", "3,500.00", "", "9,614.50"),
             ("15/03/2024", "ATM withdrawal", "400.00", "", "9,214.50"),
             ("20/03/2024", "Utility bill", "289.75", "", "8,924.75"),
             ("28/03/2024", "Interest", "", "12.25", "8,937.00")]
STATEMENT_HEADERS = ("Date", "Description", "Debit", "Credit", "Balance")


def photo_statement(seed: int = 1) -> Tuple[np.ndarray, List[dict]]:
    width, height = 1500, 1300
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    truth: List[dict] = []
    f, fb = _font(26), _font(26, bold=True)
    for text, x in (("ACCOUNT STATEMENT", 80), ("Account 0123456789", 600), ("Currency SAR", 1100)):
        _text(draw, truth, text, (x, 120), fb)
    columns = [(80, 300), (310, 760), (770, 980), (990, 1200), (1210, 1440)]
    top = 230
    for index, header in enumerate(STATEMENT_HEADERS):
        x0, x1 = columns[index]
        anchor, x = ("ra", x1 - 8) if index >= 2 else ("la", x0 + 8)
        _text(draw, truth, header, (x, top + 20), fb, kind="header", anchor=anchor, col=index, part=0)
    for r, row in enumerate(STATEMENT):
        y = top + 90 + r * 80
        for index, value in enumerate(row):
            if value:
                x0, x1 = columns[index]
                anchor, x = ("ra", x1 - 8) if index >= 2 else ("la", x0 + 8)
                _text(draw, truth, value, (x, y), f, kind="cell", anchor=anchor, row=r, col=index)
    bottom = top + 90 + len(STATEMENT) * 80
    for y in (top, top + 70, bottom):
        draw.line((70, y, 1450, y), fill=(40, 40, 40), width=2)
    for x in [70] + [c[0] - 5 for c in columns[1:]] + [1450]:
        for y in range(top, bottom, 9):
            draw.line((x, y, x, y + 4), fill=(40, 40, 40), width=2)
    array = np.array(image.convert("L")).astype(np.float32)
    array = cv2.GaussianBlur(array, (3, 3), 0) + np.random.default_rng(seed).normal(0, 10, array.shape)
    array = np.clip(array, 0, 255).astype(np.uint8)
    return cv2.cvtColor(array, cv2.COLOR_GRAY2BGR), truth


def scale_truth(truth: List[dict], factor: float) -> List[dict]:
    return [dict(item, box=tuple(int(v * factor) for v in item["box"])) for item in truth]
