"""
Document intake: every page of an uploaded PDF read once by the page
pipeline (page_pipeline.py) and stored.
Location: lib/python/legal_platform/extraction.py

Per page:
  - the page image is rendered and stored for display (pdf_to_images);
  - page_pipeline routes the page (the PDF's own text where it is reliable,
    the vision model for pictures), reads it with the case context and
    merges the candidates into one clean text;
  - that text is the page's page_text (case_document_pages), which every
    later stage reads;
  - the full extraction record (route, image kinds, every candidate reading,
    uncertain values, corrections, errors) is saved as JSON in the case
    documents folder: /cases/<case>/extraction/<page_id>.json.
Pages are rendered, read and summarised in parallel; a failed page is
retried once after the pass. Each document logs a [document timing] line.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Optional

from . import page_pipeline as pp
from .config import (
    CASE_DOCUMENT_FOLDER_ID,
    CASE_DOCUMENT_PAGES_DATASET,
    PAGE_READ_PARALLEL_CALLS,
    PAGE_SUMMARY_MAX_WORKERS,
    PDF_PAGE_MAX_CONCURRENT_REQUESTS,
    PDF_RENDER_DPI,
)
from .pdf_to_images import render_pdf_page
from .page_summary import summary_or_fallback
from .storage import append_rows

ProgressCallback = Callable[[int, int, int, str], None]
EXTRACTION_DIR = "extraction"
RECORD_SCHEMA = "page_extraction_v1"
RECORD_SAVE_WORKERS = 4


# -----------------------------------------------------------------------------
# Page extraction records (managed folder JSON)
# -----------------------------------------------------------------------------
def _record_path(case_id: str, page_id: str) -> str:
    return f"/cases/{case_id}/{EXTRACTION_DIR}/{page_id}.json"


def save_page_extraction(case_id: str, page_id: str, record: dict) -> None:
    import dataiku
    payload = json.dumps(record, ensure_ascii=False, default=str).encode("utf-8")
    dataiku.Folder(CASE_DOCUMENT_FOLDER_ID).upload_data(_record_path(case_id, page_id), payload)


def load_page_extraction(case_id: str, page_id: str) -> Optional[dict]:
    """The stored extraction record of one page, or None."""
    import dataiku
    try:
        with dataiku.Folder(CASE_DOCUMENT_FOLDER_ID).get_download_stream(_record_path(case_id, page_id)) as stream:
            return json.loads(stream.read().decode("utf-8"))
    except Exception:
        return None


def update_page_extraction(case_id: str, page_id: str, changes: dict) -> Optional[dict]:
    """Merge keys into a stored record (e.g. the accounting stage's notes)."""
    record = load_page_extraction(case_id, page_id)
    if record is None:
        return None
    record.update(changes)
    save_page_extraction(case_id, page_id, record)
    return record


def _record(case_id, case_document_id, document_name, rendered_page, result) -> dict:
    return {
        "schema": RECORD_SCHEMA,
        "case_id": case_id,
        "page_id": rendered_page.page_id,
        "case_document_id": case_document_id,
        "document_name": document_name,
        "page_number": rendered_page.page_number,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "route": result.get("route", ""),
        "route_reason": result.get("route_reason", ""),
        "text_layer_quality": result.get("text_layer_quality", ""),
        "picture_share": result.get("picture_share", 0.0),
        "regions": result.get("regions") or [],
        "candidates": result.get("readings") or {},
        "final_text": result.get("final_text", ""),
        "uncertain": result.get("uncertain") or [],
        "corrections": result.get("corrections") or [],
        "document_type": result.get("document_type", ""),
        "headings": result.get("headings") or [],
        "errors": result.get("errors") or [],
        "vision_calls": result.get("vision_calls", 0),
        "llm_calls": result.get("llm_calls", 0),
        "seconds": result.get("seconds", 0),
    }


# -----------------------------------------------------------------------------
# Page rows
# -----------------------------------------------------------------------------
def _json_list(result: dict, key: str) -> str:
    value = result.get(key, [])
    if not isinstance(value, list):
        value = []
    return json.dumps(value, ensure_ascii=False, default=str)


def _status(result: dict) -> str:
    if not str(result.get("final_text", "") or "").strip():
        return "failed"
    if result.get("uncertain") or result.get("errors"):
        return "completed_review_required"
    return "completed"


def _build_page_row(case_id, case_document_id, rendered_page, result):
    page_text = str(result.get("final_text", "") or "").strip()
    route = str(result.get("route", "") or "")
    metadata = {
        "route": route,
        "text_layer_quality": result.get("text_layer_quality", ""),
        "kinds": [region.get("kind") for region in result.get("regions") or []],
        "flags": sorted({flag for region in result.get("regions") or [] for flag in region.get("flags") or []}),
        "uncertain_values": len(result.get("uncertain") or []),
        "image_sha256": rendered_page.image_sha256,
        "native_text_extracted": route in {"native", "native+vlm"},
        "page_summary_status": result.get("summary_status", ""),
    }
    warning = "\n".join(str(e) for e in result.get("errors") or [])[:2000]
    if result.get("summary_warning"):
        warning = (warning + "\n" if warning else "") + "PAGE_SUMMARY_WARNING=" + str(result["summary_warning"])
    warning = (warning + "\n" if warning else "") + "VALIDATION_JSON=" + json.dumps(
        metadata, ensure_ascii=False, default=str)

    return {
        "page_id": rendered_page.page_id,
        "case_document_id": case_document_id,
        "case_id": case_id,
        "page_number": rendered_page.page_number,
        "page_text": page_text,
        "text_character_count": len(page_text),
        "extraction_method": f"page_pipeline:{route or 'failed'}",
        "extraction_warning": warning,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "page_image_path": rendered_page.image_path,
        "page_image_mime_type": rendered_page.mime_type,
        "page_image_width": rendered_page.width,
        "page_image_height": rendered_page.height,
        "page_summary": str(result.get("page_summary", "") or ""),
        "document_type": str(result.get("document_type", "") or ""),
        "document_language": str(result.get("document_language", "") or ""),
        "parties_json": _json_list(result, "parties"),
        "dates_json": _json_list(result, "dates"),
        "amounts_json": _json_list(result, "amounts"),
        "case_numbers_json": _json_list(result, "case_numbers"),
        "claims_json": _json_list(result, "claims"),
        "facts_json": _json_list(result, "facts"),
        "legal_references_json": _json_list(result, "legal_references"),
        "evidence_items_json": _json_list(result, "evidence_items"),
        "signatures_or_stamps_json": _json_list(result, "signatures_or_stamps"),
        "processing_status": _status(result),
    }


# -----------------------------------------------------------------------------
# The document
# -----------------------------------------------------------------------------
def _read_page(pdf_bytes, number, total, layers, base_context, vision, text_llm) -> dict:
    try:
        page = pp.load_page(pdf_bytes, number)
        return pp.process_page(page, vision, text_llm, pp.page_context(base_context, number, total, layers),
                               parallel=PAGE_READ_PARALLEL_CALLS)
    except Exception as error:
        return {"page": number, "route": "", "final_text": "", "readings": {}, "regions": [], "uncertain": [],
                "corrections": [], "errors": [f"page failed: {type(error).__name__}: {error}"]}


def extract_pdf_page_by_page(
    case_id: str,
    case_document_id: str,
    pdf_bytes: bytes,
    progress_callback: Optional[ProgressCallback] = None,
    max_concurrent_requests: int = PDF_PAGE_MAX_CONCURRENT_REQUESTS,
    dpi: int = PDF_RENDER_DPI,
    document_name: str = "",
    case_context: Optional[dict] = None,
    vision=None,
    text_llm=None,
    timings: Optional[dict] = None,
    **_,
) -> list[dict]:
    """Read every page of one PDF with the page pipeline and store the page
    rows (case_document_pages) and extraction records. `case_context` holds
    the case record and known parties, passed to the reader as a hint.

    Each page is rendered and read by the same worker, so reading starts
    with the first page, and its summary starts as soon as its text is
    ready. `timings`, when given, is filled with where the time went."""
    if max_concurrent_requests < 1:
        raise ValueError("max_concurrent_requests must be at least 1.")
    started = time.time()
    vision = vision or pp.dataiku_vision()
    text_llm = text_llm or pp.dataiku_text_llm()

    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty.")
    total_pages = pp.page_count(pdf_bytes)
    if total_pages == 0:
        return []
    layers = pp.text_layers(pdf_bytes)
    base_context = dict(case_context or {}, document_name=document_name or case_document_id)
    workers = min(int(max_concurrent_requests), total_pages)
    print(f"[document extraction] document={document_name} pages={total_pages} "
          f"page_workers={workers} summary_workers={PAGE_SUMMARY_MAX_WORKERS} pipeline=page_pipeline")

    spent = {"render_seconds": 0.0, "read_seconds": 0.0, "summary_seconds": 0.0}
    lock = threading.Lock()

    def add(key, seconds):
        with lock:
            spent[key] += seconds

    def render_and_read(number):
        began = time.time()
        rendered_page = render_pdf_page(case_id, case_document_id, pdf_bytes, number, dpi=dpi)
        rendered_at = time.time()
        result = _read_page(pdf_bytes, number, total_pages, layers, base_context, vision, text_llm)
        add("render_seconds", rendered_at - began)
        add("read_seconds", time.time() - rendered_at)
        return rendered_page, result

    def summarise(number):
        began = time.time()
        summary = summary_or_fallback({"page_id": rendered_by_number[number].page_id, "page_number": number,
                                       "page_text": results[number].get("final_text", "")})
        add("summary_seconds", time.time() - began)
        return summary

    rendered_by_number: dict = {}
    results: dict[int, dict] = {}
    summary_futures: dict = {}
    with ThreadPoolExecutor(max_workers=workers) as readers, \
            ThreadPoolExecutor(max_workers=max(1, int(PAGE_SUMMARY_MAX_WORKERS))) as summarisers:
        futures = {readers.submit(render_and_read, number): number for number in range(1, total_pages + 1)}
        completed = 0
        for future in as_completed(futures):
            number = futures[future]
            rendered_by_number[number], results[number] = future.result()
            completed += 1
            route = results[number].get("route") or "failed"
            print(f"[page read] page={number} route={route} status={_status(results[number])} "
                  f"vision_calls={results[number].get('vision_calls', 0)} seconds={results[number].get('seconds', 0)} "
                  f"reason={results[number].get('route_reason', '')}")
            if progress_callback:
                progress_callback(completed, total_pages, number, route)
            if _has_text(results[number]):
                summary_futures[number] = summarisers.submit(summarise, number)
        reads_done = time.time()

        # One more try for pages that produced no text (a transient model failure).
        for number in sorted(n for n, r in results.items() if not _has_text(r)):
            retry = _read_page(pdf_bytes, number, total_pages, layers, base_context, vision, text_llm)
            if _has_text(retry):
                retry["errors"] = list(retry.get("errors") or []) + ["recovered on a second attempt"]
                results[number] = retry
                summary_futures[number] = summarisers.submit(summarise, number)
            print(f"[page recovery] page={number} status={_status(results[number])}")
        retries_done = time.time()
        summaries = {number: future.result() for number, future in summary_futures.items()}
    summaries_done = time.time()

    rows = []
    for number in sorted(results):
        result = results[number]
        summary = summaries.get(number) or {}
        merged = {**result, **{k: v for k, v in summary.items() if k != "document_type" or v}}
        rows.append(_build_page_row(case_id, case_document_id, rendered_by_number[number], merged))

    def save_record(number):
        try:
            save_page_extraction(case_id, rendered_by_number[number].page_id,
                                 _record(case_id, case_document_id, document_name, rendered_by_number[number],
                                         results[number]))
        except Exception as error:
            print(f"[page extraction record] page={number} could not be saved: {error!r}")

    with ThreadPoolExecutor(max_workers=min(RECORD_SAVE_WORKERS, len(results))) as savers:
        list(savers.map(save_record, sorted(results)))
    records_done = time.time()

    # One dataset write for the whole document (each write is a full Dataiku write).
    append_rows(CASE_DOCUMENT_PAGES_DATASET, rows)
    finished = time.time()

    clock = {
        "pages": total_pages,
        "seconds": round(finished - started, 1),
        "reading_seconds": round(reads_done - started, 1),
        "retry_seconds": round(retries_done - reads_done, 1),
        "summary_wait_seconds": round(summaries_done - retries_done, 1),
        "records_seconds": round(records_done - summaries_done, 1),
        "rows_seconds": round(finished - records_done, 1),
        **{key: round(value, 1) for key, value in spent.items()},
        "vision_calls": sum(int(r.get("vision_calls", 0) or 0) for r in results.values()),
        "llm_calls": sum(int(r.get("llm_calls", 0) or 0) for r in results.values()) + len(summary_futures),
        "routes": _count(r.get("route") or "failed" for r in results.values()),
    }
    print("[document timing] document={} {}".format(
        document_name, " ".join(f"{k}={v}" for k, v in clock.items())))
    if timings is not None:
        timings.update(clock)
    return rows


def _has_text(result: dict) -> bool:
    return bool(str(result.get("final_text", "") or "").strip())


def _count(values) -> dict:
    out: dict = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return out
