from __future__ import annotations

import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_DATE_RE = re.compile(
    r"(?<!\d)(\d{1,2})[\-/\.](\d{1,2})[\-/\.](\d{2,4})(?!\d)"
)
_AMOUNT_RE = re.compile(
    r"(?<!\w)\(?-?[\d٠-٩][\d٠-٩,\.٬٫\s]*\)?\s*"
    r"(?:SAR|ر\.س|ريال(?:اً)?|USD|\$|EUR|€)?(?!\w)",
    flags=re.IGNORECASE,
)
_CURRENCY_RE = re.compile(r"SAR|ر\.س|ريال(?:اً)?|USD|\$|EUR|€", flags=re.IGNORECASE)
_REFERENCE_RE = re.compile(
    r"(?:ref(?:erence)?|مرجع|رقم\s*العملية|transaction\s*no\.?)\s*[:#\-]?\s*([A-Za-z0-9\-/]{4,})",
    flags=re.IGNORECASE,
)
_DEBIT_WORDS = ("debit", "مدين", "خصم", "سحب")
_CREDIT_WORDS = ("credit", "دائن", "إيداع", "ايداع")


@dataclass
class LineItemCandidate:
    page_id: str
    case_document_id: str
    page_number: int
    line_index: int
    raw_line: str
    extraction_method: str  # "deterministic_regex" | "native_table"
    date_exact_text: str = ""
    amount_exact_text: str = ""
    currency_exact_text: str = ""
    debit_or_credit: str = ""
    description: str = ""
    reference_number: str = ""
    party_source: str = ""
    running_balance_exact_text: str = ""


def _to_ascii_digits(value: str) -> str:
    return str(value or "").translate(ARABIC_INDIC_DIGITS)


def normalize_amount_for_matching(exact_text: str) -> Optional[Decimal]:
    """Best-effort numeric value used ONLY to decide whether two extraction
    methods agree. The stored/reported figure always stays exact_text as
    printed on the source document — this function never touches that.
    """
    text = _to_ascii_digits(str(exact_text or "")).strip()
    if not text:
        return None

    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").strip()
    text = _CURRENCY_RE.sub("", text).strip()
    text = re.sub(r"[^\d,.\-٬٫]", "", text)
    text = text.replace("٬", ",").replace("٫", ".")
    if not text:
        return None

    # Disambiguate "1.234,56" vs "1,234.56" by which separator appears last.
    last_comma = text.rfind(",")
    last_dot = text.rfind(".")
    if last_comma > last_dot:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")

    try:
        value = Decimal(text)
    except InvalidOperation:
        return None

    if negative or text.startswith("-"):
        value = -abs(value)
    return value


def normalize_date_for_matching(exact_text: str) -> Optional[str]:
    """Returns an ISO date ONLY when the format is unambiguous (a 4-digit
    year and a day > 12 on one side). Ambiguous dates (2-digit year, or both
    parts <= 12 so DD/MM vs MM/DD can't be resolved) return None rather than
    guess — callers fall back to comparing the raw text instead.
    """
    match = _DATE_RE.search(_to_ascii_digits(str(exact_text or "")))
    if not match:
        return None
    first, second, year_text = match.groups()
    first, second, year = int(first), int(second), int(year_text)
    if year < 100:
        return None
    if first > 12 and second <= 12:
        day, month = first, second
    elif second > 12 and first <= 12:
        day, month = second, first
    else:
        return None
    try:
        return f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return None


def extract_candidates_from_text(
    page_id: str,
    case_document_id: str,
    page_number: int,
    page_text: str,
) -> list[LineItemCandidate]:
    """A text line that contains at least one date AND one amount is treated
    as a transaction-row candidate. This deliberately only proposes rows with
    both signals on one line — it will miss rows wrapped across lines. That's
    acceptable because this pass exists to CORROBORATE the image-grounded LLM
    pass, not to be the sole extractor.
    """
    candidates: list[LineItemCandidate] = []
    for line_index, raw_line in enumerate(page_text.splitlines()):
        line = raw_line.strip()
        if not line:
            continue

        date_match = _DATE_RE.search(_to_ascii_digits(line))
        amount_matches = [
            match.group(0).strip()
            for match in _AMOUNT_RE.finditer(line)
            if re.search(r"\d", match.group(0))
        ]
        if not date_match or not amount_matches:
            continue

        amount_text = max(amount_matches, key=len)
        currency_match = _CURRENCY_RE.search(line)
        reference_match = _REFERENCE_RE.search(line)
        lowered = line.lower()

        debit_or_credit = ""
        if any(word in lowered for word in _DEBIT_WORDS):
            debit_or_credit = "debit"
        elif any(word in lowered for word in _CREDIT_WORDS):
            debit_or_credit = "credit"

        candidates.append(LineItemCandidate(
            page_id=page_id,
            case_document_id=case_document_id,
            page_number=page_number,
            line_index=line_index,
            raw_line=line,
            extraction_method="deterministic_regex",
            date_exact_text=date_match.group(0),
            amount_exact_text=amount_text,
            currency_exact_text=currency_match.group(0) if currency_match else "",
            debit_or_credit=debit_or_credit,
            description=line,
            reference_number=reference_match.group(1) if reference_match else "",
        ))
    return candidates


