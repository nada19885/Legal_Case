"""
BSF Saudi Legal Case Workbench — Standard WebApp Backend
File: backend.py
"""

import io
import re
import json
import math
import mimetypes
import uuid
import base64
import threading
import time
import traceback
import os
import sys

import pandas as pd
from flask import request, jsonify, send_file, Response, copy_current_request_context
from dataiku.customwebapp import *  
import dataiku

# -----------------------------------------------------------------------------
# USAGE ANALYTICS & MONITORING
# -----------------------------------------------------------------------------
sys.path.insert(0, "/dataiku/design/plugins/dev/usage-analytics-lib/python-lib")
try:
    from usageanalyticslib import write_usage_event
except ImportError:
    def write_usage_event(*args, **kwargs):
        pass

PROJECT_KEY = os.environ.get("DKU_CURRENT_PROJECT_KEY", "unknown_project")
LITIGATION_PROJECT_KEY = f"{PROJECT_KEY}_LITIGATION"
AGREEMENT_PROJECT_KEY = f"{PROJECT_KEY}_AGREEMENT"

def increment_usage(session_id, field, amount=1, use_case="litigation"):
    if not session_id:
        return
    virtual_key = AGREEMENT_PROJECT_KEY if use_case == "agreement" else LITIGATION_PROJECT_KEY
    try:
        write_usage_event(virtual_key, session_id, field, amount)
    except Exception:
        pass


# -----------------------------------------------------------------------------
# CORE LEGAL PLATFORM IMPORTS
# -----------------------------------------------------------------------------
from legal_platform.intake import create_case, add_message
from legal_platform.storage import list_cases, latest_case, case_rows, replace_case_rows
from legal_platform.workflow import (
    COMPLETED,
    ERROR,
    NOT_STARTED,
    READY,
    RUNNING,
    WAITING,
    build_stage_overview,
    read_workflow_state,
    restore_workflow_state as restore_state_from_frames,
    stage_patch,
    update_workflow_state,
)
from legal_platform.files import save_upload
from legal_platform.extraction import extract_pdf_page_by_page
from legal_platform.case_mapping import build_case_map
from legal_platform.case_map_storage import persist_case_map
from legal_platform.case_register import build_case_register, prioritise_pages_for_summary
from legal_platform.facts import add_fact_candidate
from legal_platform.chat_orchestrator import assess_next_step, run_legal_analysis, run_defence_plan
from legal_platform.interview_state import persist_interview_state
from legal_platform.case_summary import generate_case_summary, approve_case_summary
from legal_platform.attorney_workbench import generate_bilingual_memo, answer_case_question, revise_bilingual_pleading
from legal_platform.audit import audit
from legal_platform.agreement_workbench import (
    AGREEMENT_TYPES, RELATIONSHIP_TYPES, classify_agreement, extract_clause_map,
    run_agreement_review, save_agreement_state, load_agreement_states,
    discuss_agreement,
)

# -----------------------------------------------------------------------------
# ACCOUNTING & FORENSIC DISPUTE ENGINE IMPORTS
# -----------------------------------------------------------------------------
from legal_platform.config import (
    FINANCIAL_DISCREPANCIES_DATASET,
    FINANCIAL_DOCUMENT_CLASSIFICATION_DATASET,
    FINANCIAL_FINDINGS_DATASET,
    FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET,
    FINANCIAL_LINE_ITEMS_DATASET,
    FINANCIAL_TIMELINE_DATASET,
    CASE_DOCUMENT_FOLDER_ID,
)
from legal_platform.financial_classification import classify_case_pages, pages_needing_classification
from legal_platform.financial_corrections import (
    build_review_items,
    load_latest_corrections,
    submit_correction,
)
from legal_platform.financial_fields import FIELD_NAMES
from legal_platform.financial_extraction_pipeline import run_financial_extraction
from legal_platform.financial_forensics import (
    build_and_save_financial_timeline,
    load_saved_forensic_results,
    run_claim_based_accounting_analysis,
)
from legal_platform.financial_normalizer import (
    build_normalized_ledger,
    normalize_amount,
    normalize_debit_credit,
)

APP_ASSETS_FOLDER_ID = "qx2RWzgX"
APP_LOGO_PATH = "logo.png"

RUN_JOBS_INLINE = False
JOBS = {}
JOBS_LOCK = threading.Lock()

# =============================================================================
# TESTING WORKFLOW BYPASS
# =============================================================================
# False = a prepared attorney summary is enough to continue downstream.
# True  = require formal attorney approval and a clean case.
# IMPORTANT: set this to True before production.
REQUIRE_APPROVED_SUMMARY = False


def approval_gate_passed(state):
    """
    Keep the real workflow dependencies while optionally bypassing formal
    attorney approval during testing.

    Testing mode (REQUIRE_APPROVED_SUMMARY = False):
        - an attorney summary must exist
        - formal approval is not required
        - case_dirty does not block downstream testing

    Production mode (REQUIRE_APPROVED_SUMMARY = True):
        - an attorney summary must exist
        - it must be formally approved
        - the case must not be dirty
    """
    if not state or state.get("attorney_summary") is None:
        return False

    if not REQUIRE_APPROVED_SUMMARY:
        return True

    return (
        bool(state.get("summary_approved"))
        and not bool(state.get("case_dirty"))
    )


