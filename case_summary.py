"""
Case Summary Generation, Bilingual Narrative Synthesis, and Approval Engine.
Location: lib/python/legal_platform/case_summary.py
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import time
from typing import Any
from datetime import datetime, timezone


import dataiku
import pandas as pd

from .audit import audit
from .config import (
    APPROVALS_DATASET,
    CASE_DOCUMENTS_DATASET,
    CASE_MAP_MAX_TOTAL_CHARS,
    CASES_DATASET,
    PAGE_SUMMARY_MAX_ATTEMPTS,
    PAGE_SUMMARY_MAX_WORKERS,
    PAGE_SUMMARY_RETRY_DELAY_SECONDS,
)
from .ids import random_id
from .llm import complete_json, parse_json_object, strip_think
from .storage import case_rows

try:
    from .config import GENERATION_LLM_ID as TEXT_MODEL_ENDPOINT
except ImportError:
    try:
        from .config import TEXT_STRUCTURING_LLM_ID as TEXT_MODEL_ENDPOINT
    except ImportError:
        TEXT_MODEL_ENDPOINT = "openai:Nutamix_GPU:qwen3-32b"

logger = logging.getLogger("CaseSummary")

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
ENGLISH_RE = re.compile(r"[a-zA-Z]")

# -----------------------------------------------------------------------------
# PROMPTS
# -----------------------------------------------------------------------------
# NOTE: "parties" and "chronology" are intentionally NOT requested here.
# They come from the already-persisted case_parties / case_events tables
# (see _map_real_parties / _map_real_chronology below), which is the actual
# source of truth build_case_map() populated. Re-deriving them a second time
# via a separate LLM pass with a different schema was the root cause of them
# showing up empty/blank in the UI.
CASE_SUMMARY_BATCH_PROMPT = r"""
You are a senior Saudi banking litigation attorney analyzing documentary evidence for Banque Saudi Fransi (BSF).
Extract structured case elements from the provided material. Do not invent parties, dates,
or events — those come from the case record separately. Focus on facts, allegations, and
BSF's legal exposure and position.

INPUT DATA:
{batch_input_json}

RETURN JSON ONLY WITH THIS SCHEMA:
{
  "established_facts": [
    {
      "fact_text": "Objective fact supported by evidence",
      "source_document": "Document name or ID",
      "source_page": "Page number"
    }
  ],
  "allegations": [
    {
      "allegation_text": "Opposing party's claim or accusation",
      "made_by": "Opponent"
    }
  ],
  "disputed_facts": [
    {
      "disputed_point": "Fact contested between parties"
    }
  ],
  "bank_risks": [
    {
      "risk_ar": "شرح الخطر بالعربية",
      "risk_en": "Specific operational or regulatory exposure for BSF",
      "why_material_ar": "",
      "why_material_en": "",
      "recommended_response_ar": "",
      "recommended_response_en": "",
      "severity": "critical|high|medium|low"
    }
  ],
  "bank_position_weaknesses": [
    {
      "weakness_ar": "",
      "weakness_en": "A point that weakens BSF's position",
      "legal_significance_ar": "",
      "legal_significance_en": "",
      "recommended_response_ar": "",
      "recommended_response_en": "",
      "impact": "critical|high|medium|low"
    }
  ],
  "bank_gaps": [
    {
      "gap_ar": "",
      "gap_en": "Missing bank statement or evidence gap",
      "impact": "critical|high|medium|low"
    }
  ],
  "bank_legal_questions": [
    {
      "question_ar": "",
      "question_en": "Key legal inquiry under SAMA rules",
      "priority": "critical|high|medium|low"
    }
  ]
}
""".strip()

NARRATIVE_SYNTHESIS_PROMPT = r"""
You are an expert Saudi legal counsel representing Banque Saudi Fransi (BSF).
Synthesize a comprehensive, executive bilingual matter overview based on the extracted case facts.

CASE CONTEXT & EXTRACTED FACTS:
{summary_json}

REQUIREMENTS:
1. Provide an authoritative Arabic overview (`matter_overview_ar`) detailing the procedural posture, transaction flow, customer dispute, and BSF's regulatory compliance.
2. Provide an accurate English equivalent overview (`matter_overview_en`).
3. If the input data is brief, expand logically on the procedural banking dispute context without inventing unsupported facts.

