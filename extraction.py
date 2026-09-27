from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from typing import Callable, Optional

from .config import (
    CASE_DOCUMENT_PAGES_DATASET,
    PDF_PAGE_MAX_CONCURRENT_REQUESTS,
    PDF_RENDER_DPI,
)
from .pdf_to_images import render_pdf_to_images
from .page_summary import summarise_pages
from .storage import append_rows
from .vlm_adapter import (
    extract_page_with_vlm_fallback,
    recover_failed_page,
)

ProgressCallback = Callable[[int, int, int, str], None]


def _json_list(result: dict, key: str) -> str:
    value = result.get(key, [])
    if not isinstance(value, list):
        value = []
    return json.dumps(value, ensure_ascii=False, default=str)


def _build_page_row(case_id, case_document_id, rendered_page, result):
    page_text = str(result.get("page_text", "") or "").strip()
    status = str(result.get("processing_status", "") or "").strip().lower()
    if not status:
        status = "completed" if page_text else "failed"
    if not page_text:
        status = "failed"

    metadata = {
        "selected_text_source": result.get("selected_text_source", ""),
        "validation": result.get("validation", {}),
        "image_sha256": rendered_page.image_sha256,
        "base64_character_count": rendered_page.base64_character_count,
        "native_text_extracted": False,
        "per_page_structured_extraction": False,
        "page_summary_status": result.get("summary_status", ""),
    }

    warning = str(result.get("extraction_warning", "") or "").strip()
    summary_warning = str(result.get("summary_warning", "") or "").strip()
    if summary_warning:
        warning = (warning + "\n" if warning else "") + (
            "PAGE_SUMMARY_WARNING=" + summary_warning
        )
    if warning:
        warning += "\n"
    warning += "VALIDATION_JSON=" + json.dumps(
        metadata,
        ensure_ascii=False,
        default=str,
    )

    return {
        "page_id": rendered_page.page_id,
        "case_document_id": case_document_id,
        "case_id": case_id,
        "page_number": rendered_page.page_number,
        "page_text": page_text,
        "text_character_count": len(page_text),
        "extraction_method": (
            "fast_primary_vlm_explicit_base64_with_delayed_recovery"
        ),
        "extraction_warning": warning,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "page_image_path": rendered_page.image_path,
        "page_image_mime_type": rendered_page.mime_type,
        "page_image_width": rendered_page.width,
        "page_image_height": rendered_page.height,
        # Compact text-only summary fields are created only after OCR and
        # recovery finish. Full page_text remains stored for evidence/retrieval.
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
        "signatures_or_stamps_json": _json_list(
            result,
            "signatures_or_stamps",
        ),
        "processing_status": status,
    }


