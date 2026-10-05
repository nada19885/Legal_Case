"""
Written pleading: a complete Statement of Defence in English and Arabic.
Location: lib/python/legal_platform/pleading.py

The pleading follows a fixed structure (heading, preliminary statement,
claims, chronology, contract, legal framework, accounting findings,
response to each allegation, procedural and substantive defences, open
matters, relief, documents, signature).

How it is drafted:
  1. build_drafting_record collects what the pleading may rely on from the
     stored case: parties, the claimant's claims and their accounting
     evaluations, the dated events with their source pages, the text of
     contract pages, the legal-analysis issues that cite retrieved
     authorities, the ledger totals and the documents on file.
  2. The pleading is drafted in the language the attorney chose (English
     or Arabic) in two halves (sections 1-7, then 8-14 with the first half
     as context), so a long pleading is never cut off by the model's
     output limit.
  3. normalise_part checks every half: authority node ids the retrieval did
     not return are removed, framework entries left without any are
     dropped, and empty procedural defences are removed.

pleading_to_markdown renders a stored pleading in its language; the
screen, the .md export and the .docx export all use it.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from .llm import complete_json

PLEADING_FORMAT = "full_v2"
BANK_EN = "Banque Saudi Fransi"
BANK_AR = "البنك السعودي الفرنسي"
PLACEHOLDER = "[…]"

CONTRACT_HINTS = (
    "contract", "agreement", "terms", "schedule", "facility", "financing", "loan", "offer",
    "عقد", "اتفاقية", "اتفاق", "شروط", "جدول", "تمويل", "عرض",
)
CONTRACT_PAGE_LIMIT = 10
CONTRACT_PAGE_CHARS = 3500
CONTRACT_TOTAL_CHARS = 28000


def _text(value: Any, limit: int = 0) -> str:
    text = "" if value is None else str(value).strip()
    if text.lower() == "nan":
        text = ""
    return text[:limit] if limit else text


def _records(value: Any) -> list[dict]:
    if value is None:
        return []
    if hasattr(value, "to_dict"):
        try:
            return value.fillna("").to_dict(orient="records")
        except Exception:
            return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


# ---------------------------------------------------------------------------
# 1. The record the pleading may rely on
# ---------------------------------------------------------------------------
# The app's own case_id is not a court case number, so it is not sent.
CASE_FIELDS = (
    "case_name", "case_number", "court_case_number", "najiz_case_number", "court", "court_name",
    "judicial_authority", "committee", "circuit", "case_type", "matter_type", "jurisdiction", "product_type",
    "matter_date", "customer_type", "customer_name", "client_name", "claimant_name", "defendant_name",
    "responsible_attorney", "attorney_license", "preferred_language",
)


def _is_contract_page(page: dict, filename: str) -> bool:
    haystack = " ".join([
        _text(page.get("document_type")), _text(page.get("page_type")), filename,
        _text(page.get("page_summary"), 300),
    ]).casefold()
    return any(hint in haystack for hint in CONTRACT_HINTS)


def _contract_pages(pages: list[dict], documents: dict, page_labels: dict) -> list[dict]:
    """Full text of the pages most likely to hold contractual clauses, so
    the pleading can quote or accurately summarise the real clause."""
    selected, total = [], 0
    for page in pages:
        page_id = _text(page.get("case_document_page_id") or page.get("page_id"))
        text = _text(page.get("page_text"))
        filename = documents.get(_text(page.get("case_document_id")), "")
        if not text or not _is_contract_page(page, filename):
            continue
        text = text[:CONTRACT_PAGE_CHARS]
        if total + len(text) > CONTRACT_TOTAL_CHARS or len(selected) >= CONTRACT_PAGE_LIMIT:
            break
        total += len(text)
        selected.append({"source": page_labels.get(page_id, filename or page_id), "text": text})
    return selected


def _claims(case_data: dict, summary: dict, record_labels: dict) -> tuple[list[dict], list]:
    """The claimant's claims as evaluated by the accounting analysis, with
    the source pages of the ledger records each evaluation relies on."""
    findings = (case_data.get("forensic_findings") or {}).get("claim_evaluations") or []
    claims = []
    for evaluation in findings[:20]:
        if not isinstance(evaluation, dict):
            continue
        groups = {}
        for group in ("supporting_evidence", "partially_supporting_evidence",
                      "contradicting_evidence", "unresolved_evidence"):
            entries = []
            for entry in (evaluation.get(group) or [])[:6]:
                if not isinstance(entry, dict):
                    continue
                ids = [str(x) for x in entry.get("record_ids") or []][:8]
                entries.append({
                    "explanation": _text(entry.get("explanation"), 400),
                    "sources": sorted({record_labels[x] for x in ids if x in record_labels}),
                })
            groups[group] = entries
        claims.append({
            "claim_id": _text(evaluation.get("claim_id")),
            "claim": _text(evaluation.get("claim"), 1000),
            "parent_claim": _text(evaluation.get("parent_claim"), 600),
            "claimed_amount": _text(evaluation.get("claimed_amount")),
            "substantiated_amount": _text(evaluation.get("substantiated_amount")),
            "accounting_result": _text(evaluation.get("result")),
            "accounting_position": _text(evaluation.get("accounting_position") or evaluation.get("accounting_response"), 1500),
            "missing_evidence": [_text(x, 300) for x in (evaluation.get("missing_evidence") or [])[:8] if _text(x)],
            "limitation": _text(evaluation.get("limitation"), 600),
            **groups,
        })
    allegations = []
    for item in (summary.get("allegations") or [])[:15]:
        allegations.append(item if isinstance(item, str) else {
            key: item.get(key) for key in ("allegation", "text", "statement", "party", "source_page_ids") if item.get(key)
        })
    return claims, allegations


def _key_ledger_records(ledger: list[dict], page_labels: dict, per_type: int = 6, limit: int = 90) -> list[dict]:
    by_type: dict = {}
    for entry in ledger:
        bucket = by_type.setdefault(_text(entry.get("fact_type")) or "other", [])
        if len(bucket) < per_type:
            bucket.append(entry)
    records = []
    for entries in by_type.values():
        for entry in entries:
            records.append({
                "fact_type": _text(entry.get("fact_type")),
                "date": _text(entry.get("date")),
                "description": _text(entry.get("description"), 200),
                "value": _text(entry.get("value")),
                "currency": _text(entry.get("currency")),
                "balance": _text(entry.get("balance")),
                "source": page_labels.get(_text(entry.get("page_id")), f"page {_text(entry.get('page_number'))}"),
            })
    return records[:limit]


def build_drafting_record(
    case_record: dict,
    summary: Optional[dict],
    analysis: Optional[dict],
    research: Optional[dict],
    case_data: dict,
    register: dict,
    page_labels: dict,
    ledger: list[dict],
    ledger_overview: dict,
    instructions: str = "",
) -> dict:
    from .case_analysis import issue_has_authority

    summary = summary if isinstance(summary, dict) else {}
    analysis = analysis if isinstance(analysis, dict) else {}

    documents = {}
    document_list = []
    for row in _records(case_data.get("documents")):
        doc_id = _text(row.get("case_document_id") or row.get("document_id"))
        filename = _text(row.get("original_filename") or row.get("file_name")) or "Document"
        documents[doc_id] = filename
        document_list.append({
            "file": filename,
            "type": _text(row.get("document_type")),
            "pages": _text(row.get("page_count")),
        })

    pages = _records(case_data.get("pages"))
    page_summaries = []
    for page in pages[:60]:
        page_id = _text(page.get("case_document_page_id") or page.get("page_id"))
        text = _text(page.get("page_summary"), 350)
        if text:
            page_summaries.append({"source": page_labels.get(page_id, page_id), "summary": text})

    record_labels = {
        _text(entry.get("row_id")): page_labels.get(_text(entry.get("page_id")), f"page {_text(entry.get('page_number'))}")
        for entry in ledger
    }
    claims, allegations = _claims(case_data, summary, record_labels)

    issues = [item for item in analysis.get("issues") or [] if isinstance(item, dict)]
    supported = [
        {key: item.get(key) for key in (
            "issue_title", "applicable_rules", "our_position", "opponent_position",
            "response", "conclusion", "residual_risk",
        )}
        for item in issues if issue_has_authority(item)
    ]
    unsupported = [_text(item.get("issue_title"), 200) for item in issues if not issue_has_authority(item)]

    authorities = []
    for node in _records((research or {}).get("authority_nodes"))[:24]:
        authorities.append({
            "node_id": _text(node.get("node_id")),
            "title": _text(node.get("heading_path") or node.get("title"), 240),
            "citation": _text(node.get("citation") or node.get("article_number"), 180),
            "text": _text(node.get("canonical_text") or node.get("summary"), 1100),
        })

    return {
        "represented_party": {"en": f"{BANK_EN} (BSF)", "ar": BANK_AR},
        "case_identification": {
            key: _text(case_record.get(key), 300) for key in CASE_FIELDS if _text((case_record or {}).get(key))
        },
        "parties": [
            {"name": item.get("name"), "role": item.get("role"), "sources": item.get("page_labels", [])[:3]}
            for item in (register.get("parties") or [])[:15]
        ],
        "claimant_claims": claims,
        "other_allegations": allegations,
        "dated_events": [
            {"date": item.get("date"), "event": _text(item.get("event") or item.get("description"), 400),
             "sources": item.get("page_labels", [])[:3]}
            for item in (register.get("events") or [])[:45]
        ],
        "attorney_summary": {
            "overview": _text(summary.get("matter_overview_en"), 4000),
            **{key: (summary.get(key) or [])[:12] for key in (
                "established_facts", "disputed_facts", "missing_evidence", "bank_gaps", "available_evidence",
            )},
        },
        "contract_pages": _contract_pages(pages, documents, page_labels),
        "page_summaries": page_summaries,
        "legal_analysis": {
            "executive_summary": _text(analysis.get("executive_summary"), 2500),
            "issues_with_retrieved_authority": supported[:12],
            "issues_without_retrieved_authority": unsupported,
        },
        "authorities": authorities,
        "accounting": {
            "ledger_overview": ledger_overview,
            "key_ledger_records": _key_ledger_records(ledger, page_labels),
        },
        "documents_on_file": document_list[:40],
        "drafting_instructions": _text(instructions, 2000),
    }


RECORD_BUDGET_CHARS = 70000


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":")))


def fit_record(record: dict, budget: int = RECORD_BUDGET_CHARS) -> dict:
    """Shrink the record step by step, least important material first,
    until it fits the budget: page summaries, then ledger samples, then
    events, authority text, contract text and claim evidence detail."""
    record = json.loads(json.dumps(record, ensure_ascii=False, default=str))
    steps = [
        lambda r: r.__setitem__("page_summaries", r["page_summaries"][:25]),
        lambda r: r["accounting"].__setitem__("key_ledger_records", r["accounting"]["key_ledger_records"][:40]),
        lambda r: r.__setitem__("page_summaries", r["page_summaries"][:10]),
        lambda r: r.__setitem__("dated_events", r["dated_events"][:30]),
        lambda r: [node.__setitem__("text", node["text"][:600]) for node in r["authorities"]],
        lambda r: [page.__setitem__("text", page["text"][:2000]) for page in r["contract_pages"]],
        lambda r: [claim.__setitem__(group, claim[group][:3]) for claim in r["claimant_claims"]
                   for group in ("supporting_evidence", "partially_supporting_evidence",
                                 "contradicting_evidence", "unresolved_evidence")],
        lambda r: r.__setitem__("page_summaries", []),
        lambda r: r.__setitem__("contract_pages", r["contract_pages"][:5]),
    ]
    for step in steps:
        if _size(record) <= budget:
            break
        step(record)
    return record


# ---------------------------------------------------------------------------
# 2. Prompts
# ---------------------------------------------------------------------------
DRAFTING_RULES = r"""
You are a Saudi litigation drafting assistant working for a qualified attorney.
You draft a formal written pleading (Statement of Defence) for filing, not a
summary, memo, letter or essay. Write complete, reasoned paragraphs.

