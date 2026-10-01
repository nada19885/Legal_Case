"""
Reading statement tables from photographed or scanned pages.
Location: lib/python/legal_platform/statement_reader.py

  1. image_tables.clean_page straightens and cleans the page;
     image_tables.find_tables finds every table and its columns.
  2. Column roles: the header band is shown to the vision model with every
     column marked C1, C2, ...; it transcribes each header and the code maps
     the header words to a role (date, description, debit, credit, balance,
     ...). The model never decides the role itself.
  3. Rows: the table is read in chunks of a few rows. Each chunk is an
     enlarged picture with OUR label (DATE, DEBIT, BALANCE ...) stamped above
     every column, so a number cannot be attributed to the wrong column.
  4. Arithmetic: on a statement every balance equals the previous balance
     minus the debit plus the credit. reconcile() checks every row and
     repairs what the chain of balances proves (a misread amount, a misread
     balance, debit and credit swapped); a row it cannot prove stays
     unconfirmed.

The vision model is passed in as a function (prompt, png bytes) -> text, so
everything here can be tested without Dataiku.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import image_tables as it

VisionCall = Callable[[str, bytes], str]

ROWS_PER_CHUNK = 8

# ---------------------------------------------------------------------------
# Column roles from header words (Arabic and English)
# ---------------------------------------------------------------------------
ROLE_WORDS: List[Tuple[str, Tuple[str, ...]]] = [
    ("value_date", ("تاريخ الحق", "تاريخ القيد", "تاريخ الاستحقاق", "value date", "val. date", "value")),
    ("date", ("التاريخ", "تاريخ", "date", "posting")),
    ("debit", ("حركة منه", "مدين", "منه", "سحب", "سحوبات", "مدفوعات", "debit", "dr", "withdrawal", "paid out")),
    ("credit", ("حركة له", "دائن", "له", "ايداع", "إيداع", "إيداعات", "credit", "cr", "deposit", "paid in")),
    ("balance", ("الرصيد", "رصيد", "balance", "bal")),
    ("amount", ("المبلغ", "مبلغ", "القيمة", "amount", "value")),
    ("reference", ("المرجع", "مرجع", "رقم العملية", "reference", "ref", "cheque", "شيك")),
    ("description", ("الإيضاحات", "الايضاحات", "البيان", "التفاصيل", "الوصف", "description", "details",
                     "narration", "particulars")),
]
ROLE_LABELS = {
    "date": "DATE", "value_date": "VALUE DATE", "description": "DESCRIPTION", "debit": "DEBIT",
    "credit": "CREDIT", "balance": "BALANCE", "amount": "AMOUNT", "reference": "REFERENCE",
}
_TASHKEEL = re.compile(r"[ً-ْـ]")


def _normal(text: str) -> str:
    text = _TASHKEEL.sub("", str(text or "")).strip().lower()
    return re.sub(r"\s+", " ", text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا"))


def column_role(header: str) -> str:
    """Role of a column from its printed header; longest matching phrase
    wins, so "تاريخ الحق" (value date) beats "تاريخ" (date)."""
    text = _normal(header)
    if not text:
        return "other"
    best, best_length = "other", 0
    for role, words in ROLE_WORDS:
        for word in words:
            word = _normal(word)
            pattern = r"(?<![\w؀-ۿ])" + re.escape(word) + r"(?![\w؀-ۿ])"
            if re.search(pattern, text) and len(word) > best_length:
                best, best_length = role, len(word)
    return best


def column_roles(headers: List[str]) -> List[str]:
    roles = [column_role(h) for h in headers]
    seen: Dict[str, int] = {}
    for index, role in enumerate(roles):        # a role used twice: keep the first
        if role != "other" and role in seen:
            roles[index] = "other"
        seen.setdefault(role, index)
    return roles


# ---------------------------------------------------------------------------
# Amounts
# ---------------------------------------------------------------------------
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def table_decimals(values: List[Optional[str]]) -> Optional[int]:
    """Decimal places used in a table's amount columns (2 for SAR, 3 for
    JOD/KWD/BHD/OMR), decided from the values that show it unambiguously
    (a thousands comma followed by a decimal point, or a decimal part that
    is not exactly three digits)."""
    votes: Dict[int, int] = {}
    for value in values:
        text = str(value or "").translate(_DIGITS).strip()
        match = re.search(r"\d,\d{3}\.(\d+)$", text) or re.search(r"^-?\d{1,3}\.(\d{1,2})$", text) \
            or re.search(r"\d\.(\d+)$", text)
        if match:
            places = len(match.group(1))
            weight = 2 if "," in text else 1
            votes[places] = votes.get(places, 0) + weight
    if not votes:
        return None
    return max(votes, key=lambda places: (votes[places], places))


def parse_amount(value: Any, decimals: Optional[int]) -> Optional[Decimal]:
    """Exact amount, or None when the text is not a single readable amount.
    With the table's decimal places known, "1.000" is one unit in a JOD
    statement; without them an ambiguous "1.000" stays unreadable."""
    if value is None:
        return None
    text = str(value).translate(_DIGITS).strip().replace(" ", "")
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")") or text.endswith("-") or text.startswith("-")
    text = text.strip("()-+").upper().replace("CR", "").replace("DR", "")
    if not re.fullmatch(r"[\d.,]+", text):
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):       # 1.234,56
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        head, tail = text.rsplit(",", 1)
        text = text.replace(",", "") if len(tail) == 3 and decimals != 3 else head.replace(",", "") + "." + tail
    elif text.count(".") > 1:
        head, tail = text.rsplit(".", 1)
        text = head.replace(".", "") + "." + tail
    elif "." in text and decimals is None and re.fullmatch(r"\d{1,3}\.\d{3}", text):
        return None                                  # 1.000: one, or one thousand?
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if decimals is not None and "." in text and len(text.split(".")[1]) != decimals:
        return None                                  # 12.45 in a 3-decimal table: misread
    return -amount if negative else amount


def fmt(amount: Optional[Decimal], decimals: int) -> Optional[str]:
    if amount is None:
        return None
    return f"{amount:,.{decimals}f}"


# ---------------------------------------------------------------------------
# Arithmetic check
# ---------------------------------------------------------------------------
def reconcile(rows: List[Dict[str, Any]], decimals: int,
              opening_balance: Optional[Decimal] = None) -> List[Dict[str, Any]]:
    """Check every row against the running balance and repair what the
    chain proves. Each row gets:
      status: reconciled | repaired | first | unconfirmed | no_balance
      notes:  what was checked or changed and why
    Rows hold Decimal values under debit / credit / balance (None if empty);
    a repaired value keeps the text as read under <field>_as_read."""
    def movement(row):
        return (row.get("credit") or Decimal(0)) - (row.get("debit") or Decimal(0))

    def fits(previous, row, balance=None):
        balance = row.get("balance") if balance is None else balance
        return previous is not None and balance is not None and previous + movement(row) == balance

    out = [dict(row, status="unconfirmed", notes=list(row.get("notes") or [])) for row in rows]
    previous = opening_balance
    for index, row in enumerate(out):
        nxt = out[index + 1] if index + 1 < len(out) else None
        if row.get("balance") is None:
            row["status"] = "no_balance"
            row["notes"].append("No balance on this row; the chain restarts at the next balance.")
            previous = None
            continue
        if previous is None:
            row["status"] = "first"
            row["notes"].append("First balance on the page: checked against the next row only.")
            previous = row["balance"]
            continue
        if fits(previous, row):
            row["status"] = "reconciled"
            previous = row["balance"]
            continue

        repaired = False
        # Debit and credit swapped.
        swapped = dict(row, debit=row.get("credit"), credit=row.get("debit"))
        if (row.get("debit") or row.get("credit")) and fits(previous, swapped):
            row["debit_as_read"], row["credit_as_read"] = row.get("debit"), row.get("credit")
            row["debit"], row["credit"] = swapped["debit"], swapped["credit"]
            row["notes"].append("Debit and credit were in the wrong columns; swapped (the balance proves it).")
            repaired = True
        # The balance was misread: the computed balance also carries the next row.
        if not repaired and nxt is not None and nxt.get("balance") is not None:
            computed = previous + movement(row)
            if computed >= 0 and fits(computed, nxt) and not fits(row["balance"], nxt):
                row["balance_as_read"] = row["balance"]
                row["balance"] = computed
                row["notes"].append(
                    f"Balance read as {fmt(row['balance_as_read'], decimals)}; the previous balance and this row's "
                    f"amount give {fmt(computed, decimals)}, which the next row confirms.")
                repaired = True
        # The amount was misread: this balance and the next row agree, so the
        # amount is the difference between the two balances.
        if not repaired and nxt is not None and fits(row["balance"], nxt) and (row.get("debit") or row.get("credit")):
            difference = row["balance"] - previous
            field = "credit" if difference > 0 else "debit"
            other = "debit" if field == "credit" else "credit"
            if not row.get(other):
                row[f"{field}_as_read"] = row.get(field)
                row[field] = abs(difference)
                row["notes"].append(
                    f"{field.capitalize()} read as {fmt(row[field + '_as_read'], decimals) or 'empty'}; the balances "
                    f"before and after show {fmt(abs(difference), decimals)}, which the next row confirms.")
                repaired = True
        if repaired:
            row["status"] = "repaired"
        else:
            row["notes"].append(
                f"Does not add up: {fmt(previous, decimals)} − {fmt(row.get('debit'), decimals) or '0'} + "
                f"{fmt(row.get('credit'), decimals) or '0'} ≠ {fmt(row['balance'], decimals)}.")
        previous = row["balance"]

    # A first row is confirmed when the second row reconciles from it.
    for index, row in enumerate(out[:-1]):
        if row["status"] == "first" and out[index + 1]["status"] in ("reconciled", "repaired"):
            row["status"] = "reconciled"
            row["notes"].append("Confirmed by the next row.")
    return out


# ---------------------------------------------------------------------------
# Talking to the vision model
# ---------------------------------------------------------------------------
HEADER_PROMPT = """
The image shows the header row of a table from a financial document. A red
label C1, C2, C3 ... has been placed above every column by our software.
Transcribe the printed header text under each label exactly as printed
(Arabic stays Arabic). Use "" for a column with no header text.
Return JSON only: {"columns": [{"label": "C1", "header": "..."}, ...]}
""".strip()

ROWS_PROMPT = """
The image is part of a table from a bank or account statement. Our software
placed a red label above every column ({labels}); these labels are correct and
decide which column a value belongs to. Blue lines separate the columns.

