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
from legal_platform.ids import random_id
from legal_platform.intake import create_case, add_message
from legal_platform.storage import list_cases, latest_case, case_rows
from legal_platform.files import save_upload
from legal_platform.extraction import extract_pdf_page_by_page
from legal_platform.case_mapping import build_case_map
from legal_platform.case_map_storage import persist_case_map
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
    APPROVALS_DATASET,
    FINANCIAL_DISCREPANCIES_DATASET,
    FINANCIAL_DOCUMENT_CLASSIFICATION_DATASET,
    FINANCIAL_FINDINGS_DATASET,
    FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET,
    FINANCIAL_LINE_ITEMS_DATASET,
    FINANCIAL_TIMELINE_DATASET,
    CASE_DOCUMENT_FOLDER_ID,
)
from legal_platform.financial_classification import classify_case_pages
from legal_platform.financial_corrections import (
    list_rows_needing_review,
    load_latest_corrections,
    submit_correction,
)
from legal_platform.financial_extraction_pipeline import run_financial_extraction
from legal_platform.financial_forensics import (
    build_and_save_financial_timeline,
    load_saved_forensic_results,
    run_claim_based_accounting_analysis,
)
from legal_platform.financial_normalizer import normalize_row_for_ledger

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
def _build_normalized_ledger(case_id, line_items_df):
    if line_items_df is None or line_items_df.empty:
        return []
    corrections = load_latest_corrections(case_id)
    ledger = []
    
    for _, row in line_items_df.iterrows():
        row_dict = row.to_dict()
        
        # Unpack fields_json into flat keys
        fields_json = row_dict.get("fields_json")
        if fields_json:
            try:
                fields = json.loads(fields_json) if isinstance(fields_json, str) else fields_json
                if isinstance(fields, dict):
                    for k, v in fields.items():
                        if isinstance(v, dict) and "value" in v:
                            # Map complex schema keys to simple flat keys
                            flat_key = k
                            if k == "transaction_date": flat_key = "date"
                            elif k == "transaction_description": flat_key = "description"
                            elif k == "debit_amount": flat_key = "debit"
                            elif k == "credit_amount": flat_key = "credit"
                            row_dict[flat_key] = v["value"]
                            row_dict[k] = v["value"]
            except Exception:
                pass

        # Calculate amount and debit_or_credit if they are missing
        if not row_dict.get("amount"):
            deb = str(row_dict.get("debit", "")).strip()
            cred = str(row_dict.get("credit", "")).strip()
            if deb and deb not in ["0", "0.00", "None", ""]:
                row_dict["amount"] = deb
                row_dict["debit_or_credit"] = "Debit"
            elif cred and cred not in ["0", "0.00", "None", ""]:
                row_dict["amount"] = cred
                row_dict["debit_or_credit"] = "Credit"

        # Try the formal normalizer
        item = normalize_row_for_ledger(row_dict, corrections)
        
        # BULLETPROOF FALLBACK: If normalizer rejects it, force the display
        if item is None and row_dict.get("date") and row_dict.get("description"):
            item = {
                "row_id": str(row_dict.get("row_id", "")),
                "page_number": str(row_dict.get("page_number", "")),
                "date": str(row_dict.get("date", "")),
                "description": str(row_dict.get("description", "")),
                "debit_or_credit": str(row_dict.get("debit_or_credit", "")),
                "amount": str(row_dict.get("amount", "")),
                "currency": str(row_dict.get("currency", "SAR")),
                "row_status": "Reconciled"
            }
        
        if item is not None:
            ledger.append(item)
            
    return ledger

def _serialise_conflicts(case_id, pages_df=None):
    rows = list_rows_needing_review(case_id) or []
    out = []
    page_img_map = {}
    if isinstance(pages_df, pd.DataFrame) and not pages_df.empty:
        id_col = "case_document_page_id" if "case_document_page_id" in pages_df.columns else "page_id"
        for _, r in pages_df.iterrows():
            pid = str(r.get(id_col, ""))
            if pid:
                page_img_map[pid] = f"/page_image?case_id={case_id}&page_id={pid}"

    for row in rows:
        row_id = str(row.get("row_id", ""))
        page_id = str(row.get("page_id", ""))
        try:
            fields = json.loads(row.get("fields_json", "{}") or "{}")
        except (TypeError, json.JSONDecodeError):
            fields = {}

        conflicted_fields = []
        if isinstance(fields, dict):
            for field_name, field_data in fields.items():
                if isinstance(field_data, dict):
                    # Flag as conflict if status is conflict OR LLM says it is uncertain
                    is_conflict = field_data.get("status") == "conflict" or str(field_data.get("certain", "")).lower() == "false"
                    
                    if is_conflict:
                        candidates = [
                            {"value": c.get("value"), "source": c.get("source")}
                            for c in (field_data.get("candidates") or [])
                        ]
                        # If no strict candidates exist, surface the LLM's best guess as a candidate
                        if not candidates and field_data.get("value"):
                            candidates = [{"value": field_data.get("value"), "source": "LLM Extraction"}]
                            
                        conflicted_fields.append({
                            "field": field_name, 
                            "candidates": candidates,
                            "reason": field_data.get("reason", "")
                        })

        if conflicted_fields:
            out.append({
                "row_id": row_id,
                "page_id": page_id,
                "page_number": row.get("page_number"),
                "page_image_url": page_img_map.get(page_id, f"/page_image?case_id={case_id}&page_id={page_id}"),
                "fields": conflicted_fields,
            })
    return out

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
        "contradictions": case_rows("case_contradictions", case_id),   # NEW
        "issues": case_rows("case_issues", case_id),
        "issue_candidates": case_rows("case_issue_candidates", case_id),
        "evidence": case_rows("case_evidence", case_id),
        "approvals": case_rows("case_approvals", case_id),
        "audit_events": case_rows("audit_events", case_id),
        "financial_line_items": (lambda: (
            setattr(dataiku.Dataset(FINANCIAL_LINE_ITEMS_DATASET), 'cache_dataframe', False) or 
            case_rows(FINANCIAL_LINE_ITEMS_DATASET, case_id)
        ))(),
        "financial_classifications": case_rows(FINANCIAL_DOCUMENT_CLASSIFICATION_DATASET, case_id),
    }
    
    forensic = load_saved_forensic_results(case_id)
    data["financial_timeline"] = forensic.get("timeline", [])
    
    # FIX: Point the backend to the new claim_evaluations array
    data["forensic_findings"] = {"claim_evaluations": forensic.get("claim_evaluations", [])}
    
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
        }
    return latest


