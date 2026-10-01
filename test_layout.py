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
clean, info = it.clean_page(image)
scale = clean.shape[1] / WIDTH
boxes, box_info = lb.find_boxes(clean)
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

lines = lb.group_lines([b for b in boxes if b.kind == "text"], box_info["char_height"])
zones = lb.find_zones(lines, box_info["char_height"], clean.shape[1], lb.vertical_rules(clean))
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

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
