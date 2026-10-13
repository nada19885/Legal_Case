"""
Vision server capacity and page-routing check.
Location: paste into a Python notebook in the LEGAL_CASE project (same code
environment as the webapp), set CASE_ID and FILE_NAME, run cell by cell.

Part 1 (no model calls): why each page of one uploaded PDF goes to the
vision model or not: text layer, picture share, Arabic damage, route.

Part 2: is the vision model thinking before it answers? The same page with
and without /no_think: seconds, answer length, token counts if Dataiku
reports them.

Part 3: capacity. The same page sent with 1, 2, 4, 6, 8 calls in flight:
seconds per call, pages per minute and failures. Capacity is where pages
per minute stops rising or failures start: use that number of calls in
flight for the whole job.
"""

# %% Settings -----------------------------------------------------------------
CASE_ID = "CASE_1230F287D32947B391A6"
FILE_NAME = "دعوى هدى - حجز.pdf"     # original_filename as uploaded
TEST_PAGE = 5                        # a typical page with text and a table
LEVELS = [1, 2, 4, 6, 8]             # calls in flight to try
CALLS_PER_LEVEL = 2                  # each level sends level * this many calls

import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import dataiku
import fitz

from legal_platform import page_pipeline as pp
from legal_platform.arabic_text import ligature_damage
from legal_platform.config import CASE_DOCUMENT_FOLDER_ID, MULTIMODAL_LLM_ID
from legal_platform.storage import case_rows

documents = case_rows("case_documents", CASE_ID)
match = documents[documents["original_filename"] == FILE_NAME]
if match.empty:
    raise ValueError(f"No uploaded file named {FILE_NAME!r} in {CASE_ID}: {list(documents['original_filename'])}")
folder_path = match.iloc[-1]["folder_path"]
with dataiku.Folder(CASE_DOCUMENT_FOLDER_ID).get_download_stream(folder_path) as stream:
    PDF = stream.read()
print(f"{FILE_NAME}: {len(PDF):,} bytes, {pp.page_count(PDF)} pages")


# %% Part 1: why each page took its route --------------------------------------
def page_facts(number):
    page = pp.load_page(PDF, number)
    layer = page["text_layer"]
    with fitz.open(stream=PDF, filetype="pdf") as document:
        p = document.load_page(number - 1)
        area = p.rect.width * p.rect.height
        biggest = max((r.width * r.height / area for info in p.get_images(full=True)
                       for r in p.get_image_rects(info[0])), default=0.0)
    way = pp.route(page)
    share = page["picture_share"]
    damage = ligature_damage(layer)
    reason = pp.route_reason(page)
    return {"page": number, "route": way, "reason": reason, "words": len(layer.split()),
            "picture_share": share, "largest_image": round(biggest, 2), "pictures": len(page["pictures"]),
            "damaged_words": damage}


facts = [page_facts(n) for n in range(1, pp.page_count(PDF) + 1)]
for row in facts:
    print("page {page:>3}  {route:<10}  words={words:<5} pictures={pictures} share={picture_share:<5} "
          "largest_image={largest_image:<5} damaged={damaged_words:<3} -> {reason}".format(**row))
print("\nRoutes:", {r: sum(1 for f in facts if f["route"] == r) for r in ("native", "native+vlm", "vlm")})
print("largest_image near 1.0 with 'background image(s) ignored' in the reason: a letterhead or page\n"
      "background under the PDF's own text; the page is read from its text, not by the vision model.")


# %% Part 2: is the vision model thinking? -------------------------------------
PAGE_PNG = pp._png(pp.load_page(PDF, TEST_PAGE)["image"])
THINKING_PROMPT = pp.READ_PROMPT.format(part="", context="", table_rules=pp.TABLE_RULES)
PROMPT = "/no_think\n" + THINKING_PROMPT      # what the webapp's vision_call sends


def one_call(prompt):
    import base64
    began = time.time()
    try:
        completion = dataiku.api_client().get_default_project().get_llm(MULTIMODAL_LLM_ID).new_completion()
        completion.settings["temperature"] = 0.0
        message = completion.new_multipart_message(role="user")
        message.with_text(prompt)
        message.with_inline_image(base64.b64encode(PAGE_PNG).decode(), "image/png")
        message.add()
        response = completion.execute()
        succeeded = getattr(response, "success", True) is not False
        text = (response.text or "") if succeeded else ""
        error = "" if succeeded else str(getattr(response, "error_message", None) or "failed")
        raw = getattr(response, "_raw", {}) or {}
        usage = {k: raw[k] for k in ("promptTokens", "completionTokens", "totalTokens") if k in raw}
        if isinstance(raw.get("usage"), dict):
            usage.update(raw["usage"])
    except Exception as exc:                                              # noqa: BLE001
        text, usage, error = "", {}, repr(exc)
    return {"seconds": round(time.time() - began, 1), "chars": len(text),
            "think_tag": "<think>" in text, "usage": usage, "error": error}


for label, prompt in (("without /no_think", THINKING_PROMPT), ("with /no_think", PROMPT)):
    for attempt in (1, 2):
        result = one_call(prompt)
        print(f"{label:<15} try {attempt}: {result}")
print("\nIf 'with /no_think' is much faster for the same answer length, or completionTokens is far above\n"
      "chars / 3, the model spends most of its time reasoning before it transcribes.")


# %% Part 3: capacity -------------------------------------------------------------
USE_PROMPT = PROMPT          # the prompt the webapp sends (with /no_think)

summary = []
for level in LEVELS:
    calls = level * CALLS_PER_LEVEL
    began = time.time()
    with ThreadPoolExecutor(max_workers=level) as pool:
        results = list(pool.map(lambda _: one_call(USE_PROMPT), range(calls)))
    wall = time.time() - began
    ok = [r for r in results if not r["error"]]
    row = {"in_flight": level, "calls": calls, "failed": calls - len(ok),
           "median_call_s": round(statistics.median([r["seconds"] for r in ok]), 1) if ok else None,
           "slowest_call_s": max((r["seconds"] for r in ok), default=None),
           "pages_per_minute": round(len(ok) / wall * 60, 2)}
    summary.append(row)
    print(row)
    if row["failed"] >= max(1, calls // 2):
        print("Half the calls failed: stopping here.")
        break

best = max(summary, key=lambda r: (r["failed"] == 0, r["pages_per_minute"]))
print(f"\nBest without failures: {best['in_flight']} calls in flight -> {best['pages_per_minute']} calls/minute.")
print("Beyond that, extra calls only wait in the server's queue (slower calls, timeouts, failures).")
