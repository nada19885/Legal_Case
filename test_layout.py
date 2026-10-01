"""
End-to-end check of the position-based extraction (layout_boxes.py +
layout_reader.py) on a synthetic statement whose every value is known.

Run from the repository root:  python test_layout.py
The vision and text models are stand-ins: the vision stand-in answers by
box number from the known content (it never sees pixels), and the text
stand-in returns the structure a correct model would, by box number. So
this tests finding the boxes, numbering them, filling values from box
numbers, parsing and the checks - not the models' reading.
"""

import importlib.util
import json
import pathlib
import sys
import types
from decimal import Decimal

import cv2
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
for optional in ("dataiku", "fitz"):
    try:
        __import__(optional)
    except ImportError:
        sys.modules[optional] = types.ModuleType(optional)
try:
    import legal_platform  # noqa: F401
except ImportError:
    spec = importlib.util.spec_from_file_location("legal_platform", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules["legal_platform"] = package
    spec.loader.exec_module(package)

from legal_platform import image_tables as it          # noqa: E402
from legal_platform import layout_boxes as lb          # noqa: E402
from legal_platform import layout_reader as lr         # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


# --- a synthetic statement: known content, dotted column rules, blur, noise --
ROWS = [("01/03/2024", "Opening deposit", "", "5,000.00", "5,000.00"),
        ("03/03/2024", "Card purchase", "120.50", "", "4,879.50"),
        ("05/03/2024", "Transfer fee", "15.00", "", "4,864.50"),
        ("09/03/2024", "Salary", "", "8,250.00", "13,114.50"),
        ("12/03/2024", "Rent payment", "3,500.00", "", "9,614.50"),
        ("15/03/2024", "ATM withdrawal", "400.00", "", "9,214.50"),
        ("20/03/2024", "Utility bill", "289.75", "", "8,924.75"),
        ("28/03/2024", "Interest", "", "12.25", "8,937.00")]
HEADERS = ("Date", "Description", "Debit", "Credit", "Balance")
COLUMNS = [(80, 300), (310, 760), (770, 980), (990, 1200), (1210, 1440)]   # x ranges at 1500 px
WIDTH, HEIGHT, TOP, STEP = 1500, 1300, 300, 80

page = np.full((HEIGHT, WIDTH), 255, np.uint8)
drawn = []                       # (text, x0, y0, x1, y1) in page pixels


def put(text, column, y, right=False):
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 3)
    c0, c1 = COLUMNS[column]
    x = c1 - w - 8 if right else c0 + 8
    cv2.putText(page, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 30, 3, cv2.LINE_AA)
    drawn.append((text, x, y - h, x + w, y))