REPRESENTATION
You act only for Banque Saudi Fransi (BSF), normally the Defendant. Never draft
for the Claimant. Never request relief that benefits the Claimant.

SOURCES: use only the supplied record.
- Facts, dates and amounts come from the record (dated_events, claimant_claims,
  accounting, contract_pages, page_summaries, attorney_summary). Cite the source
  label exactly as supplied (e.g. "Financing Agreement.pdf — page 3").
- Contractual provisions: quote or accurately summarise text that appears in
  contract_pages. Never invent standard contractual language or clause numbers.
  If the clause is not in the record, say the clause text is not in the record.
- Laws and regulations: cite only the supplied authorities, by title/citation,
  with their node_ids. Include a law or regulation only when its retrieved text
  actually relates to the issue. Never cite law from general knowledge.
- Legal analysis: rely only on issues_with_retrieved_authority. Issues without
  retrieved authority may be listed as matters for determination, never argued
  as established law.
- Accounting: report the accounting results as given; never change a result,
  never compute new totals beyond the supplied figures, never hide contradicting
  evidence. Where evidence is missing or unresolved, write: "The available case
  documents are insufficient to conclusively determine this issue."
- Never fill a gap with an assumption. Unknown identification details are
  written as […]. Never cite internal record ids (such as FLI_…, CLM_…) as
  evidence or documents; cite the source label (file and page) instead.
