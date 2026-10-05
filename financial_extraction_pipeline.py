
"""
Financial Evidence-Extraction Pipeline Orchestrator.
Location: lib/python/legal_platform/financial_extraction_pipeline.py

Per financial page: the page's consolidated text (produced once at document
intake by the page pipeline: the PDF's own text where reliable, the vision
reading otherwise, tables as markdown) + PyMuPDF structural evidence from
the original PDF -> one text-LLM call into atomic facts. Each fact records
its document, page, extraction source (the page's route) and the table
row(s) it came from.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import re
from typing import Callable, Optional
from .storage import case_rows

from .config import FINANCIAL_PAGE_MAX_WORKERS, FINANCIAL_LINE_ITEMS_DATASET
from .financial_fields import parse_fields
from .financial_structural_extraction import extract_page_structure
from .financial_page_sources import (
    FinancialPageSource,
    load_document_pdf_bytes,
    load_financial_pages,
)
from .financial_facts import build_fact_rows
from .financial_reconciliation import (
    extract_page_facts,
    persist_reconciled_rows,
    split_page_output,
)

ProgressCallback = Callable[[int, int, str], None]

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


# -----------------------------------------------------------------------------
# Financial claims found in documents (layer 1: what documents SAY about
# money). Stored per case, apart from the facts: they tell the accountant
# what to verify and never enter the ledger.
# -----------------------------------------------------------------------------
def _claims_path(case_id: str) -> str:
    return f"/cases/{case_id}/financial_claims.json"


def load_document_claims(case_id: str) -> dict:
    """page_id -> [financial claims] ({} when none were stored)."""
    import json
    import dataiku
    from .config import CASE_DOCUMENT_FOLDER_ID
    try:
        with dataiku.Folder(CASE_DOCUMENT_FOLDER_ID).get_download_stream(_claims_path(case_id)) as stream:
            value = json.loads(stream.read().decode("utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def save_document_claims(case_id: str, claims_by_page: dict, replace: bool = False) -> None:
    """Merge the claims of the pages just processed into the stored ones
    (or replace them all)."""
    import json
    import dataiku
    from .config import CASE_DOCUMENT_FOLDER_ID
    stored = {} if replace else load_document_claims(case_id)
    stored.update(claims_by_page)
    dataiku.Folder(CASE_DOCUMENT_FOLDER_ID).upload_data(
        _claims_path(case_id), json.dumps(stored, ensure_ascii=False).encode("utf-8"))


def _already_extracted_page_ids(case_id: str) -> set[str]:              
    df = case_rows(FINANCIAL_LINE_ITEMS_DATASET, case_id)
    if df.empty or "page_id" not in df.columns:
        return set()
    return set(df["page_id"].astype(str).tolist())


def sanitize_extracted_line_items(raw_items: list[dict]) -> tuple[list[dict], int]:
    """Drop rows that are noise, keep everything that needs a human.

    A row is discarded only when its amount was read with certainty and is
    exactly zero (balance/heading lines). A row with a missing or uncertain
    amount is KEPT: it becomes a pending review item instead of silently
    disappearing. Returns (kept_rows, discarded_count).
    """
    clean_items = []
    discarded = 0
    for item in raw_items:
        fields = parse_fields(item)
        amount = fields.get("amount") or {}
        raw_amt = str(amount.get("value", "") or "").strip()
        if raw_amt and amount.get("status") == "verified":
            numeric_amt = re.sub(r"[^\d.]", "", raw_amt.translate(_ARABIC_DIGITS))
            try:
                if numeric_amt and float(numeric_amt) == 0:
                    discarded += 1
                    continue
            except ValueError:
                pass
        clean_items.append(item)
    return clean_items, discarded


def _process_page(
    page: FinancialPageSource,
    pdf_bytes_by_document: dict[str, Optional[bytes]],
    page_type: str = "financial",
) -> tuple[list[dict], list[str], int, list[dict]]:
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

    # The page's consolidated text from document intake (extraction.py).
    transcription_text = page.page_text
    route = page.extraction_method.split(":", 1)[1] if page.extraction_method.startswith("page_pipeline:") else ""

    # Stage 2: one LLM call breaks the page into atomic financial facts,
    # each with a status (extracted / calculated / inferred / uncertain /
    # missing). Calculated facts are recomputed in build_fact_rows.
    try:
        output = extract_page_facts(structural_evidence, transcription_text, page.page_number, route, page_type)
    except Exception as error:
        failures.append(f"Fact extraction failed: {error!r}")
        return [], failures, 0, []

    # Facts only from accounting evidence; what the page asserts about money
    # is kept apart as financial claims (never in the ledger).
    output, claims, dropped = split_page_output(output, page_type)
    for note in dropped:
        print(f"[financial facts] page={page.page_number} dropped {note}")
    for claim in claims:
        claim.update({"page_id": page.page_id, "case_document_id": page.case_document_id,
                      "page_number": page.page_number, "document_name": page.document_name})

    rows = build_fact_rows(
        page.page_id, page.case_document_id, page.page_number, output,
        created_at=datetime.now(timezone.utc).isoformat(),
        meta={"document_name": page.document_name, "extraction_source": route or "page_text"},
    )
    return rows, failures, 0, claims


def run_financial_extraction(
    case_id: str,
    page_ids: Optional[list[str]] = None,  # <--- Now accepts page_ids
    actor: str = "",
    progress_callback: Optional[ProgressCallback] = None,
    force_rerun: bool = False,
    page_types: Optional[dict] = None,
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
            "rows_discarded": 0,
        }
        

    pdf_bytes_by_document: dict[str, Optional[bytes]] = {
        document_id: load_document_pdf_bytes(case_id, document_id)
        for document_id in {page.case_document_id for page in pages}
    }

    all_rows: list[dict] = []
    claims_by_page: dict[str, list[dict]] = {}
    page_failures: list[dict] = []
    discarded_total = 0
    completed = 0
    worker_count = max(1, min(int(FINANCIAL_PAGE_MAX_WORKERS), len(pages)))

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_page = {
            executor.submit(_process_page, page, pdf_bytes_by_document,
                            (page_types or {}).get(str(page.page_id), "financial")): page
            for page in pages
        }
        for future in as_completed(future_to_page):
            page = future_to_page[future]
            try:
                rows, failures, discarded, claims = future.result()
            except Exception as error:
                rows, failures, discarded, claims = [], [f"Page worker failed: {error!r}"], 0, []
            claims_by_page[str(page.page_id)] = claims

            all_rows.extend(rows)
            discarded_total += discarded
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
    try:
        save_document_claims(case_id, claims_by_page)
    except Exception as error:
        print(f"[financial claims] could not be saved: {error!r}")
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
        "rows_discarded": discarded_total,
        "financial_claims": sum(len(c) for c in claims_by_page.values()),
    }