def extract_pdf_page_by_page(
    case_id: str,
    case_document_id: str,
    pdf_bytes: bytes,
    progress_callback: Optional[ProgressCallback] = None,
    max_concurrent_requests: int = PDF_PAGE_MAX_CONCURRENT_REQUESTS,
    dpi: int = PDF_RENDER_DPI,
    **_,
) -> list[dict]:
    """
    Fast and resilient extraction:

    - Render all pages once at fixed 144 DPI.
    - Process up to three pages concurrently.
    - Call the fast recipe-tested VLM first.
    - Call the slower VLM only when the fast call fails.
    - Do not run a text model inside each OCR page worker.
    - After OCR completes, create compact page summaries concurrently.
    - Retry only unresolved pages after the normal pass.
    - Never extract or send PyMuPDF native text.
    """
    if max_concurrent_requests < 1:
        raise ValueError("max_concurrent_requests must be at least 1.")

    rendered_pages = render_pdf_to_images(
        case_id=case_id,
        case_document_id=case_document_id,
        pdf_bytes=pdf_bytes,
        dpi=dpi,
        store_images=True,
    )

    total_pages = len(rendered_pages)
    if total_pages == 0:
        return []

    worker_count = min(int(max_concurrent_requests), total_pages)
    print(
        "[document extraction] total_pages={} page_workers={} "
        "strategy=fast_primary_then_fallback recovery=delayed "
        "image_mode=png dpi={} transport=explicit_base64_with_inline_image "
        "native_text=false per_page_structuring=false".format(
            total_pages,
            worker_count,
            int(dpi),
        )
    )

    results_by_page: dict[int, dict] = {}
    rendered_by_number = {
        page.page_number: page
        for page in rendered_pages
    }
    failed_page_numbers: list[int] = []
    completed_count = 0

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_page = {
            executor.submit(
                extract_page_with_vlm_fallback,
                page,
            ): page
            for page in rendered_pages
        }

        for future in as_completed(future_to_page):
            rendered_page = future_to_page[future]
            try:
                result = future.result()
            except Exception as error:
                result = {
                    "page_number": rendered_page.page_number,
                    "page_text": "",
                    "processing_status": "failed",
                    "selected_text_source": "normal_worker_exception",
                    "extraction_warning": repr(error),
                    "validation": {
                        "native_text_extracted": False,
                        "native_text_sent_to_vlm": False,
                        "requires_review": True,
                    },
                }

            results_by_page[rendered_page.page_number] = result

            if result.get("processing_status") == "failed":
                failed_page_numbers.append(rendered_page.page_number)

            completed_count += 1
            print(
                "[normal pass progress] completed={}/{} page={} status={}".format(
                    completed_count,
                    total_pages,
                    rendered_page.page_number,
                    result.get("processing_status", "failed"),
                )
            )

            if progress_callback:
                progress_callback(
                    completed_count,
                    total_pages,
                    rendered_page.page_number,
                    result.get("processing_status", "failed"),
                )

    if failed_page_numbers:
        failed_page_numbers = sorted(set(failed_page_numbers))
        print(
            "[recovery pass] unresolved_pages={}".format(
                failed_page_numbers
            )
        )

        # Sequential recovery avoids overloading the endpoint while giving
        # transient failures time to clear.
        for page_number in failed_page_numbers:
            rendered_page = rendered_by_number[page_number]
            recovered = recover_failed_page(rendered_page)
            results_by_page[page_number] = recovered

            print(
                "[recovery progress] page={} status={}".format(
                    page_number,
                    recovered.get("processing_status", "failed"),
                )
            )

    # Phase 2: compact summaries. This starts after all OCR/recovery calls and
    # therefore does not change the fast image extraction strategy.
    summary_inputs = []
    for page_number in sorted(results_by_page):
        result = results_by_page[page_number]
        if str(result.get("page_text", "") or "").strip():
            summary_inputs.append({
                "page_id": rendered_by_number[page_number].page_id,
                "page_number": page_number,
                "page_text": result.get("page_text", ""),
            })

    summaries_by_id = summarise_pages(summary_inputs)
    for page_number, result in results_by_page.items():
        page_id = rendered_by_number[page_number].page_id
        summary = summaries_by_id.get(page_id)
        if summary:
            result.update(summary)

    ordered_rows = []
    for page_number in sorted(results_by_page):
        rendered_page = rendered_by_number[page_number]
        row = _build_page_row(
            case_id,
            case_document_id,
            rendered_page,
            results_by_page[page_number],
        )
        ordered_rows.append(row)

    # Sequential dataset writes avoid concurrent Dataiku writer conflicts.
    for row in ordered_rows:
        print(
            "[page persistence] page={} summary_status={} parties={} dates={} "
            "amounts={} case_numbers={} claims={} facts={} legal_refs={} evidence={}".format(
                row.get("page_number", ""),
                "fallback" if "PAGE_SUMMARY_WARNING=" in str(row.get("extraction_warning", "")) else "completed",
                len(json.loads(row.get("parties_json", "[]") or "[]")),
                len(json.loads(row.get("dates_json", "[]") or "[]")),
                len(json.loads(row.get("amounts_json", "[]") or "[]")),
                len(json.loads(row.get("case_numbers_json", "[]") or "[]")),
                len(json.loads(row.get("claims_json", "[]") or "[]")),
                len(json.loads(row.get("facts_json", "[]") or "[]")),
                len(json.loads(row.get("legal_references_json", "[]") or "[]")),
                len(json.loads(row.get("evidence_items_json", "[]") or "[]")),
            )
        )
        append_rows(CASE_DOCUMENT_PAGES_DATASET, [row])

    return ordered_rows