""".strip()


PART_A_PROMPT = DRAFTING_RULES + r"""

TASK: draft sections 1 to 7 of the pleading, in the language set under LANGUAGE.

1. heading: judicial authority / competent committee, case number, claimant,
   defendant, type of dispute, and the title (e.g. "First Statement of Defence").
   "submitted_by" is "Banque Saudi Fransi – Defendant" (adjust capacity only if
   the record shows otherwise); "against" names the Claimant and capacity.
2. introduction: 2-4 paragraphs stating what the Claimant requests, the Bank's
   overall position, the main grounds of defence, and what the memorandum will
   demonstrate.
3. claims_summary: every distinct allegation of the Claimant, one entry each,
   with a short title and a faithful statement of the allegation. Use the
   claimant_claims (keep their claim_ids) and other_allegations.
4. chronology: rows in date order (date, event, supporting evidence with source
   label); then chronology_narrative: paragraphs explaining the sequence.
5. contractual_provisions: the clauses relied upon (financing amount and term,
   repayment, default, fees and charges, other relevant obligations), each with
   the clause reference as printed and its content, and the source label. If no
   contract text is in the record, leave the list empty and explain in
   contract_note.
6. legal_framework: only retrieved authorities that relate to the dispute,
   grouped under headings (financing regulations, consumer protection
   principles, debt collection rules, other authorities). Each entry states the
   authority, its node_ids and how it bears on the dispute.