# =============================================================================
# SANITIZATION HELPERS
# =============================================================================
def _clean_scalar(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return str(value)
    return value


def _json_safe(value):
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return str(value)
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (AttributeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _ok(payload):
    return jsonify(_json_safe(payload))


def frame_to_records(frame):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    return json.loads(frame.fillna("").to_json(orient="records", force_ascii=False))


# =============================================================================
# ACCOUNTING ANALYSIS HELPERS
# =============================================================================
def _page_id_column(pages_df):
    return "case_document_page_id" if "case_document_page_id" in pages_df.columns else "page_id"


def _normalized_ledger(case_id, line_items_df, corrections=None):
    """(ledger, withheld_count). Only fully reviewed rows enter the ledger."""
    if line_items_df is None or line_items_df.empty:
        return [], 0
    if corrections is None:
        corrections = load_latest_corrections(case_id)
    return build_normalized_ledger(line_items_df.to_dict(orient="records"), corrections)


def _review_items(case_id, data, corrections=None):
    """Pending accounting review items, each with the page evidence the
    user needs to answer (see financial_corrections.build_review_items)."""
    line_items = data.get("financial_line_items")
    if not isinstance(line_items, pd.DataFrame) or line_items.empty:
        return []
    if corrections is None:
        corrections = load_latest_corrections(case_id)

    pages_by_id = {}
    pages_df = data.get("pages")
    if isinstance(pages_df, pd.DataFrame) and not pages_df.empty:
        labels = _page_reference_map(data)
        id_col = _page_id_column(pages_df)
        for row in pages_df.fillna("").to_dict(orient="records"):
            page_id = str(row.get(id_col, "") or row.get("page_id", ""))
            if page_id:
                pages_by_id[page_id] = {
                    "page_text": str(row.get("page_text", "") or ""),
                    "label": labels.get(page_id, ""),
                }

    items = build_review_items(line_items.to_dict(orient="records"), corrections, pages_by_id)
    for item in items:
        item["page_image_url"] = f"/page_image?case_id={case_id}&page_id={item['page_id']}"
    return items


# =============================================================================
# CASE DATA LOADING
# =============================================================================
def load_case_data(case_id):
    data = {
        "case": latest_case(case_id) or {"case_id": case_id},
        "messages": case_rows("case_messages", case_id),
        "documents": case_rows("case_documents", case_id),
        "pages": case_rows("case_document_pages", case_id),
        "facts": case_rows("case_facts", case_id),
        "fact_candidates": case_rows("case_fact_candidates", case_id),
        "parties": case_rows("case_parties", case_id),
        "events": case_rows("case_events", case_id),
        "contradictions": case_rows("case_contradictions", case_id),
        "issues": case_rows("case_issues", case_id),
        "issue_candidates": case_rows("case_issue_candidates", case_id),
        "evidence": case_rows("case_evidence", case_id),
        "approvals": case_rows("case_approvals", case_id),
        "audit_events": case_rows("audit_events", case_id),
        "financial_line_items": case_rows(FINANCIAL_LINE_ITEMS_DATASET, case_id),
        "financial_classifications": case_rows(FINANCIAL_DOCUMENT_CLASSIFICATION_DATASET, case_id),
    }

    forensic = load_saved_forensic_results(case_id)
    data["financial_timeline"] = forensic.get("timeline", [])
    data["forensic_findings"] = {"claim_evaluations": forensic.get("claim_evaluations", [])}
    data["forensic_run_metadata"] = forensic.get("run_metadata", {})
    data["discrepancies"] = forensic.get("discrepancies", [])
    data["cross_check_summary"] = forensic.get("cross_check_summary", {})

    return data


def _latest_classifications_by_page(data):
    frame = data.get("financial_classifications")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {}
    working = frame.sort_values("created_at") if "created_at" in frame.columns else frame
    latest = {}
    for row in working.fillna("").to_dict(orient="records"):
        page_id = str(row.get("page_id", "") or row.get("case_document_page_id", ""))
        if not page_id:
            continue
        latest[page_id] = {
            "page_type": str(row.get("page_type", "") or row.get("document_type", "")).lower().strip(),
            "confidence": _clean_scalar(row.get("confidence")),
            "status": str(row.get("classification_status", "") or "completed"),
        }
    return latest


def best(data, approved_key, candidate_key):
    return data[approved_key] if not data[approved_key].empty else data[candidate_key]


# =============================================================================
# PERSISTENCE & WORKFLOW STATE
#
# State lives in legal_platform.workflow: every update is merged into the
# latest stored state (append-only, one audit row per update) so parallel
# jobs keep each other's results. Routes pass only the keys they change.
# =============================================================================
def restore_workflow_state(data):
    return restore_state_from_frames(data.get("audit_events"), data.get("approvals"))


def invalidation_changes(reason):
    """State changes applied when new material arrives. Generated content
    (review, analysis, pleading...) is kept and shown as stale; formal
    approval is revoked so nothing proceeds on an outdated sign-off."""
    return {
        "case_dirty": True,
        "dirty_reason": reason,
        "accounting_dirty": True,
        "accounting_dirty_reason": reason,
        "summary_approved": False,
        "summary_approved_by": "",
    }


def accounting_state(data, state, review_items=None):
    """
    Current accounting stage from the explicit workflow state plus the
    persisted accounting data.

    An accounting run may legitimately produce zero financial line items,
    so presence of line items must NOT be used as the completion flag —
    accounting_status (set explicitly by the /accounting/* routes below)
    is the single source of truth for "what stage are we at". Pending
    review items always win: while any exist the stage waits for the user.
    """
    status = str(state.get("accounting_status", "not_started") or "not_started").strip().lower()

    line_items = data.get("financial_line_items")
    has_line_items = isinstance(line_items, pd.DataFrame) and not line_items.empty

    classifications = data.get("financial_classifications")
    has_classifications = isinstance(classifications, pd.DataFrame) and not classifications.empty

    if review_items is None:
        review_items = _review_items(str(data["case"].get("case_id", "")), data)
    pending_count = len(review_items)

    findings = data.get("forensic_findings") or {}
    has_forensic_output = bool(findings.get("claim_evaluations") or data.get("discrepancies"))

    return {
        "status": status,
        "dirty": bool(state.get("accounting_dirty")),
        "dirty_reason": state.get("accounting_dirty_reason", ""),
        "has_classifications": has_classifications,
        "has_line_items": has_line_items,
        "has_pending_review": bool(pending_count),
        "pending_count": pending_count,
        "pending_field_count": sum(len(item.get("fields") or []) for item in review_items),
        "has_forensic_output": has_forensic_output,
    }


def stage_overview(case_id, state, data, accounting=None, register=None):
    """What every stage is doing: stored results + stage records + live jobs."""
    if accounting is None:
        accounting = accounting_state(data, state)
    if register is None:
        register = case_register(data)
    return build_stage_overview({
        "has_documents": not data["documents"].empty and not data["pages"].empty,
        "has_summary": state.get("attorney_summary") is not None,
        "gate_passed": approval_gate_passed(state),
        "case_dirty": bool(state.get("case_dirty")),
        "has_analysis": state.get("analysis") is not None,
        "has_memo": state.get("memo") is not None,
        "pleading_status": state.get("pleading_status", "draft"),
        "accounting": accounting,
        "stages": state.get("stages") or {},
        "active_jobs": _active_jobs(case_id),
        "register_fingerprint": register.get("fingerprint"),
    })


def _party_rank(role):
    text = str(role or "").lower()
    priorities = [
        (0, ("claimant", "plaintiff", "applicant", "مدعي", "طالب")),
        (1, ("defendant", "respondent", "مدعى عليه", "مدعى عليها")),
        (2, ("appellant", "مستأنف")),
        (3, ("bank", "بنك", "مصرف")),
    ]
    for rank, words in priorities:
        if any(word in text for word in words):
            return rank
    return 99


def _ordered_parties(items):
    return sorted(
        list(items or []),
        key=lambda item: (_party_rank(item.get("role")), str(item.get("name", "")).lower()),
    )


def _chronology_key(item):
    raw = str(item.get("date", "") or "").strip()
    if not raw or str(item.get("date_precision", "")).lower() == "unknown":
        return (1, "9999-99-99", raw)
    return (0, raw.replace("/", "-"), raw)


def _ordered_chronology(items):
    return sorted(list(items or []), key=_chronology_key)


def _page_reference_map(data):
    documents = {}
    doc_frame = data.get("documents")
    if isinstance(doc_frame, pd.DataFrame) and not doc_frame.empty:
        for _, row in doc_frame.fillna("").iterrows():
            doc_id = str(row.get("case_document_id", "") or row.get("document_id", "") or "")
            filename = str(row.get("original_filename", "") or row.get("file_name", "") or "Document")
            if doc_id:
                documents[doc_id] = filename

    mapping = {}
    page_frame = data.get("pages")
    if isinstance(page_frame, pd.DataFrame) and not page_frame.empty:
        for _, row in page_frame.fillna("").iterrows():
            page_id = str(row.get("case_document_page_id", "") or row.get("page_id", "") or "")
            doc_id = str(row.get("case_document_id", "") or row.get("document_id", "") or "")
            page_number = row.get("page_number", "")
            filename = documents.get(doc_id, str(row.get("original_filename", "") or "Document"))
            label = f"{filename} — page {page_number}" if page_number != "" else filename
            if page_id:
                mapping[page_id] = label
    return mapping


def _page_labels(source_ids, data):
    mapping = _page_reference_map(data)
    labels = []
    for source_id in source_ids or []:
        value = str(source_id or "").strip()
        if not value:
            continue
        label = mapping.get(value, f"Page {value[:6]}")
        if label not in labels:
            labels.append(label)
    return labels


def case_register(data):
    """The unified case register (see legal_platform.case_register): one
    consolidated view of parties, events, facts, issues, evidence requests
    and contradictions across every processed document."""
    return build_case_register(data, _page_reference_map(data))


def short_case_reference(case_id):
    raw = re.sub(r"[^A-Za-z0-9]", "", str(case_id or ""))
    suffix = raw[-6:].upper() if raw else "------"
    return f"CASE-{suffix}"


def first_case_value(row, *columns, default="—"):
    for column in columns:
        value = row.get(column, "")
        if value is not None and str(value).strip() and str(value).lower() != "nan":
            return str(value).strip()
    return default


def case_search_frame(cases, query):
    if cases.empty or not query.strip():
        return cases
    needle = query.strip().casefold()
    searchable = [
        "case_name", "client_name", "customer_name", "matter_type",
        "responsible_attorney", "created_by", "case_id", "case_status",
    ]
    mask = pd.Series(False, index=cases.index)
    for column in searchable:
        if column in cases.columns:
            mask = mask | cases[column].fillna("").astype(str).str.casefold().str.contains(needle, regex=False)
    if "case_id" in cases.columns:
        references = cases["case_id"].fillna("").astype(str).map(short_case_reference).str.casefold()
        mask = mask | references.str.contains(needle, regex=False)
    return cases[mask]


def filter_cases_by_workflow(cases, workflow_type):
    if cases.empty:
        return cases
    frame = cases.copy()
    if "workflow_type" not in frame.columns:
        return frame if workflow_type == "litigation" else frame.iloc[0:0]
    values = frame["workflow_type"].fillna("").astype(str).str.strip().str.lower()
    if workflow_type == "litigation":
        return frame[(values == "") | (values == "litigation")]
    return frame[values == "agreement_review"]


def serialise_case_card(item, workflow_type):
    case_id = str(item.get("case_id", ""))
    activity = first_case_value(item, "updated_at", "created_at", default="—")
    if "T" in activity:
        activity = activity.replace("T", " ")[:16]
    status = first_case_value(item, "workflow_status", "case_status", default="")
    return {
        "case_id": case_id,
        "reference": short_case_reference(case_id),
        "title": first_case_value(item, "case_name", "client_name", "customer_name", default=""),
        "matter": first_case_value(item, "matter_type", default=""),
        "attorney": first_case_value(item, "responsible_attorney", "created_by", default=""),
        "activity": activity,
        "status": status,
        "workflow_type": workflow_type,
    }


def serialise_summary_support(summary, data):
    """Preserves exactly what the LLM generated into standard arrays."""
    if not isinstance(summary, dict):
        return {}

    chronology_list = summary.get("chronology") or []
    parties_list = summary.get("parties") or []

    evidence_list = []
    for item in summary.get("available_evidence", []) or []:
        if isinstance(item, dict):
            page_ids = item.get("source_page_ids", []) or item.get("page_ids", []) or []
            evidence_list.append({"item": item, "page_ids": page_ids, "page_labels": _page_labels(page_ids, data)})

    contradictions_list = []
    contradictions_frame = data.get("contradictions")
    if isinstance(contradictions_frame, pd.DataFrame) and not contradictions_frame.empty:
        for row in contradictions_frame.fillna("").to_dict(orient="records"):
            try:
                source_page_ids = json.loads(row.get("source_page_ids_json", "[]") or "[]")
                if not isinstance(source_page_ids, list):
                    source_page_ids = []
            except (TypeError, json.JSONDecodeError):
                source_page_ids = []
            contradictions_list.append({
                "description": row.get("description", ""),
                "clarification_required": row.get("clarification_required", ""),
                "source_page_ids": source_page_ids,
                "page_labels": _page_labels(source_page_ids, data),
            })

    return {
        "ordered_parties": _ordered_parties(parties_list),
        "ordered_chronology": [
            {"item": item, "page_labels": _page_labels(item.get("source_page_ids", []), data)}
            for item in _ordered_chronology(chronology_list)
        ],
        "ordered_evidence": evidence_list,
        "contradictions": contradictions_list,
    }

def memo_to_markdown(memo, language):
    if not isinstance(memo, dict):
        return str(memo or "")
    section = memo.get("pleading_ar" if language == "ar" else "pleading_en", {})
    if isinstance(section, str):
        return section

    title = memo.get("title_ar" if language == "ar" else "title_en", "")
    filing_type = memo.get("filing_type_ar" if language == "ar" else "filing_type_en", "")
    is_ar = language == "ar"
    lines = []

    if is_ar and section.get("basmala"):
        lines.append(section.get("basmala"))
    if filing_type:
        lines.append(f"# {filing_type}")
    if title:
        lines.append(f"## {title}")

    for key in ("court_heading", "case_details", "party_heading", "subject", "formal_salutation", "opening"):
        value = section.get(key, "")
        if value:
            lines.append(str(value))

    def _fmt(sec):
        if isinstance(sec, str): return sec
        if isinstance(sec, list):
            res = []
            for it in sec:
                if isinstance(it, dict):
                    d = it.get("date", "")
                    f = it.get("fact") or it.get("supported_fact") or it.get("text", "")
                    prefix = f"**{d}:** " if d else "- "
                    res.append(f"{prefix}{f}")
                else:
                    res.append(f"- {str(it)}")
            return "\n".join(res)
        return str(sec or "")

    if section.get("facts"):
        lines.append("## أولاً: الوقائع وتتبع حركة الأموال" if is_ar else "## I. Statement of Facts & Fund Flows")
        lines.append(_fmt(section.get("facts")))
    if section.get("procedural_defences"):
        lines.append("## ثانياً: الدفوع الشكلية والإجرائية" if is_ar else "## II. Procedural Defences")
        lines.append(_fmt(section.get("procedural_defences")))
    if section.get("substantive_defences"):
        lines.append("## ثالثاً: الدفوع الموضوعية والنظامية" if is_ar else "## III. Substantive Defences")
        lines.append(_fmt(section.get("substantive_defences")))
    if section.get("response_to_opponent"):
        lines.append("## رابعاً: الرد على ادعاءات الخصم" if is_ar else "## IV. Response to Opposing Party")
        lines.append(_fmt(section.get("response_to_opponent")))
    if section.get("requests"):
        lines.append("## خامساً: الطلبات الختامية" if is_ar else "## V. Relief Requested")
        lines.append(_fmt(section.get("requests")))
    if section.get("closing"):
        lines.append(section.get("closing"))
    if section.get("signature_block"):
        lines.append(section.get("signature_block"))

    return "\n\n".join(lines)


def build_pleading_docx_bytes(memo, case_reference=""):
    from io import BytesIO
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement

    def _set_rtl(paragraph):
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_pr = paragraph._p.get_or_add_pPr()
        bidi = OxmlElement("w:bidi")
        p_pr.append(bidi)

    def _add_markdown_text(document, markdown_text, rtl=False):
        for raw_line in str(markdown_text or "").split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("### "):
                paragraph = document.add_heading(line[4:], level=3)
            elif line.startswith("## "):
                paragraph = document.add_heading(line[3:], level=2)
            elif line.startswith("# "):
                paragraph = document.add_heading(line[2:], level=1)
            else:
                paragraph = document.add_paragraph(line)
            if rtl:
                _set_rtl(paragraph)

    document = Document()
    if case_reference:
        title_paragraph = document.add_paragraph(case_reference)
        title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_markdown_text(document, memo_to_markdown(memo, "ar"), rtl=True)
    document.add_page_break()
    _add_markdown_text(document, memo_to_markdown(memo, "en"), rtl=False)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _load_app_logo_data_uri():
    try:
        folder = dataiku.Folder(APP_ASSETS_FOLDER_ID)
        with folder.get_download_stream(APP_LOGO_PATH) as stream:
            raw = stream.read()
        return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    except Exception:
        return ""


def _load_page_image_bytes(page_image_path):
    if not page_image_path:
        return None
    try:
        folder = dataiku.Folder(CASE_DOCUMENT_FOLDER_ID)
        with folder.get_download_stream(page_image_path) as stream:
            return stream.read()
    except Exception:
        return None


def _page_row(data, page_id):
    pages = data.get("pages")
    if not isinstance(pages, pd.DataFrame) or pages.empty:
        return None
    id_column = "case_document_page_id" if "case_document_page_id" in pages.columns else "page_id"
    if id_column not in pages.columns:
        return None
    match = pages[pages[id_column].astype(str) == str(page_id)]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


def serialise_facts_register(data):
    facts_register = best(data, "facts", "fact_candidates")
    rows = []
    if not isinstance(facts_register, pd.DataFrame) or facts_register.empty:
        return rows
    pages_frame = data.get("pages")
    for _, row in facts_register.fillna("").iterrows():
        fact_text = str(row.get("fact_text", ""))
        if not fact_text:
            continue
        fact_id = str(row.get("fact_id", "") or row.get("fact_candidate_id", ""))

        try:
            page_ids = json.loads(row.get("source_page_ids_json", "[]") or "[]")
            if not isinstance(page_ids, list):
                page_ids = []
        except (TypeError, json.JSONDecodeError):
            page_ids = []

        if not page_ids and str(row.get("page_number", "")).strip() and isinstance(pages_frame, pd.DataFrame) and not pages_frame.empty:
            doc_col = "case_document_id" if "case_document_id" in pages_frame.columns else None
            if doc_col and str(row.get("case_document_id", "")).strip():
                match = pages_frame[
                    (pages_frame[doc_col].astype(str) == str(row.get("case_document_id", "")))
                    & (pages_frame["page_number"].astype(str) == str(row.get("page_number", "")))
                ]
                id_col = "case_document_page_id" if "case_document_page_id" in pages_frame.columns else "page_id"
                if not match.empty and id_col in match.columns:
                    page_ids = [str(match.iloc[0][id_col])]

        rows.append({
            "fact_id": fact_id,
            "fact_text": fact_text,
            "confidence": _clean_scalar(row.get("confidence")),
            "source_type": str(row.get("source_type", "") or ""),
            "verification_status": str(row.get("verification_status", "") or row.get("candidate_status", "") or ""),
            "page_ids": page_ids,
            "page_labels": _page_labels(page_ids, data),
        })
    return rows

def serialise_chat_messages(data):
    messages = data.get("messages")
    out = []
    if isinstance(messages, pd.DataFrame) and not messages.empty:
        frame = messages.copy()
        if "created_at" in frame.columns:
            frame = frame.sort_values("created_at")
        for _, row in frame.iterrows():
            role = str(row.get("role", ""))
            if role in {"user", "assistant"}:
                out.append({"role": role, "content": str(row.get("message_text", ""))})
    return out


# =============================================================================
# ASYNC JOB COORDINATOR
#
# Jobs are registered per case and stage so any browser session (or a
# reload) can find the job that is running for a case and resume showing
# its progress. Finished jobs stay readable for FINISHED_JOB_TTL_SECONDS.
# A stage job also records its lifecycle in the workflow state: running
# when it starts, error with the message when it fails, and completed
# when it succeeds (unless the task already set a more precise outcome,
# e.g. waiting for the user).
# =============================================================================
FINISHED_JOB_TTL_SECONDS = 15 * 60


def _prune_jobs():
    now = time.time()
    with JOBS_LOCK:
        for job_id in [
            key for key, job in JOBS.items()
            if job.get("finished_at") and now - job["finished_at"] > FINISHED_JOB_TTL_SECONDS
        ]:
            JOBS.pop(job_id, None)


def _new_job(case_id="", stage=""):
    _prune_jobs()
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "case_id": str(case_id or ""),
            "stage": stage,
            "progress": {"stage": stage, "phase": "", "current": 0, "total": 0, "detail": ""},
            "result": None,
            "error": None,
            "finished_at": None,
        }
    return job_id


def _set_progress(job_id, **kwargs):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job:
            job["progress"].update(kwargs)


def _finish_job(job_id, result=None, error=None):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        if error is not None:
            job["status"] = "error"
            job["error"] = error
        else:
            job["status"] = "done"
            job["result"] = result
        job["finished_at"] = time.time()


def _active_jobs(case_id):
    """{stage: {job_id, progress}} for jobs still running on this case."""
    active = {}
    with JOBS_LOCK:
        for job_id, job in JOBS.items():
            if job["status"] == "running" and job.get("case_id") == str(case_id) and job.get("stage"):
                active[job["stage"]] = {"job_id": job_id, "progress": dict(job["progress"])}
    return active


def _run_job(job_id, target, session_id=None, use_case="litigation"):
    try:
        result = target()
        _finish_job(job_id, result=result)
    except Exception as error:
        traceback.print_exc()
        if session_id:
            increment_usage(session_id, "error_count", 1, use_case=use_case)
        _finish_job(job_id, error=f"{type(error).__name__}: {error}")


def _run_async(job_id, target, session_id=None, use_case="litigation"):
    if RUN_JOBS_INLINE:
        _run_job(job_id, target, session_id=session_id, use_case=use_case)
        return

    @copy_current_request_context
    def _thread_target():
        _run_job(job_id, target, session_id=session_id, use_case=use_case)

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()


def _set_phase(job_id, phase, detail="", current=0, total=0):
    _set_progress(job_id, phase=phase, detail=detail, current=current, total=total)


def _start_stage_job(case_id, stage, phase, detail, task, session_id=None, use_case="litigation"):
    """Run task(job_id) in the background as the given workflow stage.

    Returns a Flask response carrying the job id. If a job for this stage
    is already running on the case, its id is returned instead of starting
    a duplicate, so a double click or a second browser tab simply follows
    the existing job.
    """
    existing = _active_jobs(case_id).get(stage)
    if existing:
        return jsonify({"job_id": existing["job_id"], "already_running": True})

    job_id = _new_job(case_id, stage)
    _set_phase(job_id, phase, detail)
    update_workflow_state(
        case_id,
        stages={stage: stage_patch(RUNNING, phase=phase, detail=detail, job_id=job_id)},
        action=f"{stage}_started",
    )

    def _wrapped():
        try:
            result = task(job_id)
        except Exception as error:
            with JOBS_LOCK:
                failed_phase = (JOBS.get(job_id) or {}).get("progress", {}).get("phase", phase)
            try:
                update_workflow_state(
                    case_id,
                    stages={stage: stage_patch(ERROR, phase=failed_phase, error=f"{type(error).__name__}: {error}")},
                    action=f"{stage}_failed",
                )
            except Exception:
                traceback.print_exc()
            raise

        record = (read_workflow_state(case_id).get("stages") or {}).get(stage) or {}
        if record.get("status") == RUNNING and record.get("job_id") == job_id:
            update_workflow_state(case_id, stages={stage: stage_patch(COMPLETED)}, action=f"{stage}_completed")
        return result

    _run_async(job_id, _wrapped, session_id=session_id, use_case=use_case)
    return jsonify({"job_id": job_id})


@app.route("/job_status")
def job_status():
    job_id = request.args.get("job_id", "")
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"status": "unknown"}), 404
        payload = {
            "status": job["status"],
            "stage": job.get("stage", ""),
            "progress": dict(job["progress"]),
            "error": job["error"],
        }
        if job["status"] == "done":
            payload["result"] = job["result"]
    return _ok(payload)


