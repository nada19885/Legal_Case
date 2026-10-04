"""
Checks for the multi-view financial reader (financial_reader.py).

Run from the repository root:  python test_financial_reader.py
The vision model is a stand-in that knows the true statement and answers in
the format each view is asked for, with known misreadings injected, so the
consolidation, alignment and arithmetic are tested exactly.
"""

import importlib.util
import json
import pathlib
import sys
import types

import cv2
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
for optional in ("dataiku",):
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

from legal_platform import financial_reader as fr      # noqa: E402
import test_pages as tp                                  # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


# --- comparing raw readings -------------------------------------------------
check("Arabic-Indic and Latin digits compare equal", fr.canon("١٥٬٢٥٠٫٥٠") == fr.canon("15,250.50"))
check("a comma read as a point is still a difference", fr.canon("15,250") != fr.canon("15.250"))
voted = fr.vote({"original": "١٥٬٢٥٠", "enhanced": "15,250", "sharpened": "15,750"},
                ["original", "enhanced", "sharpened"])
check("two of three readings form a majority; the original's raw text is kept",
      voted["agreement"] == "majority" and voted["raw"] == "١٥٬٢٥٠"
      and voted["readings"]["sharpened"] == "15,750")
check("three equal readings agree",
      fr.vote({"a": "87,900", "b": "87,900", "c": "87,900"}, ["a", "b", "c"])["agreement"] == "agreed")


def row(*cells, table=0, kind="transaction"):
    return {"table": table, "type": kind, "cells": list(cells)}


# --- aligning rows like a diff ----------------------------------------------
a = [row("01/03", "Opening", "5,000.00"), row("03/03", "Card", "120.50"), row("05/03", "Fee", "15.00"),
     row("09/03", "Salary", "8,250.00")]
b = [row("01/03", "Opening", "5,000.00"), row("05/03", "Fee", "15.00"), row("09/03", "Salary", "8,250.00")]
c = [row("01/03", "Opening", "5,000.00"), row("03/03", "Card", "120.80"), row("05/03", "Fee", "15.00"),
     row("09/03", "Salary", "8,250.00")]
slots = fr.align({"original": a, "enhanced": b, "sharpened": c})
check("a row skipped by one view leaves a gap, not a shift",
      len(slots) == 4 and set(slots[1]) == {"original", "sharpened"} and all(len(s) == 3 for s in slots[2:]))
check("a row with one misread digit is still matched",
      slots[1]["sharpened"]["cells"][2] == "120.80")

# --- strips ---------------------------------------------------------------------
merged = fr.merge_strips([[row("1", "a", "10.00"), row("2", "b", "20.00")],
                          [row("2", "b", "20.00"), row("3", "c", "30.00")]])
check("the line repeated where two strips overlap is kept once", [r["cells"][0] for r in merged] == ["1", "2", "3"])
tall = np.full((3000, 1000), 255, np.uint8)
for i in range(60):
    cv2.putText(tall, f"{i + 1:02d}/03/2024   Payment {i}   {i * 10 + 5}.00", (40, 40 + i * 48),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, 0, 2)
cuts = fr.strips(tall, 18)
check("a dense page is cut into overlapping strips of about 18 lines",
      len(cuts) >= 3 and all(cuts[i + 1][0] < cuts[i][1] for i in range(len(cuts) - 1)))
check("a short page is one strip", fr.strips(tall[:600], 18) == [(0, 600)])

# --- reading formats ------------------------------------------------------------
tables = [{"columns": ["Date", "Description", "Debit", "Credit", "Balance"]}]
rows_lines, ctx = fr.parse_reading("lines", "T1 | transaction | 01/03 | Shop | 5.00 |  | 95.00\n"
                                            "CONTEXT | Account | 0123", tables)
check("the line format is parsed into cells in column order",
      rows_lines[0]["cells"] == ["01/03", "Shop", "5.00", "", "95.00"] and ctx == {"Account": "0123"})
rows_named, _ = fr.parse_reading("json_named", json.dumps({"rows": [{"table": 1, "type": "transaction", "values": {
    "Balance": "95.00", "Date": "01/03", "Debit": "5.00", "Description": "Shop", "Credit": ""}}]}), tables)
check("the named format is put back in column order",
      rows_named[0]["cells"] == ["01/03", "Shop", "5.00", "", "95.00"])

# --- a whole page with injected misreadings -----------------------------------------
image, _ = tp.photo_statement()
png = cv2.imencode(".png", image)[1].tobytes()
TRUE = [list(r) for r in tp.STATEMENT]          # date, description, debit, credit, balance
ARABIC = str.maketrans("0123456789,.", "٠١٢٣٤٥٦٧٨٩٬٫")


