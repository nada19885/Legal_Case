"""
Agreement page normalization + page-by-page clause structuring —
Stage 1 of the agreement clause-map pipeline (see agreement_workbench.
extract_clause_map). Stage 2, hierarchical consolidation across pages, is
in agreement_consolidation.py.
Location: lib/python/legal_platform/agreement_page_extraction.py
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

import pandas as pd

from .agreement_llm import agreement_complete_json
from .config import AGREEMENT_PAGE_MAX_WORKERS

PAGE_STRUCTURE_PROMPT = """
You are structuring one page of a legal agreement package for a page-by-page
extraction stage. A later stage will stitch these page structures together
across the whole package, so precision and traceability matter more than
completeness at this stage.

Use only the supplied page text. Do not infer content not present. A clause
may start, continue, or end on this page — mark that explicitly. Capture
every defined term this page introduces (a capitalized/quoted term the page
itself defines), not terms it merely uses.

Return JSON only:
{
  "section_heading": "",
  "clause_fragments": [
    {
      "clause_number": "",
      "heading": "",
      "text": "",
      "category": "definitions|term_and_termination|payment|liability|confidentiality|ip|data_protection|compliance|dispute_resolution|indemnity|warranties|force_majeure|assignment|notices|governing_law|other",
      "continues_from_previous_page": false,
      "continues_on_next_page": false,
      "exceptions_or_carve_outs": []
    }
  ],
  "definitions_introduced": [
    {"term": "", "definition": ""}
  ],
  "page_notes": ""
}
""".strip()


def normalize_pages(pages: Any) -> list[dict]:
    """Normalizes case_document_pages rows (a DataFrame, as loaded by
    case_rows, or an already-list-of-dicts) into a consistent shape:
    page_id, document_id, page_number, page_text, page_summary. Sorted into
    reading order (document, then page number) since consolidation depends
    on that order to stitch cross-page clause continuations correctly.
    """
    if isinstance(pages, pd.DataFrame):
        records = pages.fillna("").to_dict("records")
    elif isinstance(pages, list):
        records = pages
    else:
        records = []

    normalized = []
    for row in records:
        page_id = str(row.get("case_document_page_id") or row.get("page_id") or "").strip()
        if not page_id:
            continue
        normalized.append({
            "page_id": page_id,
            "document_id": str(row.get("case_document_id") or row.get("document_id") or ""),
            "page_number": int(row.get("page_number", 0) or 0),
            "page_text": str(row.get("page_text", "") or ""),
            "page_summary": str(row.get("page_summary", "") or ""),
        })

    normalized.sort(key=lambda page: (page["document_id"], page["page_number"]))
    return normalized


def _structure_one_page(page: dict) -> dict:
    text = (page.get("page_text") or page.get("page_summary") or "").strip()
    if not text:
        return {
            "page_id": page["page_id"],
            "document_id": page["document_id"],
            "page_number": page["page_number"],
            "section_heading": "",
            "clause_fragments": [],
            "definitions_introduced": [],
            "page_notes": "Blank or unreadable page.",
        }

    result = agreement_complete_json(
        PAGE_STRUCTURE_PROMPT,
        {"page_number": page["page_number"], "page_text": text[:6000]},
        operation=f"agreement page structuring page {page['page_number']}",
    )
    result["page_id"] = page["page_id"]
    result["document_id"] = page["document_id"]
    result["page_number"] = page["page_number"]
    result.setdefault("clause_fragments", [])
    result.setdefault("definitions_introduced", [])
    return result


def structure_agreement_pages(
    pages: Any,
    page_progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[dict]:
    """Page-by-page extraction: one LLM call per page, in parallel,
    identifying clause fragments and defined terms on that page only.
    Consolidation across pages happens afterward in agreement_consolidation.
    """
    normalized = normalize_pages(pages)
    if not normalized:
        raise ValueError("No usable extracted agreement pages are available.")

    results: dict[str, dict] = {}
    workers = max(1, min(int(AGREEMENT_PAGE_MAX_WORKERS or 1), len(normalized)))
    completed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_structure_one_page, page): page for page in normalized}
        for future in as_completed(futures):
            page = futures[future]
            try:
                results[page["page_id"]] = future.result()
            except Exception as error:
                results[page["page_id"]] = {
                    "page_id": page["page_id"],
                    "document_id": page["document_id"],
                    "page_number": page["page_number"],
                    "section_heading": "",
                    "clause_fragments": [],
                    "definitions_introduced": [],
                    "page_notes": f"Page structuring failed: {error!r}",
                }
            completed += 1
            if page_progress_callback:
                page_progress_callback(completed, len(normalized), page["page_id"])

    return [results[page["page_id"]] for page in normalized]
