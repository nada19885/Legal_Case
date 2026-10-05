"""
Attorney Workbench - Pleading Generation, Grounded Q&A, and Pleading Revision.
Location: lib/python/legal_platform/attorney_workbench.py
"""

from __future__ import annotations

import json
from typing import Any

from .llm import complete_json


def _records(value: Any) -> list[dict]:
    if value is None:
        return []
    if hasattr(value, "to_dict"):
        try:
            return value.fillna("").to_dict(orient="records")
        except Exception:
            return value.to_dict(orient="records")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _compact(value: Any, limit: int = 30) -> str:
    """Clamps string to a max limit (default 30 characters) with ellipsis."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _json_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":")))


def _compact_mapping(value: Any, allowed_fields: tuple[str, ...], *, text_limit: int = 700) -> dict:
    if not isinstance(value, dict):
        return {}
    return {
        key: _compact(value.get(key), text_limit)
        for key in allowed_fields
        if value.get(key) not in (None, "", [], {})
    }


def _compact_summary(summary: Any) -> dict:
    row = summary if isinstance(summary, dict) else {}
    result = {
        "matter_overview_ar": _compact(row.get("matter_overview_ar"), 5000),
        "matter_overview_en": _compact(row.get("matter_overview_en"), 5000),
    }
    limits = {
        "parties": 10,
        "chronology": 20,
        "established_facts": 18,
        "allegations": 10,
        "disputed_facts": 10,
        "available_evidence": 15,
        "missing_evidence": 10,
        "bank_risks": 8,
        "bank_gaps": 8,
        "bank_legal_questions": 8,
    }
    for field, max_items in limits.items():
        values = row.get(field, [])
        if isinstance(values, list):
            result[field] = values[:max_items]
    return result


def _compact_analysis(value: Any) -> Any:
    if isinstance(value, dict):
        preferred = (
            "issue_analysis", "analysis_cards", "issues", "conclusions",
            "defences", "factual_findings", "legal_findings", "warnings",
        )
        result = {}
        for key in preferred:
            item = value.get(key)
            if isinstance(item, list):
                result[key] = item[:10]
            elif isinstance(item, dict):
                result[key] = item
            elif item not in (None, ""):
                result[key] = _compact(item, 2000)
        return result
    return value or {}


def _compact_strategy(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key in ("strategy", "actions", "defence_theories", "objectives", "risks", "recommended_actions"):
            item = value.get(key)
            if isinstance(item, list):
                result[key] = item[:10]
            elif isinstance(item, dict):
                result[key] = item
            elif item not in (None, ""):
                result[key] = _compact(item, 2000)
        return result
    return value or {}


def _compact_forensic_data(case_data: dict | None) -> dict:
    """
    Extract and bound the financial timeline and the new
    claim-based accounting analysis for pleading generation.
    """
    source = case_data if isinstance(case_data, dict) else {}

    # ---------------------------------------------------------
    # Financial timeline
    # ---------------------------------------------------------
    raw_timeline = _records(source.get("financial_timeline", []))

    compact_timeline = []

    for row in raw_timeline[:35]:
        compact_timeline.append({
            "record_id": str(
                row.get("row_id", "")
                or row.get("timeline_id", "")
            ),
            "fact_type": str(row.get("fact_type", "") or "transaction"),
            "date": str(row.get("date", "") or "—"),
            "page": str(row.get("page_number", "")),
            "amount": " ".join(filter(None, [
                str(row.get("value") or row.get("amount") or "—"),
                str(row.get("currency") or ""),
            ])),
            "type": str(row.get("debit_or_credit", "") or ""),
            "description": _compact(
                row.get("description", ""),
                300,
            ),
            "status": str(row.get("status", "") or row.get("row_status", "")),
        })

    # ---------------------------------------------------------
    # Claim-based accounting analysis
    # ---------------------------------------------------------
    findings = source.get("forensic_findings") or {}

    raw_claim_evaluations = _records(
        findings.get("claim_evaluations", [])
    )

    compact_claim_evaluations = []

    for evaluation in raw_claim_evaluations[:15]:

        evidence_found = []
        # Only records confirmed to exist in the reviewed ledger may be
        # cited; ids the model produced that the ledger lacks are dropped.
        verified_ids = evaluation.get("evidence_record_ids")
        verified_ids = (
            {str(x) for x in verified_ids}
            if isinstance(verified_ids, list) and "unverified_record_ids" in evaluation
            else None
        )

        for evidence in _records(
            evaluation.get("financial_evidence_found", [])
        )[:15]:
            if verified_ids is not None and str(evidence.get("record_id", "")) not in verified_ids:
                continue
            evidence_found.append({
                "record_id": str(
                    evidence.get("record_id", "")
                ),
                "date": str(
                    evidence.get("date", "")
                ),
                "type": str(
                    evidence.get("type", "")
                ),
                "amount": evidence.get("amount"),
                "reference": _compact(
                    evidence.get("reference", ""),
                    200,
                ),
            })

        compact_claim_evaluations.append({
            "claim_id": str(
                evaluation.get("claim_id", "")
            ),
            "claim": _compact(
                evaluation.get("claim", ""),
                1200,
            ),
            "financial_question": _compact(
                evaluation.get("financial_question", ""),
                1000,
            ),
            "expected_evidence": _compact(
                evaluation.get("expected_evidence", ""),
                1000,
            ),
            "financial_evidence_found": evidence_found,
            "parent_claim": _compact(evaluation.get("parent_claim", ""), 800),
            "claimed_amount": str(evaluation.get("claimed_amount", "") or ""),
            "substantiated_amount": str(evaluation.get("substantiated_amount", "") or ""),
            "accounting_position": _compact(evaluation.get("accounting_position", ""), 1500),
            **{
                group: [
                    {
                        "record_ids": [str(x) for x in (entry.get("record_ids") or [])][:10],
                        "explanation": _compact(entry.get("explanation", ""), 500),
                    }
                    for entry in (evaluation.get(group) or [])[:8]
                    if isinstance(entry, dict)
                ]
                for group in (
                    "supporting_evidence",
                    "partially_supporting_evidence",
                    "contradicting_evidence",
                    "unresolved_evidence",
                )
            },
            "missing_evidence": [
                _compact(item, 400)
                for item in (evaluation.get("missing_evidence") or [])[:10]
                if isinstance(item, str) and item.strip()
            ],
            "contradictions": [
                {
                    "description": _compact(item.get("description", ""), 800),
                    "record_ids": [str(x) for x in (item.get("record_ids") or [])][:10],
                }
                for item in (evaluation.get("contradictions") or [])[:10]
                if isinstance(item, dict) and str(item.get("description", "")).strip()
            ],
            "comparison": _compact(
                evaluation.get("comparison", ""),
                1500,
            ),
            "result": str(
                evaluation.get("result", "")
            ),
            "accounting_response": _compact(
                evaluation.get("accounting_response", ""),
                1800,
            ),
            "limitation": _compact(
                evaluation.get("limitation", ""),
                1000,
            ),
            "evidence_record_ids": (
                evaluation.get("evidence_record_ids", [])[:20]
                if isinstance(
                    evaluation.get("evidence_record_ids"),
                    list,
                )
                else []
            ),
        })

    return {
        "reconciled_financial_timeline": compact_timeline,
        "claim_evaluations": compact_claim_evaluations,
    }


def _case_context(case_record, summary=None, analysis=None, strategy=None, research=None, case_data=None,
                  pleading=None):
    authorities = []
    for node in _records((research or {}).get("authority_nodes", []))[:24]:
        authorities.append({
            "node_id": str(node.get("node_id", "") or ""),
            "title": _compact(node.get("heading_path") or node.get("title"), 240),
            "citation": _compact(node.get("citation") or node.get("article_number"), 180),
            "text": _compact(node.get("canonical_text") or node.get("summary"), 1100),
        })

    field_map = {
        "facts": ("fact_id", "fact_text", "fact", "statement", "status", "source_page_ids", "source_ids"),
        "fact_candidates": ("fact_candidate_id", "fact_text", "fact", "statement", "status", "source_page_ids", "source_ids"),
        "parties": ("party_id", "party_name", "name", "party_role", "role", "description", "source_ids"),
        "issues": ("issue_id", "issue_title", "title", "description", "status", "source_ids"),
        "issue_candidates": ("issue_candidate_id", "issue_title", "title", "description", "status", "source_ids"),
        "evidence": ("evidence_id", "evidence_title", "title", "description", "document_id", "page_ids", "source_ids", "review_status"),
        "documents": ("case_document_id", "filename", "file_name", "document_type", "page_count"),
        "pages": ("page_id", "case_document_page_id", "case_document_id", "page_number", "page_summary", "document_type"),
        "events": ("event_id", "event_date", "date", "event_text", "event", "description", "status", "source_ids"),
    }
    item_limits = {
        "facts": 24, "fact_candidates": 16, "parties": 12,
        "issues": 12, "issue_candidates": 10, "evidence": 18,
        "documents": 20, "pages": 30, "events": 20,
    }

    material = {}
    source = case_data if isinstance(case_data, dict) else {}
    for collection, allowed_fields in field_map.items():
        rows = _records(source.get(collection))
        compact_rows = []
        for row in rows[:item_limits[collection]]:
            compact_row = _compact_mapping(row, allowed_fields, text_limit=700)
            if compact_row:
                compact_rows.append(compact_row)
        material[collection] = compact_rows

    forensic_payload = _compact_forensic_data(source)

    context = {
        "representation_mandate": {
            "represented_party": "Banque Saudi Fransi (BSF) / البنك السعودي الفرنسي",
            "role_rule": "BSF is always the represented client. The pleading must advance and protect BSF's position, never the opposing party's position.",
            "opponent_rule": "Identify the claimant, customer, applicant, or other adverse party only from the record and treat that party as the opponent.",
        },
        "case": {
            key: _compact(value, 300)
            for key, value in (case_record or {}).items()
            if key in {
                "case_id", "case_name", "case_type", "jurisdiction",
                "preferred_language", "matter_date", "customer_type",
                "regulated_entity_type", "product_type",
            }
        },
        "approved_attorney_summary": _compact_summary(summary),
        "legal_analysis": _compact_analysis(analysis),
        **({"defence_plan": _compact_strategy(strategy)} if strategy else {}),
        **({"written_pleading": _compact(pleading, 12000)} if pleading else {}),
        "forensic_financial_analysis": forensic_payload,
        "authorities": authorities,
        "case_material": material,
    }

    print(
        "[pleading context built] payload_chars={} authorities={} pages={} facts={} fin_timeline={}".format(
            _json_chars(context),
            len(authorities),
            len(material.get("pages", [])),
            len(material.get("facts", [])) + len(material.get("fact_candidates", [])),
            len(forensic_payload.get("reconciled_financial_timeline", [])),
        ),
        flush=True,
    )
    return context


PLEADING_PROMPT = r"""
You are a Saudi legal drafting assistant supporting a qualified Saudi attorney.
Prepare a formal Saudi court submission, not a conversational response, client
letter, internal memorandum, or generic essay.

