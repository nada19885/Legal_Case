
"""
Financial Evidence-Extraction Pipeline Orchestrator.
Location: lib/python/legal_platform/financial_extraction_pipeline.py

Per page: Stage 1a (PyMuPDF structural evidence, from the original PDF) +
the page's existing verbatim OCR transcription (produced once at document
intake, see extraction.py/vlm_adapter.py) -> Stage 2 (text-LLM
reconstruction into rows). No dedicated financial VLM pass: the intake OCR
already transcribes every page verbatim, including tables, at the same DPI
a financial-specific re-read would use.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
from typing import Callable, Optional
from .storage import case_rows

from .config import FINANCIAL_PAGE_MAX_WORKERS, FINANCIAL_LINE_ITEMS_DATASET
from .financial_structural_extraction import extract_page_structure
from .financial_page_sources import (
    FinancialPageSource,
    load_document_pdf_bytes,
    load_financial_pages,
)
from .financial_reconciliation import (
    build_rows_from_reconstruction,
    persist_reconciled_rows,
    reconstruct_page_transactions,
)

ProgressCallback = Callable[[int, int, str], None]


def _already_extracted_page_ids(case_id: str) -> set[str]:              
    df = case_rows(FINANCIAL_LINE_ITEMS_DATASET, case_id)
    if df.empty or "page_id" not in df.columns:
        return set()
    return set(df["page_id"].astype(str).tolist())


def sanitize_extracted_line_items(raw_items: list[dict]) -> list[dict]:
    """Filters out empty or invalid rows before writing to the database."""
    clean_items = []
    for item in raw_items:
        try:
            fields = json.loads(item.get("fields_json", "{}") or "{}")
            raw_amt = str(fields.get("amount", {}).get("value", "")).strip()
        except Exception:
            raw_amt = ""

        if not raw_amt:
            continue

        numeric_amt = re.sub(r"[^\d.]", "", raw_amt)
        if not numeric_amt:
            continue

        try:
            val = float(numeric_amt)
            if val <= 0:
                continue
            clean_items.append(item)
        except (ValueError, TypeError):
            continue

    return clean_items


def _process_page(
    page: FinancialPageSource,
    pdf_bytes_by_document: dict[str, Optional[bytes]],
) -> tuple[list[dict], list[str]]:
    failures: list[str] = []
    pdf_bytes = pdf_bytes_by_document.get(page.case_document_id)

    # Stage 1a: PyMuPDF structural evidence (native text/tables). Empty but
    # harmless on a scanned/image-only page.
    structural_evidence = {"paragraphs": [], "tables": [], "has_text_layer": False}
    if pdf_bytes:
        try:
            structural_evidence = extract_page_structure(pdf_bytes, page.page_number)
        except Exception as error:
            failures.append(f"PyMuPDF structural extraction failed: {error!r}")

    # Second evidence source: the page's own verbatim OCR transcription,
    # already produced at document intake (extraction.py) — no fresh VLM call.
    transcription_text = page.page_text

    # Stage 2: text-LLM reconstruction cross-checking both evidence sources.
    try:
        reconstruction = reconstruct_page_transactions(
            structural_evidence, transcription_text, page.page_number,
        )
    except Exception as error:
        failures.append(f"Stage 2 reconstruction failed: {error!r}")
        reconstruction = {"transactions": []}

    rows = build_rows_from_reconstruction(
        page.page_id, page.case_document_id, page.page_number, reconstruction,
    )

    cleaned_rows = sanitize_extracted_line_items(rows)
    return cleaned_rows, failures


def run_financial_extraction(
    case_id: str,
    page_ids: Optional[list[str]] = None,  # <--- Now accepts page_ids
    actor: str = "",
    progress_callback: Optional[ProgressCallback] = None,
    force_rerun: bool = False,
) -> dict:
    # Load all pages, then strictly filter to ONLY the requested financial/mixed pages
    all_pages = load_financial_pages(case_id, None)
    if page_ids is not None:
        requested = set(str(pid) for pid in page_ids)
        pages = [p for p in all_pages if str(p.page_id) in requested]
    else:
        pages = all_pages

    if not pages:
        raise ValueError("No extracted financial pages are available for this case.")
        
    if not force_rerun:
        already_done = _already_extracted_page_ids(case_id)
        pages = [p for p in pages if str(p.page_id) not in already_done]

    if not pages:
        existing = case_rows(FINANCIAL_LINE_ITEMS_DATASET, case_id).to_dict(orient="records")
        return {
            "case_id": case_id,
            "pages_processed": 0,
            "rows_persisted": 0,
            "verified": sum(1 for r in existing if r.get("row_status") == "verified"),
            "needs_review": sum(1 for r in existing if r.get("row_status") == "needs_review"),
            "page_failures": [],
            "new_rows_appended": 0,
        }
        

    pdf_bytes_by_document: dict[str, Optional[bytes]] = {
        document_id: load_document_pdf_bytes(case_id, document_id)
        for document_id in {page.case_document_id for page in pages}
    }

    all_rows: list[dict] = []
    page_failures: list[dict] = []
    completed = 0
    worker_count = max(1, min(int(FINANCIAL_PAGE_MAX_WORKERS), len(pages)))

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_page = {
            executor.submit(_process_page, page, pdf_bytes_by_document): page
            for page in pages
        }
        for future in as_completed(future_to_page):
            page = future_to_page[future]
            try:
                rows, failures = future.result()
            except Exception as error:
                rows, failures = [], [f"Page worker failed: {error!r}"]

            all_rows.extend(rows)
            if failures:
                page_failures.append({
                    "page_id": page.page_id,
                    "page_number": page.page_number,
                    "failures": failures,
                })

            completed += 1
            if progress_callback:
                progress_callback(completed, len(pages), page.page_id)

    persisted_count = persist_reconciled_rows(case_id, all_rows)
    verified_count = sum(1 for r in all_rows if r.get("row_status") == "verified")
    needs_review_count = sum(1 for r in all_rows if r.get("row_status") == "needs_review")

    return {
        "case_id": case_id,
        "pages_processed": len(pages),
        "rows_persisted": persisted_count if isinstance(persisted_count, int) else len(all_rows),
        "verified": verified_count,
        "needs_review": needs_review_count,
        "page_failures": page_failures,
        "new_rows_appended": len(all_rows),
    }

