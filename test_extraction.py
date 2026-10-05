"""
Checks for document intake (extraction.py) with the page pipeline.

Run from the repository root:  python test_extraction.py
Dataiku (folder, datasets) and the models are stand-ins: this checks that
every page is read once, that page_text is the consolidated text, and that
each page's extraction record is stored and can be read back.
"""

import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parent
FOLDER = {}


class _Folder:
    def __init__(self, folder_id):
        pass

    def upload_data(self, path, data):
        FOLDER[path] = data

    def get_download_stream(self, path):
        import io
        if path not in FOLDER:
            raise FileNotFoundError(path)
        return io.BytesIO(FOLDER[path])


dataiku = types.ModuleType("dataiku")
dataiku.Folder = _Folder
sys.modules["dataiku"] = dataiku
if "legal_platform" not in sys.modules:
    spec = importlib.util.spec_from_file_location("legal_platform", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules["legal_platform"] = package
    spec.loader.exec_module(package)

import fitz                                              # noqa: E402
import cv2                                               # noqa: E402
from legal_platform import extraction                    # noqa: E402
import test_pages as tp                                  # noqa: E402

failures = []


def check(label, condition):
    print(("[PASS] " if condition else "[FAIL] ") + label)
    if not condition:
        failures.append(label)


ROWS = []
extraction.append_rows = lambda dataset, rows: ROWS.extend(rows) or len(rows)
extraction.summarise_pages = lambda pages: {p["page_id"]: {"page_summary": f"summary of page {p['page_number']}",
                                                            "document_type": "", "parties": ["Huda"]} for p in pages}

document = fitz.open()
typed = document.new_page(width=595, height=842)
typed.insert_text((60, 80), "Statement of claim - account freeze", fontsize=14)
for line in range(20):
    typed.insert_text((60, 120 + line * 20), f"Line {line + 1}: the amount of 250 SAR was frozen on 18-10-2024.", fontsize=10)
scanned = document.new_page(width=595, height=842)
scanned.insert_image(fitz.Rect(0, 0, 595, 842), stream=cv2.imencode(".png", tp.photo_statement()[0])[1].tobytes())
data = document.tobytes()

prompts = []


def vision(prompt, png):
    prompts.append(prompt)
    if "is one band" in prompt:
        return "NONE"
    return "| Date | Description | Amount | Balance |\n|---|---|---|---|\n| 13/10 | transfer | 300.00 | 300.09 |"


def text_llm(prompt, payload):
    return {"text": "| Date | Description | Amount | Balance |\n|---|---|---|---|\n| 13/10 | transfer | 300.00 | 300.09 |",
            "uncertain": [], "corrections": [], "document_type": "bank statement", "headings": ["Statement"]}


progress = []
rows = extraction.extract_pdf_page_by_page(
    "CASE1", "CDOC1", data, progress_callback=lambda c, t, n, s: progress.append((c, t, n, s)),
    document_name="claim.pdf", case_context={"case": {"case_name": "Huda v BSF"}, "parties": ["Huda (claimant)"]},
    vision=vision, text_llm=text_llm,
)
check("one row per page, stored once", len(rows) == 2 and len(ROWS) == 2)
check("the typed page's text comes from the PDF itself (no vision call for it)",
      "account freeze" in rows[0]["page_text"] and rows[0]["extraction_method"] == "page_pipeline:native")
check("the scanned page is read by the vision model and merged",
      rows[1]["extraction_method"] == "page_pipeline:vlm" and "300.09" in rows[1]["page_text"])
check("the reader is given the document name and case", any("claim.pdf" in p and "Huda v BSF" in p for p in prompts))
check("page summaries are attached to the rows", rows[0]["page_summary"] == "summary of page 1")
check("progress is reported per page with its route", sorted(p[2] for p in progress) == [1, 2]
      and {p[3] for p in progress} == {"native", "vlm"})
record = extraction.load_page_extraction("CASE1", rows[1]["page_id"])
check("each page's extraction record is stored and read back",
      record and record["route"] == "vlm" and record["document_name"] == "claim.pdf"
      and set(record["candidates"]) >= {"original", "cleaned"} and record["final_text"] == rows[1]["page_text"])
check("the record keeps each picture's kind and flags",
      record["regions"] and record["regions"][0]["kind"] in {"scan", "photo", "screenshot"}
      and "flags" in record["regions"][0])
extraction.update_page_extraction("CASE1", rows[1]["page_id"], {"reviewed": True})
check("a record can be updated without losing its content",
      extraction.load_page_extraction("CASE1", rows[1]["page_id"])["reviewed"] is True
      and extraction.load_page_extraction("CASE1", rows[1]["page_id"])["route"] == "vlm")
check("a missing record reads as None", extraction.load_page_extraction("CASE1", "nope") is None)

failing = [0]


def flaky_vision(prompt, png):
    failing[0] += 1
    if failing[0] <= 2:
        raise RuntimeError("endpoint busy")
    return vision(prompt, png)


ROWS.clear()
again = extraction.extract_pdf_page_by_page("CASE2", "CDOC2", data, document_name="claim.pdf",
                                            vision=flaky_vision, text_llm=text_llm, max_concurrent_requests=1)
check("a page whose reads all failed is tried again after the pass",
      again[1]["page_text"] and again[1]["processing_status"] in {"completed", "completed_review_required"})

print()
if failures:
    print(f"{len(failures)} check(s) failed: {failures}")
    raise SystemExit(1)
print("All checks passed.")