MANDATORY REPRESENTATION
You act exclusively for Banque Saudi Fransi (BSF / البنك السعودي الفرنسي).
The pleading must defend, protect, and advance BSF's legal position. It must never
be drafted for the claimant, customer, applicant, account holder, or any other
adverse party. Where BSF is the defendant or respondent, draft a defence/response
on behalf of BSF. Where BSF's procedural capacity is unclear, keep BSF as the
represented party and use a bracketed placeholder for the exact capacity.

Do not request relief that primarily benefits the opponent unless it is expressly
identified as a conditional settlement option approved by BSF's attorney. In
particular, do not request release of frozen funds, compensation to the customer,
or acceptance of the opponent's allegations as BSF's primary relief.

LEGAL AND ACCOUNTING ANALYSIS INTEGRATION

The legal analysis and the accounting analysis are two independent analytical
inputs. Use both when preparing the written pleading.

LEGAL ANALYSIS:
Use the supplied `legal_analysis` for legal issues, legal reasoning, defences,
and conclusions supported by the retrieved legal authorities.

ACCOUNTING ANALYSIS:
Use the supplied `forensic_financial_analysis` for financial facts and
claim-based accounting findings.

The accounting analysis contains:
- the reconciled financial timeline; and
- `claim_evaluations`, where each customer claim has been independently
  evaluated against the available financial evidence.