def best(data, approved_key, candidate_key):
    return data[approved_key] if not data[approved_key].empty else data[candidate_key]


# =============================================================================
# PERSISTENCE & WORKFLOW STATE
# =============================================================================
WORKFLOW_KEYS = (
    "attorney_summary",
    "summary_approved",
    "summary_approved_by",

    "accounting_status",
    "accounting_dirty",
    "accounting_dirty_reason",

    "research",
    "analysis",
    "strategy",
    "memo",
    "pleading_versions",
    "pleading_status",
    "pleading_finalised_by",

    "case_dirty",
    "dirty_reason",
)


def blank_workflow_state():
    return {
        "attorney_summary": None,
        "summary_approved": False,
        "summary_approved_by": "",

        # Accounting lifecycle
        "accounting_status": "not_started",
        "accounting_dirty": False,
        "accounting_dirty_reason": "",

        "research": None,
        "analysis": None,
        "strategy": None,
        "memo": None,
        "pleading_versions": [],
        "pleading_status": "draft",
        "pleading_finalised_by": "",

        "case_dirty": False,
        "dirty_reason": "",
    }

def persist_deep_ui_state(case_id: str, state_dict: dict):
    """Saves workflow state into case_approvals so browser reload never loses data."""
    record = {
        "approval_id": random_id("UISTATE"),
        "case_id": str(case_id),
        "approved_by": "UI_STATE_MANAGER",
        "summary_json": json.dumps(state_dict, ensure_ascii=False),
        "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        ds = dataiku.Dataset(APPROVALS_DATASET)
        try:
            ex_df = ds.get_dataframe()
            if not ex_df.empty and "case_id" in ex_df.columns:
                mask = (ex_df["case_id"].astype(str) == str(case_id)) & (ex_df["approved_by"].astype(str) == "UI_STATE_MANAGER")
                ex_df = ex_df[~mask].copy()
                df = pd.concat([ex_df, pd.DataFrame([record])], ignore_index=True)
            else:
                df = pd.DataFrame([record])
        except Exception:
            df = pd.DataFrame([record])
        ds.write_with_schema(df)
    except Exception as e:
        print(f"Deep UI persistence failed: {e}")

def restore_workflow_state(data):
    state = blank_workflow_state()
    case_id = str(data["case"].get("case_id", ""))

    approvals = data.get("approvals")
    if isinstance(approvals, pd.DataFrame) and not approvals.empty and "approved_by" in approvals.columns:
        ui_states = approvals[approvals["approved_by"].astype(str) == "UI_STATE_MANAGER"]
        if not ui_states.empty:
            try:
                latest_record = ui_states.iloc[-1].to_dict()
                loaded = json.loads(str(latest_record.get("summary_json", "{}") or "{}"))
                if isinstance(loaded, dict):
                    state.update(loaded)
                    return state
            except Exception:
                pass

    audits = data.get("audit_events")
    if isinstance(audits, pd.DataFrame) and not audits.empty and "entity_type" in audits.columns:
        # 1. Try to load the new "case_workflow" format
        states = audits[audits["entity_type"].astype(str) == "case_workflow"].copy()
        if not states.empty:
            if "event_at" in states.columns:
                states = states.sort_values("event_at")
            row = states.iloc[-1].to_dict()
            try:
                payload = json.loads(str(row.get("new_value_json", "{}") or "{}"))
                if isinstance(payload, dict):
                    for key in WORKFLOW_KEYS:
                        if key in payload:
                            state[key] = payload[key]
            except Exception:
                pass
        else:
            # 2. Fallback for legacy cases using "case_summary"
            legacy_summaries = audits[audits["entity_type"].astype(str) == "case_summary"].copy()
            if not legacy_summaries.empty:
                if "event_at" in legacy_summaries.columns:
                    legacy_summaries = legacy_summaries.sort_values("event_at")
                row = legacy_summaries.iloc[-1].to_dict()
                try:
                    payload = json.loads(str(row.get("new_value_json", "{}") or "{}"))
                    if isinstance(payload, dict):
                        state["attorney_summary"] = payload
                        state["summary_approved"] = True
                        state["summary_approved_by"] = str(row.get("actor", ""))
                except Exception:
                    pass

    return state

def _frame_ids(frame, candidates):
    if frame is None or frame.empty:
        return []
    for column in candidates:
        if column in frame.columns:
            return sorted(frame[column].fillna("").astype(str).tolist())
    return [str(len(frame))]

def case_fingerprint(data):
    return {
        "documents": _frame_ids(data.get("documents"), ["case_document_id", "document_id"]),
        "pages": _frame_ids(data.get("pages"), ["case_document_page_id", "page_id"]),
        "evidence": _frame_ids(data.get("evidence"), ["case_evidence_id", "evidence_id"]),
        "facts_count": len(best(data, "facts", "fact_candidates")),
        "issues_count": len(best(data, "issues", "issue_candidates")),
    }

def persist_workflow_state(state, data, case_id, action="saved", actor="system", reason=""):
    persist_deep_ui_state(case_id, state)
    audit(
        case_id,
        "case_workflow",
        case_id,
        action,
        actor=actor,
        new_value={key: state.get(key) for key in WORKFLOW_KEYS},
        reason=reason,
    )

def invalidate_for_new_material(state, data, case_id, reason):
    state["case_dirty"] = True
    state["dirty_reason"] = reason

    state["accounting_dirty"] = True
    state["accounting_dirty_reason"] = reason

    # Revoke approval so the pleading pipeline can't proceed on stale sign-off,
    # but keep the actual generated content in place — the review, research,
    # analysis, strategy, memo and pleading versions all stay visible and are
    # simply marked stale by case_dirty / accounting_dirty until refreshed.
    state["summary_approved"] = False
    state["summary_approved_by"] = ""

    persist_workflow_state(
        state,
        data,
        case_id,
        action="invalidated",
        reason=reason,
    )
    
    
def accounting_state(data, state):
    """
    Derives the current accounting stage from persisted accounting data
    and the explicit workflow state.

    An accounting run may legitimately produce zero financial line items,
    so presence of line items must NOT be used as the completion flag —
    accounting_status (set explicitly by the /accounting/* routes below)
    is the single source of truth for "what stage are we at".
    """
    status = str(state.get("accounting_status", "not_started") or "not_started").strip().lower()

    line_items = data.get("financial_line_items")
    has_line_items = isinstance(line_items, pd.DataFrame) and not line_items.empty

    classifications = data.get("financial_classifications")
    has_classifications = isinstance(classifications, pd.DataFrame) and not classifications.empty

    pending_conflicts = _serialise_conflicts(str(data["case"].get("case_id", "")), data.get("pages"))
    has_pending_review = bool(pending_conflicts)

    findings = data.get("forensic_findings") or {}
    discrepancies = data.get("discrepancies") or []
    has_forensic_output = bool(findings or discrepancies)

    return {
        "status": status,
        "dirty": bool(state.get("accounting_dirty")),
        "has_classifications": has_classifications,
        "has_line_items": has_line_items,
        "has_pending_review": has_pending_review,
        "has_forensic_output": has_forensic_output,
    }
# =============================================================================
# PROCEDURAL ORDERING HELPERS
# =============================================================================
def workflow_steps(state, data):
    has_documents = (
        not data["documents"].empty
        and not data["pages"].empty
    )

    accounting = accounting_state(data, state)
    accounting_status = accounting["status"]

    has_accounting = accounting_status in {
        "classified",
        "extracting",
        "needs_review",
        "ready_for_synthesis",
        "normalized",
        "forensic_complete",
        "complete_no_transactions",
    }

    accounting_complete = accounting_status in {
        "forensic_complete",
        "complete_no_transactions",
    }

    has_summary = state["attorney_summary"] is not None

    # In testing mode a prepared summary is enough. In production this
    # becomes formal approval + clean case through approval_gate_passed().
    approved = approval_gate_passed(state)

    has_analysis = state["analysis"] is not None
    has_strategy = state["strategy"] = True
    has_pleading = state["memo"] is not None

    is_final = (
        has_pleading
        and state["pleading_status"] == "final"
    )

    states = [
        {
            "key": "documents",
            "done": has_documents,
        },
        {
            "key": "facts",
            "done": has_documents,
        },
        {
            "key": "review",
            "done": approved,
            "started": has_summary,
        },
        {
            "key": "accounting",
            "done": accounting_complete,
            "started": has_accounting,
            "accounting_status": accounting_status,
            "dirty": accounting["dirty"],
        },
        {
            "key": "analysis",
            "done": has_analysis,
        },
        {
            "key": "pleading",
            "done": has_pleading,
        },
        {
            "key": "final",
            "done": is_final,
        },
        {
            "key": "discussion",
            "done": True,
        },
    ]

    current_found = False

    for step in states:
        if step["done"]:
            step["state"] = "complete"

        elif not current_found:
            step["state"] = "current"
            current_found = True

        else:
            step["state"] = "upcoming"

    return states

def next_action_key(state, data):
    steps = workflow_steps(state, data)
    current = next((item for item in steps if item["state"] == "current"), steps[-1])
    return current["key"]


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
# =============================================================================
def _new_job():
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "progress": {"stage": "", "current": 0, "total": 0, "detail": ""},
            "result": None,
            "error": None,
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


@app.route("/job_status")
def job_status():
    job_id = request.args.get("job_id", "")
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"status": "unknown"}), 404
        payload = {
            "status": job["status"],
            "progress": dict(job["progress"]),
            "error": job["error"],
        }
        if job["status"] == "done":
            payload["result"] = job["result"]
        if job["status"] in {"done", "error"}:
            JOBS.pop(job_id, None)
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



