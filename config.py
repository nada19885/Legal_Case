"""
Central configuration for the Legal & Financial Analysis Platform.
Location: lib/python/legal_platform/config.py
"""

# =============================================================================
# 1. CORE DATASPACE & CASE DATASETS
# =============================================================================
LEGAL_NODES_DATASET = "legal_nodes"
LEGAL_RELATIONSHIPS_DATASET = "legal_relationships"
LEGAL_EMBEDDING_RECORDS_DATASET = "legal_embedding_records"
LEGAL_RESEARCH_LOG_DATASET = "legal_research_log"
RESEARCH_RUNS_DATASET = "legal_research_runs"
RESEARCH_PACKAGES_DATASET = "research_packages"

CASES_DATASET = "cases"
CASE_DOCUMENTS_DATASET = "case_documents"
CASE_MESSAGES_DATASET = "case_messages"
CASE_PARTIES_DATASET = "case_parties"
CASE_EVENTS_DATASET = "case_events"
CASE_DOCUMENT_PAGES_DATASET = "case_document_pages"
FACT_CANDIDATES_DATASET = "case_fact_candidates"
FACTS_DATASET = "case_facts"
ISSUE_CANDIDATES_DATASET = "case_issue_candidates"
ISSUES_DATASET = "case_issues"
EVIDENCE_DATASET = "case_evidence"
ISSUE_ANALYSIS_DATASET = "issue_analysis_cards"
STRATEGY_DATASET = "defence_strategy_actions"
APPROVALS_DATASET = "case_approvals"
AUDIT_DATASET = "audit_events"
AGREEMENT_STATE_DATASET = "agreement_workflow_state"
CASE_CONTRADICTIONS_DATASET = "case_contradictions"

# Dataiku Managed Folders and Knowledge Bank IDs
LEGAL_KB_ID = "0oYhnZqN"
CASE_DOCUMENT_FOLDER_ID = "CASE_DOCUMENTS"

# =============================================================================
# 2. FINANCIAL & ACCOUNTING PIPELINE DATASETS (Stages 1 - 12)
# =============================================================================
FINANCIAL_DISPUTE_QUESTIONS_DATASET = "financial_dispute_questions"
FINANCIAL_DOCUMENTS_DATASET = "financial_documents"
FINANCIAL_DOCUMENT_CLASSIFICATION_DATASET = "fin_doc_class"
FINANCIAL_LINE_ITEMS_DATASET = "fin_line_items"
FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET = "fin_line_item_corr"
FINANCIAL_TIMELINE_DATASET = "financial_timeline"
FINANCIAL_POSITION_DATASET = "financial_position_snapshots"
FINANCIAL_CALCULATIONS_DATASET = "financial_calculations"
FINANCIAL_CROSS_CHECKS_DATASET = "financial_cross_checks"
FINANCIAL_DISCREPANCIES_DATASET = "financial_discrepancies"
FINANCIAL_FINDINGS_DATASET = "financial_findings"

# Financial Classification Sampling Limits (Stage 2)
FINANCIAL_CLASSIFICATION_MAX_PAGES = 10
FINANCIAL_CLASSIFICATION_MAX_PAGE_CHARS = 1200
FINANCIAL_CLASSIFICATION_MAX_CHARS_PER_PAGE = 2000
FINANCIAL_CLASSIFICATION_MAX_TOTAL_CHARS = 40000

# =============================================================================
# 3. LLM & VLM MODEL REGISTRATION
# =============================================================================
MULTIMODAL_LLM_ID = "openai:qwen3-6-35b-a3b-fp8:qwen36-35b-a3b-fp8-1"
GENERATION_LLM_ID = "openai:Nutamix_GPU:qwen3-32b"

# Multimodal & OCR Bindings
PRIMARY_MULTIMODAL_LLM_ID = MULTIMODAL_LLM_ID
SECONDARY_MULTIMODAL_LLM_ID = MULTIMODAL_LLM_ID
FAST_OCR_VLM_ID = MULTIMODAL_LLM_ID
FALLBACK_OCR_VLM_ID = MULTIMODAL_LLM_ID

# Generation, Text & Reasoning Engine Bindings
TEXT_STRUCTURING_LLM_ID = GENERATION_LLM_ID
CHAT_LLM_ID = GENERATION_LLM_ID
EXTRACTION_LLM_ID = GENERATION_LLM_ID
PAGE_SUMMARY_LLM_ID = GENERATION_LLM_ID
CASE_MAPPING_LLM_ID = GENERATION_LLM_ID
ANALYSIS_LLM_ID = GENERATION_LLM_ID
COMPLETENESS_LLM_ID = GENERATION_LLM_ID
AGREEMENT_REVIEW_LLM_ID = GENERATION_LLM_ID
AGREEMENT_CHAT_LLM_ID = GENERATION_LLM_ID

# Financial Text/Classification Bindings
FINANCIAL_EXTRACTION_LLM_ID = GENERATION_LLM_ID
FINANCIAL_CLASSIFICATION_LLM_ID = GENERATION_LLM_ID