For each relevant claim evaluation:
- understand the customer's claim;
- use the identified financial question;
- use the financial evidence found;
- use the accounting comparison;
- accurately reflect the accounting result;
- incorporate the accounting response where relevant to BSF's factual position;
- preserve any stated limitations or missing evidence.

IMPORTANT:
- Do not treat accounting findings as legal conclusions.
- Do not create a legal proposition from an accounting finding unless it is
  supported by the supplied legal analysis and legal authorities.
- Do not change the result of an accounting evaluation.
- Do not omit contradictory financial evidence.
- If an accounting evaluation is NOT_VERIFIABLE or identifies a limitation,
  state that accurately rather than presenting the matter as proven.
- Use accounting evidence to strengthen the factual and monetary portions of
  the pleading where relevant.

SOURCE RESTRICTION
Use only:
1. the attorney-approved case summary, chronology, and forensic financial analysis;
2. the supplied case facts, evidence, documents, and source pages;
3. the supplied legal analysis and defence plan; and
4. the supplied legal authorities retrieved from the configured knowledge base.

Do not use general model knowledge or outside law. Every legal proposition must be traceable to a supplied authority node_id.

SAUDI DRAFTING STYLE
Draft the Arabic version as a professional Saudi pleading suitable in form for
attorney review before submission through Najiz. Select the most appropriate
document label from the supplied case posture (e.g., مذكرة جوابية, مذكرة دفاع أولى, مذكرة رد).