7. accounting_findings: standalone findings, typically: financing amount;
   amounts disbursed; payments made; outstanding balance; fees and charges;
   differences or contradictions; unresolved financial issues. Only include a
   finding the record addresses. Each has labelled points (e.g. "Contractual
   amount": "SAR 84,000"), evidence sources, a finding paragraph, and an outcome
   of "consistent", "inconsistent" or "unresolved".

Return one JSON object only:
{
  "heading": {"authority": "", "case_number": "", "claimant": "", "defendant": "",
              "dispute_type": "", "title": "", "submitted_by": "", "against": "", "subject": ""},
  "introduction": [""],
  "claims_summary": [{"number": 1, "title": "", "allegation": "", "claim_ids": [""]}],
  "chronology": [{"date": "", "event": "", "evidence": ""}],
  "chronology_narrative": [""],
  "contractual_provisions": [{"heading": "", "clause": "", "content": "", "source": ""}],
  "contract_note": "",
  "legal_framework": [{"heading": "", "authority": "", "node_ids": [""], "content": ""}],
  "accounting_findings": [{"heading": "", "points": [{"label": "", "value": ""}],
                           "evidence": [""], "finding": "", "outcome": "consistent|inconsistent|unresolved"}]
}
""".strip()


PART_B_PROMPT = DRAFTING_RULES + r"""

TASK: draft sections 8 to 14 of the pleading, in the language set under LANGUAGE.
The first half of the
pleading (sections 1-7) is supplied as `pleading_so_far`; stay consistent with it
and number the responses in the same order as claims_summary.

8. claim_responses: the most important section. One entry for EVERY claim in
   claims_summary: the Claimant's allegation; the Bank's position; the relevant
   evidence (source labels); the accounting finding for that claim; the
   applicable contractual or legal provision (with node_ids when an authority is
   cited); a reasoned analysis in full paragraphs; and a conclusion stating
   whether the documentary and accounting record supports, does not support, or
   does not conclusively resolve the allegation.
9. procedural_defences: ONLY when the record shows a real procedural issue
   (jurisdiction, standing, limitation, admissibility, procedural prerequisites),
   each with its factual basis. Never raise one merely because a document is
   missing from the file, and never raise one that could weaken the Bank's
   position (e.g. saying the Bank lacks its own enforcement documents). If there
   is none, return an empty list.
10. substantive_defences: headed defences connecting facts, accounting findings,
    contract and retrieved regulations with actual reasoning (not bare
    statements such as "BSF complied with SAMA regulations").
11. unresolved_matters: matters the current record does not conclusively
    establish, each as a sentence such as "The record presently available does
    not contain sufficient evidence to determine whether …" or "Confirmation of
    this issue requires review of …".
12. relief_requested: an introduction and numbered requests. Base them on the
    record and drafting_instructions; by default: dismiss the claims to the extent
    unsupported by the contractual, documentary and accounting record; confirm the
    amounts established by the evidence where appropriate; reject claims for
    amounts or relief not supported by evidence or law; such other relief as the
    authority considers appropriate. Never request reputational relief unless the
    record shows it was claimed and is available.
13. documents_relied_upon: the documents the pleading relies on, from
    documents_on_file (with dates where the record gives them), including the
    accounting analysis / reconstructed ledger.
14. signature: party, counsel, licence number and date; […] where unknown.
Also list attorney_checks: points the attorney must verify before filing.

Return one JSON object only:
{
  "claim_responses": [{"number": 1, "title": "", "allegation": "", "bank_position": "",
                       "evidence": [""], "accounting_finding": "", "applicable_provision": "",
                       "node_ids": [""], "analysis": [""], "conclusion": ""}],
  "procedural_defences": [{"heading": "", "basis": "", "analysis": "", "node_ids": [""]}],
  "substantive_defences": [{"heading": "", "reasoning": [""], "node_ids": [""]}],
  "unresolved_matters": [""],
  "relief_requested": {"introduction": "", "items": [""]},
  "documents_relied_upon": [""],
  "signature": {"party": "", "counsel": "", "license": "", "date": ""},
  "attorney_checks": [""]
}
""".strip()


LANGUAGE_RULES = {
    "en": """
LANGUAGE
Write every value in formal legal English. Keys stay exactly as in the schema.
""".strip(),
    "ar": """
LANGUAGE
Write every value in formal Saudi legal Arabic, in the style of a مذكرة جوابية
filed through Najiz. Rules:
- the JSON keys stay in English exactly as in the schema: do not translate the
  keys and do not wrap the answer inside another key;
- source labels (file names and page numbers), node_ids, claim_ids and the
  "outcome" values (consistent / inconsistent / unresolved) stay unchanged;
- heading.title is e.g. "مذكرة جوابية (مذكرة دفاع أولى)" and heading.submitted_by
  is e.g. "البنك السعودي الفرنسي – المدعى عليه";
- where evidence is insufficient, write: "لم يتضمن ملف القضية الحالي مستندات
  كافية للجزم بشأن هذه المسألة."
""".strip(),
}
LANGUAGES = tuple(LANGUAGE_RULES)


def _with_language(prompt: str, language: str) -> str:
    return prompt + "\n\n" + LANGUAGE_RULES[language]


REVISION_PROMPT = DRAFTING_RULES + r"""

TASK: revise the existing pleading (`current_pleading`), in the language set under LANGUAGE, as the attorney
requests in `revision_request`. Apply only requested, record-supported changes;
keep everything else unchanged. If a requested change conflicts with the record,
do not make it and explain why in rejected_changes.

Return one JSON object only:
{
  "changed_sections": {"<section key>": <complete replacement value of that section>},
  "change_notes": [""],
  "rejected_changes": [""]
}
Section keys are the top-level keys of current_pleading (e.g. "introduction",
"claim_responses", "relief_requested"). Include only sections you changed, each
in full, with the same structure as in current_pleading.
""".strip()


# ---------------------------------------------------------------------------
# 3. Checks
# ---------------------------------------------------------------------------
PART_A_KEYS = ("heading", "introduction", "claims_summary", "chronology", "chronology_narrative",
               "contractual_provisions", "contract_note", "legal_framework", "accounting_findings")
PART_B_KEYS = ("claim_responses", "procedural_defences", "substantive_defences", "unresolved_matters",
               "relief_requested", "documents_relied_upon", "signature")
HEADING_KEYS = ("authority", "case_number", "claimant", "defendant", "dispute_type", "title",
                "submitted_by", "against", "subject")
OUTCOMES = {"consistent", "inconsistent", "unresolved"}


def _str_list(value: Any, limit: int = 60) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value[:limit] if _text(item)]


_INTERNAL_ID = re.compile(r"^(FLI|CASE|NODE|CLM|ROW)_[0-9A-Za-z_]+$")


def _public_list(value: Any, limit: int = 60) -> list[str]:
    """A list of evidence or documents without the app's internal record ids."""
    return [item for item in _str_list(value, limit) if not _INTERNAL_ID.match(item)]


def _dicts(value: Any) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _ids(value: Any, allowed: set) -> list[str]:
    return [str(x) for x in (value if isinstance(value, list) else []) if str(x) in allowed]


def normalise_part(part: Any, allowed_node_ids: set, notes: Optional[list] = None) -> dict:
    """Clean one drafted half (either language): fixed shapes, only
    retrieved authority node ids, no framework entry without an authority,
    no empty procedural defence. What was removed is added to notes."""
    notes = notes if notes is not None else []
    part = part if isinstance(part, dict) else {}
    out: dict = {}

    if "heading" in part or any(key in part for key in PART_A_KEYS):
        heading = part.get("heading") if isinstance(part.get("heading"), dict) else {}
        out["heading"] = {key: _text(heading.get(key)) or PLACEHOLDER for key in HEADING_KEYS}
        out["introduction"] = _str_list(part.get("introduction"))
        out["claims_summary"] = [
            {"number": index + 1, "title": _text(item.get("title")), "allegation": _text(item.get("allegation")),
             "claim_ids": _str_list(item.get("claim_ids"), 10)}
            for index, item in enumerate(_dicts(part.get("claims_summary")))
            if _text(item.get("allegation")) or _text(item.get("title"))
        ]
        out["chronology"] = [
            {"date": _text(item.get("date")), "event": _text(item.get("event")), "evidence": _text(item.get("evidence"))}
            for item in _dicts(part.get("chronology")) if _text(item.get("event"))
        ]
        out["chronology_narrative"] = _str_list(part.get("chronology_narrative"))
        out["contractual_provisions"] = [
            {key: _text(item.get(key)) for key in ("heading", "clause", "content", "source")}
            for item in _dicts(part.get("contractual_provisions")) if _text(item.get("content"))
        ]
        out["contract_note"] = _text(part.get("contract_note"))
        framework = []
        for item in _dicts(part.get("legal_framework")):
            ids = _ids(item.get("node_ids"), allowed_node_ids)
            if not ids:
                notes.append(f"Removed from the legal framework (no retrieved authority): {_text(item.get('authority'), 120)}")
                continue
            framework.append({"heading": _text(item.get("heading")), "authority": _text(item.get("authority")),
                              "node_ids": ids, "content": _text(item.get("content"))})
        out["legal_framework"] = framework
        findings = []
        for item in _dicts(part.get("accounting_findings")):
            outcome = _text(item.get("outcome")).lower()
            findings.append({
                "heading": _text(item.get("heading")),
                "points": [{"label": _text(p.get("label")), "value": _text(p.get("value"))}
                           for p in _dicts(item.get("points")) if _text(p.get("label"))],
                "evidence": _public_list(item.get("evidence"), 20),
                "finding": _text(item.get("finding")),
                "outcome": outcome if outcome in OUTCOMES else "unresolved",
            })
        out["accounting_findings"] = findings

    if any(key in part for key in PART_B_KEYS):
        out["claim_responses"] = [
            {"number": index + 1,
             **{key: _text(item.get(key)) for key in ("title", "allegation", "bank_position",
                                                      "accounting_finding", "applicable_provision", "conclusion")},
             "evidence": _public_list(item.get("evidence"), 20),
             "node_ids": _ids(item.get("node_ids"), allowed_node_ids),
             "analysis": _str_list(item.get("analysis"))}
            for index, item in enumerate(_dicts(part.get("claim_responses")))
        ]
        procedural = []
        for item in _dicts(part.get("procedural_defences")):
            if not _text(item.get("basis")):
                notes.append(f"Removed a procedural defence without a factual basis: {_text(item.get('heading'), 120)}")
                continue
            procedural.append({"heading": _text(item.get("heading")), "basis": _text(item.get("basis")),
                               "analysis": _text(item.get("analysis")),
                               "node_ids": _ids(item.get("node_ids"), allowed_node_ids)})
        out["procedural_defences"] = procedural
        out["substantive_defences"] = [
            {"heading": _text(item.get("heading")), "reasoning": _str_list(item.get("reasoning")),
             "node_ids": _ids(item.get("node_ids"), allowed_node_ids)}
            for item in _dicts(part.get("substantive_defences")) if _str_list(item.get("reasoning"))
        ]
        out["unresolved_matters"] = _str_list(part.get("unresolved_matters"))
        relief = part.get("relief_requested") if isinstance(part.get("relief_requested"), dict) else {}
        out["relief_requested"] = {"introduction": _text(relief.get("introduction")),
                                   "items": _str_list(relief.get("items"), 20)}
        out["documents_relied_upon"] = _public_list(part.get("documents_relied_upon"))
        signature = part.get("signature") if isinstance(part.get("signature"), dict) else {}
        out["signature"] = {key: _text(signature.get(key)) or PLACEHOLDER
                            for key in ("party", "counsel", "license", "date")}
    return out


def _represents_bsf(part_a: dict) -> bool:
    heading = part_a.get("heading") or {}
    text = " ".join([heading.get("submitted_by", ""), heading.get("defendant", ""),
                     " ".join(part_a.get("introduction") or [])]).casefold()
    return any(term in text for term in ("banque saudi fransi", "bsf", "البنك السعودي الفرنسي"))


def _call(prompt: str, payload: dict, attempts: int = 2) -> dict:
    failures = []
    for attempt in range(attempts):
        try:
            return complete_json(prompt, payload, temperature=0.1)
        except Exception as error:
            failures.append(repr(error))
    raise RuntimeError("Pleading drafting failed: " + "; ".join(failures))


def _unwrap(result: Any, keys: tuple) -> dict:
    """The model sometimes wraps its answer ({"arabic_part": {...}},
    {"result": {...}}, a one-item list). Return the dict that actually
    holds the expected keys, searching nested dicts and lists."""
    best, best_hits = {}, 0
    stack = [result]
    while stack:
        value = stack.pop()
        if isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, dict):
            hits = sum(1 for key in keys if key in value)
            if hits > best_hits:
                best, best_hits = value, hits
            stack.extend(value.values())
    return best