@app.route("/accounting/run_auto_pipeline", methods=["POST"])
def accounting_run_auto_pipeline():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    session_id = body.get("session_id")
    job_id = _new_job()

    def task():
        data = load_case_data(case_id)
        state = restore_workflow_state(data)

        # 1. Get all PAGE IDs
        page_ids = []
        if not data["pages"].empty:
            id_col = "case_document_page_id" if "case_document_page_id" in data["pages"].columns else "page_id"
            page_ids = data["pages"][id_col].dropna().astype(str).tolist()

        if not page_ids:
            return {"rows_persisted": 0}

        # 2. Run Page-Level Classification
        _set_progress(job_id, stage="classify", detail=f"1/2: Classifying {len(page_ids)} pages...")
        classify_case_pages(case_id, page_ids)

        # 3. Filter only financial & mixed pages
        refreshed = load_case_data(case_id)
        classifications = _latest_classifications_by_page(refreshed)
        
        financial_page_ids = []
        for pid, cls_data in classifications.items():
            if cls_data.get("page_type", "") in ["financial", "mixed"]:
                financial_page_ids.append(pid)

        # 4. Run Extraction on filtered pages
        rows_persisted = 0
        if financial_page_ids:
            def _on_progress(current, total, page_id):
                _set_progress(
                    job_id, stage="extraction", current=current, total=total,
                    detail=f"2/2: Extracting financial data (Page {current} of {total})..."
                )
            _set_progress(job_id, stage="extraction", detail="2/2: Extracting financial data...")
            result = run_financial_extraction(case_id, financial_page_ids, progress_callback=_on_progress)
            rows_persisted = result.get("rows_persisted", 0) if isinstance(result, dict) else 0

        if session_id:
                    increment_usage(session_id, "llm_request_count", 2)
        
        import time
        time.sleep(2.5) 
        final_data = load_case_data(case_id)
        state = restore_workflow_state(final_data)
        pending = _serialise_conflicts(case_id, final_data.get("pages"))

        # Look at the actual database using BOTH possible keys to be 100% safe
        line_items_df = final_data.get("financial_line_items")
        if line_items_df is None:
            line_items_df = final_data.get("fin_line_items")
            
        has_items = line_items_df is not None and not line_items_df.empty

        if pending:
            state["accounting_status"] = "needs_review"
        elif has_items or rows_persisted > 0:
            state["accounting_status"] = "ready_for_synthesis"
        else:
            state["accounting_status"] = "complete_no_transactions"

        persist_workflow_state(state, final_data, case_id, action="accounting_auto_pipeline_complete")
        return {"rows_persisted": rows_persisted}
    
    _run_async(job_id, task, session_id=session_id)
    return jsonify({"job_id": job_id})

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
    response["workflow_state"] = state
    response["steps"] = workflow_steps(state, data)
    response["next_action_key"] = next_action_key(state, data)
    response["chat_messages"] = serialise_chat_messages(data)
    response["facts_register"] = serialise_facts_register(data)
    response["summary_support"] = serialise_summary_support(state.get("attorney_summary") or {}, data)