The Arabic pleading must:
- begin with: بسم الله الرحمن الرحيم;
- address the competent court or judicial circuit respectfully;
- state the subject and formal salutation;
- present a concise statement of facts incorporating the audited financial timeline and source pages;
- separate procedural/formal defences from substantive defences;
- organise each defence as: heading, supported fact, applicable authority, application, and requested consequence;
- respond directly and respectfully to each material opposing allegation using the legal analysis and, where financially relevant, the corresponding claim-based accounting evaluation;- cite retrieved authorities by their title/article/citation and node_id;
- number the final requests clearly;
- end respectfully with: والله الموفق، وصلى الله وسلم على نبينا محمد;
- include a signature block for the represented party or attorney.

The English version must be an independent professional translation-equivalent for review.

Return exactly one JSON object:
{
  "represented_party_ar": "البنك السعودي الفرنسي",
  "represented_party_en": "Banque Saudi Fransi (BSF)",
  "opposing_party_ar": "",
  "opposing_party_en": "",
  "representation_check": "bsf_confirmed",
  "filing_type_ar": "",
  "filing_type_en": "",
  "title_ar": "",
  "title_en": "",
  "pleading_ar": {
    "basmala": "بسم الله الرحمن الرحيم",
    "court_heading": "",
    "case_details": "",
    "party_heading": "",
    "subject": "",
    "formal_salutation": "",
    "opening": "",
    "facts": [
      {
        "sequence": 1,
        "date": "",
        "fact": "",
        "source_document": "",
        "source_page": ""
      }
    ],
    "procedural_defences": [
      {
        "heading": "",
        "supported_fact": "",
        "authority": "",
        "authority_node_ids": [""],
        "application": "",
        "requested_consequence": ""
      }
    ],
    "substantive_defences": [
      {
        "heading": "",
        "supported_fact": "",
        "authority": "",
        "authority_node_ids": [""],
        "application": "",
        "requested_consequence": ""
      }
    ],
    "response_to_opponent": [
      {
        "allegation": "",
        "response": "",
        "factual_source_ids": [""],
        "authority_node_ids": [""]
      }
    ],
    "requests": [
      {
        "priority": "primary",
        "text": "",
        "basis": ""
      }
    ],
    "evidence_reservations": [""],
    "closing": "",
    "signature_block": ""
  },
  "pleading_en": {
    "court_heading": "",
    "case_details": "",
    "party_heading": "",
    "subject": "",
    "formal_salutation": "",
    "opening": "",
    "facts": [
      {
        "sequence": 1,
        "date": "",
        "fact": "",
        "source_document": "",
        "source_page": ""
      }
    ],
    "procedural_defences": [
      {
        "heading": "",
        "supported_fact": "",
        "authority": "",
        "authority_node_ids": [""],
        "application": "",
        "requested_consequence": ""
      }
    ],
    "substantive_defences": [
      {
        "heading": "",
        "supported_fact": "",
        "authority": "",
        "authority_node_ids": [""],
        "application": "",
        "requested_consequence": ""
      }
    ],
    "response_to_opponent": [
      {
        "allegation": "",
        "response": "",
        "factual_source_ids": [""],
        "authority_node_ids": [""]
      }
    ],
    "requests": [
      {
        "priority": "primary",
        "text": "",
        "basis": ""
      }
    ],
    "evidence_reservations": [""],
    "closing": "",
    "signature_block": ""
  },
  "attorney_checks": [""],
  "factual_source_ids_used": [""],
  "legal_authority_ids_used": [""]
}
""".strip()


def _pleading_represents_bsf(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    represented = " ".join([
        str(result.get("represented_party_ar", "") or ""),
        str(result.get("represented_party_en", "") or ""),
        str(result.get("representation_check", "") or ""),
        str((result.get("pleading_ar") or {}).get("party_heading", "") or ""),
        str((result.get("pleading_en") or {}).get("party_heading", "") or ""),
    ]).casefold()
    return any(term in represented for term in (
        "banque saudi fransi", "bsf", "البنك السعودي الفرنسي", "bsf_confirmed"
    ))


def generate_bilingual_memo(
    case_record,
    approved_summary,
    analysis=None,
    strategy=None,
    research=None,
    instructions: str = "",
    case_data=None,
):
    payload = _case_context(
        case_record,
        summary=approved_summary,
        analysis=analysis,
        strategy=strategy,
        research=research,
        case_data=case_data,
    )
    payload["drafting_instructions"] = _compact(instructions, 2000)
    payload["non_negotiable_client_instruction"] = (
        "Draft exclusively for Banque Saudi Fransi (BSF). Do not draft for the claimant "
        "or customer. All primary requests and advocacy must protect BSF."
    )

    failures = []
    for attempt in range(1, 3):
        try:
            result = complete_json(
                PLEADING_PROMPT,
                {**payload, "representation_validation_attempt": attempt},
                temperature=0.1,
            )
            if not _pleading_represents_bsf(result):
                raise ValueError("Generated pleading did not confirm BSF as represented party.")
            return result
        except Exception as error:
            failures.append(repr(error))

    raise RuntimeError(
        "Pleading generation failed BSF representation validation: " + "; ".join(failures)
    )


DISCUSSION_PROMPT = r"""
You are a strictly source-grounded legal case assistant supporting a qualified
attorney. Answer the question using ONLY the supplied case record, approved
summary, forensic financial timeline, extracted case material, and retrieved knowledge-base authorities.

