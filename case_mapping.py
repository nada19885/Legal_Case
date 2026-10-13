from __future__ import annotations

import json
from typing import Iterable

from .config import (
    CASE_MAP_MAX_CHARS_PER_PAGE,
    CASE_MAP_MAX_TOTAL_CHARS,
    CASE_MAPPING_LLM_ID,
)
from .llm import complete_json


CASE_MAP_PROMPT = r"""
You are a legal case-document structuring service.

Build a neutral, traceable case map from compact page summaries.
Do not provide legal advice.
The supplied data deliberately excludes full OCR page text.

STRICT GROUNDING RULES:
- Never invent a fact, event, party position, legal defect, or procedural event.
- Every extracted item must be directly supported by the supplied page summaries.
- Preserve source page IDs for every extracted item.
- If support is ambiguous, mark the item as unclear rather than inferring.
- Do not infer a defence position unless the source explicitly states one.
- Do not infer regulatory issues, limitation issues, jurisdictional defects,
  or procedural defects unless the source directly supports them.

EVENT RULES:
- Create an event only when the source explicitly identifies an occurrence.
- Distinguish:
  * contract execution date
  * milestone/performance date
  * invoice date
  * payment due date
  * penalty accrual date
  * notice date
  * filing date
  * hearing date
  * judgment date
- Never convert one event type into another.
- A penalty accrual date is not a complaint filing date.
- A payment due date is not a litigation filing date.
- If a date has no clearly stated event, omit it.

FACT RULES:
- Separate established/stated facts from allegations.
- Use status="stated" only when the document presents the statement as a fact or contractual term.
- Use status="alleged" when a party is asserting misconduct, breach, non-payment,
  completion, damages, or another contested matter.
- Do not convert an allegation into an admitted fact.
- Evidence quotes must reflect the supplied page summary content and must not introduce new wording.

CONTRADICTION RULES:
- A contradiction exists only when two supplied statements cannot both be true.
- Missing information is NOT a contradiction.
- A date requiring clarification is NOT automatically a contradiction.
- A contractual deadline and a corresponding penalty accrual date are not contradictory
  merely because they are related.
- If clarification is needed but no contradiction exists, place it under missing_evidence
  or potential_issues instead.

POTENTIAL ISSUE RULES:
- Generate a potential issue only when grounded in the supplied facts, claims,
  contractual terms, or procedural statements.
- Do not infer issues from formatting, case-number patterns, document naming,
  or general legal knowledge.
- Targeted legal questions may identify questions for later research,
  but must not assume the legal answer.

MISSING EVIDENCE RULES:
- Distinguish between:
  1. evidence explicitly referenced but not supplied,
  2. evidence that may be useful but is not referenced,
  3. evidence actually present in the supplied pages.
- Do not say evidence is missing if it is already represented in the supplied pages.
- Phrase missing-evidence items neutrally.

PARTY RULES:
- Identify only parties explicitly supported by the supplied page summaries.
- Do not classify regulators, courts, lawyers, or mentioned persons as litigation parties
  unless the source explicitly establishes that role.

DEDUPLICATION:
- Deduplicate repeated facts/events across pages.
- If two pages describe the same event, merge their source_page_ids.

Return only valid JSON.

Schema:
{
  "case_name_suggestion": "",
  "case_type": "",
  "matter_summary": "",
  "procedural_posture": "",
  "parties": [
    {
      "name":"",
      "party_type":"",
      "role_in_case":"",
      "source_page_ids":[]
    }
  ],
  "events": [
    {
      "event_date":"",
      "event_type":"",
      "description":"",
      "party_names":[],
      "source_page_ids":[]
    }
  ],
  "facts": [
    {
      "fact_text":"",
      "fact_date":"",
      "party":"",
      "fact_type":"",
      "status":"stated|alleged|admitted|denied|unclear",
      "evidence_quote":"",
      "source_page_ids":[],
      "confidence":0.0
    }
  ],
  "claims_and_requests": [
    {
      "claim":"",
      "claimed_by":"",
      "requested_outcome":"",
      "source_page_ids":[]
    }
  ],
  "potential_issues": [
    {
      "issue_title":"",
      "issue_description":"",
      "targeted_legal_questions":[],
      "supporting_page_ids":[],
      "priority":"critical|high|medium|low"
    }
  ],
  "contradictions": [
    {
      "description":"",
      "source_page_ids":[],
      "clarification_required":""
    }
  ],
  "missing_evidence": [
    {
      "evidence_type":"",
      "description":"",
      "purpose":"",
      "priority":"critical|high|medium|low"
    }
  ],
  "document_quality_gaps": [],
  "matter_date": "",
  "customer_type": "",
  "regulated_entity_type": "",
  "product_type": "",
  "confidence": 0.0
}
""".strip()