# =============================================================================
# 4. OCR & DOCUMENT EXTRACTION PARAMETERS
# =============================================================================
PDF_RENDER_DPI = 200

PDF_PAGE_MAX_CONCURRENT_REQUESTS = 4
# Vision calls one page may make at the same time (its views are read in
# parallel); total parallel calls are at most this x the page workers.
PAGE_READ_PARALLEL_CALLS = 2
FAST_VLM_MAX_ATTEMPTS = 1
FALLBACK_VLM_MAX_ATTEMPTS = 1
FAILED_PAGE_RECOVERY_ATTEMPTS = 1
FAILED_PAGE_RECOVERY_DELAY_SECONDS = 5.0
VLM_TEMPERATURE = 0.0

PAGE_SUMMARY_MAX_WORKERS = 4
PAGE_SUMMARY_MAX_INPUT_CHARS = 15000
PAGE_SUMMARY_MAX_ATTEMPTS = 2
PAGE_SUMMARY_RETRY_DELAY_SECONDS = 2.0

CASE_MAP_MAX_CHARS_PER_PAGE = 2000
CASE_MAP_MAX_TOTAL_CHARS = 42000

# =============================================================================
# 5. RETRIEVAL & LEGAL KNOWLEDGE BANK SETTINGS
# =============================================================================
DEFAULT_LANGUAGE = "ar"
DEFAULT_RETRIEVAL_LIMIT = 12
DEFAULT_EXPANDED_LIMIT = 40

# =============================================================================
# 6. COMPLETENESS & REVIEW PIPELINE LIMITS
# =============================================================================
COMPLETENESS_MAX_PAGE_SUMMARIES = 40
COMPLETENESS_MAX_LATEST_PAGE_SUMMARIES = 12
COMPLETENESS_MAX_SUMMARY_CHARS = 2000
COMPLETENESS_MAX_PARTIES = 30
COMPLETENESS_MAX_FACTS = 40
COMPLETENESS_MAX_ISSUES = 25
COMPLETENESS_MAX_EVENTS = 40
COMPLETENESS_MAX_EVIDENCE = 30
COMPLETENESS_MAX_DOCUMENTS = 30
COMPLETENESS_MAX_MESSAGES = 8
COMPLETENESS_MAX_MESSAGE_CHARS = 2000
COMPLETENESS_MAX_LEGAL_RESEARCH = 20
COMPLETENESS_MAX_TOTAL_CHARS = 45000

COMPLETENESS_MAX_PAGES = COMPLETENESS_MAX_PAGE_SUMMARIES
COMPLETENESS_MAX_LATEST_PAGES = COMPLETENESS_MAX_LATEST_PAGE_SUMMARIES
COMPLETENESS_MAX_CHARS_PER_PAGE = COMPLETENESS_MAX_SUMMARY_CHARS

REVIEW_BATCH_MAX_CHARS = 24000
REVIEW_MERGE_MAX_CHARS = 26000
REVIEW_MAX_BATCH_ITEMS = 30
REVIEW_REQUEST_MAX_ATTEMPTS = 2
REVIEW_RETRY_DELAY_SECONDS = 2.0
REVIEW_BATCH_MAX_WORKERS = 4
REVIEW_MERGE_MAX_ATTEMPTS = 2
REVIEW_MERGE_RETRY_DELAY_SECONDS = 2.0

# =============================================================================
# 7. AGREEMENT REVIEW WORKFLOW SETTINGS
# =============================================================================
AGREEMENT_PAGE_MAX_WORKERS = 4
AGREEMENT_CHUNK_MAX_WORKERS = 3
AGREEMENT_CLAUSE_REVIEW_MAX_WORKERS = 4
AGREEMENT_SYNTHESIS_MAX_WORKERS = 3
AGREEMENT_REQUEST_MAX_ATTEMPTS = 2
AGREEMENT_RETRY_DELAY_SECONDS = 2.0
AGREEMENT_JSON_REPAIR_MAX_ATTEMPTS = 2

# =============================================================================
# 8. FINANCIAL ANALYSIS PIPELINE (Stages 1 - 3 Execution)
# =============================================================================
FINANCIAL_DOCUMENT_TYPES = [
    "bank_statement",
    "invoice",
    "general_ledger",
    "trial_balance",
    "balance_sheet",
    "income_statement",
    "cash_flow_statement",
    "journal_entry",
    "tax_filing",
    "audit_report",
    "other_financial",
    "non_financial",
]

# Classification worker parameters & budgets (Stage 2)
FINANCIAL_CLASSIFICATION_MAX_WORKERS = 4
FINANCIAL_CLASSIFICATION_MAX_ATTEMPTS = 2
FINANCIAL_CLASSIFICATION_RETRY_DELAY_SECONDS = 2.0

# Extraction pipeline parameters (Stage 3): Stage 1a (PyMuPDF structural) +
# Stage 1b (single VLM visual pass) + Stage 2 (text-LLM reconstruction)
FINANCIAL_PAGE_MAX_WORKERS = 4
FINANCIAL_REQUEST_MAX_ATTEMPTS = 3
FINANCIAL_RETRY_DELAY_SECONDS = 2.0



