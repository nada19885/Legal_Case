"""
Arabic text stored in visual order.
Location: lib/python/legal_platform/arabic_text.py

Many Arabic PDFs (bank statements especially) store text in the order it
is DRAWN on the page, left to right, instead of the order it is READ.
PyMuPDF returns that text as-is, so "البنك السعودي" comes out as
"يدوعسلا كنبلا", brackets are mirrored, and mixed Arabic/English lines
are scrambled. This module detects such lines and restores reading order.

Detection is conservative: a line is only rewritten when its Arabic words
clearly look reversed (e.g. many words END with "لا", the reversed
definite article "ال", or START with "ة", which no Arabic word does).
Lines already in reading order, and English-only text, are left untouched.
Pure functions only.
"""

from __future__ import annotations

import re
from typing import Any

_ARABIC_WORD = re.compile(r"[ء-يٱ-ۓً-ٰٟ]{2,}")
_ARABIC_LETTER = re.compile(r"[ء-يٱ-ۓ]")
# A left-to-right run: Latin letters / digits, possibly joined by the
# punctuation that appears inside references, amounts and names, plus
# brackets and masking characters attached directly to its ends
# ("Pay)", "611**#").
_LTR_CORE = r"[A-Za-z0-9٠-٩]"
_LTR_RUN = re.compile(
    r"[()\[\]#*]*" + _LTR_CORE
    + r"(?:[A-Za-z0-9٠-٩ .,:;_*#@&%+=/\\'-]*" + _LTR_CORE + r")?"
    + r"[()\[\]#*]*"
)


# Frequent words in bank statements and case files. Seeing one of them
# spelled backwards is strong evidence the line is in visual order.
_COMMON_WORDS = {
    "ريال", "تحويل", "رسوم", "مبلغ", "حساب", "رصيد", "بطاقة", "شراء", "ايداع", "إيداع", "سحب", "دفع",
    "عبر", "مدى", "من", "الى", "إلى", "على", "في", "عن", "مع", "رقم", "تاريخ", "قيمة", "ضريبة", "خصم",
    "سداد", "قسط", "دائن", "مدين", "عميل", "بنك", "مصرف", "فاتورة", "حوالة", "واردة", "صادرة", "نقاط",
    "بيع", "تمويل", "فوائد", "غرامة", "عمولة", "اجمالي", "إجمالي", "المبلغ", "الرصيد", "البنك",
}
_COMMON_REVERSED = {word[::-1] for word in _COMMON_WORDS} - _COMMON_WORDS


def _scores(line: str) -> tuple[int, int]:
    """(reading-order evidence, visual-order evidence) for one line."""
    logical = visual = 0
    for word in _ARABIC_WORD.findall(line):
        letters = "".join(_ARABIC_LETTER.findall(word))
        if len(letters) < 2:
            continue
        if letters in _COMMON_WORDS:
            logical += 2
        elif letters in _COMMON_REVERSED:
            visual += 2
        if len(letters) >= 3 and letters.startswith("ال"):
            logical += 1
        if letters.endswith("ة"):
            logical += 1
        if len(letters) >= 3 and letters.endswith("لا"):
            visual += 1
        # No Arabic word starts with taa marbuta or alef maqsura.
        if letters[0] in "ةى":
            visual += 2
    return logical, visual


def is_visual_order(line: str) -> bool:
    logical, visual = _scores(line)
    return visual >= 1 and visual > logical


def fix_line(line: str) -> str:
    """Restore reading order of one visually-ordered line: reverse it, then
    put each left-to-right run (English words, numbers, references) back
    in its own order. Brackets need no mirroring: reversing the line puts
    them back in logical order, and the browser mirrors them in RTL text."""
    reversed_line = line[::-1]
    return _LTR_RUN.sub(lambda match: match.group(0)[::-1], reversed_line)


def fix_visual_arabic(text: Any) -> Any:
    """Fix every visually-ordered line in text; anything else is returned
    unchanged (non-strings included)."""
    if not isinstance(text, str) or not _ARABIC_LETTER.search(text):
        return text
    return "\n".join(fix_line(line) if is_visual_order(line) else line for line in text.split("\n"))


def fix_structure(value: Any) -> Any:
    """Apply fix_visual_arabic to every string in a nested dict/list."""
    if isinstance(value, str):
        return fix_visual_arabic(value)
    if isinstance(value, list):
        return [fix_structure(item) for item in value]
    if isinstance(value, dict):
        return {key: fix_structure(item) for key, item in value.items()}
    return value