PROHIBITED:
- using general model knowledge, memory, outside law, common legal practice, or assumptions;
- inventing facts, dates, roles, evidence, procedural steps, laws, article numbers, citations, or conclusions;
- presenting an allegation or inference as an established fact;
- citing any identifier that is not present in the supplied payload.

GROUNDING RULES:
1. Every factual proposition must be supported by one or more supplied case source IDs or financial timeline events.
2. Every legal proposition must be supported by one or more supplied authority node_ids.
3. If the supplied record or authorities are insufficient, say so clearly using the standard insufficiency phrase.
4. Answer independently in Arabic and English.

Return JSON only:
{
  "answer_ar": "",
  "answer_en": "",
  "key_points": [""],
  "factual_source_ids": [""],
  "legal_authority_ids": [""],
  "uncertainties": [""],
  "insufficient_support": false,
  "suggested_next_question": ""
}
""".strip()

GROUNDING_AUDIT_PROMPT = r"""
Audit and rewrite a proposed case answer. Use ONLY the supplied source catalog,
case context, forensic financial timeline, and knowledge-base authorities. Remove every unsupported factual
or legal claim.

Every retained factual claim must be traceable to an allowed factual source ID.
Every retained legal claim must be traceable to an allowed authority node_id.
Unknown IDs are forbidden.