# --- accounting section ---
    accounting_meta = accounting_state(data, state)
    classifications_by_page = _latest_classifications_by_page(data) # <--- Use the new page function
    
    response["accounting"] = {
        "status": accounting_meta["status"],
        "dirty": accounting_meta["dirty"],
        "has_classifications": accounting_meta["has_classifications"],
        "has_line_items": accounting_meta["has_line_items"],
        "has_pending_review": accounting_meta["has_pending_review"],
        "documents": [
            {
                "case_document_id": str(row.get("case_document_id", "")),
                "original_filename": row.get("original_filename") or row.get("case_document_id", ""),
                # Since we classify by page now, we leave the document-level UI badge blank
                "classification": {}, 
            }
            for row in frame_to_records(data["documents"])
        ],
        "pending_conflicts": _serialise_conflicts(case_id, data["pages"]),
        "normalized_ledger": _build_normalized_ledger(case_id, data["financial_line_items"]),
        "cross_check_summary": data.get("cross_check_summary") or {},
        "discrepancies": data.get("discrepancies") or [],
        "findings": data.get("forensic_findings") or {},
    }
    return _ok(response)
def _load_state(case_id):
    data = load_case_data(case_id)
    return data, restore_workflow_state(data)


@app.route("/state/persist", methods=["POST"])
def state_persist():
    body = request.get_json(force=True)
    case_id = str(body.get("case_id", ""))
    state = body.get("state", {})
    if not case_id:
        return jsonify({"error": "case_id required"}), 400
    persist_deep_ui_state(case_id, state)
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
    case_id = request.form.get("case_id", "")
    file_purpose = request.form.get("file_purpose", "full_case")
    session_id = request.form.get("session_id")
    render_zoom = 1.6
    uploaded = request.files.getlist("files")
    payloads = [(f.filename, f.read(), f.mimetype) for f in uploaded]
    job_id = _new_job()

    def task():
        total_pages, usable_pages = 0, 0
        totals = {"facts": 0, "issues": 0, "parties": 0, "events": 0, "evidence_requests": 0}
        status_counts, failure_notes = {}, []
        llm_call_count = 0

        for name, raw, content_type in payloads:
            document_row, pdf_bytes = save_upload(
                case_id, _MemoryUpload(name, raw, content_type), document_type=file_purpose
            )
            def update_progress(current, total, page_number, state, _name=name):
                _set_progress(job_id, stage="extract", current=current, total=total,
                              detail=f"{_name}: page {page_number}/{total} — {state}")
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
                case_map = build_case_map(completed_pages)
                llm_call_count += 1
                counts = persist_case_map(case_id, case_map)
                for key in totals:
                    totals[key] += int(counts.get(key, 0) or 0)

        if llm_call_count:
            increment_usage(session_id, "llm_request_count", llm_call_count)
        if payloads:
            increment_usage(session_id, "attachment_count", len(payloads))

        data = load_case_data(case_id)
        state = restore_workflow_state(data)
        invalidate_for_new_material(state, data, case_id, "New document or evidence was uploaded.")

        return {
            "files": len(payloads),
            "usable": usable_pages,
            "total": total_pages,
            "page_status": status_counts,
            "page_errors": failure_notes[:3],
            **totals,
        }

    _run_async(job_id, task, session_id=session_id)
    return jsonify({"job_id": job_id})


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
# Accounting & forensic dispute analysis
#
# Same pipeline as the Streamlit "Accounting analysis" tab:
#   1. classify_case_pages            (Stage 2 — optional, manual trigger)
#   2. run_financial_extraction       (Stage 3 — dual-resolution OCR + reconcile)
#   3. submit_correction              (manual conflict resolution)
#   4. normalize_row_for_ledger       (per-row, done on every /case read)
#   5. build_and_save_financial_timeline + run_discrepancy_and_findings_analysis
# The normalized ledger, conflicts, timeline and findings are all
# returned as part of /case (see case_endpoint) so the tab renders from
# the same snapshot as everything else; these routes only perform writes.
# ============================================================
@app.route("/accounting/classify_documents", methods=["POST"])
def accounting_classify_documents():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    session_id = body.get("session_id")
    job_id = _new_job()

    def task():
        data = load_case_data(case_id)
        pages = data["pages"]
        id_col = "case_document_page_id" if "case_document_page_id" in pages.columns else "page_id"
        page_ids = pages[id_col].dropna().astype(str).tolist() if not pages.empty else []
        _set_progress(job_id, stage="classify", detail="Classifying financial pages…")
        classify_case_pages(case_id, page_ids)
        ### Added by Youssif for Monitoring Purposes ###
        increment_usage(session_id, "llm_request_count", 1)
        ### END ###
        return {"classified_pages": len(page_ids)}
    ### Youssif added session_id here ##
    _run_async(job_id, task, session_id=session_id)
    return jsonify({"job_id": job_id})