@app.route("/diagnostics")
def diagnostics():
    case_id = request.args.get("case_id", "")
    if not case_id:
        return jsonify({"error": "case_id is required"}), 400
    data = load_case_data(case_id)
    counts = {}
    for key, frame in data.items():
        if isinstance(frame, pd.DataFrame):
            counts[key] = int(len(frame))
        elif isinstance(frame, dict):
            counts[key] = len(frame)
    state = restore_workflow_state(data)
    return _ok({
        "case_id": case_id,
        "row_counts": counts,
        "extraction_reached_facts": bool(counts.get("facts", 0) or counts.get("fact_candidates", 0)),
        "workflow": {
            "has_attorney_summary": bool(state.get("attorney_summary")),
            "summary_approved": bool(state.get("summary_approved")),
            "has_analysis": bool(state.get("analysis")),
            "has_memo": bool(state.get("memo")),
            "case_dirty": bool(state.get("case_dirty")),
            "dirty_reason": state.get("dirty_reason", ""),
            "stages": state.get("stages") or {},
        },
        "run_jobs_inline": RUN_JOBS_INLINE,
    })


# =============================================================================
# FLASK APPLICATION ROUTES
# =============================================================================
@app.route("/bootstrap")
def bootstrap():
    return jsonify({
        "logo": _load_app_logo_data_uri(),
        "agreement_types": list(AGREEMENT_TYPES),
        "relationship_types": list(RELATIONSHIP_TYPES),
    })