def _has_content(part: dict, keys: tuple) -> bool:
    for key in keys:
        value = part.get(key)
        if key == "heading":
            if any(v and v != PLACEHOLDER for v in (value or {}).values()):
                return True
        elif key in ("relief_requested", "signature"):
            continue
        elif value:
            return True
    return False


def _draft_part(prompt: str, payload: dict, keys: tuple, allowed: set, notes: list) -> tuple[dict, dict]:
    """One drafting call: (normalised part, the raw answer that held it).
    A wrapped answer is unwrapped; an answer holding none of the expected
    sections is retried once with the exact key list."""
    payload = dict(payload)
    for attempt in range(2):
        raw = _call(prompt, payload)
        found = _unwrap(raw, keys)
        part = normalise_part(found, allowed, notes)
        if _has_content(part, keys):
            return part, found
        print("[pleading] attempt {} returned no usable sections; top-level keys={}".format(
            attempt + 1, list(raw)[:12] if isinstance(raw, dict) else type(raw).__name__), flush=True)
        payload["previous_answer_problem"] = (
            "Your previous answer did not contain the required keys. Return ONE JSON object whose "
            "top-level keys are exactly: " + ", ".join(keys) + ". Do not wrap it and do not translate the keys."
        )
    raise ValueError("The model did not return the pleading sections in the expected form; please generate again.")


