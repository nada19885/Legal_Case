"""
Case workflow state and per-stage status.
Location: lib/python/legal_platform/workflow.py

The litigation workflow is a set of stages that read each other's outputs:

    documents ─┬─> review ──> analysis ─┐
               └─> accounting ──────────┴─> pleading ──> discussion

Each stage keeps a small status record inside the case workflow state
(state["stages"][key]) that says what it is doing now, when it last
finished, and why it failed if it did. The heavy outputs (analysis, memo,
ledger rows...) stay where they already live; this module only tracks
progress and decides what the user sees.

Persistence: each case's state is one small JSON file in the case
documents managed folder (workflow_state/<case_id>.json), read and written
per case. audit_events receives a short entry per change (what changed,
stage statuses), never the full state: the state holds the legal research,
analysis and pleading versions and can be several MB, and appending it on
every update made audit_events grow to GBs that every read had to scan.
Cases saved the old way are migrated on first read.

Every update is a merge applied to the *latest* stored state under a
process lock, so two background jobs finishing at the same time can no
longer overwrite each other's results.
"""

from __future__ import annotations

import copy
import json
import re
import threading
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

import dataiku

from .audit import audit
from .config import APPROVALS_DATASET, AUDIT_DATASET, CASE_DOCUMENT_FOLDER_ID
from .storage import case_rows

STATE_FOLDER_DIR = "workflow_state"

# -----------------------------------------------------------------------------
# Stage vocabulary
# -----------------------------------------------------------------------------
STAGE_KEYS = ("documents", "review", "accounting", "analysis", "pleading", "discussion")

# Stages whose completed output feeds the key stage. When a dependency
# finishes after the stage did, the stage's output is stale.
STAGE_DEPENDENCIES = {
    "documents": (),
    "review": ("documents",),
    "accounting": ("documents",),
    "analysis": ("review",),
    "pleading": ("analysis", "accounting"),
    "discussion": ("documents",),
}

NOT_STARTED = "not_started"
BLOCKED = "blocked"
RUNNING = "running"
WAITING = "waiting_for_user"
READY = "ready"
COMPLETED = "completed"
STALE = "stale"
ERROR = "error"

# Accounting sub-status values written by the /accounting/* routes.
ACCOUNTING_COMPLETE = {"forensic_complete", "complete_no_transactions"}

INTERRUPTED_ERROR = (
    "The job stopped before finishing (the server restarted or the worker "
    "was lost). Run this step again."
)

WORKFLOW_KEYS = (
    "attorney_summary",
    "summary_approved",
    "summary_approved_by",

    "accounting_status",
    "accounting_dirty",
    "accounting_dirty_reason",
    "accounting_instructions",
    "accounting_facts_confirmed",
    "accounting_facts_confirmed_by",
    "accounting_facts_confirmed_at",

    "research",
    "analysis",
    "strategy",
    "memo",
    "pleading_versions",
    "pleading_status",
    "pleading_finalised_by",
    "pleading_language",

    "case_dirty",
    "dirty_reason",

    "stages",
)

_STATE_LOCK = threading.RLock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def blank_workflow_state() -> dict:
    return {
        "attorney_summary": None,
        "summary_approved": False,
        "summary_approved_by": "",

        # Accounting lifecycle
        "accounting_status": "not_started",
        "accounting_dirty": False,
        "accounting_dirty_reason": "",
        "accounting_instructions": "",
        "accounting_facts_confirmed": False,
        "accounting_facts_confirmed_by": "",
        "accounting_facts_confirmed_at": "",

        "research": None,
        "analysis": None,
        "strategy": None,
        "memo": None,
        "pleading_versions": [],
        "pleading_status": "draft",
        "pleading_finalised_by": "",
        "pleading_language": "",

        "case_dirty": False,
        "dirty_reason": "",

        "stages": {},
    }


