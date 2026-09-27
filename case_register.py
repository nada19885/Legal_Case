"""
Unified case register.
Location: lib/python/legal_platform/case_register.py

The documents stage stores what it understands about a case in separate
datasets (parties, events, facts, issues, evidence requests,
contradictions), one case map per uploaded document. This module
assembles them into ONE register: the single structured view of the case
that the attorney review, the legal analysis, the accounting claims and
the chatbot all read.

Consolidation rules:
  * items with the same normalised content are merged, whichever document
    they came from, and keep every source page;
  * attorney-approved facts / issues take precedence over candidates;
  * facts keep their status ("stated" vs "alleged") so an allegation is
    never presented as an established fact;
  * events are ordered chronologically, parties by procedural role.

The register is derived from stored rows on every read, so it is always
current and never needs its own reset. Pure functions (no Dataiku access).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable

_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_NON_WORD = re.compile(r"[\W_]+", flags=re.UNICODE)
_ALEF = str.maketrans("أإآٱ", "اااا")


def normalise_text(value: Any) -> str:
    """Comparison key: case, punctuation, Arabic diacritics/tatweel and
    alef variants do not make two items different."""
    text = str(value or "").casefold().translate(_ALEF)
    text = _DIACRITICS.sub("", text)
    return _NON_WORD.sub(" ", text).strip()


def _records(value: Any) -> list[dict]:
    if value is None:
        return []
    if hasattr(value, "to_dict"):
        try:
            return value.fillna("").to_dict(orient="records")
        except (TypeError, AttributeError):
            return value.to_dict(orient="records")
    return [row for row in (value or []) if isinstance(row, dict)]


def _text(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, "") and str(value).strip() and str(value).lower() != "nan":
            return str(value).strip()
    return ""


def _json_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return [value] if isinstance(value, str) and value.strip() else []
    return parsed if isinstance(parsed, list) else []


def _page_ids(row: dict, *keys: str) -> list[str]:
    ids: list[str] = []
    for key in keys:
        for item in _json_list(row.get(key)):
            item = str(item or "").strip()
            if item and item not in ids:
                ids.append(item)
    return ids


class _Merger:
    """Keeps the first item per key and unions the source pages of later
    duplicates into it."""

    def __init__(self):
        self.items: dict[str, dict] = {}

    def add(self, key: str, item: dict) -> None:
        if not key:
            return
        existing = self.items.get(key)
        if existing is None:
            item.setdefault("source_page_ids", [])
            item["merged_count"] = 1
            self.items[key] = item
            return
        existing["merged_count"] += 1
        for page_id in item.get("source_page_ids") or []:
            if page_id not in existing["source_page_ids"]:
                existing["source_page_ids"].append(page_id)
        for field, value in item.items():
            if existing.get(field) in (None, "", []) and value not in (None, "", []):
                existing[field] = value

    def values(self) -> list[dict]:
        return list(self.items.values())


# -----------------------------------------------------------------------------
# Ordering
# -----------------------------------------------------------------------------
_ROLE_PRIORITY = (
    (0, ("claimant", "plaintiff", "applicant", "complainant", "مدعي", "طالب", "مشتكي")),
    (1, ("defendant", "respondent", "مدعى عليه", "مدعى عليها")),
    (2, ("appellant", "مستأنف")),
    (3, ("bank", "بنك", "مصرف")),
)


def _party_rank(role: str) -> int:
    text = str(role or "").lower()
    for rank, words in _ROLE_PRIORITY:
        if any(word in text for word in words):
            return rank
    return 99


def _date_key(value: str) -> tuple:
    raw = str(value or "").strip()
    if not raw:
        return (1, "9999-99-99", raw)
    digits = raw.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", digits)
    if match:
        y, m, d = match.groups()
        return (0, f"{int(y):04d}-{int(m):02d}-{int(d):02d}", raw)
    match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", digits)
    if match:
        d, m, y = match.groups()
        return (0, f"{int(y):04d}-{int(m):02d}-{int(d):02d}", raw)
    match = re.search(r"\b(\d{4})\b", digits)
    if match:
        return (0, f"{match.group(1)}-99-99", raw)
    return (1, "9999-99-99", raw)


# -----------------------------------------------------------------------------
# Builders
# -----------------------------------------------------------------------------
def _parties(rows: Iterable[dict]) -> list[dict]:
    merger = _Merger()
    for row in rows:
        name = _text(row, "party_name", "name")
        if not name:
            continue
        merger.add(normalise_text(name), {
            "party_id": _text(row, "party_id"),
            "name": name,
            "party_type": _text(row, "party_type"),
            "role": _text(row, "role_in_case", "role"),
            "review_status": _text(row, "review_status") or "candidate",
            "source_page_ids": _page_ids(row, "source_page_ids_json", "source_page_ids"),
        })
    return sorted(merger.values(), key=lambda p: (_party_rank(p["role"]), p["name"].lower()))


def _events(rows: Iterable[dict]) -> list[dict]:
    merger = _Merger()
    for row in rows:
        description = _text(row, "event_description", "description", "event")
        if not description:
            continue
        date = _text(row, "event_date", "date")
        merger.add(f"{normalise_text(date)}|{normalise_text(description)}", {
            "event_id": _text(row, "event_id"),
            "date": date,
            "event_type": _text(row, "event_type"),
            "description": description,
            "parties": [str(p) for p in _json_list(row.get("party_ids_json")) if str(p).strip()],
            "review_status": _text(row, "review_status") or "candidate",
            "source_page_ids": _page_ids(row, "source_id", "source_page_ids_json"),
        })
    return sorted(merger.values(), key=lambda e: _date_key(e["date"]))


def _fact_item(row: dict, approved: bool) -> dict:
    status = _text(row, "status", "fact_status", "candidate_status").lower()
    if status in {"", "pending", "candidate"}:
        status = "stated" if approved else "unclassified"
    return {
        "fact_id": _text(row, "fact_id", "fact_candidate_id"),
        "fact_text": _text(row, "fact_text", "fact", "statement"),
        "fact_date": _text(row, "fact_date"),
        "party": _text(row, "party"),
        "fact_type": _text(row, "fact_type"),
        "status": status,
        "evidence_quote": _text(row, "evidence_quote"),
        "confidence": row.get("confidence", ""),
        "source_type": _text(row, "source_type") or "document",
        "approved": approved,
        "source_page_ids": _page_ids(row, "source_page_ids_json", "source_page_ids"),
    }


def _facts(approved_rows: Iterable[dict], candidate_rows: Iterable[dict]) -> list[dict]:
    merger = _Merger()
    for approved, rows in ((True, approved_rows), (False, candidate_rows)):
        for row in rows:
            item = _fact_item(row, approved)
            if item["fact_text"]:
                merger.add(normalise_text(item["fact_text"]), item)
    return merger.values()


def _issues(approved_rows: Iterable[dict], candidate_rows: Iterable[dict]) -> list[dict]:
    merger = _Merger()
    priority_rank = {"high": 0, "critical": 0, "medium": 1, "low": 2}
    for approved, rows in ((True, approved_rows), (False, candidate_rows)):
        for row in rows:
            title = _text(row, "issue_title", "title", "issue_text")
            if not title:
                continue
            merger.add(normalise_text(title), {
                "issue_id": _text(row, "issue_id", "issue_candidate_id"),
                "issue_title": title,
                "issue_description": _text(row, "issue_description", "description"),
                "priority": (_text(row, "priority") or "medium").lower(),
                "targeted_questions": [str(q) for q in _json_list(row.get("targeted_questions_json")) if str(q).strip()],
                "approved": approved,
                "source_page_ids": _page_ids(row, "supporting_fact_ids_json", "source_page_ids_json"),
            })
    return sorted(merger.values(), key=lambda i: (not i["approved"], priority_rank.get(i["priority"], 1)))


def _evidence(rows: Iterable[dict]) -> list[dict]:
    merger = _Merger()
    for row in rows:
        title = _text(row, "evidence_title", "title", "evidence_type")
        description = _text(row, "description")
        if not (title or description):
            continue
        merger.add(f"{normalise_text(title)}|{normalise_text(description)}", {
            "evidence_id": _text(row, "evidence_id"),
            "title": title,
            "evidence_type": _text(row, "evidence_type"),
            "description": description,
            "purpose": _text(row, "purpose"),
            "priority": (_text(row, "priority") or "medium").lower(),
            "status": _text(row, "review_status", "status") or "requested",
            "source_page_ids": _page_ids(row, "source_page_ids_json", "page_ids"),
        })
    return merger.values()


def _contradictions(rows: Iterable[dict]) -> list[dict]:
    merger = _Merger()
    for row in rows:
        description = _text(row, "description")
        if not description:
            continue
        merger.add(normalise_text(description), {
            "contradiction_id": _text(row, "contradiction_id"),
            "description": description,
            "clarification_required": _text(row, "clarification_required"),
            "source_page_ids": _page_ids(row, "source_page_ids_json"),
        })
    return merger.values()


def build_case_register(sources: dict, page_labels: dict | None = None) -> dict:
    """Assemble the register from stored rows.

    sources keys (DataFrames or lists of dicts): parties, events, facts,
    fact_candidates, issues, issue_candidates, evidence, contradictions,
    documents, pages. page_labels maps page_id -> "file.pdf — page N".
    """
    page_labels = page_labels or {}

    register = {
        "parties": _parties(_records(sources.get("parties"))),
        "events": _events(_records(sources.get("events"))),
        "facts": _facts(_records(sources.get("facts")), _records(sources.get("fact_candidates"))),
        "issues": _issues(_records(sources.get("issues")), _records(sources.get("issue_candidates"))),
        "evidence_requests": _evidence(_records(sources.get("evidence"))),
        "contradictions": _contradictions(_records(sources.get("contradictions"))),
    }

    for items in register.values():
        for item in items:
            item["page_labels"] = [
                page_labels.get(page_id, f"Page {page_id[:6]}") for page_id in item.get("source_page_ids") or []
            ]

    register["allegations"] = [fact for fact in register["facts"] if fact["status"] == "alleged"]

    pages = _records(sources.get("pages"))
    usable = [
        page for page in pages
        if str(page.get("processing_status", "completed") or "completed") in {"completed", "completed_review_required"}
        and str(page.get("page_text", "") or "").strip()
    ]
    register["sources"] = {
        "documents": len(_records(sources.get("documents"))),
        "pages": len(pages),
        "usable_pages": len(usable),
    }
    register["counts"] = {
        key: len(register[key])
        for key in ("parties", "events", "facts", "allegations", "issues", "evidence_requests", "contradictions")
    }

    signature = json.dumps(
        {key: sorted(normalise_text(json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))
                     for item in register[key])
         for key in ("parties", "events", "facts", "issues", "evidence_requests", "contradictions")},
        ensure_ascii=False,
    )
    register["fingerprint"] = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
    return register


def prioritise_pages_for_summary(pages: Any) -> list[dict]:
    """Pages for the attorney review, ordered so pages whose own summary
    recorded claims, parties or facts come first. Uses only the documents
    stage's per-page extraction, never the accounting classification, so
    the legal track does not depend on whether accounting has run."""
    rows = _records(pages)

    def weight(row: dict) -> tuple:
        claims = len(_json_list(row.get("claims_json")))
        facts = len(_json_list(row.get("facts_json")))
        parties = len(_json_list(row.get("parties_json")))
        try:
            number = int(float(row.get("page_number") or 0))
        except (TypeError, ValueError):
            number = 0
        return (-(claims * 3 + facts + parties), str(row.get("case_document_id", "")), number)

    return sorted(rows, key=weight)