def _node_ids_used(section: dict) -> list[str]:
    used = []

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "node_ids" and isinstance(item, list):
                    used.extend(str(x) for x in item if str(x) not in used)
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(section)
    return used


def pleading_language(memo: Any) -> str:
    """The language a stored pleading was drafted in."""
    if not isinstance(memo, dict):
        return "en"
    if memo.get("language") in LANGUAGES:
        return memo["language"]
    return "en" if memo.get("pleading_en") else "ar"


def pleading_languages(memo: Any) -> tuple:
    """The language versions a stored pleading holds (one)."""
    return (pleading_language(memo),)


def draft_pleading(record: dict, language: str = "en",
                   progress: Optional[Callable[[str], None]] = None) -> dict:
    """Draft the full pleading in one language (English or Arabic), in two
    calls: sections 1-7, then sections 8-14 with the first half as context."""
    language = language if language in LANGUAGES else "en"
    name = "Arabic" if language == "ar" else "English"
    report = progress or (lambda message: None)
    allowed = {node["node_id"] for node in record.get("authorities", []) if node.get("node_id")}
    notes: list = []
    record = fit_record(record)
    # The second half works from the first: the contract text and page
    # summaries it needs are already drafted into sections 1-7.
    record_b = {key: value for key, value in record.items() if key not in ("contract_pages", "page_summaries")}

    part_a = {}
    for attempt in range(2):
        report(f"Drafting the {name} pleading: heading, claims, facts, contract, law and accounts…")
        part_a, _ = _draft_part(_with_language(PART_A_PROMPT, language), record, PART_A_KEYS, allowed, notes)
        if _represents_bsf(part_a):
            break
    if not _represents_bsf(part_a):
        raise ValueError("The drafted pleading did not present Banque Saudi Fransi as the represented party.")

    report(f"Drafting the {name} pleading: responses, defences, relief and exhibits…")
    part_b, raw_b = _draft_part(_with_language(PART_B_PROMPT, language), {**record_b, "pleading_so_far": part_a},
                                PART_B_KEYS, allowed, notes)
    checks = _str_list(raw_b.get("attorney_checks"), 30)
    section = {**part_a, **part_b}

    if not record.get("contract_pages"):
        checks.append("No contract pages were found in the record; add the contractual clauses manually.")
    missing = [key for key in ("authority", "case_number", "claimant") if section["heading"].get(key) == PLACEHOLDER]
    if missing:
        checks.append("Complete the heading: " + ", ".join(missing).replace("_", " ") + ".")

    return {
        "format": PLEADING_FORMAT,
        "language": language,
        "represented_party_en": f"{BANK_EN} (BSF)",
        "represented_party_ar": BANK_AR,
        "representation_check": "bsf_confirmed",
        f"title_{language}": section["heading"].get("title", ""),
        f"pleading_{language}": section,
        "attorney_checks": checks + notes,
        "source_ids_used": _node_ids_used(section),
    }


def revise_pleading(memo: dict, revision_request: str, record: dict,
                    progress: Optional[Callable[[str], None]] = None) -> dict:
    """Apply an attorney's requested changes in the pleading's language:
    only the sections that change are rewritten."""
    report = progress or (lambda message: None)
    language = pleading_language(memo)
    key = f"pleading_{language}"
    allowed = {node["node_id"] for node in record.get("authorities", []) if node.get("node_id")}
    current = dict(memo.get(key) or {})

    record = fit_record({**record, "page_summaries": []}, 45000)
    report("Revising the pleading…")
    result = _call(_with_language(REVISION_PROMPT, language),
                   {**record, "current_pleading": current, "revision_request": _text(revision_request, 4000)})
    changed = _unwrap(result, ("changed_sections", "change_notes")).get("changed_sections")
    changed = changed if isinstance(changed, dict) else {}
    changed = {name: value for name, value in changed.items() if name in PART_A_KEYS + PART_B_KEYS}
    notes: list = []
    revised = {**current, **normalise_part({**current, **changed}, allowed, notes)}

    return {
        **memo,
        "language": language,
        f"title_{language}": revised.get("heading", {}).get("title", memo.get(f"title_{language}", "")),
        key: revised,
        "change_notes": _str_list(result.get("change_notes"), 20),
        "rejected_changes": _str_list(result.get("rejected_changes"), 20),
        "attorney_checks": list(memo.get("attorney_checks") or []) + notes,
        "source_ids_used": _node_ids_used(revised),
    }


def is_full_pleading(memo: Any) -> bool:
    return isinstance(memo, dict) and memo.get("format") == PLEADING_FORMAT


# ---------------------------------------------------------------------------
# 4. Rendering
# ---------------------------------------------------------------------------
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV"]
ARABIC_ORDINALS = ["أولاً", "ثانياً", "ثالثاً", "رابعاً", "خامساً", "سادساً", "سابعاً", "ثامناً", "تاسعاً",
                   "عاشراً", "الحادي عشر", "الثاني عشر", "الثالث عشر", "الرابع عشر"]