@app.route("/cases")
def cases_endpoint():
    workflow = request.args.get("workflow", "litigation")
    query = request.args.get("query", "")
    cases = list_cases()
    filtered = filter_cases_by_workflow(cases, workflow)
    filtered = case_search_frame(filtered, query)
    if "updated_at" in filtered.columns:
        filtered = filtered.sort_values("updated_at", ascending=False)
    cards = [serialise_case_card(row, workflow) for row in frame_to_records(filtered)]
    return _ok({"cases": cards})


@app.route("/create_case", methods=["POST"])
def create_case_endpoint():
    body = request.get_json(force=True)
    case_name = str(body.get("case_name", "")).strip()
    language = body.get("language", "en")
    workflow_type = body.get("workflow_type", "litigation")
    if not case_name:
        return jsonify({"error": "case_name is required"}), 400
    case_id = create_case(
        case_name=case_name,
        intake_mode="mixed",
        language=language,
        workflow_type=workflow_type,
    )
    return jsonify({"case_id": case_id})



@app.route("/case")
def case_endpoint():
    case_id = request.args.get("case_id", "")
    if not case_id:
        return jsonify({"error": "case_id is required"}), 400
    data = load_case_data(case_id)
    case = data["case"]
    workflow_type = str(case.get("workflow_type", "") or "").strip() or "litigation"

    response = {
        "case_id": case_id,
        "reference": short_case_reference(case_id),
        "workflow_type": workflow_type,
        "case": {k: _clean_scalar(v) for k, v in case.items()},
        "display_name": first_case_value(case, "client_name", "customer_name", "case_name", default=""),
        "counts": {
            "documents": int(len(data["documents"])),
            "pages": int(len(data["pages"])),
            "facts": int(len(best(data, "facts", "fact_candidates"))),
            "parties": int(len(data["parties"])),
            "issues": int(len(best(data, "issues", "issue_candidates"))),
        },
    }

    if workflow_type == "agreement_review":
        stored = load_agreement_states(case_id)
        response["agreement_state"] = {
            "classification": stored.get("classification"),
            "profile": stored.get("confirmed_profile"),
            "clause_map": stored.get("clause_map"),
            "authorities": stored.get("authorities"),
            "review": stored.get("review"),
        }
        return _ok(response)

    state = restore_workflow_state(data)
    corrections = load_latest_corrections(case_id)
    review_items = _review_items(case_id, data, corrections)
    accounting_meta = accounting_state(data, state, review_items)
    register = case_register(data)
    overview = stage_overview(case_id, state, data, accounting_meta, register)

    response["workflow_state"] = state
    response["stages"] = overview["stages"]
    response["waiting"] = overview["waiting"]
    response["running"] = overview["running"]
    response["errors"] = overview["errors"]
    response["next_stage"] = overview["next_stage"]
    # Legacy names kept for callers that still read them.
    response["steps"] = overview["stages"]
    response["next_action_key"] = overview["next_stage"]

    response["chat_messages"] = serialise_chat_messages(data)
    response["case_register"] = register
    response["facts_register"] = serialise_facts_register(data)
    response["summary_support"] = serialise_summary_support(state.get("attorney_summary") or {}, data)

    ledger, withheld = _normalized_ledger(case_id, data["financial_line_items"], corrections)
    classifications = _latest_classifications_by_page(data)
    accounting_record = (state.get("stages") or {}).get("accounting") or {}
    response["accounting"] = {
        "status": accounting_meta["status"],
        "dirty": accounting_meta["dirty"],
        "dirty_reason": accounting_meta["dirty_reason"],
        "has_classifications": accounting_meta["has_classifications"],
        "has_line_items": accounting_meta["has_line_items"],
        "has_pending_review": accounting_meta["has_pending_review"],
        "pending_count": accounting_meta["pending_count"],
        "pending_field_count": accounting_meta["pending_field_count"],
        "documents": [
            {
                "case_document_id": str(row.get("case_document_id", "")),
                "original_filename": row.get("original_filename") or row.get("case_document_id", ""),
                "classification": {},
            }
            for row in frame_to_records(data["documents"])
        ],
        "page_classification_counts": _classification_counts(classifications),
        "last_run_report": accounting_record.get("report") or {},
        "review_items": review_items,
        "pending_conflicts": review_items,
        "normalized_ledger": ledger,
        "withheld_rows": withheld,
        "instructions": state.get("accounting_instructions", ""),
        "run_metadata": data.get("forensic_run_metadata") or {},
        "cross_check_summary": data.get("cross_check_summary") or {},
        "discrepancies": data.get("discrepancies") or [],
        "findings": _claims_with_evidence(data.get("forensic_findings"), ledger, data),
    }
    return _ok(response)


CLAIM_RESULT_ORDER = (
    "CONTRADICTED", "PARTIALLY_SUPPORTED", "SUPPORTED",
    "NOT_VERIFIABLE", "NO_FINANCIAL_EVIDENCE", "NOT_FINANCIAL_CLAIM",
)


def _claims_with_evidence(findings, ledger, data):
    """Claim evaluations with every cited ledger row resolved to its date,
    amount, reference and source page, so each finding can be checked
    against the statement it relies on.

    A cited id that is no longer in the ledger (it was cleared or
    re-extracted after the analysis ran) is listed separately rather
    than silently dropped."""
    by_id = {str(entry.get("row_id")): entry for entry in ledger}
    labels = _page_reference_map(data)

    def resolve(ids):
        rows, missing = [], []
        for record_id in ids or []:
            entry = by_id.get(str(record_id))
            if entry is None:
                missing.append(str(record_id))
                continue
            rows.append({
                "row_id": entry.get("row_id"),
                "date": entry.get("date"),
                "amount": entry.get("amount"),
                "currency": entry.get("currency"),
                "debit_or_credit": entry.get("debit_or_credit"),
                "reference_number": entry.get("reference_number", ""),
                "description": entry.get("description", ""),
                "page_id": entry.get("page_id", ""),
                "page_label": labels.get(str(entry.get("page_id", "")), ""),
            })
        return rows, missing

    evaluations = []
    counts = {}
    for raw in (findings or {}).get("claim_evaluations") or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        ids = list(item.get("evidence_record_ids") or [])
        for found in item.get("financial_evidence_found") or []:
            if isinstance(found, dict) and found.get("record_id") and str(found["record_id"]) not in ids:
                ids.append(str(found["record_id"]))
        item["evidence_rows"], stale = resolve(ids)
        contradictions = []
        for entry in item.get("contradictions") or []:
            if isinstance(entry, dict):
                entry = dict(entry)
                entry["rows"], more_stale = resolve(entry.get("record_ids"))
                stale.extend(more_stale)
                contradictions.append(entry)
            elif str(entry or "").strip():
                contradictions.append({"description": str(entry), "record_ids": [], "rows": []})
        item["contradictions"] = contradictions
        item["missing_evidence"] = [str(x) for x in (item.get("missing_evidence") or []) if str(x).strip()]
        item["no_longer_in_ledger"] = list(dict.fromkeys(stale))
        result = str(item.get("result") or "NOT_VERIFIABLE").upper()
        counts[result] = counts.get(result, 0) + 1
        evaluations.append(item)

    rank = {result: position for position, result in enumerate(CLAIM_RESULT_ORDER)}
    evaluations.sort(key=lambda item: rank.get(str(item.get("result") or "").upper(), len(rank)))
    return {"claim_evaluations": evaluations, "result_counts": counts}


def _classification_counts(classifications):
    counts = {}
    for item in classifications.values():
        key = "failed" if item.get("status") == "failed" else (item.get("page_type") or "other")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _load_state(case_id):
    data = load_case_data(case_id)
    return data, restore_workflow_state(data)


@app.route("/state/persist", methods=["POST"])
def state_persist():
    """Merge the given workflow keys into the stored state. Only keys the
    caller sends are touched; stage records are managed by the server."""
    body = request.get_json(force=True)
    case_id = str(body.get("case_id", ""))
    state = body.get("state", {})
    if not case_id or not isinstance(state, dict):
        return jsonify({"error": "case_id and a state object are required"}), 400
    changes = {key: value for key, value in state.items() if key != "stages"}
    update_workflow_state(case_id, changes=changes, action="ui_state_saved")
    return _ok({"persisted": True})


