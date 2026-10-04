"""
Checks for the page-by-page pipeline (page_pipeline.py).

Run from the repository root:  python test_page_pipeline.py
A synthetic PDF holds a typed page, a phone photo of a statement taken at an
angle (with a shadow), and a page of two separate screenshots. The models are
stand-ins, so this checks pages, regions, kinds, variants, parts and the
consolidation contract, not the models' reading.
"""

import importlib.util
import json
import pathlib
import sys
import types

import cv2
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
sys.modules.setdefault("dataiku", types.ModuleType("dataiku"))
if "legal_platform" not in sys.modules:
    spec = importlib.util.spec_from_file_location("legal_platform", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules["legal_platform"] = package
    spec.loader.exec_module(package)

import fitz                                              # noqa: E402
from legal_platform import page_pipeline as pp           # noqa: E402
import test_pages as tp                                  # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


def phone_photo():
    """The synthetic statement, photographed at an angle on a desk, with a shadow."""
    page, _ = tp.photo_statement()
    h, w = page.shape[:2]
    canvas = np.full((int(h * 1.3), int(w * 1.3), 3), 70, np.uint8)
    source = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    target = np.float32([[120, 90], [w * 1.2, 160], [w * 1.25, h * 1.22], [60, h * 1.18]])
    matrix = cv2.getPerspectiveTransform(source, target)
    warped = cv2.warpPerspective(page, matrix, (canvas.shape[1], canvas.shape[0]), borderValue=(70, 70, 70))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), matrix, (canvas.shape[1], canvas.shape[0]))
    canvas[mask > 0] = warped[mask > 0]
    shadow = np.tile(np.linspace(0.65, 1.0, canvas.shape[1]), (canvas.shape[0], 1))[..., None]
    return (canvas * shadow).astype(np.uint8)


def png(image):
    return cv2.imencode(".png", image)[1].tobytes()


document = fitz.open()
typed = document.new_page(width=595, height=842)
typed.insert_text((60, 80), "Statement of claim - account freeze", fontsize=14)
for line in range(30):
    typed.insert_text((60, 120 + line * 20), f"Paragraph line {line + 1}: the amount of 250 SAR was frozen on 18-10-2024.",
                      fontsize=10)
photo_page = document.new_page(width=595, height=842)
photo_page.insert_image(fitz.Rect(0, 0, 595, 842), stream=png(phone_photo()))
two = document.new_page(width=595, height=842)
email, _ = tp.email_screenshot(width=1600, size=16)
two.insert_image(fitz.Rect(20, 30, 575, 30 + 555 * email.shape[0] / email.shape[1]), stream=png(email))
two.insert_image(fitz.Rect(20, 450, 575, 800), stream=png(tp.photo_statement()[0]))
data = document.tobytes()

pages = pp.pdf_pages(data, "case.pdf")
check("every page is rendered as an image", len(pages) == 3 and all(p["image"].shape[0] > 2000 for p in pages))
check("the typed page keeps its PDF text layer as context", "Statement of claim" in pages[0]["text_layer"])
check("a page of two separate pictures is cut into two regions", [r[0] for r in pages[2]["regions"]] ==
      ["picture 1", "picture 2"])
check("a page with one picture stays whole", [r[0] for r in pages[1]["regions"]] == ["whole page"])

kinds = [pp.classify(p["regions"][0][1])[0] for p in pages]
check("the typed page is digital", kinds[0] == "digital")
check("the phone photo is recognised as a photo", kinds[1] == "photo")
check("a screenshot is digital", pp.classify(pages[2]["regions"][0][1])[0] == "digital")

photo_variants = pp.variants(pages[1]["regions"][0][1], "photo")
corrected = photo_variants["corrected"]
check("a photo is read once, perspective-corrected", list(photo_variants) == ["corrected"])
check("the corrected photo is straightened (page fills the picture, no desk)",
      float(np.percentile(corrected, 10)) > 120)
check("other pages get the original and a light variant",
      list(pp.variants(pages[0]["regions"][0][1], "digital")) == ["original", "sharpened"])

tall = np.full((9000, 1200, 3), 255, np.uint8)
for i in range(180):
    cv2.putText(tall, f"Row {i}  12/03/2024  1,{i:03d}.50", (30, 40 + i * 48), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
pieces = pp.parts(tall)
check("a very tall dense picture is read in overlapping parts",
      len(pieces) >= 2 and sum(p.shape[0] for p in pieces) >= tall.shape[0])
check("a normal page is read in one piece", len(pp.parts(pages[0]["image"])) == 1)

prompts, payloads = [], []


def vision(prompt, picture):
    prompts.append(prompt)
    return "Statement of claim\namount 250 SAR, date 18-10-2024"


def text_llm(prompt, payload):
    payloads.append(payload)
    return {"text": "Statement of claim\nAmount 250 SAR, date 18-10-2024", "uncertain": [],
            "corrections": [{"from": "amount", "to": "Amount", "why": "capital"}],
            "document_type": "statement of claim", "headings": ["Statement of claim"]}


results = pp.process_pdf(data, "case.pdf", vision, text_llm, debug=True)
check("every page gets a final text", [bool(r["final_text"]) for r in results] == [True, True, True])
check("the PDF text layer goes to the reader as a hint only",
      "hint only" in prompts[0] and "Statement of claim - account freeze" in prompts[0])
check("the reading prompt asks for ? instead of guesses", "?" in pp.READ_PROMPT and "Never guess" in pp.READ_PROMPT)
check("each variant is read and kept", set(results[0]["readings"]) == {"original", "sharpened"}
      and set(results[1]["readings"]) == {"corrected"})
check("pictures on one page are read and consolidated one by one",
      "[picture 1]" in results[2]["final_text"] and "[picture 2]" in results[2]["final_text"])
check("earlier pages' type and headings are passed on as context",
      "statement of claim" in prompts[-1].lower() and "page 1" in prompts[-1])
check("the variant pictures are kept for the notebook", set(results[1]["pictures"]) == {"corrected"})


def broken_llm(prompt, payload):
    raise RuntimeError("timeout")


fallback = pp.process_pdf(data, "case.pdf", vision, broken_llm, pages=[1])[0]
check("a failed consolidation keeps the longest reading and says so",
      fallback["final_text"] and any("consolidation failed" in e for e in fallback["errors"]))

image_only = pp.process_pdf(png(email), "shot.png", vision, text_llm)
check("an image file is one page", len(image_only) == 1 and image_only[0]["regions"][0]["kind"] == "digital")

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