# -----------------------------------------------------------------------------
# Restore
# -----------------------------------------------------------------------------
def _latest_json(frame: Any, value_column: str, sort_column: str) -> Optional[dict]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return None
    working = frame.sort_values(sort_column, kind="stable") if sort_column in frame.columns else frame
    for _, row in working.iloc[::-1].iterrows():
        try:
            payload = json.loads(str(row.get(value_column, "") or "{}"))
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def restore_workflow_state(audits: Any, approvals: Any = None) -> dict:
    """Latest workflow state for a case from its audit rows.

    Order of preference:
      1. the newest audit_events row with entity_type == "case_workflow"
         (every update writes one);
      2. the legacy UI_STATE_MANAGER record in case_approvals (cases saved
         before workflow updates became append-only);
      3. the legacy "case_summary" audit row (oldest cases).
    """
    state = blank_workflow_state()

    if isinstance(audits, pd.DataFrame) and not audits.empty and "entity_type" in audits.columns:
        entity = audits["entity_type"].astype(str)
        payload = _latest_json(audits[entity == "case_workflow"], "new_value_json", "event_at")
        if payload is not None:
            for key in WORKFLOW_KEYS:
                if key in payload:
                    state[key] = payload[key]
            return _normalise(state)

    if isinstance(approvals, pd.DataFrame) and not approvals.empty and "approved_by" in approvals.columns:
        ui_states = approvals[approvals["approved_by"].astype(str) == "UI_STATE_MANAGER"]
        payload = _latest_json(ui_states, "summary_json", "timestamp")
        if payload is not None:
            state.update({key: payload[key] for key in WORKFLOW_KEYS if key in payload})
            return _normalise(state)

    if isinstance(audits, pd.DataFrame) and not audits.empty and "entity_type" in audits.columns:
        legacy = audits[audits["entity_type"].astype(str) == "case_summary"]
        payload = _latest_json(legacy, "new_value_json", "event_at")
        if payload is not None:
            state["attorney_summary"] = payload
            state["summary_approved"] = True
            state["summary_approved_by"] = str(legacy.iloc[-1].get("actor", "") or "")

    return _normalise(state)


def _normalise(state: dict) -> dict:
    # Legacy bug: workflow_steps() once assigned strategy = True.
    if state.get("strategy") is True:
        state["strategy"] = None
    if not isinstance(state.get("stages"), dict):
        state["stages"] = {}
    if not isinstance(state.get("pleading_versions"), list):
        state["pleading_versions"] = []
    return state


_STATE_CACHE: dict = {}


def _state_path(case_id: str) -> str:
    return f"/{STATE_FOLDER_DIR}/{re.sub(r'[^A-Za-z0-9_.-]', '_', str(case_id))}.json"