@app.route("/accounting/clear", methods=["POST"])
def accounting_clear():
    body = request.get_json(force=True)
    case_id = str(body.get("case_id", ""))
    if not case_id:
        return jsonify({"error": "case_id is required"}), 400
    for dataset_name in [
        FINANCIAL_LINE_ITEMS_DATASET,
        FINANCIAL_LINE_ITEM_CORRECTIONS_DATASET,
        FINANCIAL_TIMELINE_DATASET,
        FINANCIAL_DISCREPANCIES_DATASET,
        FINANCIAL_FINDINGS_DATASET,
        FINANCIAL_DOCUMENT_CLASSIFICATION_DATASET,  # was missing
    ]:
        try:
            dataset = dataiku.Dataset(dataset_name)
            frame = dataset.get_dataframe()
            if not frame.empty and "case_id" in frame.columns:
                dataset.write_with_schema(frame[frame["case_id"].astype(str) != case_id])
        except Exception:
            traceback.print_exc()

    data = load_case_data(case_id)
    state = restore_workflow_state(data)
    state["accounting_status"] = "not_started"
    state["accounting_dirty"] = False
    state["accounting_dirty_reason"] = ""
    persist_workflow_state(state, data, case_id, action="accounting_cleared")

    return _ok({"cleared": True})

