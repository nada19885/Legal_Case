"""
Post-extraction normalization engine.
Location: lib/python/legal_platform/financial_normalizer.py
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation

ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    "يناير": "01", "فبراير": "02", "مارس": "03", "أبريل": "04", "مايو": "05", "يونيو": "06",
    "يوليو": "07", "أغسطس": "08", "سبتمبر": "09", "أكتوبر": "10", "نوفمبر": "11", "ديسمبر": "12",
}


def to_ascii_digits(text: str) -> str:
    if not text:
        return ""
    return str(text).translate(ARABIC_INDIC_DIGITS).strip()


def normalize_amount(raw_amount: str) -> str:
    """Standardizes amount strings to clean numeric strings with 2 decimal places (e.g. 4092.44)."""
    text = to_ascii_digits(raw_amount)
    if not text or text == "—":
        return "—"

    # Remove currency symbols, words, or bracketed content
    text = re.sub(r"[^\d.,\-]", "", text)
    if not text:
        return "—"

    # Disambiguate European vs US format (e.g., 4.090,00 vs 4,090.00)
    last_comma = text.rfind(",")
    last_dot = text.rfind(".")
    if last_comma > last_dot:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")

    try:
        val = Decimal(text)
        return f"{val:,.2f}"
    except (InvalidOperation, ValueError):
        return raw_amount


def normalize_date(raw_date: str) -> str:
    """Standardizes dates to YYYY-MM-DD or YYYY-MM-DD (AH) for Hijri dates."""
    text = to_ascii_digits(raw_date)
    if not text or text == "—":
        return "—"

    is_hijri = "هـ" in raw_date or "ه" in raw_date or "AH" in raw_date.upper()
    clean = re.sub(r"[^\w/\-]", " ", text).strip()

    # Pattern A: YYYY-MM-DD or YYYY/MM/DD
    match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", clean)
    if match:
        y, m, d = match.groups()
        year_int = int(y)
        if year_int < 1500 or is_hijri:
            return f"{year_int:04d}-{int(m):02d}-{int(d):02d} (AH)"
        return f"{year_int:04d}-{int(m):02d}-{int(d):02d}"

    # Pattern B: DD/MM/YYYY or DD-MM-YYYY
    match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", clean)
    if match:
        d, m, y = match.groups()
        year_int = int(y)
        if year_int < 1500 or is_hijri:
            return f"{year_int:04d}-{int(m):02d}-{int(d):02d} (AH)"
        return f"{year_int:04d}-{int(m):02d}-{int(d):02d}"

    # Pattern C: Textual month (e.g., "26 MAY 23" or "26-MAY-2023")
    match = re.search(r"(\d{1,2})[\s\-_]([A-Za-z]+|\w+)[\s\-_](\d{2,4})", clean)
    if match:
        d, month_name, y = match.groups()
        month_code = MONTH_MAP.get(month_name.lower()[:3])
        if month_code:
            year_int = int(y)
            if year_int < 100:
                year_int += 2000
            return f"{year_int:04d}-{month_code}-{int(d):02d}"

    # Pattern D: Short YY/MM/DD (e.g. 45/01/07 -> 1445-01-07 AH)
    match = re.search(r"^(\d{2})[/-](\d{1,2})[/-](\d{1,2})$", clean)
    if match:
        y, m, d = match.groups()
        return f"14{y}-{int(m):02d}-{int(d):02d} (AH)"

    return clean[:10]


def normalize_currency(raw_currency: str, description_hint: str = "") -> str:
    """Standardizes currency labels to ISO 4217 codes."""
    combined = f"{raw_currency} {description_hint}".upper()
    if any(k in combined for k in ["USDT", "TETHER"]):
        return "USDT"
    if any(k in combined for k in ["USD", "$", "دولار", "DOLLAR"]):
        return "USD"
    if any(k in combined for k in ["EUR", "€", "يورو"]):
        return "EUR"
    if any(k in combined for k in ["SAR", "ر.س", "ريال", "ريالا", "SR", "SAUDI RIYAL"]):
        return "SAR"
    return "SAR"


def normalize_debit_credit(raw_dc: str, description: str = "") -> str:
    """Classifies transaction direction based on Arabic and English markers."""
    val = (raw_dc or "").lower().strip()
    if val in {"debit", "credit"}:
        return val

    desc = (description or "").lower()
    if any(w in desc for w in ["خصم", "سحب", "تحويل صادر", "رسوم", "فاتورة", "purchase", "pos", "fee", "debit", "مدين"]):
        return "debit"
    if any(w in desc for w in ["إيداع", "ايداع", "تحويل وارد", "بيع", "حوالة واردة", "راتب", "credit", "deposit", "refund", "دائن"]):
        return "credit"

    return "unclear"


def normalize_row_for_ledger(row_dict: dict, corrections: dict) -> dict:
    """Applies human corrections first, then normalizes all financial fields."""
    try:
        fields_dict = json.loads(row_dict.get("fields_json", "{}") or "{}")
    except Exception:
        fields_dict = {}

    row_id = str(row_dict.get("row_id", ""))
    row_corrections = corrections.get(row_id, {})

    def _val(field: str, fallback: str = "—") -> str:
        if field in row_corrections:
            return str(row_corrections[field].get("corrected_value", fallback))
        return str(fields_dict.get(field, {}).get("value", fallback) or fallback)

    raw_desc = _val("description", "—")
    raw_date = _val("date", "—")
    raw_amount = _val("amount", "—")
    raw_dc = _val("debit_or_credit", "unclear")
    raw_curr = _val("currency", "SAR")

    # Clean description artifacts
    clean_desc = raw_desc.replace("|", " ").replace("<br>", " ").replace("####", " ").replace("---", " ").strip()
    clean_desc = re.sub(r"\s+", " ", clean_desc)

    return {
        "page_number": row_dict.get("page_number", ""),
        "date": normalize_date(raw_date),
        "description": clean_desc,
        "debit_or_credit": normalize_debit_credit(raw_dc, clean_desc),
        "amount": normalize_amount(raw_amount),
        "currency": normalize_currency(raw_curr, clean_desc),
        "row_status": row_dict.get("row_status", ""),
    }