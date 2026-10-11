"""
Checks for the contract's pages without their text (agreement_pages.blank_page).

Run from the repository root:  python test_agreement_pages.py
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

import cv2                                                    # noqa: E402
import fitz                                                   # noqa: E402
import numpy as np                                            # noqa: E402
from legal_platform.agreement_pages import blank_page         # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


document = fitz.open()
page = document.new_page(width=595, height=842)
logo = np.full((70, 220, 3), (40, 110, 60), np.uint8)
page.insert_image(fitz.Rect(380, 25, 560, 82), stream=cv2.imencode(".png", logo)[1].tobytes())
page.draw_line((40, 95), (555, 95), color=(0.55, 0.45, 0.15), width=2)
for line in range(15):
    page.insert_text((60, 140 + line * 26), "The parties agree to the terms of this contract.", fontsize=11)
scan = document.new_page(width=595, height=842)
scan.insert_image(scan.rect, stream=cv2.imencode(".png", np.full((842, 595, 3), 250, np.uint8))[1].tobytes())
data = document.tobytes()

png, layout = blank_page(data, 1, dpi=72)
image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
body = image[130:520, 50:350]
check("a digital page can be cleared", layout["available"] and png[:4] == b"\x89PNG")
check("its text is removed", (body < 200).sum() == 0)
check("its logo is kept", abs(int(image[50, 470, 1]) - 110) < 25 and int(image[50, 470, 0]) < 80)
check("its lines are kept", (image[93:98, 100:500] < 200).any())
check("the text area and text size are measured",
      0.05 < layout["text_box"][0] < 0.15 and abs(layout["text_box"][2] - (1 - layout["text_box"][0])) < 0.001
      and 0.14 < layout["text_box"][1] < 0.17 and 0.015 < layout["font"] < 0.022)
none, scanned = blank_page(data, 2, dpi=72)
check("a scanned page (no text in the PDF) is not cleared", none is None and scanned["available"] is False)

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