@app.route("/accounting/extract", methods=["POST"])
def accounting_extract():
    body = request.get_json(force=True)

    case_id = str(body.get("case_id", "")).strip()
    document_ids = [
        str(doc_id).strip()
        for doc_id in (body.get("document_ids") or [])
        if str(doc_id).strip()
    ]
    session_id = body.get("session_id")

    if not case_id:
        return jsonify({"error": "case_id is required"}), 400

    if not document_ids:
        return jsonify({"error": "At least one document must be selected."}), 400

    job_id = _new_job()

    def task():
        # ---------------------------------------------------------
        # 1. Load current case
        # ---------------------------------------------------------
        data = load_case_data(case_id)
        pages = data["pages"]

        if pages.empty:
            raise ValueError("No document pages are available for extraction.")

        page_id_col = (
            "case_document_page_id"
            if "case_document_page_id" in pages.columns
            else "page_id"
        )

        doc_id_col = (
            "case_document_id"
            if "case_document_id" in pages.columns
            else "document_id"
        )

        if doc_id_col not in pages.columns:
            raise ValueError(
                "Could not identify the document ID column in case pages."
            )

        # ---------------------------------------------------------
        # 2. Keep only pages belonging to documents selected by user
        # ---------------------------------------------------------
        selected_pages = pages[
            pages[doc_id_col].astype(str).isin(document_ids)
        ]

        if selected_pages.empty:
            raise ValueError(
                "No pages were found for the selected documents."
            )

        # ---------------------------------------------------------
        # 3. From selected documents, extract only
        #    FINANCIAL or MIXED pages
        # ---------------------------------------------------------
        classifications = _latest_classifications_by_page(data)

        financial_page_ids = []

        for _, row in selected_pages.iterrows():
            page_id = str(row.get(page_id_col, "")).strip()

            if not page_id:
                continue

            classification = classifications.get(page_id, {})
            page_type = str(
                classification.get("page_type", "")
            ).lower().strip()

            if page_type in {"financial", "mixed"}:
                financial_page_ids.append(page_id)

        if not financial_page_ids:
            raise ValueError(
                "No financial or mixed pages were found "
                "in the selected documents. Run classification first."
            )

        # ---------------------------------------------------------
        # 4. Mark accounting as extracting
        # ---------------------------------------------------------
        state = restore_workflow_state(data)
        state["accounting_status"] = "extracting"

        persist_workflow_state(
            state,
            data,
            case_id,
            action="accounting_extraction_started",
        )

        # ---------------------------------------------------------
        # 5. Run financial extraction
        # ---------------------------------------------------------
        def _on_progress(current, total, page_id):
            _set_progress(
                job_id,
                stage="extraction",
                current=current,
                total=total,
                detail=(
                    f"Extracting financial data "
                    f"(page {current} of {total})..."
                ),
            )

        _set_progress(
            job_id,
            stage="extraction",
            current=0,
            total=len(financial_page_ids),
            detail=(
                f"Extracting financial data from "
                f"{len(financial_page_ids)} financial pages..."
            ),
        )

        result = run_financial_extraction(
            case_id,
            financial_page_ids,
            progress_callback=_on_progress,
        )

        rows_persisted = (
            result.get("rows_persisted", 0)
            if isinstance(result, dict)
            else 0
        )

        # ---------------------------------------------------------
        # 6. Reload persisted results
        # ---------------------------------------------------------
        final_data = load_case_data(case_id)
        state = restore_workflow_state(final_data)

        pending = _serialise_conflicts(
            case_id,
            final_data.get("pages"),
        )

        line_items_df = final_data.get("financial_line_items")

        has_items = (
            line_items_df is not None
            and not line_items_df.empty
        )

        # ---------------------------------------------------------
        # 7. Decide next accounting stage
        # ---------------------------------------------------------
        if pending:
            state["accounting_status"] = "needs_review"

        elif has_items or rows_persisted > 0:
            state["accounting_status"] = "ready_for_synthesis"

        else:
            state["accounting_status"] = "complete_no_transactions"

        state["accounting_dirty"] = False
        state["accounting_dirty_reason"] = ""

        persist_workflow_state(
            state,
            final_data,
            case_id,
            action="accounting_extraction_complete",
        )

        if session_id:
            increment_usage(
                session_id,
                "llm_request_count",
                1,
            )

        return {
            "rows_persisted": rows_persisted,
            "pages_extracted": len(financial_page_ids),
            "pending_conflicts": len(pending),
            "accounting_status": state["accounting_status"],
        }

    _run_async(
        job_id,
        task,
        session_id=session_id,
    )

    return jsonify({"job_id": job_id})



@app.route("/accounting/correction", methods=["POST"])
def accounting_correction():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    row_id = str(body.get("row_id", ""))
    field_name = str(body.get("field_name", ""))
    value = body.get("value", "")
    corrected_by = str(body.get("corrected_by", "") or "attorney")
    if not (case_id and row_id and field_name):
        return jsonify({"error": "case_id, row_id and field_name are required."}), 400

    submit_correction(case_id, row_id, field_name, value, corrected_by=corrected_by)

    data = load_case_data(case_id)
    state = restore_workflow_state(data)
    if str(state.get("accounting_status", "")).lower() == "needs_review":
        pending = _serialise_conflicts(case_id, data.get("pages"))
        if not pending:
            state["accounting_status"] = "ready_for_synthesis"
            persist_workflow_state(state, data, case_id, action="accounting_conflicts_resolved")

    return _ok({"saved": True})


