"""
Checks for the calculator (money_check.py).

Run from the repository root:  python test_money_check.py
The structuring LLM is a stand-in returning what a correct copy of each page
gives; everything else (checks, proofs, corrections, writing back) is the
real code, on several kinds of document.
"""

import importlib.util
import pathlib
import sys
import types
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parent
sys.modules.setdefault("dataiku", types.ModuleType("dataiku"))
if "legal_platform" not in sys.modules:
    spec = importlib.util.spec_from_file_location("legal_platform", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules["legal_platform"] = package
    spec.loader.exec_module(package)

from legal_platform import money_check as mc      # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


def stand_in(data):
    return lambda prompt, payload: data


# --- numbers as written ---------------------------------------------------------------
check("Arabic-Indic amounts with signs and currency are read exactly",
      mc.to_number("-٢٠٠.٠٠") == Decimal("-200.00") and mc.to_number("SAR300.00") == Decimal("300.00")
      and mc.to_number("١٣٬١١٤٫٥٠") == Decimal("13114.50") and mc.to_number("(45.00)") == Decimal("-45.00"))
check("a corrected value keeps the style of what was read",
      mc.write_like(Decimal("-300.00"), "-٢٠٠.٠٠") == "-٣٠٠.٠٠"
      and mc.write_like(Decimal("300.00"), "SAR200.00") == "SAR300.00"
      and mc.write_like(Decimal("9614.50"), "9,644.50") == "9,614.50")
check("one or two different digits are a plausible misreading, a different number is not",
      mc.plausible_misreading("-٢٠٠.٠٠", Decimal("-300.00")) and mc.plausible_misreading("900,000.00", Decimal("90000.00"))
      and not mc.plausible_misreading("1,250.00", Decimal("87.40")))

# --- page 26: a statement with one signed amount column, 2 read instead of 3 ------------
PAGE_26 = """التاريخ | البيان / التفاصيل | المبلغ | الرصيد
| رصيد الافتتاح | | ٠.٠٩
٢٤/١٠/١٢ | IPS INCOMING TRANSFERS حوالة سريعة واردة | ٣٠٠.٠٠ | ٣٠٠.٠٩
| HUDA HUSSAIN: المحول/SAR200.00/ 19:42/2024-10-12/ | |
٢٤/١٠/١٨ | IPS INCOMING TRANSFERS حوالة سريعة واردة | ٢٥٠.٠٠ | ٥٥٠.٠٩
| HUDA HUSSAIN: المحول/SAR250.00/ 11:11/2024-10-18/ | |
٢٤/١٠/٢٢ | سحب نقدي-جهاز الصراف الآلي / ATM | -٢٠٠.٠٠ | ٢٥٠.٠٩
| المبلغ SAR200.00 سعر الصرف ١ الرسوم ٠ | |
الرصيد النهائي
٢٥٠.٠٩
-٣٠٠.٠٠
٥٥٠.٠٠
١ مجموع الحركات المدينة ***
٢ مجموع الحركات الدائنة ***"""
DATA_26 = {"kind": "statement", "opening_balance": "٠.٠٩", "closing_balance": "٢٥٠.٠٩",
           "total_debit": "-٣٠٠.٠٠", "total_credit": "٥٥٠.٠٠",
           "rows": [{"date": "٢٤/١٠/١٢", "description_start": "IPS INCOMING TRANSFERS", "amount": "٣٠٠.٠٠",
                     "balance": "٣٠٠.٠٩", "description_amounts": ["SAR200.00"]},
                    {"date": "٢٤/١٠/١٨", "description_start": "IPS INCOMING TRANSFERS", "amount": "٢٥٠.٠٠",
                     "balance": "٥٥٠.٠٩", "description_amounts": ["SAR250.00"]},
                    {"date": "٢٤/١٠/٢٢", "description_start": "سحب نقدي-جهاز الصراف الآلي", "amount": "-٢٠٠.٠٠",
                     "balance": "٢٥٠.٠٩", "description_amounts": ["SAR200.00"]}]}
out = mc.run(PAGE_26, stand_in(DATA_26))
fixes = {(c["row"], c["field"]): c for c in out["corrections"]}
check("the ATM amount read -٢٠٠٫٠٠ is corrected to -٣٠٠٫٠٠ by the running balance",
      fixes.get((2, "amount"), {}).get("corrected") == "-٣٠٠.٠٠" and "| -٣٠٠.٠٠ | ٢٥٠.٠٩" in out["text"])
check("the amounts inside both descriptions are corrected to the row's amount",
      fixes.get((0, "description_amount"), {}).get("corrected") == "SAR300.00"
      and fixes.get((2, "description_amount"), {}).get("corrected") == "SAR300.00"
      and out["text"].count("SAR300.00") == 2 and "SAR200.00" not in out["text"])
check("correct values are left alone",
      "SAR250.00" in out["text"] and "| ٣٠٠.٠٠ | ٣٠٠.٠٩" in out["text"] and "٢٤/١٠/١٢" in out["text"])
check("after the corrections every check passes (balance, totals, opening -> closing)",
      all(c["ok"] for c in out["checks"] if c["check"] != "amount in description") and not out["unresolved"])
check("the restated table is returned with the corrected values, one row per transaction",
      [r.get("amount") for r in out["table"] if r["date"]] == ["٣٠٠.٠٠", "٢٥٠.٠٠", "-٣٠٠.٠٠"]
      and out["table"][0]["description"] == "opening balance"
      and out["table"][3]["amounts in description"] == "SAR300.00")
check("every correction keeps what was read and why",
      all(c["read"] and c["reason"] and c["applied"] for c in out["corrections"]))

# --- a debit / credit statement in Latin digits, a misread balance ------------------------
STATEMENT = """Date Description Debit Credit Balance
01/03/2024 Opening deposit  5,000.00 5,000.00
03/03/2024 Card purchase 120.50  4,879.50
05/03/2024 Transfer fee 15.00  4,864.50
09/03/2024 Salary  8,250.00 13,114.50
12/03/2024 Rent payment 3,500.00  9,644.50
15/03/2024 ATM withdrawal 400.00  9,214.50"""
rows = [("01/03/2024", "Opening deposit", "", "5,000.00", "5,000.00"), ("03/03/2024", "Card purchase", "120.50", "", "4,879.50"),
        ("05/03/2024", "Transfer fee", "15.00", "", "4,864.50"), ("09/03/2024", "Salary", "", "8,250.00", "13,114.50"),
        ("12/03/2024", "Rent payment", "3,500.00", "", "9,644.50"), ("15/03/2024", "ATM withdrawal", "400.00", "", "9,214.50")]
data = {"rows": [{"date": d, "description_start": t, "debit": a, "credit": b, "balance": c} for d, t, a, b, c in rows]}
out = mc.run(STATEMENT, stand_in(data))
check("a misread balance is corrected because the next row confirms the right one",
      [(c["field"], c["read"], c["corrected"]) for c in out["corrections"]] == [("balance", "9,644.50", "9,614.50")]
      and "9,614.50" in out["text"] and "9,644.50" not in out["text"])

# --- a difference that is not a misreading is reported, never changed ------------------------
data = {"opening_balance": "100.00", "rows": [
    {"date": "01/01", "description_start": "A", "amount": "-20.00", "balance": "80.00"},
    {"date": "02/01", "description_start": "B", "amount": "-1,250.00", "balance": "70.00"},
    {"date": "03/01", "description_start": "C", "amount": "-5.00", "balance": "65.00"}]}
out = mc.run("01/01 A -20.00 80.00\n02/01 B -1,250.00 70.00\n03/01 C -5.00 65.00", stand_in(data))
check("an amount far from what the balance needs is reported for review, not changed",
      not out["corrections"] and out["unresolved"] and "-1,250.00" in out["text"])

# --- an invoice ---------------------------------------------------------------------------------
data = {"kind": "invoice", "subtotal": "300.00", "tax": "45.00", "grand_total": "354.00",
        "rows": [{"description_start": "Item A", "quantity": "2", "unit_price": "100.00", "line_total": "200.00"},
                 {"description_start": "Item B", "quantity": "1", "unit_price": "100.00", "line_total": "100.00"}]}
out = mc.run("Item A 2 x 100.00 = 200.00\nItem B 1 x 100.00 = 100.00\nSubtotal 300.00 VAT 45.00 Total 354.00",
             stand_in(data))
check("an invoice whose total does not add up is reported (subtotal + tax)",
      any(u["field"] == "grand_total" and "345.00" in u["reason"] for u in out["unresolved"])
      and any(c["check"] == "quantity x price" and c["ok"] for c in out["checks"]))

# --- pages without money rows ------------------------------------------------------------------
out = mc.run("A letter with no figures.", stand_in({"rows": []}))
check("a page with nothing to calculate is left unchanged", out["text"] == "A letter with no figures." and not out["checks"])

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