# =============================================================================
# INGESTION & DOCUMENT PROCESSING
# =============================================================================
class _MemoryUpload:
    def __init__(self, name, raw, content_type=""):
        self.name = name
        self.type = content_type or mimetypes.guess_type(name or "")[0] or "application/octet-stream"
        self.size = len(raw or b"")
        self.id = uuid.uuid4().hex
        self.file_id = self.id
        self._raw = raw
        self._buffer = io.BytesIO(raw)

    def read(self, *args, **kwargs): return self._buffer.read(*args, **kwargs)
    def seek(self, *args, **kwargs): return self._buffer.seek(*args, **kwargs)
    def tell(self): return self._buffer.tell()
    def getvalue(self): return self._raw
    def getbuffer(self): return self._buffer.getbuffer()
    def close(self): self._buffer.close()


@app.route("/documents/process", methods=["POST"])
def documents_process():
    """Stage "documents": pages -> images -> OCR -> page summaries ->
    parties / events / facts / issues / evidence merged into the case
    register. New material marks downstream work stale."""
    case_id = request.form.get("case_id", "")
    file_purpose = request.form.get("file_purpose", "full_case")
    session_id = request.form.get("session_id")
    render_zoom = 1.6
    uploaded = request.files.getlist("files")
    payloads = [(f.filename, f.read(), f.mimetype) for f in uploaded]
    if not case_id or not payloads:
        return jsonify({"error": "case_id and at least one file are required"}), 400

    def task(job_id):
        total_pages, usable_pages = 0, 0
        totals = {"facts": 0, "issues": 0, "parties": 0, "events": 0, "evidence_requests": 0}
        status_counts, failure_notes = {}, []
        llm_call_count = 0

        for file_index, (name, raw, content_type) in enumerate(payloads, start=1):
            _set_phase(job_id, "extracting_pages", f"{name} ({file_index}/{len(payloads)}): rendering pages…")
            document_row, pdf_bytes = save_upload(
                case_id, _MemoryUpload(name, raw, content_type), document_type=file_purpose
            )
            def update_progress(current, total, page_number, state, _name=name):
                _set_phase(job_id, "extracting_pages",
                           f"{_name}: page {page_number}/{total} — {state}", current=current, total=total)
            pages = extract_pdf_page_by_page(
                case_id=case_id,
                case_document_id=document_row["case_document_id"],
                pdf_bytes=pdf_bytes,
                zoom=render_zoom,
                progress_callback=update_progress,
            )
            llm_call_count += len(pages)
            completed_pages = [p for p in pages if p.get("processing_status") in {"completed", "completed_review_required"}]
            for page in pages:
                page_status = str(page.get("processing_status", "") or "unknown")
                status_counts[page_status] = status_counts.get(page_status, 0) + 1
                if page_status in {"completed", "completed_review_required"}:
                    continue
                for note_key in ("processing_error", "error", "processing_note", "note", "failure_reason"):
                    if page.get(note_key):
                        note = str(page[note_key])[:300]
                        if note not in failure_notes:
                            failure_notes.append(note)
                        break

            total_pages += len(pages)
            usable_pages += len(completed_pages)
            if completed_pages:
                _set_phase(job_id, "building_case_register", f"{name}: extracting parties, events, facts and issues…")
                case_map = build_case_map(completed_pages)
                llm_call_count += 1
                counts = persist_case_map(case_id, case_map)
                for key in totals:
                    totals[key] += int(counts.get(key, 0) or 0)

        if llm_call_count:
            increment_usage(session_id, "llm_request_count", llm_call_count)
        increment_usage(session_id, "attachment_count", len(payloads))

        report = {
            "files": len(payloads),
            "usable": usable_pages,
            "total": total_pages,
            "page_status": status_counts,
            "page_errors": failure_notes[:3],
            **totals,
        }
        failed = total_pages - usable_pages
        update_workflow_state(
            case_id,
            changes=invalidation_changes("New document or evidence was uploaded."),
            stages={"documents": stage_patch(
                COMPLETED,
                detail=f"{usable_pages}/{total_pages} pages usable" + (f", {failed} failed" if failed else ""),
                report=report,
            )},
            action="documents_processed",
        )
        return report

    return _start_stage_job(
        case_id, "documents", "extracting_pages", "Preparing documents…", task, session_id=session_id,
    )


@app.route("/documents/review_completeness", methods=["POST"])
def documents_review_completeness():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    session_id = body.get("session_id")
    data, state = _load_state(case_id)
    interview_state = body.get("interview_state")
    result = assess_next_step(
        case_record=data["case"], messages=data["messages"], documents=data["documents"], pages=data["pages"],
        facts=data["facts"], fact_candidates=data["fact_candidates"], parties=data["parties"],
        issues=data["issues"], issue_candidates=data["issue_candidates"], evidence=data["evidence"],
        legal_research=((state.get("research") or {}).get("authority_nodes", [])),
        previous_state=interview_state,
    )
    increment_usage(session_id, "llm_request_count", 1)
    increment_usage(session_id, "message_count", 1)
    persist_interview_state(case_id, result["decision"].payload)
    return _ok({"reply": result["reply"], "interview_state": result["decision"].payload})


# ============================================================
# Accounting & forensic dispute analysis — stage "accounting"
#
#   1. classify pages (financial / claim / mixed / other). Stored results
#      are reused; only new pages and failed attempts are classified.
#   2. extract financial rows from financial + mixed pages only, reusing
#      stored rows (PyMuPDF structure + intake OCR -> LLM reconstruction).
#   3. every uncertain or missing required value becomes a pending review
#      item; the stage WAITS for the user until all are answered.
#   4. corrections are stored separately (never overwrite the extraction);
#      the normalized ledger contains only fully reviewed rows.
#   5. claims vs evidence analysis runs only on the reviewed ledger, with
#      the user's instructions stored alongside the result.
# ============================================================
def _selected_page_ids(data, document_ids=None):
    pages = data["pages"]
    if pages.empty:
        return []
    id_col = _page_id_column(pages)
    if document_ids:
        doc_col = "case_document_id" if "case_document_id" in pages.columns else "document_id"
        pages = pages[pages[doc_col].astype(str).isin([str(d) for d in document_ids])]
    return pages[id_col].dropna().astype(str).tolist()


def _accounting_pipeline(job_id, case_id, document_ids=None, extract=True, session_id=None):
    data = load_case_data(case_id)
    before = restore_workflow_state(data)
    page_ids = _selected_page_ids(data, document_ids)
    if not page_ids:
        raise ValueError("No processed document pages are available. Process the case documents first.")

    # 1. Classification — only pages without a usable stored result.
    to_classify = pages_needing_classification(case_id, page_ids)
    if to_classify:
        _set_phase(job_id, "classifying_pages", f"Classifying {len(to_classify)} page(s) as financial / non-financial…")
        classify_case_pages(case_id, to_classify)
        if session_id:
            increment_usage(session_id, "llm_request_count", len(to_classify))

    classifications = _latest_classifications_by_page(load_case_data(case_id))
    in_scope = [classifications.get(pid, {}) for pid in page_ids]
    classification_failures = sum(1 for item in in_scope if item.get("status") == "failed")
    financial_page_ids = [
        pid for pid in page_ids
        if classifications.get(pid, {}).get("page_type") in {"financial", "mixed"}
        and classifications.get(pid, {}).get("status") != "failed"
    ]
    report = {
        "pages_in_scope": len(page_ids),
        "pages_classified_now": len(to_classify),
        "classification_failures": classification_failures,
        "financial_pages": len(financial_page_ids),
    }

    if not extract:
        update_workflow_state(
            case_id,
            changes={"accounting_status": "classified"} if before.get("accounting_status") in {"", "not_started"} else {},
            stages={"accounting": stage_patch(READY, detail="pages_classified", report=report)},
            action="accounting_classified",
        )
        return report

    # 2. Extraction — only financial pages not yet extracted.
    extraction = {"new_rows_appended": 0, "rows_discarded": 0, "page_failures": [], "pages_processed": 0}
    if financial_page_ids:
        _set_phase(job_id, "extracting_financial_data",
                   f"Extracting financial data from {len(financial_page_ids)} page(s)…", total=len(financial_page_ids))

        def _on_progress(current, total, page_id):
            _set_phase(job_id, "extracting_financial_data",
                       f"Extracting financial data (page {current} of {total})…", current=current, total=total)

        try:
            extraction = run_financial_extraction(case_id, financial_page_ids, progress_callback=_on_progress)
        except ValueError as error:
            # No page text available for the selected pages.
            report["extraction_note"] = str(error)
        if session_id:
            increment_usage(session_id, "llm_request_count", int(extraction.get("pages_processed", 0) or 0))

    report.update({
        "pages_extracted_now": int(extraction.get("pages_processed", 0) or 0),
        "rows_added": int(extraction.get("new_rows_appended", 0) or 0),
        "rows_discarded": int(extraction.get("rows_discarded", 0) or 0),
        "extraction_failures": len(extraction.get("page_failures") or []),
    })

    # 3. Decide where accounting stands now.
    _set_phase(job_id, "checking_review_items", "Checking for values that need your confirmation…")
    final_data = load_case_data(case_id)
    pending = _review_items(case_id, final_data)
    has_items = not final_data["financial_line_items"].empty
    previous = str(before.get("accounting_status", "") or "")
    report["pending_review_items"] = sum(len(item.get("fields") or []) for item in pending)

    changes = {"accounting_dirty": False, "accounting_dirty_reason": ""}
    if pending:
        changes["accounting_status"] = "needs_review"
        stage = stage_patch(WAITING, detail="review_items", report=report)
    elif (
        report["rows_added"] == 0
        and previous in {"forensic_complete", "complete_no_transactions"}
        and not before.get("accounting_dirty")
    ):
        # Nothing new: keep the completed analysis instead of forcing a rerun.
        changes = {}
        stage = stage_patch(COMPLETED, detail=previous, report=report)
    elif has_items:
        changes["accounting_status"] = "ready_for_synthesis"
        stage = stage_patch(READY, detail="ready_for_analysis", report=report)
    else:
        changes["accounting_status"] = "complete_no_transactions"
        stage = stage_patch(COMPLETED, detail="complete_no_transactions", report=report)

    update_workflow_state(case_id, changes=changes, stages={"accounting": stage}, action="accounting_pipeline_complete")
    report["accounting_status"] = changes.get("accounting_status", previous)
    report["rows_persisted"] = report["rows_added"]
    return report


