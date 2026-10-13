"""
Checks for the Financial Memory (financial_memory.py).

Run from the repository root:  python test_financial_memory.py
Pages are built directly in the phase 1/2 result shape, so every rule is
tested on known values; the re-check round uses the synthetic statement
image with the stand-in models of test_pages / test_financial_verify.
"""

import importlib.util
import json
import pathlib
import sys
import types
from decimal import Decimal

import cv2

ROOT = pathlib.Path(__file__).resolve().parent
sys.modules.setdefault("dataiku", types.ModuleType("dataiku"))
if "legal_platform" not in sys.modules:
    spec = importlib.util.spec_from_file_location("legal_platform", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules["legal_platform"] = package
    spec.loader.exec_module(package)

from legal_platform import financial_memory as fm      # noqa: E402
from legal_platform import financial_reader as fr      # noqa: E402
from legal_platform import financial_verify as fv      # noqa: E402
from legal_platform.statement_reader import parse_amount  # noqa: E402
import test_pages as tp                                  # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


ROLES = ["date", "description", "debit", "credit", "balance"]


def make_page(rows, context=None, currency="SAR", decimals=2, kinds=None):
    """A page in the shape read_financial_page / verify_page return."""
    table_rows = []
    for index, values in enumerate(rows):
        facts = {}
        for role, raw in zip(ROLES, values):
            normalized = None
            if role in ("debit", "credit", "balance") and raw:
                value = parse_amount(fr.canon(raw), decimals)
                normalized = str(value) if value is not None else None
            facts[role] = {"raw": raw, "normalized": normalized, "readings": {}, "agreement": "agreed",
                           "arithmetic": "ok", "status": "verified", "reasons": []}
        table_rows.append({"type": (kinds or {}).get(index, "transaction"), "facts": facts, "where": {}})
    return {"financial": True, "kind": "bank statement", "currency": currency, "views": [],
            "tables": [{"headers": ["Date", "Description", "Debit", "Credit", "Balance"], "roles": ROLES,
                        "decimals": decimals, "check": None, "notes": [], "rows": table_rows}],
            "context": {name: {"raw": value, "normalized": None, "readings": {}, "agreement": "agreed",
                               "arithmetic": "n/a", "status": "verified", "reasons": []}
                        for name, value in (context or {}).items()}}


# --- normalising ------------------------------------------------------------------
check("dates are read day-first by default", fm.parse_date("05/03/2024").isoformat() == "2024-03-05")
check("Arabic-Indic dates are read", fm.parse_date("١٢/٠٣/٢٠٢٤").isoformat() == "2024-03-12")
check("a document writing 12/28/2015 is month-first", fm.day_first_for(["12/28/2015", "1/12/2016"]) is False)
check("currencies are recognised in either language",
      fm.currency_code("دينار اردني") == "JOD" and fm.currency_code("SAR") == "SAR")

# --- continuity between pages -------------------------------------------------------
memory = fm.FinancialMemory()
memory.add_page(make_page([("01/03/2024", "Opening deposit", "", "5,000.00", "5,000.00"),
                           ("03/03/2024", "Card purchase", "120.50", "", "4,879.50")],
                          context={"Account number": "0123456789"}), "statement.pdf", 1)
memory.add_page(make_page([("05/03/2024", "Transfer fee", "15.00", "", "4,846.50"),     # 4,864.50 expected
                           ("09/03/2024", "Salary", "", "8,250.00", "13,096.50")]), "statement.pdf", 2)
found = memory.check()
continuity = [a for a in found if a["rule"] == "continuity"]
check("a balance that does not chain from one page to the next is caught",
      len(continuity) == 1 and "expected 4864.50" in continuity[0]["message"]
      and {f["page_key"] for f in continuity[0]["facts"]} == {"statement.pdf#p1", "statement.pdf#p2"})
check("a page without an account number inherits its document's account",
      all(r["account"] == "0123456789" for r in memory.records))

# --- the same transaction in two documents ------------------------------------------
memory = fm.FinancialMemory()
memory.add_page(make_page([("12/03/2024", "Transfer to Riyad Bank", "878.00", "", "9,000.00")]), "statement.pdf", 1)
memory.add_page(make_page([("12/03/2024", "Transfer to Riyad Bank", "873.00", "", "")]), "bank_email.pdf", 1)
duplicates = [a for a in memory.check() if a["rule"] == "duplicate"]
check("the same transfer with different amounts in two documents is caught",
      len(duplicates) == 1 and "878.00" in duplicates[0]["message"] and "873.00" in duplicates[0]["message"])

# --- totals, dates, decimals ---------------------------------------------------------
memory = fm.FinancialMemory()
memory.add_page(make_page([("01/03/2024", "Fee", "10.00", "", "90.00"),
                           ("02/03/2024", "Fee", "20.00", "", "70.00"),
                           ("04/03/2024", "Fee", "5.000", "", "65.00"),                 # 3 decimals in SAR
                           ("21/02/2024", "Fee", "5.00", "", "60.00"),                  # out of order and period
                           ("06/03/2024", "Fee", "5.00", "", "55.00"),
                           ("", "Total", "50.00", "", "")],
                          context={"Period": "01/03/2024 - 31/03/2024"}, kinds={5: "total"}), "statement.pdf", 1)
rules = {a["rule"]: a for a in memory.check()}
check("a total that differs from its rows is caught", "total" in rules and "reads 50.00" in rules["total"]["message"])
check("a date outside the statement period is caught",
      any(a["rule"] == "date" and "outside the period" in a["message"] for a in memory.anomalies))
check("a date out of the statement's order is caught",
      any(a["rule"] == "date" and "order" in a["message"] for a in memory.anomalies))
check("an amount with the wrong decimals for its currency is caught",
      "decimals" in rules and "5.000" in rules["decimals"]["message"])

# --- outliers --------------------------------------------------------------------------
payments = [("0%d/04/2024" % (d + 1), "Installment payment", "", amount, "") for d, amount in
            enumerate(["9,500.00", "10,000.00", "9,800.00", "900,000.00", "9,750.00"])]
memory = fm.FinancialMemory()
memory.add_page(make_page(payments), "payments.pdf", 1)
outliers = [a for a in memory.check() if a["rule"] == "outlier"]
check("a payment 100x the others is flagged as a likely misread (power of ten)",
      len(outliers) == 1 and outliers[0]["severity"] == "high" and "900000.00" in outliers[0]["message"])
memory = fm.FinancialMemory()
memory.add_page(make_page([("0%d/04/2024" % (d + 1), "Installment payment", "", a, "") for d, a in
                           enumerate(["9,500.00", "10,000.00", "9,800.00", "9,750.00"])]), "payments.pdf", 1)
check("ordinary payments raise nothing", memory.check() == [])

# --- re-checking against the source (phase 2 crops) --------------------------------------
image, _ = tp.photo_statement()
png = cv2.imencode(".png", image)[1].tobytes()
first = fr.read_financial_page(png, tp.statement_stand_in)


def crop_truth(prompt, png_bytes):
    if "Read these fields" in prompt:
        return json.dumps({"fields": {}})
    return json.dumps({"rows": [{"table": 1, "type": "transaction", "cells": list(r)} for r in tp.TRUE]})


page_one = fv.verify_page(png, first, crop_truth)
memory = fm.FinancialMemory()
memory.add_page(page_one, "statement.pdf", 1)
# Page 2 of the same statement, read elsewhere: its first balance does not chain.
memory.add_page(make_page([("30/03/2024", "Card purchase", "100.00", "", "8,873.00")]), "statement.pdf", 2)
check("a verified page and a following page are both in the memory",
      len(memory.records) == len(tp.TRUE) + 1 and memory.check())
outcomes = memory.recheck(crop_truth, lambda document, page: png if page == 1 else None)
outcome = next(o for o in outcomes if o["rule"] == "continuity")
check("the anomaly's facts are re-read from the source crop",
      any(f["ref"]["page_key"] == "statement.pdf#p1" and f["decision"] for f in outcome["facts"]))
check("values read correctly that still conflict go to the user, never silently changed",
      outcome["outcome"] == "user_review"
      and fr.canon(memory.pages["statement.pdf#p1"]["tables"][0]["rows"][7]["facts"]["balance"]["raw"]) == "8,937.00")
check("a fact with no source image to check is sent to the user",
      any(f["ref"]["page_key"] == "statement.pdf#p2" and f["status"] == "user_review" for f in outcome["facts"]))

# An outlier that the source confirms stays verified, with a note.
memory = fm.FinancialMemory()
memory.add_page(make_page(payments), "payments.pdf", 1)
memory.check()
memory.pages["payments.pdf#p1"]["tables"][0]["rows"][3]["where"] = {}
outcomes = memory.recheck(lambda p, b: json.dumps({"rows": []}), lambda d, p: None)
check("an anomaly that cannot be checked against the source goes to the user",
      outcomes and outcomes[0]["outcome"] == "user_review")

# The ledger and saving.
ledger = memory.ledger()
check("the ledger lists the case's transactions in date order with their status",
      [r["date"] for r in ledger] == sorted(r["date"] for r in ledger) and ledger[3]["status"] == "user review")
restored = fm.FinancialMemory.from_json(memory.to_json())
check("the memory can be saved and loaded",
      len(restored.records) == len(memory.records) and restored.records[0]["credit"] == Decimal("9500.00"))

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