Return JSON only using the same schema as the proposed answer:
{
  "answer_ar": "",
  "answer_en": "",
  "key_points": [""],
  "factual_source_ids": [""],
  "legal_authority_ids": [""],
  "uncertainties": [""],
  "insufficient_support": false,
  "suggested_next_question": ""
}
""".strip()


def _collect_ids(value: Any) -> set[str]:
    ids: set[str] = set()
    id_keys = {
        "node_id", "source_id", "page_id", "case_document_page_id",
        "case_document_id", "document_id", "evidence_id", "case_evidence_id",
        "fact_id", "case_fact_id", "case_fact_candidate_id", "issue_id",
        "case_issue_id", "event_id", "case_event_id", "party_id",
        "case_party_id", "message_id", "case_message_id", "timeline_id",
        "discrepancy_id", "finding_id",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in id_keys and str(item or "").strip():
                ids.add(str(item).strip())
            ids.update(_collect_ids(item))
    elif isinstance(value, list):
        for item in value:
            ids.update(_collect_ids(item))
    return ids


def _authority_ids(context: dict) -> set[str]:
    return {
        str(item.get("node_id", "")).strip()
        for item in context.get("authorities", [])
        if str(item.get("node_id", "")).strip()
    }


def _clean_id_list(values: Any, allowed: set[str]) -> list[str]:
    result = []
    for value in values if isinstance(values, list) else []:
        item = str(value or "").strip()
        if item and item in allowed and item not in result:
            result.append(item)
    return result


def answer_case_question(
    question: str,
    case_record,
    approved_summary=None,
    analysis=None,
    strategy=None,
    research=None,
    case_data=None,
    pleading=None,
):
    payload = _case_context(
        case_record,
        summary=approved_summary,
        analysis=analysis,
        strategy=strategy,
        research=research,
        case_data=case_data,
        pleading=pleading,
    )
    payload["question"] = _compact(question, 3000)
    draft = complete_json(
        DISCUSSION_PROMPT,
        payload,
        temperature=0.0,
    )

    allowed_authorities = _authority_ids(payload)
    allowed_factual = _collect_ids(payload.get("case_material", {}))
    allowed_factual.update(_collect_ids(payload.get("approved_attorney_summary", {})))
    allowed_factual.update(_collect_ids(payload.get("case", {})))
    allowed_factual.update(_collect_ids(payload.get("forensic_financial_analysis", {})))

    audit_payload = {
        "question": payload["question"],
        "case_context": payload,
        "proposed_answer": draft,
        "allowed_factual_source_ids": sorted(allowed_factual),
        "allowed_legal_authority_ids": sorted(allowed_authorities),
    }
    audited = complete_json(
        GROUNDING_AUDIT_PROMPT,
        audit_payload,
        temperature=0.0,
    )

    audited["factual_source_ids"] = _clean_id_list(
        audited.get("factual_source_ids"), allowed_factual
    )
    audited["legal_authority_ids"] = _clean_id_list(
        audited.get("legal_authority_ids"), allowed_authorities
    )
    audited["source_ids"] = (
        audited["factual_source_ids"] + audited["legal_authority_ids"]
    )

    has_answer = bool(
        str(audited.get("answer_ar", "")).strip()
        or str(audited.get("answer_en", "")).strip()
    )
    if not has_answer:
        audited["answer_ar"] = "لا تتوافر في سجل القضية والمواد النظامية المسترجعة من قاعدة المعرفة معلومات كافية للإجابة عن هذه النقطة."
        audited["answer_en"] = "The available case record and retrieved knowledge-base authorities do not provide enough information to answer this point."
        audited["insufficient_support"] = True

    return audited


REVISION_PROMPT = r"""
You are revising an existing bilingual Saudi written pleading after an attorney's
case discussion. You act exclusively for Banque Saudi Fransi (BSF / البنك السعودي الفرنسي).
Never change the represented party to the claimant, customer, or another opponent. Apply only the requested, record-supported changes. Preserve
all sound sections that are not affected. Do not invent facts or authorities.
Where a proposed change conflicts with the approved record or forensic timeline, keep the pleading
unchanged and explain the conflict in change_notes. Produce complete replacement
Arabic and English pleadings using the same JSON structure as the existing draft.

Return JSON only with the same pleading fields plus:
{
  "represented_party_ar": "البنك السعودي الفرنسي",
  "represented_party_en": "Banque Saudi Fransi (BSF)",
  "representation_check": "bsf_confirmed",
  "title_ar": "",
  "title_en": "",
  "pleading_ar": {},
  "pleading_en": {},
  "attorney_checks": [""],
  "source_ids_used": [""],
  "change_notes": [""],
  "rejected_changes": [""]
}
""".strip()


def revise_bilingual_pleading(
    revision_request: str,
    current_pleading,
    case_record,
    approved_summary=None,
    analysis=None,
    strategy=None,
    research=None,
    case_data=None,
):
    payload = _case_context(
        case_record,
        summary=approved_summary,
        analysis=analysis,
        strategy=strategy,
        research=research,
        case_data=case_data,
    )
    payload["current_pleading"] = current_pleading or {}
    payload["revision_request"] = _compact(revision_request, 4000)
    revised = complete_json(
        REVISION_PROMPT + "\n\nRequired pleading schema:\n" + PLEADING_PROMPT.split("Return exactly one JSON object:", 1)[1],
        payload,
        temperature=0.1,
    )
    if not _pleading_represents_bsf(revised):
        raise ValueError("Revised pleading did not preserve BSF as represented party.")
    return revised