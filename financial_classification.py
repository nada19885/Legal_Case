
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import re
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
You decide whether ONE page of a legal case file contains ACCOUNTING EVIDENCE:
a genuine financial record that a forensic accountant would inspect to verify
the financial claims of the case.

Accounting records: bank / account statements, transaction histories,
account ledgers, general ledgers, balance reports, debit / credit records,
payment and transfer records or confirmations, financing and loan
statements, repayment / amortization schedules, instalment histories,
outstanding-balance records, settlement and reconciliation statements,
financial statements, balance sheets, income and cash-flow statements, trial
balances, journal entries, invoices and receipts.

NOT accounting evidence, even when they contain amounts, dates, account
numbers, IBANs, claimed balances, payments, transfers, deductions or frozen
amounts: emails, letters, internal or fraud-investigation correspondence,
statements of claim / claim forms (صحيفة دعوى), complaints, pleadings,
defence memoranda, case summaries, witness statements, narrative
explanations, legal arguments. What they say about money is a CLAIM to be
verified, not evidence.

Categories:
- "financial": the page is an accounting record.
- "mixed": the page is mainly correspondence / narrative, but a distinct
  section of it IS an accounting record (e.g. an email with a pasted account
  transaction record showing a date, an amount and a reference or balance).
  An email that only mentions an amount is NOT mixed.
- "claim": the claimant's allegations, claim form, complaint or demands.
- "other": everything else (emails, letters, decisions, forms, IDs...).

Return ONLY JSON:
{
  "page_type": "financial | mixed | claim | other",
  "financial_document_type": "bank_statement | account_statement | transaction_record | ledger | balance_sheet | income_statement | cash_flow_statement | trial_balance | journal | invoice | receipt | transfer_confirmation | loan_statement | repayment_schedule | settlement_statement | other_financial | none",
  "confidence": <0.0 to 1.0>,
  "reasoning": "<one sentence: what the page is and, for mixed, which part is the record>"
}
""".strip()

# Raise when the rules change: stored results of an older version are
# classified again.
CLASSIFIER_VERSION = "3"

# ============================================================
# ALLOWED TYPES
# ============================================================

ALLOWED_PAGE_TYPES = {"financial", "mixed", "claim", "other"}
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
# SAFEGUARD: emails and claim forms are never financial records
# ============================================================
_EMAIL_HEADER = re.compile(r"^\s*(from|to|cc|sent|date|subject|من|إلى|الموضوع|أرسل)\s*:", re.I | re.M)
_EMAIL_ADDRESS = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_CLAIM_FORM = re.compile(r"(صحيفة\s*(ال)?دعوى|statement of claim|المدعى\s*عليه|المدعي|الطلبات\s*في\s*الدعوى)")
_MONEY = re.compile(r"[0-9٠-٩][0-9٠-٩,٬]*[.٫][0-9٠-٩]{2}(?![0-9٠-٩])")
_DATE = re.compile(r"[0-9٠-٩]{1,4}[/\-.][0-9٠-٩]{1,2}[/\-.][0-9٠-٩]{1,4}")


def _record_rows(text: str) -> int:
    """Lines that look like transaction rows: a date and an amount."""
    return sum(1 for line in str(text or "").splitlines() if _DATE.search(line) and _MONEY.search(line))


def _has_record_section(text: str) -> bool:
    """Something that looks like an accounting record inside the page: a
    dated amount line, or a markdown table holding amounts."""
    text = str(text or "")
    if _record_rows(text) >= 1:
        return True
    table_lines = [line for line in text.splitlines() if line.count("|") >= 2]
    return sum(1 for line in table_lines if _MONEY.search(line)) >= 1


def non_financial_reason(text: str) -> str:
    """Why a page can never be a financial record, or "" (deterministic, so a
    model answer cannot put an email or a claim form into the accounting)."""
    text = str(text or "")
    if _record_rows(text) >= 3:
        return ""                                   # a real list of dated amounts
    if len(_EMAIL_HEADER.findall(text)) >= 2 or (_EMAIL_HEADER.search(text) and _EMAIL_ADDRESS.search(text)):
        return "email or correspondence"
    if _CLAIM_FORM.search(text):
        return "statement of claim / claim form"
    return ""


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
            "classification_status": "completed",
            "classifier_version": CLASSIFIER_VERSION,
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
        reasoning = _normalise_string(raw_result.get("reasoning", ""))
        blocked = non_financial_reason(page_text)
        if page_type == "financial" and blocked:
            # Correspondence or a claim form is never a financial record as a
            # whole; it is mixed only if a record section is really there.
            page_type = "mixed" if _has_record_section(page_text) else ("claim" if "claim" in blocked else "other")
            reasoning = f"Not a financial record as a whole ({blocked}). " + reasoning
        if page_type == "mixed" and not _has_record_section(page_text):
            page_type = "claim" if "claim" in blocked else "other"
            reasoning = "No accounting record section found on the page. " + reasoning

        return {
            "case_id": str(case_id),
            "page_id": str(page_id),
            "page_type": page_type,
            "financial_document_type": _normalise_string(raw_result.get("financial_document_type", ""))
            if page_type in ("financial", "mixed") else "none",
            "confidence": _normalise_confidence(raw_result.get("confidence", 0.0)),
            "reasoning": reasoning,
            "classification_status": "completed",
            "classifier_version": CLASSIFIER_VERSION,
        }
    except Exception as error:
        return {
            "case_id": str(case_id),
            "page_id": str(page_id),
            "page_type": SAFE_FALLBACK_PAGE_TYPE,
            "confidence": 0.0,
            "reasoning": f"Classification failed: {repr(error)}",
            "classification_status": "failed",
            "classifier_version": CLASSIFIER_VERSION,
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
        # The page's own text: a summary loses what kind of page it is
        # (an email that quotes an amount reads like a payment).
        text = row.get("page_text", "")
        if not text or str(text) == "nan":
            text = row.get("page_summary", "")
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
            latest[str(row.get("page_id", ""))] = (str(row.get("classification_status", "completed") or "completed"),
                                                   str(row.get("classifier_version", "") or ""))
        # Failed attempts and results of older classification rules are redone.
        done = {pid for pid, (status, version) in latest.items()
                if status != "failed" and version == CLASSIFIER_VERSION}
    return [str(pid) for pid in page_ids if str(pid) not in done]