def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _compact_page(page: dict) -> dict:
    return {
        "page_id": str(page.get("page_id", "")),
        "page_number": page.get("page_number", ""),
        "document_type": str(page.get("document_type", "") or ""),
        "document_language": str(page.get("document_language", "") or ""),
        "summary": str(page.get("page_summary", "") or ""),
        "parties": _json_list(page.get("parties_json")),
        "dates": _json_list(page.get("dates_json")),
        "amounts": _json_list(page.get("amounts_json")),
        "case_numbers": _json_list(page.get("case_numbers_json")),
        "claims": _json_list(page.get("claims_json")),
        "key_facts": _json_list(page.get("facts_json")),
        "legal_references": _json_list(page.get("legal_references_json")),
        "evidence": _json_list(page.get("evidence_items_json")),
        "signatures_or_stamps": _json_list(
            page.get("signatures_or_stamps_json")
        ),
    }


def _compact_case_pages(pages: Iterable[dict]) -> list[dict]:
    compact_pages: list[dict] = []
    total_chars = 0

    for page in pages:
        compact = _compact_page(page)
        if not compact["summary"].strip():
            continue

        serialised = json.dumps(
            compact,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        if len(serialised) > int(CASE_MAP_MAX_CHARS_PER_PAGE):
            compact["summary"] = compact["summary"][:900]
            compact["parties"] = compact["parties"][:8]
            compact["dates"] = compact["dates"][:8]
            compact["amounts"] = compact["amounts"][:8]
            compact["case_numbers"] = compact["case_numbers"][:8]
            compact["claims"] = compact["claims"][:5]
            compact["key_facts"] = compact["key_facts"][:5]
            compact["legal_references"] = compact["legal_references"][:5]
            compact["evidence"] = compact["evidence"][:5]
            compact["signatures_or_stamps"] = compact[
                "signatures_or_stamps"
            ][:5]
            serialised = json.dumps(
                compact,
                ensure_ascii=False,
                separators=(",", ":"),
            )

        if len(serialised) > int(CASE_MAP_MAX_CHARS_PER_PAGE):
            compact = {
                "page_id": compact["page_id"],
                "page_number": compact["page_number"],
                "document_type": compact["document_type"],
                "summary": compact["summary"][:700],
                "key_facts": compact["key_facts"][:4],
            }
            serialised = json.dumps(
                compact,
                ensure_ascii=False,
                separators=(",", ":"),
            )

        if total_chars + len(serialised) > int(CASE_MAP_MAX_TOTAL_CHARS):
            break

        compact_pages.append(compact)
        total_chars += len(serialised)

    return compact_pages


def build_case_map(pages: Iterable[dict]) -> dict:
    pages = list(pages)
    if not pages:
        raise ValueError("No extracted case pages were supplied.")

    compact_pages = _compact_case_pages(pages)
    if not compact_pages:
        raise ValueError(
            "No compact page summaries are available for case mapping."
        )

    payload_chars = len(
        json.dumps(compact_pages, ensure_ascii=False, separators=(",", ":"))
    )
    print(
        "[case map request] pages={} summary_chars={} "
        "full_page_text_sent=false llm_id={}".format(
            len(compact_pages),
            payload_chars,
            CASE_MAPPING_LLM_ID,
        )
    )

    return complete_json(
        system_prompt=CASE_MAP_PROMPT,
        user_payload={
        "instruction": (
        "Build one deduplicated, source-grounded case map from these compact "
        "page summaries. Do not infer unsupported events, contradictions, "
        "party positions, or legal defects. Preserve all source page IDs."
        ),
        "pages": compact_pages,
},
        llm_id=CASE_MAPPING_LLM_ID,
        temperature=0.0,
    )
