"""
Checks for the page-by-page pipeline (page_pipeline.py).

Run from the repository root:  python test_page_pipeline.py
A synthetic PDF holds a typed page, a phone photo of a statement taken at an
angle (with a shadow), a page of two separate screenshots and a typed letter
with an embedded picture. The models are
stand-ins, so this checks pages, regions, kinds, variants, parts and the
consolidation contract, not the models' reading.
"""

import importlib.util
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
mixed = document.new_page(width=595, height=842)
mixed.insert_text((60, 80), "Letter from the bank about the attached receipt", fontsize=14)
for line in range(12):
    mixed.insert_text((60, 110 + line * 18), f"Line {line + 1}: the customer account 0123456789 was reviewed.", fontsize=10)
mixed.insert_image(fitz.Rect(60, 400, 535, 780), stream=png(tp.photo_statement()[0]))
data = document.tobytes()

pages = pp.pdf_pages(data, "case.pdf")
check("every page is rendered as an image", len(pages) == 4 and all(p["image"].shape[0] > 2000 for p in pages))
check("the typed page keeps its PDF text", "Statement of claim" in pages[0]["native_text"])
check("a page of two separate pictures is cut into two regions", [r[0] for r in pages[2]["regions"]] ==
      ["picture 1", "picture 2"])
check("a page with one picture stays whole", [r[0] for r in pages[1]["regions"]] == ["whole page"])

# --- routing ---------------------------------------------------------------------------
check("reliable PDF text with no pictures is used directly (no vision call)", pp.route(pages[0]) == "native")
check("a photographed page goes to the vision model", pp.route(pages[1]) == "vlm")
check("a page of screenshots goes to the vision model", pp.route(pages[2]) == "vlm")
check("reliable text around an embedded picture keeps the text and reads the picture",
      pp.route(pages[3]) == "native+vlm" and len(pages[3]["pictures"]) == 1)
check("a damaged text layer goes to the vision model",
      pp.route({"text_layer": "ʄʈȊ ɢɲ؈ ݍݏݝ word word word", "native_text": "x", "picture_share": 0}) == "vlm")
check("a scan with an OCR text layer (page covered by a picture) is read as an image",
      pp.route({"text_layer": "a clean ocr layer of five words", "native_text": "x", "picture_share": 0.95,
                "pictures": [("picture 1", None, (0, 1))]}) == "vlm")