@app.route("/accounting/run_auto_pipeline", methods=["POST"])
def accounting_run_auto_pipeline():
    body = request.get_json(force=True)
    case_id = str(body.get("case_id", "")).strip()
    document_ids = [str(d).strip() for d in (body.get("document_ids") or []) if str(d).strip()]
    session_id = body.get("session_id")
    if not case_id:
        return jsonify({"error": "case_id is required"}), 400
    return _start_stage_job(
        case_id, "accounting", "classifying_pages", "Starting accounting extraction…",
        lambda job_id: _accounting_pipeline(job_id, case_id, document_ids or None, session_id=session_id),
        session_id=session_id,
    )


@app.route("/accounting/classify_documents", methods=["POST"])
def accounting_classify_documents():
    body = request.get_json(force=True)
    case_id = str(body.get("case_id", "")).strip()
    session_id = body.get("session_id")
    if not case_id:
        return jsonify({"error": "case_id is required"}), 400
    return _start_stage_job(
        case_id, "accounting", "classifying_pages", "Classifying pages…",
        lambda job_id: _accounting_pipeline(job_id, case_id, None, extract=False, session_id=session_id),
        session_id=session_id,
    )


@app.route("/accounting/extract", methods=["POST"])
def accounting_extract():
    body = request.get_json(force=True)
    case_id = str(body.get("case_id", "")).strip()
    document_ids = [str(d).strip() for d in (body.get("document_ids") or []) if str(d).strip()]
    session_id = body.get("session_id")
    if not case_id:
        return jsonify({"error": "case_id is required"}), 400
    if not document_ids:
        return jsonify({"error": "At least one document must be selected."}), 400
    return _start_stage_job(
        case_id, "accounting", "classifying_pages", "Starting accounting extraction…",
        lambda job_id: _accounting_pipeline(job_id, case_id, document_ids, session_id=session_id),
        session_id=session_id,
    )


# What "Clear accounting data" deletes, for this case only. Documents,
# OCR text, the case register, the attorney review and the legal analysis
# are NOT touched. A pleading built on the cleared accounting is kept but
# shown as stale until accounting is completed again.
ACCOUNTING_CLEAR_DATASETS = {
    "page_classifications": FINANCIAL_DOCUMENT_CLASSIFICATION_DATASET,
    "extracted_line_items": FINANCIAL_LINE_ITEMS_DATASET,
    "user_corrections": FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET,
    "financial_timeline": FINANCIAL_TIMELINE_DATASET,
    "discrepancies": FINANCIAL_DISCREPANCIES_DATASET,
    "claim_findings": FINANCIAL_FINDINGS_DATASET,
}


@app.route("/accounting/clear", methods=["POST"])
def accounting_clear():
    body = request.get_json(force=True)
    case_id = str(body.get("case_id", ""))
    if not case_id:
        return jsonify({"error": "case_id is required"}), 400
    if _active_jobs(case_id).get("accounting"):
        return jsonify({"error": "The accounting analysis is running. Wait for it to finish before clearing."}), 409

    deleted = {}
    for label, dataset_name in ACCOUNTING_CLEAR_DATASETS.items():
        try:
            before = len(case_rows(dataset_name, case_id))
            replace_case_rows(dataset_name, case_id, [])
            deleted[label] = before
        except Exception:
            traceback.print_exc()
            deleted[label] = "error"

    update_workflow_state(
        case_id,
        changes={
            "accounting_status": "not_started",
            "accounting_dirty": False,
            "accounting_dirty_reason": "",
        },
        stages={"accounting": stage_patch(NOT_STARTED, finished_at="", report={})},
        action="accounting_cleared",
    )
    return _ok({"cleared": True, "deleted": deleted})


def _validate_correction(field_name, value):
    """(clean_value, error). Only values that downstream analysis can use
    are accepted, so a correction can never re-introduce an unusable field."""
    value = str(value or "").strip()
    if field_name not in FIELD_NAMES:
        return None, f"Unknown field '{field_name}'."
    if not value:
        return None, "A value is required."
    if field_name == "debit_or_credit":
        direction = normalize_debit_credit(value, value)
        if direction not in {"debit", "credit"}:
            return None, "Enter 'debit' or 'credit'."
        return direction, None
    if field_name in {"amount", "running_balance"}:
        if not re.fullmatch(r"-?[\d,]+\.\d{2}", normalize_amount(value)):
            return None, "Enter a numeric amount, e.g. 12,450.00."
    return value, None


@app.route("/accounting/correction", methods=["POST"])
def accounting_correction():
    """Store the user's answer for one pending field. When the last pending
    item is answered, accounting is ready to continue (ready_for_analysis)
    and the response says so, with the instructions last used."""
    body = request.get_json(force=True)
    case_id = str(body.get("case_id", ""))
    row_id = str(body.get("row_id", ""))
    field_name = str(body.get("field_name", ""))
    corrected_by = str(body.get("corrected_by", "") or "attorney")
    note = str(body.get("note", "") or "")
    if not (case_id and row_id and field_name):
        return jsonify({"error": "case_id, row_id and field_name are required."}), 400
    value, error = _validate_correction(field_name, body.get("value", ""))
    if error:
        return jsonify({"error": error}), 400

    submit_correction(case_id, row_id, field_name, value, corrected_by=corrected_by, correction_note=note)

    data = load_case_data(case_id)
    state = restore_workflow_state(data)
    pending = _review_items(case_id, data)
    status = str(state.get("accounting_status", "") or "")

    if pending:
        update_workflow_state(
            case_id,
            stages={"accounting": stage_patch(WAITING, detail="review_items")},
            action="accounting_field_corrected",
            actor=corrected_by,
        )
    elif status in {"forensic_complete", "complete_no_transactions"}:
        update_workflow_state(
            case_id,
            changes={
                "accounting_status": "ready_for_synthesis",
                "accounting_dirty": True,
                "accounting_dirty_reason": "The ledger was corrected after the accounting analysis ran.",
            },
            stages={"accounting": stage_patch(READY, detail="ready_for_analysis")},
            action="accounting_ledger_corrected",
            actor=corrected_by,
        )
    else:
        update_workflow_state(
            case_id,
            changes={"accounting_status": "ready_for_synthesis"},
            stages={"accounting": stage_patch(READY, detail="ready_for_analysis")},
            action="accounting_review_resolved",
            actor=corrected_by,
        )

    return _ok({
        "saved": True,
        "value": value,
        "pending_count": len(pending),
        "ready_for_analysis": not pending,
        "instructions": state.get("accounting_instructions", ""),
    })


def _financial_claims(state, data):
    """(claims, source). The attorney review's allegations when a review
    exists; otherwise the alleged facts from the case register, so the
    accounting track does not depend on the attorney review."""
    summary = state.get("attorney_summary") or {}
    allegations = [a for a in (summary.get("allegations") or []) if a]
    if allegations:
        return allegations, "attorney_review"

    claims = [
        {
            "allegation_text": fact["fact_text"],
            "made_by": fact.get("party", ""),
            "source_page_ids": fact.get("source_page_ids", []),
        }
        for fact in case_register(data)["allegations"]
    ]
    return claims, "case_register"


@app.route("/accounting/synthesize", methods=["POST"])
def accounting_synthesize():
    body = request.get_json(force=True)
    case_id = str(body.get("case_id", ""))
    instructions = str(body.get("instructions", "") or "")
    session_id = body.get("session_id")
    if not case_id:
        return jsonify({"error": "case_id is required"}), 400

    data = load_case_data(case_id)
    pending = _review_items(case_id, data)
    if pending:
        return jsonify({
            "error": f"{len(pending)} accounting item(s) are waiting for your confirmation. "
                     "Resolve them before running the analysis.",
            "pending_count": len(pending),
        }), 409

    def task(job_id):
        data = load_case_data(case_id)
        state = restore_workflow_state(data)
        normalized_ledger, withheld = _normalized_ledger(case_id, data["financial_line_items"])
        if withheld:
            raise ValueError(f"{withheld} ledger row(s) still await review.")
        if not normalized_ledger:
            raise ValueError("The reviewed ledger is empty. Run the accounting extraction first.")

        claims, claims_source = _financial_claims(state, data)

        _set_phase(job_id, "building_timeline", "Building the chronological financial timeline…")
        build_and_save_financial_timeline(case_id, normalized_ledger)

        _set_phase(job_id, "analysing_claims", f"Comparing {len(claims)} claim(s) with the reviewed ledger…")
        result = run_claim_based_accounting_analysis(
            case_id, normalized_ledger, claims, instructions, claims_source=claims_source,
        )

        if session_id:
            increment_usage(session_id, "llm_request_count", 1)

        update_workflow_state(
            case_id,
            changes={
                "accounting_status": "forensic_complete",
                "accounting_dirty": False,
                "accounting_dirty_reason": "",
                "accounting_instructions": instructions,
            },
            stages={"accounting": stage_patch(
                COMPLETED,
                detail="forensic_complete",
                analysis={"claims": len(claims), "claims_source": claims_source, "ledger_rows": len(normalized_ledger)},
            )},
            action="accounting_synthesized",
        )
        return {"findings": {"claim_evaluations": result.get("claim_evaluations", [])}}

    return _start_stage_job(
        case_id, "accounting", "analysing_claims", "Preparing the accounting analysis…", task, session_id=session_id,
    )


# =============================================================================
# SUMMARY, ANALYSIS & WRITTEN PLEADING ENDPOINTS
# =============================================================================
def _gate_error():
    return (
        "Prepare the consolidated attorney review first."
        if not REQUIRE_APPROVED_SUMMARY
        else "Approve the consolidated attorney review first."
    )


