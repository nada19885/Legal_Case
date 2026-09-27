"""
Accounting Analysis Workbench — orchestrates classification, extraction,
and forensic synthesis behind one call the page uses.
Location: lib/python/legal_platform/financial_workbench.py
"""

from __future__ import annotations

from .financial_classification import classify_case_pages
from .financial_extraction_pipeline import run_financial_extraction
from .financial_forensics import (
    build_full_normalized_ledger,
    run_discrepancy_and_findings_analysis,
    load_saved_forensic_results,
)
from .financial_corrections import list_rows_needing_review


def run_accounting_analysis(
    case_id: str,
    page_ids: list[str],
    actor: str = "",
    force_rerun: bool = False,
) -> dict:
    """
    1. Classify only pages not yet classified (unless force_rerun).
    2. Extract only pages not yet extracted (unless force_rerun).
    3. If step 2 appended any new rows, rebuild the full ledger and
       rerun the case-wide forensic synthesis. Otherwise, load what's
       already saved — zero LLM calls.
    """
    classifications = classify_case_pages(
        case_id, page_ids, actor=actor, force_rerun=force_rerun,
    )

    extraction_result = run_financial_extraction(
        case_id, page_ids, actor=actor, force_rerun=force_rerun,
    )

    new_rows = extraction_result.get("new_rows_appended", 0)

    if force_rerun or new_rows > 0:
        normalized_ledger = build_full_normalized_ledger(case_id)
        forensic_results = run_discrepancy_and_findings_analysis(case_id, normalized_ledger)
    else:
        forensic_results = load_saved_forensic_results(case_id)

    return {
        "case_id": case_id,
        "classifications": classifications,
        "extraction": extraction_result,
        "rows_needing_review": list_rows_needing_review(case_id),
        "forensic_results": forensic_results,
    }