LETTERS_EN = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LETTERS_AR = ["أ", "ب", "ج", "د", "هـ", "و", "ز", "ح", "ط", "ي", "ك", "ل", "م", "ن"]

LABELS = {
    "en": {
        "submitted_by": "Submitted by", "against": "Against", "case_number": "Case No.",
        "subject": "Subject", "authority": "Before", "dispute_type": "Type of dispute",
        "introduction": "Preliminary Statement",
        "claims": "Summary of the Claimant's Allegations",
        "claim": "Claim",
        "chronology": "Factual Background and Chronology",
        "table": ("Date", "Event", "Supporting Evidence"),
        "contract": "Relevant Contractual Provisions",
        "framework": "Applicable Legal and Regulatory Framework",
        "accounting": "Accounting and Financial Findings",
        "evidence": "Evidence", "finding": "Accounting finding",
        "outcomes": {"consistent": "Consistent", "inconsistent": "Inconsistent", "unresolved": "Unresolved"},
        "responses": "Response to the Claimant's Allegations",
        "response_to": "Response to Allegation",
        "allegation": "Claimant's allegation", "position": "Bank's position",
        "relevant_evidence": "Relevant evidence", "accounting_finding": "Accounting finding",
        "provision": "Applicable provision", "analysis": "Analysis", "conclusion": "Conclusion",
        "authority_nodes": "Authority", "source": "Source",
        "procedural": "Procedural Defences", "basis": "Basis",
        "substantive": "Substantive Defences",
        "unresolved": "Matters Not Conclusively Established by the Current Record",
        "relief": "Relief Requested",
        "relief_default": "For the reasons set out above, Banque Saudi Fransi respectfully requests that the competent authority:",
        "documents": "Documents Relied Upon",
        "signature": ("Counsel", "License No.", "Date"),
    },
    "ar": {
        "submitted_by": "مقدمة من", "against": "ضد", "case_number": "رقم القضية",
        "subject": "موضوع الدعوى", "authority": "إلى", "dispute_type": "نوع النزاع",
        "introduction": "مقدمة وتمهيد",
        "claims": "ملخص ادعاءات المدعي",
        "claim": "الادعاء",
        "chronology": "الوقائع والتسلسل الزمني للقضية",
        "table": ("التاريخ", "الواقعة", "المستند المؤيد"),
        "contract": "الأحكام التعاقدية ذات الصلة",
        "framework": "الإطار النظامي والتنظيمي المطبق",
        "accounting": "النتائج المحاسبية والمالية",
        "evidence": "الأدلة", "finding": "النتيجة المحاسبية",
        "outcomes": {"consistent": "متسقة", "inconsistent": "غير متسقة", "unresolved": "غير محسومة"},
        "responses": "الرد على ادعاءات المدعي",
        "response_to": "الرد على الادعاء",
        "allegation": "ادعاء المدعي", "position": "رد البنك",
        "relevant_evidence": "الأدلة والمستندات المؤيدة", "accounting_finding": "النتيجة المحاسبية ذات الصلة",
        "provision": "السند التعاقدي أو النظامي", "analysis": "التحليل", "conclusion": "النتيجة",
        "authority_nodes": "السند", "source": "المصدر",
        "procedural": "الدفوع الشكلية والإجرائية", "basis": "الأساس",
        "substantive": "الدفوع الموضوعية",
        "unresolved": "المسائل غير المحسومة أو أوجه النقص في الأدلة",
        "relief": "الطلبات",
        "relief_default": "بناءً على ما تقدم، يلتمس البنك السعودي الفرنسي من الجهة المختصة ما يلي:",
        "documents": "المستندات والمرفقات المؤيدة",
        "closing_section": "الخاتمة والتوقيع",
        "signature": ("المحامي", "رقم الترخيص", "التاريخ"),
    },
}


def _cell(value: str) -> str:
    return (value or "—").replace("|", "/").replace("\n", " ")


