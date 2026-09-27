"""
Add these constants to the existing config.py.

This is not a standalone importable module — every financial_*.py file below
does `from .config import ...` exactly like the rest of the codebase, so
these need to live in the same config.py alongside TEXT_STRUCTURING_LLM_ID,
CASE_DOCUMENT_PAGES_DATASET, etc.
"""

# --- Accounting-analysis dataset names (stage 1-12) -------------------------
# Only the stage-3 ones (FINANCIAL_LINE_ITEMS_DATASET and
# FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET) are used by the code in this
# batch. The rest are listed here so the naming is settled up front for
# stages 4-12.
FINANCIAL_DISPUTE_QUESTIONS_DATASET = "financial_dispute_questions"
FINANCIAL_DOCUMENTS_DATASET = "financial_documents"
FINANCIAL_LINE_ITEMS_DATASET = "fin_line_items"
FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET = "fin_line_item_corr"
FINANCIAL_TIMELINE_DATASET = "financial_timeline"
FINANCIAL_POSITION_DATASET = "financial_position_snapshots"
FINANCIAL_CALCULATIONS_DATASET = "financial_calculations"
FINANCIAL_CROSS_CHECKS_DATASET = "financial_cross_checks"
FINANCIAL_DISCREPANCIES_DATASET = "financial_discrepancies"
FINANCIAL_FINDINGS_DATASET = "financial_findings"

# --- Models: reuse existing model ids, no new endpoints needed -------------
# FINANCIAL_EXTRACTION_LLM_ID is reserved for later stages (labelling native
# table cells, generating stage-1 dispute questions, stage 10/11 findings).
FINANCIAL_EXTRACTION_LLM_ID = TEXT_STRUCTURING_LLM_ID
FINANCIAL_VLM_PRIMARY_ID = FAST_OCR_VLM_ID
FINANCIAL_VLM_SECONDARY_ID = FALLBACK_OCR_VLM_ID

# --- Stage 3 execution knobs -------------------------------------------------
FINANCIAL_PAGE_MAX_WORKERS = 4
FINANCIAL_REQUEST_MAX_ATTEMPTS = 3
FINANCIAL_RETRY_DELAY_SECONDS = 2.0


# --- Dataiku datasets you need to create before running stage 3 ------------
#
# fin_line_items (managed dataset, append mode):
#   row_id, case_id, page_id, case_document_id, page_number, cluster_key,
#   fields_json, row_status, has_conflict, created_at
#
# fin_line_item_corr (managed dataset, append mode):
#   correction_id, case_id, row_id, field_name, candidates_json,
#   corrected_value, corrected_by, corrected_at, correction_note
#
# Same pattern as your existing append-only datasets (case_fact_candidates,
# audit_events, ...): create them empty in the Flow first; append_rows()
# will infer/extend the schema on first write.