@app.route("/summary/prepare", methods=["POST"])
def summary_prepare():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    session_id = body.get("session_id")

    def task(job_id):
        data = load_case_data(case_id)
        _set_phase(job_id, "preparing_summary", "Preparing consolidated attorney review…")

        # Reads the case register and the documents stage's own page
        # extraction only (pages that recorded claims first), never the
        # accounting classification: the legal track must not depend on
        # whether accounting has run.
        register = case_register(data)
        summary = generate_case_summary(
            case_record=data["case"],
            pages=prioritise_pages_for_summary(data["pages"]),
            facts=register["facts"],
            evidence=data["evidence"],
            parties=data["parties"],
            events=data["events"],
            force_rerun=True,
        )

        if session_id:
            increment_usage(session_id, "llm_request_count", 1)
            increment_usage(session_id, "message_count", 1)

        update_workflow_state(
            case_id,
            changes={"attorney_summary": summary, "summary_approved": False, "summary_approved_by": ""},
            stages={"review": stage_patch(WAITING if REQUIRE_APPROVED_SUMMARY else COMPLETED,
                                          detail="approve_summary" if REQUIRE_APPROVED_SUMMARY else "",
                                          register_fingerprint=register["fingerprint"])},
            action="summary_prepared",
        )
        response_summary = dict(summary)
        if data.get("forensic_findings"):
            response_summary["forensic_findings"] = data["forensic_findings"]

        return {"attorney_summary": response_summary, "summary_support": serialise_summary_support(summary, data)}

    return _start_stage_job(
        case_id, "review", "preparing_summary", "Preparing consolidated attorney review…", task, session_id=session_id,
    )


@app.route("/summary/approve", methods=["POST"])
def summary_approve():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    reviewer = str(body.get("reviewer", "")).strip()
    comments = body.get("comments", "")
    data, state = _load_state(case_id)
    summary = state.get("attorney_summary")
    if not summary or not reviewer:
        return jsonify({"error": "A prepared summary and reviewer name are required."}), 400
    approval_record = approve_case_summary(case_id, summary, reviewer, comments)
    state = update_workflow_state(
        case_id,
        changes={
            "summary_approved": True,
            "summary_approved_by": reviewer,
            "case_dirty": False,
            "dirty_reason": "",
        },
        stages={"review": stage_patch(COMPLETED, detail="approved")},
        action="summary_approved",
        actor=reviewer,
    )
    return _ok({"approval_id": approval_record["approval_id"], "workflow_state": state})


@app.route("/analysis/run", methods=["POST"])
def analysis_run():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    session_id = body.get("session_id")

    def task(job_id):
        data = load_case_data(case_id)
        state = restore_workflow_state(data)
        if not approval_gate_passed(state):
            raise ValueError(_gate_error())
        register = case_register(data)
        facts = register["facts"]
        issues = register["issues"]
        if not facts or not issues:
            raise ValueError("The case register has no facts or issues yet. Process the case documents first.")
        _set_phase(job_id, "researching_law", "Retrieving SAMA authorities and evaluating legal defenses…")
        result = run_legal_analysis(data["case"], facts, issues, register["evidence_requests"])
        if session_id:
            increment_usage(session_id, "llm_request_count", 1)
            increment_usage(session_id, "message_count", 1)
        update_workflow_state(
            case_id,
            changes={"research": result["research"], "analysis": result["analysis"]},
            stages={"analysis": stage_patch(COMPLETED, detail="analysis",
                                            register_fingerprint=register["fingerprint"])},
            action="analysis_prepared",
        )
        return {"research": result["research"], "analysis": result["analysis"]}

    return _start_stage_job(
        case_id, "analysis", "researching_law", "Starting legal analysis…", task, session_id=session_id,
    )


@app.route("/analysis/defence_plan", methods=["POST"])
def analysis_defence_plan():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    session_id = body.get("session_id")

    def task(job_id):
        data = load_case_data(case_id)
        state = restore_workflow_state(data)
        if not approval_gate_passed(state):
            raise ValueError(_gate_error())
        if not state.get("analysis") or not state.get("research"):
            raise ValueError("Run the legal analysis before preparing the defence plan.")
        _set_phase(job_id, "planning_defence", "Developing defence plan…")
        register = case_register(data)
        strategy = run_defence_plan(
            data["case"], state["analysis"], register["facts"],
            register["evidence_requests"], (state.get("research") or {}).get("authority_nodes", []),
        )
        if session_id:
            increment_usage(session_id, "llm_request_count", 1)
            increment_usage(session_id, "message_count", 1)
        # The defence plan extends the analysis; it does not make it newer.
        previous = (state.get("stages") or {}).get("analysis") or {}
        patch = stage_patch(COMPLETED, detail="analysis_and_defence_plan")
        if previous.get("finished_at"):
            patch["finished_at"] = previous["finished_at"]
        update_workflow_state(
            case_id,
            changes={"strategy": strategy},
            stages={"analysis": patch},
            action="defence_plan_prepared",
        )
        return {"strategy": strategy}

    return _start_stage_job(
        case_id, "analysis", "planning_defence", "Developing defence plan…", task, session_id=session_id,
    )


@app.route("/pleading/generate", methods=["POST"])
def pleading_generate():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    memo_instructions = body.get("instructions", "")
    direct = bool(body.get("direct", False))
    session_id = body.get("session_id")

    def task(job_id):
        data = load_case_data(case_id)
        state = restore_workflow_state(data)

        # 1. Attorney review must be prepared / approved.
        if not approval_gate_passed(state):
            raise ValueError(_gate_error())

        # 2. Legal analysis must be completed.
        if not state.get("analysis"):
            raise ValueError("Complete the legal analysis before generating the written pleading.")

        # 3. Accounting analysis must be completed on a fully reviewed ledger.
        accounting = accounting_state(data, state)
        if accounting["pending_count"]:
            raise ValueError(
                f"{accounting['pending_count']} accounting item(s) are waiting for your confirmation."
            )
        if accounting["status"] not in {"forensic_complete", "complete_no_transactions"}:
            raise ValueError("Complete the accounting analysis before generating the written pleading.")

        case = data["case"]
        _set_phase(job_id, "generating_pleading", "Synthesizing bilingual court pleading…")
        instructions = (
            "Prepare a complete formal defence pleading exclusively on behalf of Banque Saudi Fransi (BSF)."
            if direct else (memo_instructions or "Prepare a complete formal defence pleading on behalf of BSF.")
        )
        summary_obj = dict(state.get("attorney_summary") or {})
        if data.get("forensic_findings"):
            summary_obj["forensic_findings"] = data["forensic_findings"]
        memo = generate_bilingual_memo(
            case, summary_obj, state.get("analysis"), state.get("strategy"),
            state.get("research"), instructions,
            case_data=data,
        )
        if session_id:
            increment_usage(session_id, "llm_request_count", 1)
            increment_usage(session_id, "message_count", 1)
        note = "Initial approved-summary draft" if direct else (memo_instructions or "Initial pleading draft")
        versions = [{"version": 1, "draft": memo, "note": note}]
        update_workflow_state(
            case_id,
            changes={
                "memo": memo,
                "pleading_versions": versions,
                "pleading_status": "draft",
                "pleading_finalised_by": "",
            },
            stages={"pleading": stage_patch(COMPLETED, detail="draft")},
            action="pleading_prepared",
        )
        return {"memo": memo, "pleading_versions": versions, "pleading_status": "draft"}

    return _start_stage_job(
        case_id, "pleading", "generating_pleading", "Preparing the written pleading…", task, session_id=session_id,
    )


@app.route("/pleading/revise", methods=["POST"])
def pleading_revise():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    revision_request = body.get("revision_request", "")
    session_id = body.get("session_id")

    def task(job_id):
        data = load_case_data(case_id)
        state = restore_workflow_state(data)
        if not state.get("memo"):
            raise ValueError("Generate the written pleading before revising it.")
        _set_phase(job_id, "revising_pleading", "Revising the written pleading…")
        revised = revise_bilingual_pleading(
            revision_request,
            state["memo"],
            data["case"],
            state["attorney_summary"],
            state["analysis"],
            state["strategy"],
            state["research"],
            case_data=data,
        )
        if session_id:
            increment_usage(session_id, "llm_request_count", 1)
            increment_usage(session_id, "message_count", 1)
        versions = list(read_workflow_state(case_id).get("pleading_versions") or [])
        version_no = len(versions) + 1
        versions.append({"version": version_no, "draft": revised, "note": revision_request})
        update_workflow_state(
            case_id,
            changes={"memo": revised, "pleading_versions": versions, "pleading_status": "draft"},
            stages={"pleading": stage_patch(COMPLETED, detail="draft")},
            action="pleading_revised",
            reason=revision_request,
        )
        return {
            "memo": revised,
            "pleading_versions": versions,
            "pleading_status": "draft",
            "version": version_no,
        }

    return _start_stage_job(
        case_id, "pleading", "revising_pleading", "Revising the written pleading…", task, session_id=session_id,
    )


@app.route("/pleading/restore_version", methods=["POST"])
def pleading_restore_version():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    selected_version = body.get("version")
    state = read_workflow_state(case_id)
    versions = list(state.get("pleading_versions") or [])
    selected = next((v for v in versions if v["version"] == selected_version), None)
    if not selected:
        return jsonify({"error": "version not found"}), 404
    version_no = len(versions) + 1
    versions.append({
        "version": version_no, "draft": selected["draft"],
        "note": f"Restored from version {selected_version}",
    })
    state = update_workflow_state(
        case_id,
        changes={"memo": selected["draft"], "pleading_versions": versions},
        action="pleading_version_restored",
    )
    return _ok({"memo": state["memo"], "pleading_versions": state["pleading_versions"]})


@app.route("/pleading/mark_final", methods=["POST"])
def pleading_mark_final():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    final_reviewer = str(body.get("final_reviewer", "")).strip()
    if not final_reviewer:
        return jsonify({"error": "final_reviewer is required"}), 400
    update_workflow_state(
        case_id,
        changes={"pleading_status": "final", "pleading_finalised_by": final_reviewer},
        action="pleading_finalised",
        actor=final_reviewer,
    )
    return jsonify({"pleading_status": "final", "pleading_finalised_by": final_reviewer})


