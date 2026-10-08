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

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
