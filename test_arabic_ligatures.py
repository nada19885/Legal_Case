"""
Checks for Arabic text whose ligatures a PDF stored out of order
(arabic_text.ligature_damage / repair_ligatures, page_pipeline.route).

Run from the repository root:  python test_arabic_ligatures.py
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

from legal_platform.arabic_text import ligature_damage, repair_ligatures      # noqa: E402
from legal_platform import page_pipeline as pp                                # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


DAMAGED = ("املادة الثامنة: إنهاء العقد: للطرف الأول الحق بموجب إخطار ال تقل مدته عن عشرة (10) أيام وال يستحق أي "
           "اتعاب، مع سداد كامل األتعاب املتفق عليها. تكون جميع املراسالت واإلشعارات على العناوين املثبتة. الحمد هلل. "
           "جوهر بن عبد هللا. تم االتفاق في اململكة العربية.")
REPAIRED = repair_ligatures(DAMAGED)
check("damaged words are counted", ligature_damage(DAMAGED) >= 10)
for wrong, right in (("املادة", "المادة"), ("ال تقل", "لا تقل"), ("وال يستحق", "ولا يستحق"), ("األتعاب", "الأتعاب"),
                     ("املتفق", "المتفق"), ("واإلشعارات", "والإشعارات"), ("الحمد هلل", "الحمد لله"),
                     ("عبد هللا", "عبد الله"), ("االتفاق", "الاتفاق"), ("اململكة", "المملكة")):
    check(f"repaired: {wrong} -> {right}", right in REPAIRED and wrong not in REPAIRED)
check("numbers are never touched", "(10)" in REPAIRED)

CLEAN = ("المادة الأولى: لا يجوز للمحامي خالد مالك الأتعاب، والالتزام والاتفاق، الطرف الآخر، اسم الله، "
         "والمحامي سالم في المملكة، إملاء الشروط، الأمل، لله الحمد")
check("correct Arabic is left exactly as it is", repair_ligatures(CLEAN) == CLEAN and ligature_damage(CLEAN) == 0)
check("English text is left as it is", repair_ligatures("Article 8: termination, all fees.") ==
      "Article 8: termination, all fees.")

page = {"text_layer": DAMAGED, "native_text": DAMAGED, "picture_share": 0.0, "pictures": []}
check("a page with damaged Arabic is read from its image", pp.route(page) == "vlm")
check("a clean Arabic page keeps its own text",
      pp.route({"text_layer": CLEAN + " " + CLEAN, "native_text": CLEAN, "picture_share": 0.0, "pictures": []}) == "native")

# --- The regulator's current name in what the review writes -------------------
from legal_platform.arabic_text import use_central_bank_name, use_central_bank_names    # noqa: E402

check("سلطة النقد becomes البنك المركزي السعودي",
      use_central_bank_name("أمام لجان المنازعات والمخالفات المصرفية والتمويلية سلطة النقد (SAMA) أو أي جهة")
      == "أمام لجان المنازعات والمخالفات المصرفية والتمويلية البنك المركزي السعودي (SAMA) أو أي جهة")
for old_name, new_name in (("مؤسسة النقد العربي السعودي", "البنك المركزي السعودي"),
                           ("سلطة النقد العربي السعودي", "البنك المركزي السعودي"),
                           ("الشكوى لسلطة النقد", "الشكوى للبنك المركزي السعودي"),
                           ("وسلطة النقد السعودية", "والبنك المركزي السعودي"),
                           ("بمؤسسة النقد", "بالبنك المركزي السعودي"),
                           ("the Saudi Arabian Monetary Authority (SAMA)", "the Saudi Central Bank (SAMA)")):
    check(f"{old_name} -> {new_name}", use_central_bank_name(old_name) == new_name)
check("other words with نقد are untouched", use_central_bank_name("نقد الأتعاب نقداً") == "نقد الأتعاب نقداً")
nested = use_central_bank_names({"clause_reviews": [{"legal_finding_ar": "وفق تعليمات مؤسسة النقد", "risk_level": "high",
                                                     "authority_node_ids": ["N1"]}], "count": 3})
check("every text of a saved review is updated, other values kept",
      nested == {"clause_reviews": [{"legal_finding_ar": "وفق تعليمات البنك المركزي السعودي", "risk_level": "high",
                                     "authority_node_ids": ["N1"]}], "count": 3})

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
