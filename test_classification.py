"""
Checks for the financial page classification (financial_classification.py).

Run from the repository root:  python test_classification.py
The model is a stand-in that (wrongly) calls every page financial: the
code safeguard must still keep emails and claim forms out of accounting.
"""

import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent
sys.modules.setdefault("dataiku", types.ModuleType("dataiku"))
if "legal_platform" not in sys.modules:
    spec = importlib.util.spec_from_file_location("legal_platform", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules["legal_platform"] = package
    spec.loader.exec_module(package)

from legal_platform import financial_classification as fc   # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


EMAIL = """From: "FraudAlerts@alrajhibank.com.sa" <FraudAlerts@alrajhibank.com.sa>
Date: Friday, 29 August 2025 at 5:37:05 AM
To: "Fraudalerts" <Fraudalerts@bsf.sa>
Subject: RE: 53282673 احتيال
إشارة إلى البلاغ ... تحويل مبلغ بقيمة (250.00) ريال لحساب عميل البنك السعودي الفرنسي رقم الآيبان (SA82550000000F7634500180)"""
CLAIM = """صحيفة دعوى (تجميد حساب أو مبلغ مالي)
املدعي هدى حسين عبدالكريم العبدالكريم رقم الهوية 1027476025
املبلغ محل التجميد 250 ريال سعودي  كامل رصيد الحساب 0.18  تاريخ بداية التجميد 18 -10 -2024"""
STATEMENT = """| التاريخ | البيان | المبلغ | الرصيد |
|---|---|---|---|
| ٢٤/١٠/١٢ | IPS INCOMING TRANSFERS | ٣٠٠.٠٠ | ٣٠٠.٠٩ |
| ٢٤/١٠/١٨ | IPS INCOMING TRANSFERS | ٢٥٠.٠٠ | ٥٥٠.٠٩ |
| ٢٤/١٠/٢٢ | سحب نقدي | -٣٠٠.٠٠ | ٢٥٠.٠٩ |"""
EMAILED_STATEMENT = "From: bank@x.com\nSubject: your statement\n" + STATEMENT

fc.complete_json = lambda **kwargs: {"page_type": "financial", "financial_document_type": "bank_statement",
                                     "confidence": 0.9, "reasoning": "has amounts"}
email = fc.classify_accounting_page("C", "P8", EMAIL)
claim = fc.classify_accounting_page("C", "P1", CLAIM)
statement = fc.classify_accounting_page("C", "P26", STATEMENT)
check("an email quoting an amount is never financial, whatever the model says",
      email["page_type"] == "other" and "email" in email["reasoning"])
check("a claim form quoting amounts is a claim page, not financial", claim["page_type"] == "claim")
check("a statement with dated amounts is financial", statement["page_type"] == "financial"
      and statement["financial_document_type"] == "bank_statement")
check("a statement sent inside an email still counts (it is a list of dated amounts)",
      fc.classify_accounting_page("C", "P9", EMAILED_STATEMENT)["page_type"] == "financial")
fc.complete_json = lambda **kwargs: {"page_type": "mixed", "confidence": 0.7}
check("the old 'mixed' answer no longer sends a page to accounting",
      fc.classify_accounting_page("C", "P2", "Some page with 250.00")["page_type"] == "claim")
check("the prompt lists what is never financial",
      "emails and email chains" in fc.CLASSIFY_ACCOUNTING_PAGE_PROMPT and "صحيفة دعوى" in fc.CLASSIFY_ACCOUNTING_PAGE_PROMPT)
check("results carry the rules version (older results are classified again)",
      email["classifier_version"] == fc.CLASSIFIER_VERSION)

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
