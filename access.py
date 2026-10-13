"""
Users and case ownership: every case belongs to the Dataiku user who
created it, and only that user can see or change it.
Location: lib/python/legal_platform/access.py

Identity: the user signed in to Dataiku (the webapp reads it from the
browser's Dataiku session; the app stores no passwords).

Ownership: one small JSON per case in the case documents folder,
    /ownership/cases/<case_id>.json   {case_id, owner, workflow_type, details, archived, created_at}
and one index per user listing their cases,
    /ownership/users/<user key>.json  {"cases": [case_id, ...]}
so no dataset schema changes. Every record of a case (documents, pages,
facts, claims, analyses, pleadings, chat) is reached through its case_id,
so checking the case's owner on every request isolates all of them.
Cases without an ownership record belong to nobody and are never shown.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from .config import CASE_DOCUMENT_FOLDER_ID

OWNERSHIP_DIR = "/ownership"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
_LOCK = threading.RLock()
_OWNER_CACHE: dict = {}             # case_id -> (record, read_at)
_CACHE_SECONDS = 30.0
DETAIL_FIELDS = ("case_number", "client_name", "opposing_party", "case_type", "description", "counterparty",
                 "contract_type")


class Store:
    """Where the ownership files live (a Dataiku managed folder by default;
    tests pass a dict-backed store)."""

    def read(self, path: str) -> Optional[dict]:
        import dataiku
        try:
            with dataiku.Folder(CASE_DOCUMENT_FOLDER_ID).get_download_stream(path) as stream:
                value = json.loads(stream.read().decode("utf-8"))
            return value if isinstance(value, dict) else None
        except Exception:
            return None

    def write(self, path: str, value: dict) -> None:
        import dataiku
        dataiku.Folder(CASE_DOCUMENT_FOLDER_ID).upload_data(path, json.dumps(value, ensure_ascii=False).encode("utf-8"))


STORE = Store()


# -----------------------------------------------------------------------------
# Identity
# -----------------------------------------------------------------------------
def user_from_headers(headers) -> str:
    """The Dataiku login of the browser making the request, or ""."""
    try:
        import dataiku
        info = dataiku.api_client().get_auth_info_from_browser_headers(dict(headers))
    except Exception as error:
        print(f"[access] could not read the Dataiku identity: {error!r}")
        return ""
    return str((info or {}).get("authIdentifier") or "").strip()


def _user_key(user: str) -> str:
    """A file-safe, collision-free name for a user's index."""
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", user)[:40]
    return f"{slug}_{hashlib.sha256(user.encode('utf-8')).hexdigest()[:16]}"


def valid_id(value: str) -> bool:
    return bool(_SAFE_ID.match(str(value or "")))


# -----------------------------------------------------------------------------
# Ownership records
# -----------------------------------------------------------------------------
def _case_path(case_id: str) -> str:
    return f"{OWNERSHIP_DIR}/cases/{case_id}.json"


def _user_path(user: str) -> str:
    return f"{OWNERSHIP_DIR}/users/{_user_key(user)}.json"


def case_record(case_id: str, store: Store = None) -> Optional[dict]:
    """The ownership record of a case (cached briefly), or None."""
    store = store or STORE
    if not valid_id(case_id):
        return None
    with _LOCK:
        cached = _OWNER_CACHE.get(case_id)
        if cached and time.time() - cached[1] < _CACHE_SECONDS:
            return dict(cached[0]) if cached[0] else None
    record = store.read(_case_path(case_id))
    with _LOCK:
        _OWNER_CACHE[case_id] = (record, time.time())
    return dict(record) if record else None


def owns_case(user: str, case_id: str, store: Store = None) -> bool:
    record = case_record(case_id, store)
    return bool(user) and bool(record) and record.get("owner") == user


def register_case(case_id: str, user: str, workflow_type: str, details: Optional[dict] = None,
                  store: Store = None) -> dict:
    """Make `user` the owner of a new case."""
    store = store or STORE
    if not (user and valid_id(case_id)):
        raise ValueError("A signed-in user and a valid case id are required.")
    record = {
        "case_id": case_id, "owner": user, "workflow_type": workflow_type,
        "details": {k: str(v).strip() for k, v in (details or {}).items() if k in DETAIL_FIELDS and str(v or "").strip()},
        "archived": False, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _LOCK:
        if store.read(_case_path(case_id)):
            raise ValueError("That case already has an owner.")
        store.write(_case_path(case_id), record)
        index = store.read(_user_path(user)) or {"user": user, "cases": []}
        if case_id not in index["cases"]:
            index["cases"].append(case_id)
        store.write(_user_path(user), index)
        _OWNER_CACHE[case_id] = (record, time.time())
    return record


def update_case_record(case_id: str, user: str, changes: dict, store: Store = None) -> dict:
    """Change the archive flag or the details of a case the user owns."""
    store = store or STORE
    with _LOCK:
        record = store.read(_case_path(case_id))
        if not record or record.get("owner") != user:
            raise PermissionError("Case not found.")
        if "archived" in changes:
            record["archived"] = bool(changes["archived"])
        if isinstance(changes.get("details"), dict):
            details = dict(record.get("details") or {})
            details.update({k: str(v).strip() for k, v in changes["details"].items() if k in DETAIL_FIELDS})
            record["details"] = {k: v for k, v in details.items() if v}
        store.write(_case_path(case_id), record)
        _OWNER_CACHE[case_id] = (record, time.time())
    return record


def user_cases(user: str, store: Store = None) -> list[dict]:
    """The ownership records of every case of `user` (only records that
    still name them as owner)."""
    store = store or STORE
    if not user:
        return []
    index = store.read(_user_path(user)) or {}
    out = []
    for case_id in index.get("cases") or []:
        record = case_record(case_id, store)
        if record and record.get("owner") == user:
            out.append(record)
    return out


# -----------------------------------------------------------------------------
# The request check
# -----------------------------------------------------------------------------
def requested_case_id(args, form, body) -> str:
    """The case a request is about, wherever the client sent it."""
    for source in (args, form, body if isinstance(body, dict) else {}):
        try:
            value = source.get("case_id")
        except Exception:
            value = None
        if value:
            return str(value).strip()
    return ""


def authorise(user: str, case_id: str, job_case_id: Optional[str] = None,
              owns: Callable[[str, str], bool] = None) -> tuple[int, str]:
    """(status, message) for one request: 401 without a signed-in user, 404
    for a case (or a job's case) the user does not own - the same answer as
    a case that does not exist, so ids cannot be probed - else 200."""
    owns = owns or owns_case
    if not user:
        return 401, "Please sign in to Dataiku to use the workbench."
    for target in (case_id, job_case_id):
        if target is not None and target != "" and not owns(user, target):
            return 404, "Case not found."
    return 200, ""
