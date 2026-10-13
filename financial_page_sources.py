from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import dataiku

from .config import (
    CASE_DOCUMENT_FOLDER_ID,
    CASE_DOCUMENT_PAGES_DATASET,
    CASE_DOCUMENTS_DATASET,
)
from .storage import case_rows


@dataclass
class FinancialPageSource:
    page_id: str
    case_document_id: str
    page_number: int
    page_text: str
    page_image_path: str
    page_image_mime_type: str
    extraction_method: str = ""
    document_name: str = ""


def load_financial_pages(
    case_id: str,
    case_document_ids: Optional[list[str]] = None,
) -> list[FinancialPageSource]:
    """Pull already-extracted OCR pages for the financial documents in scope
    (stage 2 output). Reuses case_document_pages exactly as populated by the
    existing OCR pipeline — no re-OCR happens here; this stage only adds
    structured financial extraction on top of what already exists.
    """
    pages_df = case_rows(CASE_DOCUMENT_PAGES_DATASET, case_id)
    if pages_df.empty:
        return []

    if case_document_ids:
        wanted = {str(item) for item in case_document_ids}
        pages_df = pages_df[pages_df["case_document_id"].astype(str).isin(wanted)]

    names = {}
    docs_df = case_rows(CASE_DOCUMENTS_DATASET, case_id)
    if not docs_df.empty:
        for doc in docs_df.to_dict(orient="records"):
            names[str(doc.get("case_document_id", ""))] = str(doc.get("original_filename") or "")

    sources: list[FinancialPageSource] = []
    for row in pages_df.to_dict(orient="records"):
        text = str(row.get("page_text", "") or "").strip()
        if not text:
            continue
        sources.append(FinancialPageSource(
            page_id=str(row.get("page_id", "")),
            case_document_id=str(row.get("case_document_id", "")),
            page_number=int(row.get("page_number", 0) or 0),
            page_text=text,
            page_image_path=str(row.get("page_image_path", "")),
            page_image_mime_type=str(row.get("page_image_mime_type", "") or "image/png"),
            extraction_method=str(row.get("extraction_method", "") or ""),
            document_name=names.get(str(row.get("case_document_id", "")), ""),
        ))

    sources.sort(key=lambda page: (page.case_document_id, page.page_number))
    return sources


def load_document_pdf_bytes(case_id: str, case_document_id: str) -> Optional[bytes]:
    """Best-effort fetch of the original uploaded PDF, used only for the
    optional native-table corroboration pass. Returns None (not an error) if
    the document row or file can't be found — that source is simply skipped.
    """
    docs_df = case_rows(CASE_DOCUMENTS_DATASET, case_id)
    if docs_df.empty:
        return None

    matches = docs_df[docs_df["case_document_id"].astype(str) == str(case_document_id)]
    if matches.empty:
        return None

    folder_path = str(matches.iloc[0].get("folder_path", "") or "")
    if not folder_path:
        return None

    folder = dataiku.Folder(CASE_DOCUMENT_FOLDER_ID)
    try:
        with folder.get_download_stream(folder_path) as stream:
            return stream.read()
    except Exception as error:
        print(f"[financial pdf source] could not load {folder_path}: {error!r}")
        return None