def _load_state_file(case_id: str) -> Optional[dict]:
    try:
        folder = dataiku.Folder(CASE_DOCUMENT_FOLDER_ID)
        with folder.get_download_stream(_state_path(case_id)) as stream:
            payload = json.loads(stream.read().decode("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _save_state_file(case_id: str, state: dict) -> bool:
    try:
        folder = dataiku.Folder(CASE_DOCUMENT_FOLDER_ID)
        data = json.dumps({key: state.get(key) for key in WORKFLOW_KEYS}, ensure_ascii=False, default=str)
        folder.upload_data(_state_path(case_id), data.encode("utf-8"))
        return True
    except Exception as error:
        print(f"[workflow state] could not save state file for {case_id}: {error!r}", flush=True)
        return False


def read_workflow_state(case_id: str) -> dict:
    """Latest state for one case: process cache -> state file -> legacy
    audit/approvals rows (read once, then migrated to the state file)."""
    case_id = str(case_id)
    with _STATE_LOCK:
        cached = _STATE_CACHE.get(case_id)
        if cached is not None:
            return copy.deepcopy(cached)

        payload = _load_state_file(case_id)
        if payload is not None:
            state = blank_workflow_state()
            state.update({key: payload[key] for key in WORKFLOW_KEYS if key in payload})
            state = _normalise(state)
        else:
            state = restore_workflow_state(
                case_rows(AUDIT_DATASET, case_id),
                case_rows(APPROVALS_DATASET, case_id),
            )
            _save_state_file(case_id, state)

        _STATE_CACHE[case_id] = copy.deepcopy(state)
        return state


def _audit_summary(before: dict, after: dict) -> dict:
    """What an update changed, small enough for audit_events."""
    changed = [key for key in WORKFLOW_KEYS if key != "stages" and before.get(key) != after.get(key)]
    stages = {
        key: {field: record.get(field) for field in ("status", "phase", "detail", "error")}
        for key, record in (after.get("stages") or {}).items()
        if record != (before.get("stages") or {}).get(key)
    }
    small = {key: after.get(key) for key in changed
             if isinstance(after.get(key), (str, int, float, bool)) or after.get(key) is None}
    return {"changed_keys": changed, "stages": stages, "values": small}


# -----------------------------------------------------------------------------
# Update
# -----------------------------------------------------------------------------
def merge_state(state: dict, changes: Optional[dict] = None, stages: Optional[dict] = None) -> dict:
    """Pure merge used by update_workflow_state: top-level keys replace,
    stage records merge field by field."""
    merged = copy.deepcopy(state)
    for key, value in (changes or {}).items():
        if key == "stages":
            continue
        merged[key] = value

    now = utc_now()
    all_stages = merged.setdefault("stages", {})
    for key, patch in (stages or {}).items():
        record = dict(all_stages.get(key) or {})
        if patch and all(record.get(field) == value for field, value in patch.items()):
            continue  # nothing new: keep the record (and its timestamps) as is
        record.update(patch or {})
        status = record.get("status")
        record["updated_at"] = now
        if status == RUNNING and "started_at" not in (patch or {}):
            record["started_at"] = now
            record["error"] = ""
        if status in {COMPLETED, READY, WAITING} and "finished_at" not in (patch or {}):
            record["finished_at"] = now
            record["error"] = ""
        if status != RUNNING and "job_id" not in (patch or {}):
            record.pop("job_id", None)
        all_stages[key] = record
    return merged


def update_workflow_state(
    case_id: str,
    changes: Optional[dict] = None,
    stages: Optional[dict] = None,
    action: str = "saved",
    actor: str = "system",
    reason: str = "",
) -> dict:
    """Apply changes to the latest stored state and persist it.

    Only the keys in `changes` (and the stage records in `stages`) are
    touched, so concurrent jobs that each update their own keys keep
    each other's results. An update that changes nothing is not written.

    The full state goes to the case's state file; audit_events only gets a
    summary of what changed. If the state file cannot be written, the full
    state is written to audit_events as before, so nothing is lost.
    """
    case_id = str(case_id)
    with _STATE_LOCK:
        current = read_workflow_state(case_id)
        merged = merge_state(current, changes, stages)
        if all(merged.get(key) == current.get(key) for key in WORKFLOW_KEYS):
            return current

        if _save_state_file(case_id, merged):
            audit_value = _audit_summary(current, merged)
            entity = "case_workflow_change"
        else:
            audit_value = {key: merged.get(key) for key in WORKFLOW_KEYS}
            entity = "case_workflow"
        _STATE_CACHE[case_id] = copy.deepcopy(merged)
        audit(case_id, entity, case_id, action, actor=actor, new_value=audit_value, reason=reason)
        return merged


def stage_patch(status: str, phase: str = "", detail: str = "", error: str = "", **extra) -> dict:
    patch = {"status": status, "phase": phase, "detail": detail, "error": error}
    patch.update(extra)
    return patch


# -----------------------------------------------------------------------------
# Status overview
# -----------------------------------------------------------------------------
def _derived_status(key: str, facts: dict) -> tuple[str, str, list]:
    """(status, detail, blocked_by) from stored outputs alone."""
    has_documents = bool(facts.get("has_documents"))
    accounting = facts.get("accounting") or {}

    if key == "documents":
        return (COMPLETED if has_documents else NOT_STARTED), "", []

    if key == "review":
        if not has_documents:
            return BLOCKED, "", ["documents"]
        if not facts.get("has_summary"):
            return NOT_STARTED, "", []
        if facts.get("gate_passed"):
            return (STALE if facts.get("case_dirty") else COMPLETED), "", []
        return WAITING, "approve_summary", []

    if key == "accounting":
        if not has_documents:
            return BLOCKED, "", ["documents"]
        pending = int(accounting.get("pending_count") or 0)
        status = str(accounting.get("status") or "not_started")
        if pending:
            return WAITING, "review_items", []
        if accounting.get("has_line_items") and not accounting.get("facts_confirmed") \
                and status not in ACCOUNTING_COMPLETE:
            return WAITING, "confirm_facts", []
        if status in ACCOUNTING_COMPLETE:
            return (STALE if accounting.get("dirty") else COMPLETED), status, []
        if status == "ready_for_synthesis" or accounting.get("has_line_items"):
            return READY, "ready_for_analysis", []
        return NOT_STARTED, "", []

    if key == "analysis":
        if not facts.get("gate_passed"):
            return BLOCKED, "", ["review"]
        if facts.get("has_analysis"):
            return (STALE if facts.get("case_dirty") else COMPLETED), "", []
        return NOT_STARTED, "", []

    if key == "pleading":
        blocked = []
        if not facts.get("has_analysis"):
            blocked.append("analysis")
        if str(accounting.get("status") or "") not in ACCOUNTING_COMPLETE or accounting.get("pending_count"):
            blocked.append("accounting")
        if facts.get("has_memo"):
            # A pleading whose inputs have since been cleared or reopened
            # is kept, but no longer reflects the current analysis.
            if blocked:
                return STALE, "inputs_missing", blocked
            final = facts.get("pleading_status") == "final"
            return COMPLETED, ("final" if final else "draft"), []
        if blocked:
            return BLOCKED, "", blocked
        return NOT_STARTED, "", []

    if key == "discussion":
        if not has_documents:
            return BLOCKED, "", ["documents"]
        return READY, "", []

    return NOT_STARTED, "", []


def build_stage_overview(facts: dict) -> dict:
    """Combine stored outputs, persisted stage records and live jobs into
    the list of stages the UI shows.

    facts keys: has_documents, has_summary, gate_passed, case_dirty,
    has_analysis, has_memo, pleading_status, accounting{status,
    pending_count, has_line_items, dirty}, stages (persisted records),
    active_jobs {stage_key: {job_id, progress}}, register_fingerprint
    (the current case register; a stage built on another one is stale).
    """
    persisted = facts.get("stages") or {}
    active = facts.get("active_jobs") or {}
    result = []

    for key in STAGE_KEYS:
        record = dict(persisted.get(key) or {})
        status, detail, blocked_by = _derived_status(key, facts)
        entry = {
            "key": key,
            "status": status,
            "detail": detail,
            "phase": "",
            "error": "",
            "progress": None,
            "blocked_by": blocked_by,
            "finished_at": record.get("finished_at", ""),
            "updated_at": record.get("updated_at", ""),
        }

        job = active.get(key)
        if job:
            progress = dict(job.get("progress") or {})
            entry.update({
                "status": RUNNING,
                "phase": progress.get("phase") or record.get("phase", ""),
                "detail": progress.get("detail", ""),
                "progress": progress,
                "job_id": job.get("job_id"),
            })
        elif record.get("status") == RUNNING:
            entry.update({"status": ERROR, "error": INTERRUPTED_ERROR, "phase": record.get("phase", "")})
        elif record.get("status") == ERROR:
            entry.update({"status": ERROR, "error": record.get("error", ""), "phase": record.get("phase", "")})
        elif entry["status"] == COMPLETED:
            used = record.get("register_fingerprint")
            current = facts.get("register_fingerprint")
            if used and current and used != current:
                entry["status"] = STALE
                entry["stale_because"] = "documents"
            own = record.get("finished_at", "")
            for dependency in (STAGE_DEPENDENCIES.get(key, ()) if entry["status"] == COMPLETED else ()):
                upstream = (persisted.get(dependency) or {}).get("finished_at", "")
                if own and upstream and upstream > own:
                    entry["status"] = STALE
                    entry["stale_because"] = dependency
                    break

        # A finished step counts as done even when something changed after it.
        entry["done"] = entry["status"] in {COMPLETED, STALE}
        result.append(entry)

    # Legacy progress-bar states: complete / current / upcoming.
    current_found = False
    for entry in result:
        if entry["done"]:
            entry["state"] = "complete"
        elif not current_found:
            entry["state"] = "current"
            current_found = True
        else:
            entry["state"] = "upcoming"

    waiting = [entry for entry in result if entry["status"] == WAITING]
    running = [entry for entry in result if entry["status"] == RUNNING]
    errors = [entry for entry in result if entry["status"] == ERROR]

    next_stage = None
    for bucket in (waiting, errors):
        if bucket:
            next_stage = bucket[0]["key"]
            break
    if next_stage is None:
        for entry in result:
            if entry["status"] in {NOT_STARTED, READY} and entry["key"] != "discussion":
                next_stage = entry["key"]
                break
    if next_stage is None:
        next_stage = "discussion"

    return {
        "stages": result,
        "waiting": [entry["key"] for entry in waiting],
        "running": [entry["key"] for entry in running],
        "errors": [entry["key"] for entry in errors],
        "next_stage": next_stage,
    }
