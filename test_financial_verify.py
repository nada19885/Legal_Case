"""
Checks for the targeted verification of doubtful facts (financial_verify.py).

Run from the repository root:  python test_financial_verify.py
Phase 1 reads the synthetic statement with the stand-in model of
test_pages (known misreadings); phase 2's crop reader is a stand-in too,
answering per crop variant with known readings.
"""

import importlib.util
import json
import pathlib
import sys
import types

import cv2

ROOT = pathlib.Path(__file__).resolve().parent
sys.modules.setdefault("dataiku", types.ModuleType("dataiku"))
if "legal_platform" not in sys.modules:
    spec = importlib.util.spec_from_file_location("legal_platform", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules["legal_platform"] = package
    spec.loader.exec_module(package)

from legal_platform import financial_reader as fr      # noqa: E402
from legal_platform import financial_verify as fv      # noqa: E402
import test_pages as tp                                  # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


image, _ = tp.photo_statement()
png = cv2.imencode(".png", image)[1].tobytes()
first = fr.read_financial_page(png, tp.statement_stand_in)
flagged = [(i, role) for i, row in enumerate(first["tables"][0]["rows"])
           for role, f in row["facts"].items() if f["raw"] and f["status"] != "verified"]
check("phase 1 leaves doubtful facts to verify", len(flagged) >= 5)
check("phase 1 records where every row was read",
      all(row["where"] for row in first["tables"][0]["rows"]))


def crop_reader(overrides=None, missing=()):
    """Answers a crop with the true rows, as each crop variant reads them."""
    calls = []

    def read(prompt, png_bytes):
        variant = prompt.split("(")[1].split(" copy)")[0]
        calls.append(variant)
        if variant in missing:
            return json.dumps({"rows": []})
        if "Read these fields" in prompt:
            return json.dumps({"fields": {"account": "0123456789"}})
        rows = [list(r) for r in tp.TRUE]
        for (row, column), values in (overrides or {}).items():
            if variant in values:
                rows[row][column] = values[variant]
        return json.dumps({"rows": [{"table": 1, "type": "transaction", "cells": r} for r in rows]})
    return read, calls


# The utility-bill debit is read 289.75 by two crop variants and 289.15 by
# the other two: no agreement.
reader, calls = crop_reader({(6, 2): {"enlarged": "289.15", "contrast": "289.15"}})
second = fv.verify_page(png, first, reader, debug=True)
rows = second["tables"][0]["rows"]
check("the input page is left unchanged", first["tables"][0]["rows"][7]["facts"]["credit"]["raw"] == "12.75")
check("a 2-of-3 value confirmed by every crop reading is verified",
      rows[3]["facts"]["credit"]["status"] == "verified"
      and rows[3]["facts"]["credit"]["verification"]["decision"] == "confirmed from the source crop")
check("a value the balance had chosen is confirmed by the crop", rows[4]["facts"]["balance"]["status"] == "verified")
interest = rows[7]["facts"]["credit"]
check("a misreading shared by all views is corrected from the crop, the first reading kept",
      interest["status"] == "reverified" and fr.canon(interest["raw"]) == "12.25"
      and interest["initial_consensus"] == "12.75" and interest["normalized"] == "12.25")
check("the running balance holds again after the correction", rows[7]["arithmetic"] in ("reconciled", "first"))
utility = rows[6]["facts"]["debit"]
check("crop readings that disagree go to the user, with every reading",
      utility["status"] == "user_review" and utility["verification"]["crop_agreement"] == "2 of 4"
      and utility["verification"]["crop_readings"]["contrast"] == "289.15")
check("only doubtful facts are touched",
      "verification" not in rows[1]["facts"]["debit"] and rows[1]["facts"]["debit"]["status"] == "verified")
check("rows sharing a region are read from one crop (4 variants per crop)",
      second["verification"]["calls"] == 4 * len(second["verification"]["crops"])
      and len(second["verification"]["crops"]) < len({i for i, _ in flagged}))
check("the crop pictures and answers are kept for the notebook",
      set(second["verification"]["crops"][0]["pictures"]) == set(fv.CROP_VARIANTS))
check("the summary counts the final statuses",
      second["summary"]["needs_check"] == 0 and second["summary"]["user_review"] >= 1
      and second["summary"]["reverified"] >= 1)
check("the change list shows before, crop readings and after",
      any(c["column"] == "credit" and c["first reading"] == "12.75" and c["status"] == "reverified"
          for c in fv.changes(second)))
check("the consolidated table shows re-read values as verified",
      "re-read" in fr.facts_table(second)[7]["status"])

# Every crop reads the salary as 8,350.00: consistent, but the balance
# chain proves it wrong, so it goes to the user with the balance's figure.
reader, _ = crop_reader({(3, 3): {v: "8,350.00" for v in fv.CROP_VARIANTS}})
third = fv.verify_page(png, first, reader)
salary = third["tables"][0]["rows"][3]["facts"]["credit"]
check("a consistent crop reading that breaks the running balance goes to the user",
      salary["status"] == "user_review" and salary["verification"].get("balance_suggests") == "8250.00")

# The crops never show the row: a taller crop is tried, then the user decides.
reader, calls = crop_reader(missing=set(fv.CROP_VARIANTS))
fourth = fv.verify_page(png, first, reader)
check("a row not found in its crop is tried once more with a taller crop, then sent to the user",
      {c["attempt"] for c in fourth["verification"]["crops"]} == {1, 2}
      and all(f["status"] == "user_review" for r in fourth["tables"][0]["rows"] for f in r["facts"].values()
              if "verification" in f))

# A doubtful context field is read again from the whole page.
with_context = json.loads(json.dumps(first, default=str))
with_context["context"] = {"account": {"raw": "0123456789", "normalized": "0123456789", "readings": {},
                                       "agreement": "majority", "arithmetic": "n/a", "status": "needs_check",
                                       "reasons": ["views majority"]}}
reader, calls = crop_reader()
fifth = fv.verify_page(png, first | {"context": with_context["context"]}, reader)
check("a doubtful context field is confirmed from the whole page",
      fifth["context"]["account"]["status"] == "verified")

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