for text, x in (("ACCOUNT STATEMENT", 80), ("Account 0123456789", 600), ("Currency SAR", 1100)):
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 3)
    cv2.putText(page, text, (x, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 30, 3, cv2.LINE_AA)
    drawn.append((text, x, 150 - h, x + w, 150))
for index, header in enumerate(HEADERS):
    put(header, index, TOP - 25, right=index >= 2)
for r, row in enumerate(ROWS):
    y = TOP + 40 + r * STEP
    for index, value in enumerate(row):
        if value:
            put(value, index, y, right=index >= 2)
bottom = TOP + 40 + len(ROWS) * STEP
for y in (TOP - 70, TOP, bottom):
    cv2.line(page, (70, y), (1450, y), 40, 2)
for c0, _ in COLUMNS[1:] + [(1450, 0)]:            # dotted vertical rules
    x = c0 - 5
    for y in range(TOP - 70, bottom, 9):
        cv2.line(page, (x, y), (x, y + 4), 40, 2)
cv2.line(page, (70, TOP - 70), (70, bottom), 40, 2)
noisy = cv2.GaussianBlur(page, (3, 3), 0).astype(np.float32) + np.random.default_rng(1).normal(0, 10, page.shape)
image = cv2.cvtColor(np.clip(noisy, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
ok, png = cv2.imencode(".png", image)

# --- boxes ------------------------------------------------------------------
prepared = it.prepare_page(image)
clean = prepared.find
scale = clean.shape[1] / WIDTH
boxes, zones, box_info = lb.layout(clean, prepared.digital)
truth = {}
for box in boxes:
    for text, x0, y0, x1, y1 in drawn:
        if x0 * scale - 6 <= box.cx <= x1 * scale + 6 and y0 * scale - 6 <= box.cy <= y1 * scale + 6:
            truth.setdefault(box.id, []).append((x0, text))
values_found = {t for parts in truth.values() for _, t in parts}
expected_values = {t for t, *_ in drawn}
check("every printed value lies in a box", expected_values <= values_found)
split = [b for b, parts in truth.items() if len({t for _, t in parts}) > 1 and
         any(any(ch.isdigit() for ch in t) for _, t in parts)]
check("no box mixes two numbers or a number and other text (cells stay apart)", not split)

tables = [z for z in zones if z.kind == "table"]
check("one table zone found", len(tables) == 1)
check("table zone holds the header and every row", tables and len(tables[0].lines) >= len(ROWS) + 1)
check("column hints match the five printed columns", tables and len(tables[0].columns) == 5)

# --- reading, structure, checks -----------------------------------------------
def box_text(box_id):
    parts = sorted(truth.get(box_id, []))
    return " ".join(t for _, t in parts)

MISREAD = "9,644.50"                      # the 9,614.50 balance read with a 4 for the 1
sheets = []


def vision(prompt, png_bytes):
    sheets.append(prompt)
    ids = [int(x) for x in prompt.split("The numbers on this sheet are:")[1].split(".")[0].split(",")]
    out = {}
    for i in ids:
        text = box_text(i)
        out[str(i)] = MISREAD if text == "9,614.50" else text
    return json.dumps({"boxes": out})


def text_llm(prompt, payload):
    """What a correct model returns: structure by box number only."""
    by_text = {}
    for row in payload["boxes"]:
        by_text.setdefault(row["text"], []).append(row["box"])
    taken = set()

    def ids(text):
        for i in by_text.get(text, []):
            if i not in taken:
                taken.add(i)
                return [i]
        return []
    roles = ("date", "description", "debit", "credit", "balance")
    columns = [{"header_boxes": ids(h), "role": r} for h, r in zip(HEADERS, roles)]
    rows = []
    for row in ROWS:
        cells = {}
        for role, value in zip(roles, row):
            if value:
                cells[role] = ids(MISREAD if value == "9,614.50" else value)
        rows.append(cells)
    account = [r["box"] for r in payload["boxes"] if "ACCOUNT" in r["text"] or "0123456789" in r["text"]]
    return {"context": {"statement heading": account}, "tables": [{"kind": "transactions", "columns": columns,
                                                                    "rows": rows}], "text_boxes": []}


result = lr.read_image(png.tobytes(), vision, text_llm, debug=True)
check("page recognised as a table page", result["page_kind"] == "table")
check("boxes read in numbered sheets", len(sheets) >= 1 and all("numbers on this sheet" in p for p in sheets))
table = result["tables"][0] if result.get("tables") else {}
check("header words mapped to roles by our dictionary",
      [c["role"] for c in table.get("columns", [])] == ["date", "description", "debit", "credit", "balance"])
check("all rows built from box numbers", len(table.get("rows", [])) == len(ROWS))
check("two decimals detected", table.get("decimals") == 2)
rent = table["rows"][4] if table else {}
check("misread balance repaired by the running-balance check",
      rent.get("status") == "repaired" and str(rent.get("balance")) == "9614.50")
check("every other row reconciles",
      table and table["check"]["reconciled"] + table["check"].get("first", 0) == len(ROWS) - 1)
check("values keep their box numbers (traceable to a position)",
      all(c["boxes"] for r in table.get("rows", []) for c in r["cells"].values()))
check("statement heading kept as context", "statement heading" in result.get("context", {}))
check("report and score render", "TABLE 1" in lr.report(result) and lr.score(result)["rows"] == len(ROWS))
check("debug pictures kept", {"cleaned page", "boxes and zones"} <= {i["name"] for i in result["images"]})

# A model answer that names a box which does not exist is ignored, never invented.
bogus = lr.build_tables({"tables": [{"columns": [], "rows": [{"balance": [99999]}]}]}, {}, boxes)[0]
check("unknown box numbers produce no value", bogus[0]["rows"][0]["cells"]["balance"]["text"] == "")

# Typed PDF text keeps distant words apart.
check("typed text keeps column gaps", lr._typed_text([(0, 0, 40, 10, "Date"), (300, 0, 360, 10, "Amount")])
      == "Date | Amount")

# --- general pages: screenshots, unknown headers, weak model answers ----------
import test_pages as tp                                # noqa: E402


def truth_reader(image_bgr, truth):
    """A stand-in vision model that knows what is printed where: it answers
    each numbered box with the text drawn inside it (in reading order)."""
    prepared_page = it.prepare_page(image_bgr)
    factor = prepared_page.read.shape[1] / image_bgr.shape[1]
    page_boxes, _, _ = lb.layout(prepared_page.find, prepared_page.digital)
    known = {}
    for box in page_boxes:
        parts = [t for t in truth if t["box"][0] * factor - 4 <= box.cx <= t["box"][2] * factor + 4
                 and t["box"][1] * factor - 4 <= box.cy <= t["box"][3] * factor + 4]
        known[box.id] = " ".join(t["text"] for t in sorted(parts, key=lambda t: (t["box"][1], t["box"][0])))
    calls = []

    def read(prompt, png_bytes):
        calls.append(prompt)
        ids = [int(x) for x in prompt.split("The numbers on this sheet are:")[1].split(".")[0].split(",")]
        return json.dumps({"boxes": {str(i): known.get(i, "") for i in ids}})
    return read, calls, page_boxes, prepared_page


email, email_truth = tp.email_screenshot(width=2400, size=13)
prepared_email = it.prepare_page(email)
check("a screenshot is recognised as one and only scaled (no smoothing)",
      prepared_email.digital and prepared_email.find is prepared_email.read)
check("small screenshot text is enlarged, never shrunk", prepared_email.info["scale"] > 1)
email_boxes, email_zones, email_info = lb.layout(prepared_email.find, prepared_email.digital)
factor = prepared_email.read.shape[1] / email.shape[1]
# A line longer than MAX_BOX_WIDTH letters is read in pieces cut at word
# gaps; anything else in more than one piece is a broken word or cell.
broken = []
for t in email_truth:
    pieces = sum(1 for b in email_boxes if t["box"][0] * factor - 4 <= b.cx <= t["box"][2] * factor + 4
                 and t["box"][1] * factor - 4 <= b.cy <= t["box"][3] * factor + 4)
    allowed = 1 + int((t["box"][2] - t["box"][0]) * factor / (lb.MAX_BOX_WIDTH * email_info["char_height"]))
    if "|" not in t["text"] and pieces > allowed:
        broken.append(t["text"])
check(f"no word, number or cell of the screenshot is cut into pieces (cut: {broken})", not broken)
email_tables = [z for z in email_zones if z.kind == "table"]
check("the transfer table is found as one table", len(email_tables) == 1)

# The text model answers nothing usable: the table is built from the positions.
reader, reads, _, _ = truth_reader(email, email_truth)
llm_calls = []


def useless_llm(prompt, payload):
    llm_calls.append(payload)
    return {"oops": "no structure"}


page = lr.read_image(cv2.imencode(".png", email)[1].tobytes(), reader, useless_llm)
grid = page["tables"][0] if page.get("tables") else {"rows": [], "columns": []}
check("an unusable model answer is asked once more, then replaced by the position grid",
      len(llm_calls) == 2 and any("positions alone" in n for n in page["structure_notes"]))
check("the grid keeps every transfer row", len(grid["rows"]) == len(tp.TRANSFERS))
check("the grid gives the amount column its role from the header",
      [r.get("amount") for r in grid["rows"]] == [Decimal(t[2]) for t in tp.TRANSFERS])
check("the grid keeps two-line headers whole, one per data column",
      any(c["header"] == "Beneficiary's IBAN" for c in grid["columns"]) and len(grid["columns"]) == 6
      and any(c["header"] == "Original Amount" and c["role"] == "amount" for c in grid["columns"]))

# Headers in words no dictionary knows, and a model that mixes up the money
# columns: the running balance decides which column is which.
fake = [lb.Box(i, 0, i * 30, 50, i * 30 + 20, line=i) for i in range(1, 40)]
texts_unknown = {1: "Out", 2: "In", 3: "Running"}
structure_unknown = {"tables": [{"columns": [{"header_boxes": [1], "role": "balance"},
                                             {"header_boxes": [2], "role": "debit"},
                                             {"header_boxes": [3], "role": "credit"}], "rows": []}]}
next_id = 4
for debit, credit, balance in (("", "", "1,000.00"), ("200.00", "", "800.00"), ("", "50.00", "850.00"),
                               ("100.00", "", "750.00"), ("", "300.00", "1,050.00")):
    row = {}
    for role, value in (("balance", debit), ("debit", credit), ("credit", balance)):
        if value:
            texts_unknown[next_id] = value
            row[role] = [next_id]
            next_id += 1
    structure_unknown["tables"][0]["rows"].append(row)
mixed, _ = lr.build_tables(structure_unknown, texts_unknown, fake)
check("money columns are decided by the running balance, not the header words",
      mixed[0]["roles"] == ["debit", "credit", "balance"] and mixed[0]["check"]["unconfirmed"] == 0
      and any("running balance" in n for n in mixed[0]["notes"]))

# One unsigned amount column: debit or credit follows the balance.
single = {"tables": [{"columns": [], "rows": [{"amount": [1], "balance": [2]}, {"amount": [3], "balance": [4]},
                                             {"amount": [5], "balance": [6]}]}]}
signed, _ = lr.build_tables(single, {1: "500.00", 2: "500.00", 3: "120.00", 4: "380.00", 5: "20.00",
                                     6: "400.00"}, fake)
check("an unsigned amount becomes a debit or a credit from the balance",
      signed[0]["rows"][1].get("debit") == Decimal("120.00") and signed[0]["rows"][2].get("credit") == Decimal("20.00")
      and signed[0]["check"]["unconfirmed"] == 0)

# A box named twice is used once.
cleaned, problems = lr.clean_structure({"tables": [{"columns": [], "rows": [{"date": [1]}, {"date": [1, 2]}]}],
                                        "context": {"x": [2]}}, fake)
check("a box named twice by the model is used once",
      cleaned["tables"][0]["rows"][1] == {"date": [2]} and "x" not in cleaned["context"] and problems)

# A model that leaves rows out is asked again with the boxes it missed.
asked = []


def forgetful_llm(prompt, payload):
    asked.append(payload)
    full = text_llm(prompt, payload)
    if "previous_answer_problem" not in payload:
        full["tables"][0]["rows"] = full["tables"][0]["rows"][:2]
    return full


again = lr.read_image(png.tobytes(), vision, forgetful_llm)
check("boxes left out are sent back to the model, and the fuller answer is kept",
      len(asked) == 2 and "were not placed" in asked[1]["previous_answer_problem"]
      and len(again["tables"][0]["rows"]) == len(ROWS))

# A money cell read wrongly is read again, enlarged, and kept when it adds up.
def misreading(prompt, png_bytes):
    answer = json.loads(vision(prompt, png_bytes))
    if "first reading did not add up" not in prompt:
        answer["boxes"] = {k: ("3,5OO.0O" if v == "3,500.00" else v) for k, v in answer["boxes"].items()}
    return json.dumps(answer)


def placing_llm(prompt, payload):
    """The stand-in model places a misread cell by its position, as a real
    model does (it recognises the cell, not the exact characters)."""
    boxes_seen = [dict(b, text="3,500.00" if b["text"] == "3,5OO.0O" else b["text"]) for b in payload["boxes"]]
    return text_llm(prompt, dict(payload, boxes=boxes_seen))


fixed = lr.read_image(png.tobytes(), misreading, placing_llm)
rent_row = fixed["tables"][0]["rows"][4]
check("an unreadable amount is read again and the new reading kept",
      any(r["first"] == "3,5OO.0O" and r["second"] == "3,500.00" and r["kept"] for r in fixed["re_read"])
      and rent_row.get("debit") == Decimal("3500.00"))

# White text on a dark header band is turned dark on light and found.
band = np.full((700, 1400), 255, np.uint8)
cv2.rectangle(band, (60, 80), (1340, 150), 40, -1)
for text, x in (("Date", 90), ("Details", 400), ("Amount", 1000)):
    cv2.putText(band, text, (x, 128), cv2.FONT_HERSHEY_SIMPLEX, 1.1, 255, 2, cv2.LINE_AA)
for r in range(5):
    for text, x in ((f"0{r + 1}/05/2024", 90), (f"Payment {r + 1}", 400), (f"{r + 1},250.00", 1000)):
        cv2.putText(band, text, (x, 220 + 80 * r), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 30, 2, cv2.LINE_AA)
prepared_band = it.prepare_page(cv2.cvtColor(band, cv2.COLOR_GRAY2BGR))
band_boxes, band_zones, _ = lb.layout(prepared_band.find, prepared_band.digital)
header_y = 115 * prepared_band.info["scale"]
check("a dark header band is inverted and its words are found",
      prepared_band.info.get("inverted") and
      sum(1 for b in band_boxes if abs(b.cy - header_y) < 30 * prepared_band.info["scale"]) == 3)

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