def pleading_to_markdown(memo: dict, language: str = "") -> str:
    """Markdown of a stored pleading, in the language it was drafted in.
    Pleadings drafted in both languages (before the language choice) are
    shown in the requested language."""
    if memo.get("language") in LANGUAGES or not memo.get(f"pleading_{language}"):
        language = pleading_language(memo)
    is_ar = language == "ar"
    labels = LABELS["ar" if is_ar else "en"]
    section = memo.get("pleading_ar" if is_ar else "pleading_en") or {}
    letters = LETTERS_AR if is_ar else list(LETTERS_EN)
    lines: list[str] = []
    counter = [0]

    def title(text: str) -> None:
        index = counter[0]
        counter[0] += 1
        number = ARABIC_ORDINALS[index] if is_ar else ROMAN[index]
        lines.append(f"## {number}: {text}" if is_ar else f"## {number}. {text}")

    def paragraphs(values) -> None:
        lines.extend(value for value in values or [] if value)

    def ids(values) -> str:
        return f" `[{', '.join(values)}]`" if values else ""

    heading = section.get("heading") or {}
    if is_ar:
        lines.append("بسم الله الرحمن الرحيم")
    if heading.get("authority") not in (None, "", PLACEHOLDER):
        lines.append(f"**{labels['authority']}:** {heading['authority']}")
    lines.append(f"# {heading.get('title') or ('مذكرة جوابية' if is_ar else 'Statement of Defence')}")
    lines.append("\n".join([
        f"**{labels['submitted_by']}:** {heading.get('submitted_by', PLACEHOLDER)}",
        f"**{labels['against']}:** {heading.get('against', PLACEHOLDER)}",
        f"**{labels['case_number']}:** {heading.get('case_number', PLACEHOLDER)}",
        f"**{labels['subject']}:** {heading.get('subject') if heading.get('subject') not in (None, '', PLACEHOLDER) else heading.get('dispute_type', PLACEHOLDER)}",
    ]))

    # Preliminary statement: numbered in Arabic (أولاً), unnumbered in English.
    if is_ar:
        title(labels["introduction"])
    else:
        lines.append(f"## {labels['introduction']}")
    paragraphs(section.get("introduction"))

    title(labels["claims"])
    for item in section.get("claims_summary") or []:
        lines.append(f"### {labels['claim']} {item['number']} — {item.get('title') or ''}".rstrip(" —"))
        lines.append(item.get("allegation", ""))

    title(labels["chronology"])
    rows = section.get("chronology") or []
    if rows:
        head = labels["table"]
        lines.append("\n".join(
            [f"| {head[0]} | {head[1]} | {head[2]} |", "| --- | --- | --- |"]
            + [f"| {_cell(row['date'])} | {_cell(row['event'])} | {_cell(row['evidence'])} |" for row in rows]
        ))
    paragraphs(section.get("chronology_narrative"))

    title(labels["contract"])
    for index, item in enumerate(section.get("contractual_provisions") or []):
        letter = letters[index % len(letters)]
        lines.append(f"### {letter}. {item.get('heading') or item.get('clause') or ''}")
        clause = f"**{item['clause']}** — " if item.get("clause") else ""
        source = f" ({labels['source']}: {item['source']})" if item.get("source") else ""
        lines.append(f"{clause}{item.get('content', '')}{source}")
    if section.get("contract_note"):
        lines.append(section["contract_note"])

    title(labels["framework"])
    for index, item in enumerate(section.get("legal_framework") or []):
        letter = letters[index % len(letters)]
        lines.append(f"### {letter}. {item.get('heading') or item.get('authority') or ''}")
        authority = f"**{item['authority']}**{ids(item.get('node_ids'))}" if item.get("authority") else ""
        lines.append(" — ".join(filter(None, [authority, item.get("content", "")])))

    title(labels["accounting"])
    for index, item in enumerate(section.get("accounting_findings") or []):
        letter = letters[index % len(letters)]
        lines.append(f"### {letter}. {item.get('heading', '')}")
        points = [f"- {point['label']}: {point['value'] or '—'}" for point in item.get("points") or []]
        if item.get("evidence"):
            points.append(f"- {labels['evidence']}: {'; '.join(item['evidence'])}")
        points.append(f"- {labels['finding']}: {labels['outcomes'].get(item.get('outcome'), item.get('outcome', ''))}")
        lines.append("\n".join(points))
        if item.get("finding"):
            lines.append(item["finding"])

    title(labels["responses"])
    for item in section.get("claim_responses") or []:
        lines.append(f"### {item['number']}. {labels['response_to']}: {item.get('title', '')}")
        for key, label in (("allegation", "allegation"), ("bank_position", "position")):
            if item.get(key):
                lines.append(f"**{labels[label]}:** {item[key]}")
        if item.get("evidence"):
            lines.append(f"**{labels['relevant_evidence']}:**")
            lines.append("\n".join(f"- {value}" for value in item["evidence"]))
        if item.get("accounting_finding"):
            lines.append(f"**{labels['accounting_finding']}:** {item['accounting_finding']}")
        if item.get("applicable_provision") or item.get("node_ids"):
            lines.append(f"**{labels['provision']}:** {item.get('applicable_provision', '')}{ids(item.get('node_ids'))}")
        if item.get("analysis"):
            lines.append(f"**{labels['analysis']}:**")
            paragraphs(item["analysis"])
        if item.get("conclusion"):
            lines.append(f"**{labels['conclusion']}:** {item['conclusion']}")

    if section.get("procedural_defences"):
        title(labels["procedural"])
        for index, item in enumerate(section["procedural_defences"]):
            lines.append(f"### {letters[index % len(letters)]}. {item.get('heading', '')}")
            lines.append(f"**{labels['basis']}:** {item.get('basis', '')}")
            if item.get("analysis"):
                lines.append(item["analysis"] + ids(item.get("node_ids")))

    title(labels["substantive"])
    for index, item in enumerate(section.get("substantive_defences") or []):
        lines.append(f"### {letters[index % len(letters)]}. {item.get('heading', '')}")
        paragraphs(item.get("reasoning"))
        if item.get("node_ids"):
            lines.append(f"{labels['authority_nodes']}:{ids(item['node_ids'])}")

    title(labels["unresolved"])
    unresolved = section.get("unresolved_matters") or []
    if unresolved:
        lines.append("\n".join(f"- {value}" for value in unresolved))

    title(labels["relief"])
    relief = section.get("relief_requested") or {}
    lines.append(relief.get("introduction") or labels["relief_default"])
    if relief.get("items"):
        lines.append("\n".join(f"{index + 1}. {value}" for index, value in enumerate(relief["items"])))

    title(labels["documents"])
    documents = section.get("documents_relied_upon") or []
    if documents:
        lines.append("\n".join(f"{index + 1}. {value}" for index, value in enumerate(documents)))

    signature = section.get("signature") or {}
    if is_ar:
        title(labels["closing_section"])
        lines.append("والله الموفق، وصلى الله وسلم على نبينا محمد.")
    else:
        lines.append("---")
    sig = labels["signature"]
    lines.append("\n".join([
        f"**{signature.get('party') if signature.get('party') not in (None, '', PLACEHOLDER) else (BANK_AR if is_ar else BANK_EN)}**",
        f"{sig[0]}: {signature.get('counsel', PLACEHOLDER)}",
        f"{sig[1]}: {signature.get('license', PLACEHOLDER)}",
        f"{sig[2]}: {signature.get('date', PLACEHOLDER)}",
    ]))
    return "\n\n".join(line for line in lines if line is not None and line != "")