@app.route("/accounting/synthesize", methods=["POST"])
def accounting_synthesize():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    instructions = body.get("instructions", "")
    session_id = body.get("session_id")
    job_id = _new_job()

    def task():
        data = load_case_data(case_id)
        state = restore_workflow_state(data)
        line_items_df = data["financial_line_items"]
        if line_items_df.empty:
            raise ValueError("No extracted line items available. Run extraction first.")
            
        normalized_ledger = _build_normalized_ledger(case_id, line_items_df)
        
        # Pull claims from the attorney summary allegations
        summary = state.get("attorney_summary", {})
        customer_claims = summary.get("allegations", [])
        
        _set_progress(job_id, stage="timeline", detail="Building chronological timeline…")
        build_and_save_financial_timeline(case_id, normalized_ledger)
        
        _set_progress(job_id, stage="findings", detail="Evaluating claims against financial ledger…")
        # Call the new claim-based engine
        from legal_platform.financial_forensics import run_claim_based_accounting_analysis
        run_claim_based_accounting_analysis(case_id, normalized_ledger, customer_claims, instructions)
        
        if session_id:
            increment_usage(session_id, "llm_request_count", 1)

        refreshed = load_case_data(case_id)
        state = restore_workflow_state(refreshed)
        state["accounting_status"] = "forensic_complete" if normalized_ledger else "complete_no_transactions"
        persist_workflow_state(state, refreshed, case_id, action="accounting_synthesized")

        return {"findings": refreshed.get("forensic_findings") or {}}

    _run_async(job_id, task, session_id=session_id)
    return jsonify({"job_id": job_id})
# =============================================================================
# SUMMARY, ANALYSIS & WRITTEN PLEADING ENDPOINTS
# =============================================================================
@app.route("/summary/prepare", methods=["POST"])
def summary_prepare():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    session_id = body.get("session_id")
    job_id = _new_job()

    def task():
            data = load_case_data(case_id)
            state = restore_workflow_state(data)
            _set_progress(job_id, stage="summary", detail="Preparing consolidated attorney review…")

            # Get classifications to find claim/mixed pages
            classifications = _latest_classifications_by_page(data)
            claim_page_ids = [
                pid for pid, cls in classifications.items() 
                if cls.get("page_type") in ["claim", "mixed"]
            ]

            # Filter pages: if we found claim pages, use them. If none found, fallback to all pages.
            if claim_page_ids and not data["pages"].empty:
                id_col = "case_document_page_id" if "case_document_page_id" in data["pages"].columns else "page_id"
                filtered_pages = data["pages"][data["pages"][id_col].astype(str).isin(claim_page_ids)]
            else:
                filtered_pages = data["pages"]

            summary = generate_case_summary(
                case_record=data["case"],
                pages=filtered_pages,  # <--- NOW ONLY PASSES CLAIM PAGES!
                facts=best(data, "facts", "fact_candidates"),
                evidence=data["evidence"],
                parties=data["parties"],
                events=data["events"],
                force_rerun=True,
            )

            if session_id:
                increment_usage(session_id, "llm_request_count", 1)
                increment_usage(session_id, "message_count", 1)

            state["attorney_summary"] = summary
            state["summary_approved"] = False
            persist_workflow_state(state, data, case_id, action="summary_prepared")
            response_summary = dict(summary)
            if data.get("forensic_findings"):
                response_summary["forensic_findings"] = data["forensic_findings"]

            return {"attorney_summary": response_summary, "summary_support": serialise_summary_support(summary, data)}
    _run_async(job_id, task, session_id=session_id)
    return jsonify({"job_id": job_id})

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
    state["summary_approved"] = True
    state["summary_approved_by"] = reviewer
    state["case_dirty"] = False
    state["dirty_reason"] = ""
    persist_workflow_state(state, data, case_id, action="summary_approved", actor=reviewer)
    return _ok({"approval_id": approval_record["approval_id"], "workflow_state": state})

@app.route("/analysis/run", methods=["POST"])
def analysis_run():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    session_id = body.get("session_id")
    job_id = _new_job()

    def task():
        data = load_case_data(case_id)
        state = restore_workflow_state(data)
        if not approval_gate_passed(state):
            raise ValueError(
                "Prepare the consolidated attorney review first."
                if not REQUIRE_APPROVED_SUMMARY
                else "Approve the consolidated attorney review first."
            )
        facts = best(data, "facts", "fact_candidates")
        issues = best(data, "issues", "issue_candidates")
        if facts.empty or issues.empty:
            raise ValueError("Extracted facts and issues are required.")
        _set_progress(job_id, stage="analysis", detail="Retrieving SAMA authorities and evaluating legal defenses…")
        result = run_legal_analysis(data["case"], facts, issues, data["evidence"])
        if session_id:
            increment_usage(session_id, "llm_request_count", 1)
            increment_usage(session_id, "message_count", 1)
        state["research"] = result["research"]
        state["analysis"] = result["analysis"]
        persist_workflow_state(state, data, case_id, action="analysis_prepared")
        return {"research": state["research"], "analysis": state["analysis"]}

    _run_async(job_id, task, session_id=session_id)
    return jsonify({"job_id": job_id})