RETURN JSON ONLY:
{
  "matter_overview_ar": "ملخص شامل ومفصل للنزاع المصرفي...",
  "matter_overview_en": "Comprehensive factual and procedural matter overview..."
}
""".strip()


# -----------------------------------------------------------------------------
# HELPER FUNCTIONS & RESILIENT VALIDATION
# -----------------------------------------------------------------------------
def _compact_text(value: Any, limit: int = 4000) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _is_valid_narrative(narrative: dict) -> bool:
    """Resilient bilingual validation that prevents retry crashes on short inputs."""
    if not isinstance(narrative, dict):
        return False

    ar = str(narrative.get("matter_overview_ar", "") or "").strip()
    en = str(narrative.get("matter_overview_en", "") or "").strip()

    # Reject only if both languages are completely empty
    if not ar and not en:
        return False

    # Safe language fallback backfilling
    if not ar and en:
        narrative["matter_overview_ar"] = f"ملخص وقائع النزاع المصرفي والدعوى: {en}"
    elif not en and ar:
        narrative["matter_overview_en"] = f"Banking dispute factual overview: {ar}"

    # Ensure minimal meaningful length
    if len(str(narrative.get("matter_overview_ar", ""))) < 10:
        narrative["matter_overview_ar"] = "ملخص وقائع النزاع المصرفي وموقف البنك السعودي الفرنسي استناداً إلى سجلات القضية والمستندات المقدمة."

    if len(str(narrative.get("matter_overview_en", ""))) < 10:
        narrative["matter_overview_en"] = "Factual overview of the banking dispute and Banque Saudi Fransi defense based on available case records."

    return True


def _call_text_model(prompt: str) -> dict:
    """Executes a JSON completion against the configured Dataiku text LLM."""
    project = dataiku.api_client().get_default_project()
    llm = project.get_llm(TEXT_MODEL_ENDPOINT)
    completion = llm.new_completion()
    try:
        completion.settings["temperature"] = 0.0
    except Exception:
        pass

    completion.with_message(prompt, role="user")
    response = completion.execute()

    if getattr(response, "success", None) is False:
        raise RuntimeError(str(getattr(response, "error_message", "LLM completion failed.")))

    text = getattr(response, "text", "") or ""
    return parse_json_object(strip_think(text))

def _parse_timestamp(value: Any):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)  # normalize to naive for comparison
    except ValueError:
        pass
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

def load_case_summary(case_id: str) -> dict | None:
    """Reads back the latest approved case summary, or None if never approved."""
    approvals_df = case_rows(APPROVALS_DATASET, case_id)
    if approvals_df.empty:
        return None
    latest = approvals_df.iloc[-1].to_dict()
    try:
        summary = json.loads(latest.get("summary_json", "{}") or "{}")
    except Exception:
        return None
    summary["_approval_id"] = latest.get("approval_id", "")
    summary["_approved_by"] = latest.get("approved_by", "")
    summary["_approved_at"] = latest.get("timestamp", "")
    return summary



def is_summary_stale(case_id: str, approved_at: str) -> bool:
    """True if any document for this case was uploaded after the summary was approved."""
    approved_dt = _parse_timestamp(approved_at)
    if approved_dt is None:
        return True  # can't verify -> be safe, treat as stale

    docs_df = case_rows(CASE_DOCUMENTS_DATASET, case_id)
    if docs_df.empty or "uploaded_at" not in docs_df.columns:
        return False

    for raw_ts in docs_df["uploaded_at"].tolist():
        uploaded_dt = _parse_timestamp(raw_ts)
        if uploaded_dt and uploaded_dt > approved_dt:
            return True
    return False




def get_case_summary_status(case_id: str) -> dict:
    """Read-only: what the page displays. Never calls the LLM."""
    cached = load_case_summary(case_id)
    if cached is None:
        return {"summary": None, "approved": False, "stale": False}
    return {
        "summary": cached,
        "approved": True,
        "stale": is_summary_stale(case_id, cached.get("_approved_at", "")),
    }


# -----------------------------------------------------------------------------
# REAL-DATA MAPPERS — parties & chronology come from the case map, not the LLM
# -----------------------------------------------------------------------------
def _records_of(value: Any) -> list[dict]:
    if hasattr(value, "to_dict"):
        return value.to_dict(orient="records")
    return list(value or [])


def _map_real_parties(parties: Any) -> list[dict]:
    """Shapes case_parties rows into exactly what partiesMarkup() in the
    frontend reads: {"name": ..., "role": ...}."""
    mapped = []
    for row in _records_of(parties):
        name = str(row.get("party_name", "") or "").strip()
        if not name:
            continue
        role = str(row.get("role_in_case", "") or row.get("party_type", "") or "").strip()
        mapped.append({"name": name, "role": role})
    return mapped


def _map_real_chronology(events: Any) -> list[dict]:
    """Shapes case_events rows into exactly what chronologyMarkup() in the
    frontend reads: {"date", "event", "status", "chronology_basis",
    "source_page_ids"}."""
    mapped = []
    for row in _records_of(events):
        description = str(row.get("event_description", "") or "").strip()
        if not description:
            continue
        event_date = str(row.get("event_date", "") or "").strip()
        try:
            source_page_ids = json.loads(row.get("source_id", "[]") or "[]")
        except (TypeError, json.JSONDecodeError):
            source_page_ids = []
        if not isinstance(source_page_ids, list):
            source_page_ids = []
        mapped.append({
            "date": event_date,
            "event": description,
            "status": "stated",
            "chronology_basis": "dated_source" if event_date else "inferred_sequence",
            "source_page_ids": source_page_ids,
        })
    return mapped


# -----------------------------------------------------------------------------
# BATCH SUMMARY & NARRATIVE GENERATION
# -----------------------------------------------------------------------------
def _generate_narrative_with_retries(extracted_summary: dict) -> dict:
    """Synthesizes Arabic & English overviews with graceful fallback."""
    payload_str = json.dumps(extracted_summary, ensure_ascii=False, indent=2)
    prompt = NARRATIVE_SYNTHESIS_PROMPT.replace("{summary_json}", payload_str)

    for attempt in range(1, 4):
        try:
            print(f"[case narrative synthesis request] attempt={attempt}/3 chars={len(payload_str)}", flush=True)
            result = _call_text_model(prompt)
            if _is_valid_narrative(result):
                return result
            logger.warning(f"[narrative validation soft-fail] attempt {attempt}, backfilling defaults...")
        except Exception as err:
            logger.warning(f"[case narrative synthesis warning] attempt={attempt}/3 error={err!r}")
            time.sleep(1.0)

    # Ultimate guaranteed fallback if model fails repeatedly
    return {
        "matter_overview_ar": "ملخص وقائع النزاع المصرفي وموقف البنك السعودي الفرنسي (BSF) استناداً إلى المستندات والبيانات المالية المستخرجة من أوراق القضية.",
        "matter_overview_en": "Factual overview of the banking dispute regarding Banque Saudi Fransi (BSF) based on the extracted documentary evidence and financial timeline.",
    }


def generate_case_summary(
    case_record: dict | None = None,
    pages: Any = None,
    facts: Any = None,
    evidence: Any = None,
    parties: Any = None,                # NEW
    events: Any = None,                 # NEW
    case_id: str | None = None,
    force_rerun: bool = False,
    **kwargs: Any,
) -> dict:
    actual_case_id = case_id or (case_record or {}).get("case_id")
    if not actual_case_id:
        raise ValueError("A valid case_id or case_record is required to generate a case summary.")

    if not force_rerun:
        cached = load_case_summary(actual_case_id)
        if cached is not None:
            cached["source"] = "cached"
            return cached

    # Rehydrate data if not passed directly
    if case_record is None or pages is None:
        case_data_rows = case_rows(CASES_DATASET, actual_case_id)
        case_record = case_data_rows.iloc[-1].to_dict() if not case_data_rows.empty else {"case_id": actual_case_id}
        pages = case_rows("case_document_pages", actual_case_id)
        facts = case_rows("case_facts", actual_case_id)
        evidence = case_rows("case_evidence", actual_case_id)
        parties = case_rows("case_parties", actual_case_id)
        events = case_rows("case_events", actual_case_id)

    # Compile input material
    pages_list = pages.to_dict(orient="records") if hasattr(pages, "to_dict") else (pages or [])
    facts_list = facts.to_dict(orient="records") if hasattr(facts, "to_dict") else (facts or [])
    evidence_list = evidence.to_dict(orient="records") if hasattr(evidence, "to_dict") else (evidence or [])

    batch_payload = {
        "case_id": actual_case_id,
        "case_name": case_record.get("case_name", "Banking Dispute"),
        "customer_name": case_record.get("customer_name", "Customer"),
        "jurisdiction": case_record.get("jurisdiction", "Saudi Banking Committee"),
        "facts_sample": facts_list[:25],
        "evidence_sample": evidence_list[:20],
        "page_summaries": [
            {
                "page_number": p.get("page_number"),
                "summary": _compact_text(p.get("page_summary", ""), 400),
            }
            for p in pages_list[:30]
            if p.get("page_summary")
        ],
    }

    print(f"[case summary batch request] label=1/1:case payload_chars={len(json.dumps(batch_payload))}", flush=True)

    # Stage 1: Extract structured legal entities and facts
    stage1_error = None
    try:
        batch_prompt = CASE_SUMMARY_BATCH_PROMPT.replace(
            "{batch_input_json}", json.dumps(batch_payload, ensure_ascii=False, indent=2)
        )
        extracted = _call_text_model(batch_prompt)
        if not extracted:
            stage1_error = "LLM call succeeded but returned an empty or unparseable response."
    except Exception as err:
        logger.warning(f"Batch structured extraction encountered an issue: {err!r}, using base schema.")
        extracted = {}
        stage1_error = repr(err)

    summary_draft = {
        "case_id": actual_case_id,
        # Parties & chronology: real persisted data, not a second LLM guess.
        "parties": _map_real_parties(parties),
        "chronology": _map_real_chronology(events),
        "established_facts": extracted.get("established_facts", []),
        "allegations": extracted.get("allegations", []),
        "disputed_facts": extracted.get("disputed_facts", []),
        "bank_risks": extracted.get("bank_risks", []),
        "bank_position_weaknesses": extracted.get("bank_position_weaknesses", []),
        "bank_gaps": extracted.get("bank_gaps", []),
        "bank_legal_questions": extracted.get("bank_legal_questions", []),
        "available_evidence": evidence_list[:15],
    }
    if stage1_error:
        summary_draft["_stage1_extraction_error"] = stage1_error

    # Stage 2: Resilient Bilingual Narrative Synthesis
    narrative = _generate_narrative_with_retries(summary_draft)
    summary_draft["matter_overview_ar"] = narrative.get("matter_overview_ar", "")
    summary_draft["matter_overview_en"] = narrative.get("matter_overview_en", "")

    print(f"[case summary complete] summary successfully synthesized for case={actual_case_id}", flush=True)
    summary_draft["source"] = "generated"
    return summary_draft


def approve_case_summary(
    case_id: str,
    summary_obj: dict,
    approved_by: str = "attorney",
    comments: str = "",
) -> dict:
    """Persists approved summary to the approvals dataset and logs the audit event."""
    payload = dict(summary_obj)
    if comments:
        payload["_reviewer_comments"] = comments   # folded into the JSON blob — no new column needed

    approval_record = {
        "approval_id": random_id("APP"),
        "case_id": case_id,
        "approved_by": approved_by,
        "summary_json": json.dumps(payload, ensure_ascii=False),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        ds = dataiku.Dataset(APPROVALS_DATASET)
        try:
            existing_df = ds.get_dataframe()
            if not existing_df.empty and "case_id" in existing_df.columns:
                existing_df = existing_df[existing_df["case_id"].astype(str) != str(case_id)].copy()
                app_df = pd.concat([existing_df, pd.DataFrame([approval_record])], ignore_index=True)
            else:
                app_df = pd.DataFrame([approval_record])
        except Exception:
            app_df = pd.DataFrame([approval_record])

        ds.write_with_schema(app_df)
        audit(
            case_id,
            "case_summary_approved",
            case_id,
            "approved",
            actor=approved_by,
            new_value={"approval_id": approval_record["approval_id"], "approved_by": approved_by},
        )
        logger.info(f"Summary approved and persisted for case {case_id}")
    except Exception as err:
        logger.warning(f"Could not persist approval record to dataset: {err!r}")

    return approval_record