@app.route("/pleading/reopen", methods=["POST"])
def pleading_reopen():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    update_workflow_state(
        case_id,
        changes={"pleading_status": "draft", "pleading_finalised_by": ""},
        action="pleading_reopened",
    )
    return jsonify({"pleading_status": "draft"})


@app.route("/pleading/export")
def pleading_export():
    case_id = request.args.get("case_id", "")
    fmt = request.args.get("fmt", "md")
    language = request.args.get("lang", "en")
    data, state = _load_state(case_id)
    memo = state.get("memo")
    if not memo:
        return jsonify({"error": "no pleading available"}), 404
    reference = short_case_reference(case_id)
    if fmt == "docx":
        try:
            docx_bytes = build_pleading_docx_bytes(memo, reference)
        except ImportError:
            return jsonify({"error": "python-docx is not installed in this code environment."}), 501
        return send_file(
            io.BytesIO(docx_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=f"pleading_{reference}.docx",
        )
    text = memo_to_markdown(memo, language)
    return Response(
        text,
        mimetype="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="pleading_{language}.md"'},
    )


@app.route("/discussion/ask", methods=["POST"])
def discussion_ask():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    conversation_id = body.get("conversation_id", "")
    question = body.get("question", "")
    add_to_record = bool(body.get("add_to_record", False))
    session_id = body.get("session_id")

    def task(job_id):
        _set_phase(job_id, "answering", "Answering from the stored case record…")
        data = load_case_data(case_id)
        state = restore_workflow_state(data)
        message_id = add_message(case_id, conversation_id, "user", question)
        answer = answer_case_question(
            question, data["case"], state["attorney_summary"], state["analysis"],
            state["strategy"], state["research"], case_data=data,
        )
        increment_usage(session_id, "llm_request_count", 2)
        increment_usage(session_id, "message_count", 1)

        assistant_text = json.dumps({
            "answer_ar": answer.get("answer_ar", ""),
            "answer_en": answer.get("answer_en", ""),
            "uncertainties": answer.get("uncertainties") or [],
            "source_ids": answer.get("source_ids") or [],
        }, ensure_ascii=False)
        add_message(case_id, conversation_id, "assistant", assistant_text)

        if add_to_record:
            add_fact_candidate(
                case_id=case_id, fact_text=question, source_type="chat",
                source_id=message_id, fact_type="user_statement", quote=question, confidence=0.65,
            )
        return {"answer": answer, "invalidated": False}

    return _start_stage_job(
        case_id, "discussion", "answering", "Answering from the stored case record…", task, session_id=session_id,
    )


@app.route("/page_image")
def page_image():
    case_id = request.args.get("case_id", "")
    page_id = request.args.get("page_id", "")
    data = load_case_data(case_id)
    row = _page_row(data, page_id)
    if not row:
        return Response(status=404)
    image_bytes = _load_page_image_bytes(row.get("page_image_path", ""))
    if not image_bytes:
        return Response(status=404)
    return send_file(io.BytesIO(image_bytes), mimetype="image/png")


@app.route("/page_text")
def page_text():
    case_id = request.args.get("case_id", "")
    page_id = request.args.get("page_id", "")
    data = load_case_data(case_id)
    row = _page_row(data, page_id)
    if not row:
        return jsonify({"label": "", "text": ""})
    label = _page_reference_map(data).get(str(page_id), "Original page")
    return _ok({"label": label, "text": str(row.get("page_text", "") or "")[:4000]})


@app.route("/flag", methods=["POST"])
def flag_control():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    entity_type = body.get("entity_type", "")
    entity_id = body.get("entity_id", "")
    action = body.get("action", "")
    actor = body.get("actor", "") or "attorney"
    reason = body.get("reason", "")
    if action not in {"verified", "flagged", "corrected"}:
        return jsonify({"error": "invalid action"}), 400
    audit(case_id, entity_type, entity_id, action, actor=actor, reason=reason)
    return jsonify({"ok": True})


# =============================================================================
# AGREEMENT WORKFLOW ENDPOINTS
# =============================================================================
@app.route("/agreement/process", methods=["POST"])
def agreement_process():
    case_id = request.form.get("case_id", "")
    session_id = request.form.get("session_id")
    try:
        zoom = float(request.form.get("zoom", "1.6"))
    except ValueError:
        zoom = 1.6
    uploaded = request.files.getlist("files")
    payloads = [(f.filename, f.read(), f.mimetype) for f in uploaded]
    job_id = _new_job()

    def task():
        processed = 0
        llm_call_count = 0
        for name, raw, content_type in payloads:
            document_row, pdf_bytes = save_upload(case_id, _MemoryUpload(name, raw, content_type), document_type="agreement")
            def on_page(current, total, page_number, state, _name=name):
                _set_progress(job_id, stage="extract", current=current, total=total,
                              detail=f"{_name}: page {page_number}/{total} — {state}")
            pages = extract_pdf_page_by_page(
                case_id=case_id,
                case_document_id=document_row["case_document_id"],
                pdf_bytes=pdf_bytes, zoom=zoom,
                progress_callback=on_page,
            )
            llm_call_count += len(pages)
            if pages:
                processed += 1

        if llm_call_count:
            increment_usage(session_id, "llm_request_count", llm_call_count, use_case="agreement")
        if processed:
            increment_usage(session_id, "attachment_count", processed, use_case="agreement")
        return {"processed": processed}

    _run_async(job_id, task, session_id=session_id, use_case="agreement")
    return jsonify({"job_id": job_id})


@app.route("/agreement/classify", methods=["POST"])
def agreement_classify():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    session_id = body.get("session_id")
    job_id = _new_job()

    def task():
        data = load_case_data(case_id)
        _set_progress(job_id, stage="classify", detail="Detecting agreement type and relationship…")
        result = classify_agreement(data["pages"])
        increment_usage(session_id, "llm_request_count", 1, use_case="agreement")
        increment_usage(session_id, "message_count", 1, use_case="agreement")
        save_agreement_state(case_id, "classification", result)
        return {"classification": result}

    _run_async(job_id, task, session_id=session_id, use_case="agreement")
    return jsonify({"job_id": job_id})


@app.route("/agreement/confirm_classification", methods=["POST"])
def agreement_confirm_classification():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    profile = {
        "agreement_type": body.get("agreement_type"),
        "relationship_type": body.get("relationship_type"),
        "represented_party": str(body.get("represented_party", "")).strip(),
        "counterparty": str(body.get("counterparty", "")).strip(),
        "review_objective": str(body.get("review_objective", "")).strip(),
        "confirmed_by_attorney": True,
    }
    if not profile["represented_party"]:
        return jsonify({"error": "represented_party is required"}), 400
    save_agreement_state(case_id, "confirmed_profile", profile)
    return _ok({"profile": profile})


@app.route("/agreement/extract_clauses", methods=["POST"])
def agreement_extract_clauses():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    session_id = body.get("session_id")
    job_id = _new_job()

    def task():
        data = load_case_data(case_id)
        stored = load_agreement_states(case_id)
        profile = stored.get("confirmed_profile")

        def on_page(current, total, page_id):
            _set_progress(job_id, stage="pages", current=current, total=total,
                          detail=f"Page structure {current}/{total} · {page_id}")

        def on_chunk(current, total, chunk_id):
            _set_progress(job_id, stage="chunks", current=current, total=total,
                          detail=f"Consolidation chunk {current}/{total} · {chunk_id}")

        clause_map = extract_clause_map(
            data["pages"], profile,
            page_progress_callback=on_page,
            chunk_progress_callback=on_chunk,
        )
        increment_usage(session_id, "llm_request_count", 1, use_case="agreement")
        increment_usage(session_id, "message_count", 1, use_case="agreement")
        save_agreement_state(case_id, "clause_map", clause_map)
        return {"clause_map": clause_map}

    _run_async(job_id, task, session_id=session_id, use_case="agreement")
    return jsonify({"job_id": job_id})


@app.route("/agreement/run_review", methods=["POST"])
def agreement_run_review():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    instructions = body.get("instructions", "")
    session_id = body.get("session_id")
    job_id = _new_job()

    def task():
        stored = load_agreement_states(case_id)
        clause_map = stored.get("clause_map")
        profile = stored.get("confirmed_profile")

        def on_review(current, total, clause_id):
            _set_progress(job_id, stage="review", current=current, total=total,
                          detail=f"Clause review {current}/{total} · {clause_id}")

        review, authorities = run_agreement_review(
            clause_map, profile, instructions=instructions, progress_callback=on_review,
        )
        increment_usage(session_id, "llm_request_count", 1, use_case="agreement")
        increment_usage(session_id, "message_count", 1, use_case="agreement")
        authorities_payload = {"authority_nodes": authorities}
        save_agreement_state(case_id, "authorities", authorities_payload)
        save_agreement_state(case_id, "review", review)
        return {"review": review, "authorities": authorities_payload}

    _run_async(job_id, task, session_id=session_id, use_case="agreement")
    return jsonify({"job_id": job_id})


@app.route("/agreement/discuss", methods=["POST"])
def agreement_discuss():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    question = body.get("question", "")
    session_id = body.get("session_id")
    job_id = _new_job()

    def task():
        stored = load_agreement_states(case_id)
        authority_nodes = (stored.get("authorities") or {}).get("authority_nodes", [])
        answer = discuss_agreement(
            question,
            stored.get("confirmed_profile") or {},
            stored.get("clause_map") or {},
            stored.get("review") or {},
            authority_nodes,
        )
        increment_usage(session_id, "llm_request_count", 1, use_case="agreement")
        increment_usage(session_id, "message_count", 1, use_case="agreement")
        return {"answer": answer}

    _run_async(job_id, task, session_id=session_id, use_case="agreement")
    return jsonify({"job_id": job_id})