@app.route("/analysis/defence_plan", methods=["POST"])
def analysis_defence_plan():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    session_id = body.get("session_id")
    job_id = _new_job()

    def task():
        data = load_case_data(case_id)
        state = restore_workflow_state(data)
        if not approval_gate_passed(state):
            raise ValueError(
                "Prepare the consolidated attorney review first."
                if not REQUIRE_APPROVED_SUMMARY
                else "Approve the consolidated attorney review first."
            )
        _set_progress(job_id, stage="defence", detail="Developing defence plan…")
        strategy = run_defence_plan(
            data["case"], state["analysis"], best(data, "facts", "fact_candidates"),
            data["evidence"], state["research"]["authority_nodes"],
        )
        if session_id:
            increment_usage(session_id, "llm_request_count", 1)
            increment_usage(session_id, "message_count", 1)
        state["strategy"] = strategy
        persist_workflow_state(state, data, case_id, action="defence_plan_prepared")
        return {"strategy": strategy}

    _run_async(job_id, task, session_id=session_id)
    return jsonify({"job_id": job_id})


@app.route("/pleading/generate", methods=["POST"])
def pleading_generate():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    memo_instructions = body.get("instructions", "")
    direct = bool(body.get("direct", False))
    session_id = body.get("session_id")
    job_id = _new_job()

    def task():
        data = load_case_data(case_id)
        state = restore_workflow_state(data)
    
        # ---------------------------------------------------------
        # 1. Attorney review must be approved
        # ---------------------------------------------------------
        if not approval_gate_passed(state):
            raise ValueError(
                "Prepare the consolidated attorney review first."
                if not REQUIRE_APPROVED_SUMMARY
                else "Approve the consolidated attorney review first."
            )
    
        # ---------------------------------------------------------
        # 2. Legal analysis must be completed
        # ---------------------------------------------------------
        if not state.get("analysis"):
            raise ValueError(
                "Complete the legal analysis before generating the written pleading."
            )
    
        # ---------------------------------------------------------
        # 3. Accounting analysis must be completed
        # ---------------------------------------------------------
        accounting = accounting_state(data, state)
    
        if accounting["status"] not in {
            "forensic_complete",
            "complete_no_transactions",
        }:
            raise ValueError(
                "Complete the accounting analysis before generating the written pleading."
            )
    
        case = data["case"]
        _set_progress(job_id, stage="pleading", detail="Synthesizing bilingual court pleading…")
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
        state["memo"] = memo
        note = "Initial approved-summary draft" if direct else (memo_instructions or "Initial pleading draft")
        state["pleading_versions"] = [{"version": 1, "draft": memo, "note": note}]
        state["pleading_status"] = "draft"
        state["pleading_finalised_by"] = ""
        persist_workflow_state(state, data, case_id, action="pleading_prepared")
        return {"memo": memo, "pleading_versions": state["pleading_versions"], "pleading_status": "draft"}

    _run_async(job_id, task, session_id=session_id)
    return jsonify({"job_id": job_id})


@app.route("/pleading/revise", methods=["POST"])
def pleading_revise():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    revision_request = body.get("revision_request", "")
    session_id = body.get("session_id")
    job_id = _new_job()

    def task():
        data = load_case_data(case_id)
        state = restore_workflow_state(data)
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
        version_no = len(state["pleading_versions"]) + 1
        state["memo"] = revised
        state["pleading_versions"].append({"version": version_no, "draft": revised, "note": revision_request})
        state["pleading_status"] = "draft"
        persist_workflow_state(state, data, case_id, action="pleading_revised", reason=revision_request)
        return {
            "memo": revised,
            "pleading_versions": state["pleading_versions"],
            "pleading_status": "draft",
            "version": version_no,
        }

    _run_async(job_id, task, session_id=session_id)
    return jsonify({"job_id": job_id})


@app.route("/pleading/restore_version", methods=["POST"])
def pleading_restore_version():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    selected_version = body.get("version")
    data, state = _load_state(case_id)
    selected = next((v for v in state["pleading_versions"] if v["version"] == selected_version), None)
    if not selected:
        return jsonify({"error": "version not found"}), 404
    version_no = len(state["pleading_versions"]) + 1
    state["memo"] = selected["draft"]
    state["pleading_versions"].append({
        "version": version_no, "draft": selected["draft"],
        "note": f"Restored from version {selected_version}",
    })
    persist_workflow_state(state, data, case_id, action="pleading_version_restored")
    return _ok({"memo": state["memo"], "pleading_versions": state["pleading_versions"]})


@app.route("/pleading/mark_final", methods=["POST"])
def pleading_mark_final():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    final_reviewer = str(body.get("final_reviewer", "")).strip()
    if not final_reviewer:
        return jsonify({"error": "final_reviewer is required"}), 400
    data, state = _load_state(case_id)
    state["pleading_status"] = "final"
    state["pleading_finalised_by"] = final_reviewer
    persist_workflow_state(state, data, case_id, action="pleading_finalised", actor=final_reviewer)
    return jsonify({"pleading_status": "final", "pleading_finalised_by": final_reviewer})


@app.route("/pleading/reopen", methods=["POST"])
def pleading_reopen():
    body = request.get_json(force=True)
    case_id = body.get("case_id", "")
    data, state = _load_state(case_id)
    state["pleading_status"] = "draft"
    state["pleading_finalised_by"] = ""
    persist_workflow_state(state, data, case_id, action="pleading_reopened")
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
    job_id = _new_job()

    def task():
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

    _run_async(job_id, task, session_id=session_id)
    return jsonify({"job_id": job_id})


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