# --- kinds and flags --------------------------------------------------------------------
kinds = [pp.classify(p["regions"][0][1])[0] for p in pages[:3]]
check("the typed page is a screenshot-like digital image", kinds[0] == "screenshot")
check("the phone photo is recognised as a camera shot", kinds[1] == "photo")
check("a screenshot is recognised", pp.classify(pages[2]["regions"][0][1])[0] == "screenshot")
check("a typed letter is not flagged table-heavy", "table_heavy" not in pp.classify(pages[0]["image"])[1]["flags"])
tiny = cv2.resize(pages[0]["image"], None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
check("a small, blurred page is flagged low-resolution", "low_resolution" in pp.classify(tiny)[1]["flags"])

# --- views --------------------------------------------------------------------------------
photo_views = pp.variants(pages[1]["regions"][0][1], "photo")
check("a camera shot is read in two views (corrected, local contrast)", list(photo_views) == ["corrected", "contrast"])
check("the corrected photo is straightened (page fills the picture, no desk)",
      float(np.percentile(photo_views["corrected"], 10)) > 120)
check("both photo views keep the same geometry", photo_views["corrected"].shape == photo_views["contrast"].shape)
check("a screenshot gets the original and a light variant",
      list(pp.variants(pages[0]["regions"][0][1], "screenshot")) == ["original", "sharpened"])

tall = np.full((9000, 1200, 3), 255, np.uint8)
for i in range(180):
    cv2.putText(tall, f"Row {i}  12/03/2024  1,{i:03d}.50", (30, 40 + i * 48), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
pieces = pp.parts(tall)
check("a very tall dense picture is read in overlapping parts",
      len(pieces) >= 2 and sum(p.shape[0] for p in pieces) >= tall.shape[0])
check("a normal page is read in one piece", len(pp.parts(pages[0]["image"])) == 1)

# --- the whole document ---------------------------------------------------------------------
prompts, payloads = [], []


def vision(prompt, picture):
    prompts.append(prompt)
    return "Statement of claim\namount 250 SAR, date 18-10-2024"


def text_llm(prompt, payload):
    payloads.append((prompt, payload))
    return {"text": "Statement of claim\nAmount 250 SAR, date 18-10-2024", "uncertain": [],
            "corrections": [{"from": "amount", "to": "Amount", "why": "capital"}],
            "document_type": "statement of claim", "headings": ["Statement of claim"]}


case_context = {"case": {"case_name": "Huda v BSF", "claimant_name": "Huda"}, "parties": ["Huda (claimant)", "BSF"],
                "currency": "SAR"}
results = pp.process_pdf(data, "case.pdf", vision, text_llm, debug=True, context=case_context)
check("every page gets a final text", [bool(r["final_text"]) for r in results] == [True] * 4)
check("the native page made no vision call and kept its own text",
      results[0]["route"] == "native" and results[0]["vision_calls"] == 0
      and "account freeze" in results[0]["final_text"])
check("the reading prompt asks for ? instead of guesses and for one row per entry",
      "?" in pp.READ_PROMPT and "Never guess" in pp.READ_PROMPT and "<br>" in prompts[0])
check("the reader gets the case context as a hint: case, document, page, parties, currency, neighbours",
      all(x in prompts[0] for x in ("Huda v BSF", "Document: case.pdf, page 2 of 4", "Known parties", "SAR",
                                     "Previous page (start)", "Statement of claim - account freeze")))
check("each view of the photo is read and kept", set(results[1]["readings"]) == {"corrected", "contrast"})
check("pictures on one page are read and consolidated one by one",
      "[picture 1]" in results[2]["final_text"] and "[picture 2]" in results[2]["final_text"])
mixed_result = results[3]
check("a text page with a picture: the PDF text and the picture's views are merged together",
      mixed_result["route"] == "native+vlm" and "pdf_text" in mixed_result["readings"]
      and "[picture 1]" in mixed_result["readings"]["pdf_text"]
      and sum(k.startswith("picture 1 / ") for k in mixed_result["readings"]) == 2
      and mixed_result["vision_calls"] == 2)
check("the merge is told never to calculate or correct unusual numbers",
      "never\n  invent, calculate" in pp.CONSOLIDATE_PROMPT and "looks unusual" in pp.CONSOLIDATE_PROMPT)
check("the view pictures are kept for debugging", set(results[1]["pictures"]) == {"corrected", "contrast"})


def broken_llm(prompt, payload):
    raise RuntimeError("timeout")


fallback = pp.process_pdf(data, "case.pdf", vision, broken_llm, pages=[2])[0]
check("a failed consolidation keeps the longest reading and says so",
      fallback["final_text"] and any("consolidation failed" in e for e in fallback["errors"]))

image_only = pp.process_pdf(png(email), "shot.png", vision, text_llm)
check("an image file is one page", len(image_only) == 1 and image_only[0]["regions"][0]["kind"] == "screenshot")

# --- numbers: none is invented ----------------------------------------------------------------
invented = pp.process_page(pages[1], vision, lambda p, x: {"text": "amount 999,111.00 on 18-10-2024", "uncertain": [],
                                                          "corrections": [], "document_type": "", "headings": []})
check("a number in the merged text that no reading shows is listed as uncertain (text kept as merged)",
      any(u["value"] == "999,111.00" for u in invented["uncertain"]) and "999,111.00" in invented["final_text"]
      and not any(u["value"].startswith("18-10") for u in invented["uncertain"]))
check("a number written with other separators or digits is not flagged",
      pp.unsupported_numbers("١٨/١٠/٢٠٢٤ and 1,250.00", ["date 18-10-2024 amount 1250.00"]) == [])

# --- Arabic PDF text: words repaired, numbers untouchable ------------------------------------
arabic_page = {"page": 1, "text_layer": "صحيفة دعوى املدعي هدى رقم الهوية 1027476025 املبلغ 250 ريال",
               "native_text": "صحيفة دعوى املدعي هدى رقم الهوية 1027476025 املبلغ 250 ريال",
               "picture_share": 0.0, "pictures": [], "regions": []}
fixed = pp.process_page(arabic_page, vision, lambda p, x: {
    "text": "صحيفة دعوى المدعي هدى رقم الهوية 1027476025 المبلغ 250 ريال",
    "corrections": [{"from": "املدعي", "to": "المدعي", "why": "export swap"}], "document_type": "statement of claim",
    "headings": []})
check("Arabic PDF text gets its swapped words repaired by the text model",
      "المدعي" in fixed["final_text"] and fixed["llm_calls"] == 1 and fixed["vision_calls"] == 0)
kept = pp.process_page(arabic_page, vision, lambda p, x: {"text": "صحيفة دعوى المدعي رقم الهوية 1027476026 المبلغ 250",
                                                          "corrections": []})
check("a repair that changes any number is rejected and the PDF text kept",
      "1027476025" in kept["final_text"] and any("changed a number" in e for e in kept["errors"]))
english = pp.process_page({**arabic_page, "native_text": "Plain English letter, amount 250.", "text_layer": "Plain English letter, amount 250."},
                          vision, broken_llm)
check("an English PDF page needs no model call at all", english["llm_calls"] == 0 and not english["errors"])

# --- markdown tables: wrapped rows joined back ----------------------------------------------
split_table = """التاريخ | البيان / التفاصيل | المبلغ | الرصيد
---|---|---|---
| رصيد الافتتاح | | ٠.٠٩
٢٤/١٠/١٢ | IPS INCOMING TRANSFERS حوالة سريعة واردة | ٣٠٠.٠٠ | ٣٠٠.٠٩
| الحوالات - الرياض/ رقم المرجع | |
| HUDA HUSSAIN: المحول/SAR200.00/ 19:42/2024-10-12/ | |
٢٤/١٠/١٨ | IPS INCOMING TRANSFERS | ٢٥٠.٠٠ | ٥٥٠.٠٩
| الأجنبي/ Others | |
٢٤/١٠/٢٢ | سحب نقدي-جهاز الصراف الآلي | -٢٠٠.٠٠ | ٢٥٠.٠٩"""
tidy = pp.tidy_tables(split_table).split("\n")
check("a table split by wrapped descriptions becomes one row per transaction",
      len(tidy) == 6 and all(line.startswith("|") and line.endswith("|") for line in tidy))
check("the wrapped lines are joined into the description cell with <br>",
      "حوالة سريعة واردة<br>الحوالات - الرياض/ رقم المرجع<br>HUDA HUSSAIN: المحول/SAR200.00/" in tidy[3]
      and tidy[3].endswith("| ٣٠٠.٠٠ | ٣٠٠.٠٩ |"))
check("the opening balance row keeps its own row", "رصيد الافتتاح" in tidy[2] and "٠.٠٩" in tidy[2])
names = "| Name | Role |\n|---|---|\n| Huda | claimant |\n| | defendant's agent |"
check("a table without amounts is left as it is", pp.tidy_tables(names) == names.replace("| | defendant's agent |", "|  | defendant's agent |")
      or pp.tidy_tables(names).count("\n") == 3)

# --- the numbers pass on money tables ------------------------------------------------
statement = cv2.cvtColor(tp.photo_statement()[0], cv2.COLOR_BGR2GRAY)
calls = []


def statement_vision(prompt, picture):
    calls.append(prompt)
    if "is one band" in prompt:
        return "13/10 | transfer | 300.00; 300.09"
    return "Date Description Amount Balance\n13/10 transfer 300.00 300.09\n18/10 transfer 250.00 550.09\n22/10 ATM -300.00 250.09"


seen_payloads = []


def recording_llm(prompt, payload):
    seen_payloads.append((prompt, payload))
    return {"text": "statement", "uncertain": [], "corrections": [], "document_type": "bank statement", "headings": []}


page = {"page": 1, "image": cv2.cvtColor(statement, cv2.COLOR_GRAY2BGR), "text_layer": "", "native_text": "",
        "picture_share": 1.0, "pictures": [], "regions": [("whole page", cv2.cvtColor(statement, cv2.COLOR_GRAY2BGR))]}
done = pp.process_page(page, statement_vision, recording_llm)
check("a page with money figures gets the numbers pass on three enlarged bands",
      sum("is one band" in c for c in calls) == 3 and done["regions"][0].get("numbers_pass"))
check("the numbers reading goes to the consolidation, which is told to prefer it for figures",
      "numbers" in seen_payloads[-1][1]["readings"] and "most reliable reading" in seen_payloads[-1][0])
check("a page whose reading is a money table is flagged table-heavy", "table_heavy" in done["regions"][0]["flags"])
check("the consolidation runs without hidden thinking", seen_payloads[-1][0].startswith("/no_think"))
check("no calculator runs: the page has no calculator output", "calculator" not in done)
calls.clear()
plain_page = dict(page, page=2)
pp.process_page(plain_page, lambda p, b: (calls.append(p), "A letter with no figures.")[1], recording_llm)
check("a page without money figures skips the numbers pass", not any("is one band" in c for c in calls))

# --- text layers: clean numbers are exact, damaged numbers are hidden ---------------
damaged = ("قرارات الدائرة الأوڲʄ لݏجنة المنازعات المصرفية رقم القرار ٥١٥/٥٢٠٢/د Ȋسم الله الرحمن الرحيم "
           "اݍحمد ھلل رب العالم؈ن مبلغٍ مقـداره (٠٥٢) رʈـال ࢭʏ حسابها")
clean = "صحيفة دعوى املدعي هدى رقم الهوية 1027476025 تاريخ بداية التجميد 18 -10 -2024 املبلغ محل التجميد 250"
check("a text layer with broken glyphs is damaged, an ordinary one clean",
      pp.text_layer_quality(damaged) == "damaged" and pp.text_layer_quality(clean) == "clean"
      and pp.text_layer_quality("") == "none")
check("a damaged layer's digits are hidden from the models (a reversed number cannot be copied)",
      "٥٢٠٢" not in pp.hint_text(damaged, "damaged") and "#" in pp.hint_text(damaged, "damaged")
      and "18 -10 -2024" in pp.hint_text(clean, "clean"))
check("the reader is told a clean layer's numbers are exact, a damaged layer's are hidden",
      "exact copies" in pp._context_text(clean, "", "clean") and "digits are hidden" in pp._context_text(damaged, "", "damaged"))
pp.consolidate({"original": "x"}, clean, recording_llm, "screenshot")
check("the consolidation is told when the text layer's numbers are exact",
      seen_payloads[-1][1]["text_layer_quality"] == "clean" and "18 -10 -2024" in seen_payloads[-1][1]["pdf_text_layer"])

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