# ---------------------------------------------------------------------------
# Native PDF table extraction: a bonus corroborating source only, for pages
# that have a real text/table layer. Its output is never sent to a model —
# it only ever feeds the deterministic reconciliation step. Degrades to
# "no extra signal" (empty list) if pdfplumber is not installed, or if the
# page has no extractable table.
# ---------------------------------------------------------------------------

def extract_candidates_from_native_table(
    page_id: str,
    case_document_id: str,
    page_number: int,
    pdf_bytes: bytes,
) -> list[LineItemCandidate]:
    try:
        import pdfplumber
    except ImportError:
        return []

    candidates: list[LineItemCandidate] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if page_number - 1 >= len(pdf.pages) or page_number < 1:
                return []
            page = pdf.pages[page_number - 1]
            tables = page.extract_tables() or []

            for table in tables:
                if not table or len(table) < 2:
                    continue
                header = [str(cell or "").strip().lower() for cell in table[0]]
                columns = _map_columns(header)
                if columns.get("amount") is None:
                    continue

                for row_index, raw_row in enumerate(table[1:], start=1):
                    row = [str(cell or "").strip() for cell in raw_row]
                    amount_cell = _cell(row, columns.get("amount"))
                    if not amount_cell or not re.search(r"\d", amount_cell):
                        continue

                    candidates.append(LineItemCandidate(
                        page_id=page_id,
                        case_document_id=case_document_id,
                        page_number=page_number,
                        line_index=row_index,
                        raw_line=" | ".join(row),
                        extraction_method="native_table",
                        date_exact_text=_cell(row, columns.get("date")),
                        amount_exact_text=amount_cell,
                        currency_exact_text="",
                        debit_or_credit=_infer_debit_credit(columns, row),
                        description=_cell(row, columns.get("description")),
                        reference_number=_cell(row, columns.get("reference")),
                        running_balance_exact_text=_cell(row, columns.get("balance")),
                    ))
    except Exception as error:
        print(f"[financial native table] page={page_number} error={error!r}")
        return []
    return candidates


def _cell(row: list[str], index: Optional[int]) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index]


def _map_columns(header: list[str]) -> dict:
    mapping: dict[str, int] = {}
    for index, name in enumerate(header):
        if any(keyword in name for keyword in ("date", "تاريخ")):
            mapping.setdefault("date", index)
        elif any(keyword in name for keyword in ("debit", "مدين")):
            mapping.setdefault("debit", index)
        elif any(keyword in name for keyword in ("credit", "دائن")):
            mapping.setdefault("credit", index)
        elif any(keyword in name for keyword in ("balance", "رصيد")):
            mapping.setdefault("balance", index)
        elif any(keyword in name for keyword in ("amount", "مبلغ", "قيمة")):
            mapping.setdefault("amount", index)
        elif any(keyword in name for keyword in ("ref", "مرجع", "رقم")):
            mapping.setdefault("reference", index)
        elif any(keyword in name for keyword in ("description", "بيان", "الوصف")):
            mapping.setdefault("description", index)

    if "amount" not in mapping:
        if "debit" in mapping:
            mapping["amount"] = mapping["debit"]
        elif "credit" in mapping:
            mapping["amount"] = mapping["credit"]
    return mapping


def _infer_debit_credit(columns: dict, row: list[str]) -> str:
    debit_value = _cell(row, columns.get("debit"))
    credit_value = _cell(row, columns.get("credit"))
    if debit_value and re.search(r"\d", debit_value):
        return "debit"
    if credit_value and re.search(r"\d", credit_value):
        return "credit"
    return ""