def rows_for(style):
    rows = [list(r) for r in TRUE]
    if style == "json_rows":                     # original: Arabic-Indic digits for every figure
        rows = [[c.translate(ARABIC) if any(ch.isdigit() for ch in c) else c for c in r] for r in rows]
        rows[4][4] = "٩٬٦٤٤٫٥٠"                  # Rent balance 9,614.50 misread as 9,644.50
    if style == "lines":
        rows[3][3] = "8,750.00"                  # Salary credit misread in this view only
        rows[4][4] = "9,814.50"                  # Rent balance: a third different reading
        del rows[6]                              # Utility bill row skipped
    if style == "json_named":
        rows[4][4] = "9,614.50"
    for r in rows:
        if r[1] == "Interest":
            r[3] = "12.75"                       # all three views read 12.25 as 12.75
    return rows


def stand_in(prompt, png_bytes):
    if "describe its layout" in prompt:
        return json.dumps({"financial": True, "kind": "bank statement", "currency": "SAR",
                           "tables": [{"columns": list(tp.STATEMENT_HEADERS)}]})
    if "one line per row" in prompt:
        lines = [" | ".join(["T1", "transaction"] + r) for r in rows_for("lines")]
        return "\n".join(lines + ["CONTEXT | Account | 0123456789"])
    if '"values"' in prompt:
        return json.dumps({"rows": [{"table": 1, "type": "transaction",
                                     "values": dict(zip(tp.STATEMENT_HEADERS, r))} for r in rows_for("json_named")],
                           "context": {"Account": "0123456789"}})
    return json.dumps({"rows": [{"table": 1, "type": "transaction", "cells": r} for r in rows_for("json_rows")],
                       "context": {"account": "٠١٢٣٤٥٦٧٨٩"}})


page = fr.read_financial_page(png, stand_in, debug=True)
table = page["tables"][0]
facts = [r["facts"] for r in table["rows"]]
check("the page is recognised as financial and read in three views",
      page["financial"] and page["views"] == ["original", "enhanced", "sharpened"])
check("every row is found once, including the one a view skipped", len(table["rows"]) == len(TRUE))
check("money columns get their roles", table["roles"] == ["date", "description", "debit", "credit", "balance"])
check("dates read in Arabic-Indic digits by one view still agree",
      facts[0]["date"]["agreement"] == "agreed" and facts[0]["date"]["status"] == "verified")
check("a value all views agree on, whose row adds up, is verified",
      facts[1]["debit"]["status"] == "verified" and facts[1]["debit"]["normalized"] == "120.50")
salary = facts[3]["credit"]
check("a 2-of-3 majority takes the majority reading but still needs checking",
      salary["agreement"] == "majority" and salary["normalized"] == "8250.00" and salary["status"] == "needs_check"
      and salary["readings"]["enhanced"] == "8,750.00")
rent = facts[4]["balance"]
check("three different readings: the one the running balance confirms is chosen, and flagged",
      rent["agreement"] == "disagree" and rent["normalized"] == "9614.50" and "resolved" in rent
      and rent["status"] == "needs_check")
check("the row skipped by one view is flagged, other rows are not shifted",
      facts[6]["debit"]["status"] == "needs_check" and "row not seen in enhanced" in facts[6]["debit"]["reasons"]
      and fr.canon(facts[7]["date"]["raw"]) == "28/03/2024")
interest = facts[7]
check("a misreading shared by all views is caught by the running balance",
      interest["credit"]["agreement"] == "agreed" and interest["credit"]["status"] == "needs_check"
      and any("running balance" in r for r in interest["credit"]["reasons"]))
check("the raw readings of each view are kept for audit",
      set(rent["readings"]) == {"original", "enhanced", "sharpened"} and rent["readings"]["original"] == "٩٬٦٤٤٫٥٠")
check("context is voted across views (digit scripts unified)",
      page["context"].get("account", page["context"].get("Account", {})).get("agreement") == "agreed")
check("the summary counts verified and doubtful facts",
      page["summary"]["needs_check"] >= 5 and page["summary"]["verified"] > 20 and page["summary"]["calls"] == 4)
check("the notebook tables render", len(fr.facts_table(page)) == len(TRUE) and fr.passes_table(page)
      and json.loads(fr.to_json(page))["tables"])

# A failed view leaves a gap and a note, not a crash.
def flaky(prompt, png_bytes):
    if "one line per row" in prompt:
        raise RuntimeError("The vision request failed after 3 tries: timeout")
    return stand_in(prompt, png_bytes)


partial = fr.read_financial_page(png, flaky)
check("a failed view is reported and the page is still consolidated from the others",
      partial["errors"] and len(partial["tables"][0]["rows"]) == len(TRUE))

# A page that is not financial stops after the layout look.
plain = fr.read_financial_page(png, lambda p, b: json.dumps({"financial": False, "kind": "letter", "tables": []}))
check("a non-financial page is not read in three views", not plain["financial"] and "tables" not in plain)

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
