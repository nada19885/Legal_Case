
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from typing import Any

from .storage import case_rows, replace_case_rows
from .config import (
    FINANCIAL_DOCUMENT_CLASSIFICATION_DATASET,
    FINANCIAL_CLASSIFICATION_LLM_ID,
    FINANCIAL_CLASSIFICATION_MAX_PAGE_CHARS,
    FINANCIAL_CLASSIFICATION_MAX_WORKERS,
)
from .ids import random_id
from .llm import complete_json

# ============================================================
# PAGE-LEVEL CLASSIFICATION PROMPT
# ============================================================

CLASSIFY_ACCOUNTING_PAGE_PROMPT = """
You are an expert legal and forensic routing AI. Analyze the extracted text of this specific page from a legal case file.

Your job is to categorize this single page into EXACTLY ONE of the following four categories:
1. "financial" - Bank statements, transaction ledgers, receipts, invoices, or tabular financial numbers.
2. "claim" - Customer allegations, legal demands, complaints, statement of claims, or attorney arguments.
3. "mixed" - BOTH financial numbers/tables AND explicit legal claims/arguments.
4. "other" - Procedural history, cover pages, signatures, unrelated correspondence, or general non-financial/non-claim text.

Return ONLY a valid JSON object in this format:
{
  "page_type": "<financial | claim | mixed | other>",
  "confidence": <number between 0.0 and 1.0>,
  "reasoning": "<brief explanation of why>"
}
""".strip()

# ============================================================
# ALLOWED TYPES
# ============================================================

ALLOWED_PAGE_TYPES = {"financial", "claim", "mixed", "other"}
SAFE_FALLBACK_PAGE_TYPE = "other"


# ============================================================
# GENERIC HELPERS
# ============================================================

def _normalise_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()

def _normalise_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, confidence))


# ============================================================
# CLASSIFY ONE PAGE
# ============================================================

def classify_accounting_page(case_id: str, page_id: str, page_text: str) -> dict:
    """Classifies a single page using the LLM."""
    if not page_text or not str(page_text).strip():
        return {
            "case_id": str(case_id),
            "page_id": str(page_id),
            "page_type": SAFE_FALLBACK_PAGE_TYPE,
            "confidence": 1.0,
            "reasoning": "Blank page or no extracted text.",
            "classification_status": "completed"
        }

    try:
        raw_result = complete_json(
            system_prompt=CLASSIFY_ACCOUNTING_PAGE_PROMPT,
            user_payload={
                "page_text": str(page_text)[:FINANCIAL_CLASSIFICATION_MAX_PAGE_CHARS]
            },
            llm_id=FINANCIAL_CLASSIFICATION_LLM_ID,
            temperature=0.0,
        )
        
        page_type = _normalise_string(raw_result.get("page_type", "")).lower()
        if page_type not in ALLOWED_PAGE_TYPES:
            page_type = SAFE_FALLBACK_PAGE_TYPE
            
        return {
            "case_id": str(case_id),
            "page_id": str(page_id),
            "page_type": page_type,
            "confidence": _normalise_confidence(raw_result.get("confidence", 0.0)),
            "reasoning": _normalise_string(raw_result.get("reasoning", "")),
            "classification_status": "completed"
        }
    except Exception as error:
        return {
            "case_id": str(case_id),
            "page_id": str(page_id),
            "page_type": SAFE_FALLBACK_PAGE_TYPE,
            "confidence": 0.0,
            "reasoning": f"Classification failed: {repr(error)}",
            "classification_status": "failed"
        }


# ============================================================
# CLASSIFY ALL SELECTED PAGES (PARALLEL WORKERS)
# ============================================================

def classify_case_pages(case_id: str, page_ids: list[str], actor: str = "", force_rerun: bool = False) -> list[dict]:
    """Loops through the requested pages, classifies them, and saves the results in bulk."""
    if not page_ids:
        return []
        
    requested_ids = [str(x) for x in page_ids]
    
    # Load all pages to get texts
    pages_df = case_rows("case_document_pages", case_id)
    if pages_df is None or pages_df.empty:
        raise ValueError("No case_document_pages are available yet for this case.")
        
    id_col = "case_document_page_id" if "case_document_page_id" in pages_df.columns else "page_id"
    
    # Map page IDs to their extracted text
    pages_dict = {}
    for _, row in pages_df[pages_df[id_col].astype(str).isin(requested_ids)].iterrows():
        pid = str(row[id_col])
        text = row.get("page_summary", "")
        if not text or str(text) == "nan":
            text = row.get("page_text", "")
        pages_dict[pid] = text

    def process(pid: str) -> dict:
        text = pages_dict.get(pid, "")
        res = classify_accounting_page(case_id, pid, text)
        res["financial_document_classification_id"] = random_id("FDOC")
        res["created_by"] = actor
        res["created_at"] = datetime.now(timezone.utc).isoformat()
        return res

    # --------------------------------------------------------
    # Parallel execution
    # --------------------------------------------------------
    workers = max(1, min(FINANCIAL_CLASSIFICATION_MAX_WORKERS, len(requested_ids)))
    results: list[dict] = []
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process, pid) for pid in requested_ids]
        for future in as_completed(futures):
            results.append(future.result())
            
    # --------------------------------------------------------
    # Save: replace only the classifications of the pages just
    # classified, keeping every other page's stored result.
    # --------------------------------------------------------
    if results:
        classified = {str(row["page_id"]) for row in results}
        replace_case_rows(
            FINANCIAL_DOCUMENT_CLASSIFICATION_DATASET,
            case_id,
            results,
            remove_where=lambda frame: frame["page_id"].astype(str).isin(classified),
        )

    return results




def pages_needing_classification(case_id: str, page_ids: list[str]) -> list[str]:
    """Pages with no usable stored classification: never classified, or
    the last attempt failed (a failed call must be retried, not treated as
    a non-financial page)."""
    frame = case_rows(FINANCIAL_DOCUMENT_CLASSIFICATION_DATASET, case_id)
    done = set()
    if not frame.empty and "page_id" in frame.columns:
        working = frame.sort_values("created_at") if "created_at" in frame.columns else frame
        latest = {}
        for row in working.to_dict(orient="records"):
            latest[str(row.get("page_id", ""))] = str(row.get("classification_status", "completed") or "completed")
        done = {pid for pid, status in latest.items() if status != "failed"}
    return [str(pid) for pid in page_ids if str(pid) not in done]