Read every row from top to bottom. A row starts where a date appears in the
{anchor} column; the description may continue on the following lines and
belongs to the same row. This part contains {count} rows.

For each row give exactly what is printed in each labelled column, as text,
digits and separators exactly as printed (for example "1,482.034"). Use null
when the cell is empty. Never move a value to another column, never compute
or guess a value, and ignore watermarks, logos and stamps printed over the
table. Ignore a row that is cut off at the top or bottom edge of the image.

Return JSON only: {{"rows": [{{{keys}}}, ...]}}
""".strip()

BOX_PROMPT = """
The image shows one box from a financial document. Transcribe it exactly.
If it holds label/value pairs (for example account number, IBAN, currency,
period), return them as pairs; otherwise return the text.
Return JSON only: {"pairs": [{"label": "...", "value": "..."}], "text": "..."}
""".strip()


def dataiku_vision(model_id: Optional[str] = None, temperature: float = 0.0) -> VisionCall:
    """A VisionCall that sends the picture to a Dataiku LLM Mesh vision
    model (the same base64 contract as vlm_adapter)."""
    import base64
    import dataiku
    from .config import MULTIMODAL_LLM_ID

    llm = dataiku.api_client().get_default_project().get_llm(model_id or MULTIMODAL_LLM_ID)

    def call(prompt: str, png: bytes) -> str:
        completion = llm.new_completion()
        try:
            completion.settings["temperature"] = float(temperature)
        except Exception:
            pass
        message = completion.new_multipart_message(role="user")
        message.with_text(prompt)
        message.with_inline_image(base64.b64encode(png).decode("ascii"), "image/png")
        message.add()
        response = completion.execute()
        if getattr(response, "success", True) is False:
            raise RuntimeError(str(getattr(response, "error_message", None) or "The vision request failed."))
        return str(getattr(response, "text", "") or "")

    return call


def _json(text: str) -> Dict[str, Any]:
    text = re.sub(r"<think>.*?</think>", "", str(text or ""), flags=re.S).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        value = json.loads(text)
    except ValueError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        value = json.loads(match.group(0)) if match else {}
    return value if isinstance(value, dict) else {"rows": value} if isinstance(value, list) else {}


def _chunks(anchors: List[Tuple[int, int]], body: Tuple[int, int], size: int = ROWS_PER_CHUNK) -> List[Tuple[int, int, int]]:
    """(y0, y1, row count) for chunks of about `size` rows. Each cut is put
    in the blank space just above a row's first line, at most 60 px above it,
    so a curled page does not push a number into the neighbouring chunk."""
    if not anchors:
        return [(body[0], body[1], 0)]
    cuts = [0]
    while len(anchors) - cuts[-1] > size:
        start = cuts[-1]
        window = range(start + max(2, size - 2), min(len(anchors) - 1, start + size + 2) + 1)
        # Cut at the widest gap between consecutive rows in the window.
        best = max(window, key=lambda i: anchors[i][0] - anchors[i - 1][1])
        cuts.append(best)
    chunks = []
    for number, start in enumerate(cuts):
        end = cuts[number + 1] if number + 1 < len(cuts) else len(anchors)
        top = body[0] if start == 0 else anchors[start][0] - min(60, (anchors[start][0] - anchors[start - 1][1]) // 2 + 8)
        bottom = body[1] if end == len(anchors) else anchors[end][0] - min(60, (anchors[end][0] - anchors[end - 1][1]) // 2 + 8)
        chunks.append((int(top), int(bottom), end - start))
    return chunks


def read_page(image_bytes: bytes, vision: VisionCall) -> Dict[str, Any]:
    """Every table on one photographed/scanned page, read and checked.

    Returns {"page": cleaning info, "tables": [...]}; a statement table has
    kind "transactions", roles, rows (as read and as checked) and the
    decimal places; other regions are "box" with pairs/text."""
    clean, info = it.clean_page(it.decode(image_bytes))
    result: Dict[str, Any] = {"page": info, "tables": []}
    for number, table in enumerate(it.find_tables(clean), start=1):
        entry: Dict[str, Any] = {"table": number, "box": list(table.box), "source": table.source}
        if len(table.columns) < 3 or table.header is None:
            sheet = it.crop(clean, *table.box)
            answer = _json(vision(BOX_PROMPT, it.to_png(sheet)))
            entry.update(kind="box", pairs=answer.get("pairs") or [], text=answer.get("text") or "")
            result["tables"].append(entry)
            continue

        header_labels = [f"C{i + 1}" for i in range(len(table.columns))]
        header_sheet = it.reading_sheet(clean, table, header_labels, table.header[0] - 4, table.header[1] + 4)
        answer = _json(vision(HEADER_PROMPT, it.to_png(header_sheet)))
        by_label = {str(c.get("label")): str(c.get("header") or "") for c in answer.get("columns") or []
                    if isinstance(c, dict)}
        headers = [by_label.get(label, "") for label in header_labels]
        roles = column_roles(headers)
        entry.update(headers=headers, roles=roles)
        if "balance" not in roles or not ({"debit", "credit", "amount"} & set(roles)):
            entry["kind"] = "table"
        else:
            entry["kind"] = "transactions"

        labels = [ROLE_LABELS.get(role, f"C{i + 1}") for i, role in enumerate(roles)]
        anchor_role = "value_date" if "value_date" in roles else "date" if "date" in roles else None
        anchor_column = table.columns[roles.index(anchor_role)] if anchor_role else table.columns[0]
        anchors = it.row_anchors(clean, anchor_column, table.body)
        rows: List[Dict[str, Any]] = []
        for y0, y1, count in _chunks(anchors, table.body):
            sheet = it.reading_sheet(clean, table, labels, y0, y1)
            prompt = ROWS_PROMPT.format(labels=", ".join(labels), anchor=ROLE_LABELS.get(anchor_role or "", labels[0]),
                                        count=count, keys=", ".join(f'"{label}": "..."' for label in labels))
            chunk_rows = [r for r in _json(vision(prompt, it.to_png(sheet))).get("rows") or [] if isinstance(r, dict)]
            if count and len(chunk_rows) != count:
                for row in chunk_rows:
                    row.setdefault("_notes", []).append(
                        f"This part of the table has {count} dates but {len(chunk_rows)} rows were read.")
            for row in chunk_rows:
                row["_crop"] = [table.box[0], y0, table.box[2], y1]
            rows.extend(chunk_rows)
        entry["anchors"] = len(anchors)
        entry["rows_as_read"] = rows
        if entry["kind"] == "transactions":
            entry.update(check_rows(rows, roles))
        result["tables"].append(entry)
    return result


def check_rows(rows: List[Dict[str, Any]], roles: List[str]) -> Dict[str, Any]:
    """Parse the amounts the model read and run the arithmetic check."""
    label = {role: ROLE_LABELS[role] for role in roles if role in ROLE_LABELS}
    amount_fields = [f for f in ("debit", "credit", "balance", "amount") if f in label]
    decimals = table_decimals([row.get(label[f]) for row in rows for f in amount_fields]) or 2
    parsed = []
    for row in rows:
        item = {role: row.get(name) for role, name in label.items() if role not in amount_fields}
        for field in amount_fields:
            item[f"{field}_text"] = row.get(label[field])
            item[field] = parse_amount(row.get(label[field]), decimals)
        if "amount" in item and item.get("amount") is not None and not item.get("debit") and not item.get("credit"):
            (item.__setitem__("debit", -item["amount"]) if item["amount"] < 0 else item.__setitem__("credit", item["amount"]))
        item["notes"] = list(row.get("_notes") or [])
        item["crop"] = row.get("_crop")
        parsed.append(item)
    checked = reconcile(parsed, decimals)
    summary = {status: sum(1 for r in checked if r["status"] == status)
               for status in ("reconciled", "repaired", "first", "unconfirmed", "no_balance")}
    return {"decimals": decimals, "rows": checked, "summary": summary}
