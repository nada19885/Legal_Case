from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .llm import complete_json


INTERVIEWER_SYSTEM_PROMPT = r"""
You are a Saudi legal case-intake and evidence-planning assistant.

Review the entire case after every interaction. The user may upload one PDF,
many PDFs together, or add documents later to the same case.

Always use:
- all prior documents and extracted pages;
- the latest uploaded document batch separately;
- all messages and answers;
- facts, parties, events, issues and evidence requests;
- previous interview state and legal research.

Do not treat a new case_document_id as a separate case when case_id is the same.

Identify whether the latest material:
- confirms an existing fact;
- contradicts another source;
- fills an evidence gap;
- refers to a missing attachment, appendix, letter, email, approval, statement,
  schedule, report, notice or other evidence;
- introduces a new party, event or issue;
- requires clarification.

A referenced document is missing only when the current material clearly refers
to it and no uploaded document appears to match by title, description, date,
sender, recipient, reference number or content.

Rules:
1. Treat the latest user message as an answer to the immediately preceding
   assistant question.
2. Acknowledge the latest answer or upload.
3. Never repeat a resolved question or evidence request.
4. Return up to five follow-up actions.
5. Ask no more than three clarification questions in one reply.
6. You may request several genuinely missing documents in one reply.
7. Prioritise critical and high-value gaps.
8. Do not manufacture questions merely because a document was uploaded.
9. Separate established facts, allegations, disputed facts, contradictions
   and unknowns.
10. Do not invent facts, evidence or law.
11. Do not recommend concealment, destruction, alteration or fabrication.
12. Return valid JSON only.
13. Do not place literal control characters in JSON strings.

Return exactly:
{
  "acknowledgement": "",
  "case_summary": "",
  "case_type": "",
  "procedural_posture": "",
  "established_facts": [],
  "allegations": [],
  "material_unknowns": [],
  "contradictions": [],
  "potential_issues": [],
  "follow_up_actions": [
    {
      "action_type": "ask_question|request_evidence|confirm_fact",
      "question": "",
      "evidence_type": "",
      "evidence_description": "",
      "referenced_in_document": "",
      "referenced_page_ids": [],
      "reason": "",
      "priority": "critical|high|medium|low"
    }
  ],
  "ready_for_research": false,
  "ready_for_analysis": false,
  "ready_for_defence": false,
  "blocking_gaps": [],
  "confidence": 0.0
}
"""


@dataclass
class InterviewDecision:
    payload: dict

    @property
    def acknowledgement(self) -> str:
        return str(self.payload.get("acknowledgement", "")).strip()

    @property
    def follow_up_actions(self) -> list[dict]:
        actions = self.payload.get("follow_up_actions", [])
        if not isinstance(actions, list):
            return []
        return [item for item in actions if isinstance(item, dict)][:5]

    @property
    def ready_for_research(self) -> bool:
        return bool(self.payload.get("ready_for_research", False))

    @property
    def ready_for_analysis(self) -> bool:
        return bool(self.payload.get("ready_for_analysis", False))

    @property
    def ready_for_defence(self) -> bool:
        return bool(self.payload.get("ready_for_defence", False))

    @property
    def action_type(self) -> str:
        if self.ready_for_research and not self.follow_up_actions:
            return "ready_for_research"
        return "follow_up"

    @property
    def question(self) -> str:
        for action in self.follow_up_actions:
            if action.get("action_type") == "ask_question":
                return str(action.get("question", "")).strip()
        return ""


def _records(value: Any) -> list[dict]:
    if value is None:
        return []
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict(orient="records")
        except TypeError:
            pass
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def build_case_state(
    case_record: dict,
    messages=None,
    document_pages=None,
    documents=None,
    approved_facts=None,
    fact_candidates=None,
    parties=None,
    approved_issues=None,
    issue_candidates=None,
    evidence=None,
    legal_research=None,
    previous_interview_state=None,
    latest_documents=None,
    latest_document_pages=None,
) -> dict:
    return {
        "case": case_record or {},
        "messages": _records(messages),
        "documents": _records(documents),
        "document_pages": _records(document_pages),
        "approved_facts": _records(approved_facts),
        "fact_candidates": _records(fact_candidates),
        "parties": _records(parties),
        "approved_issues": _records(approved_issues),
        "issue_candidates": _records(issue_candidates),
        "evidence": _records(evidence),
        "legal_research": _records(legal_research),
        "previous_interview_state": previous_interview_state or {},
        "latest_documents": _records(latest_documents),
        "latest_document_pages": _records(latest_document_pages),
    }


def assess_case_completeness(case_state: dict) -> InterviewDecision:
    result = complete_json(
        system_prompt=INTERVIEWER_SYSTEM_PROMPT,
        user_payload={
            "instruction": (
                "Review the whole case and the latest upload or answer. "
                "Return only unresolved, material follow-up actions."
            ),
            "case_state": case_state,
        },
    )
    if not isinstance(result.get("follow_up_actions"), list):
        result["follow_up_actions"] = []
    return InterviewDecision(payload=result)


def format_interviewer_reply(decision: InterviewDecision) -> str:
    parts = []
    if decision.acknowledgement:
        parts.append(decision.acknowledgement)

    evidence = [
        item for item in decision.follow_up_actions
        if item.get("action_type") == "request_evidence"
    ]
    questions = [
        item for item in decision.follow_up_actions
        if item.get("action_type") == "ask_question"
    ][:3]
    confirmations = [
        item for item in decision.follow_up_actions
        if item.get("action_type") == "confirm_fact"
    ]

    if evidence:
        lines = ["### Missing or referenced evidence"]
        for index, item in enumerate(evidence, 1):
            title = str(item.get("evidence_type") or "Supporting document").strip()
            description = str(item.get("evidence_description", "")).strip()
            source = str(item.get("referenced_in_document", "")).strip()
            reason = str(item.get("reason", "")).strip()
            line = f"{index}. **{title}**"
            if description:
                line += f" — {description}"
            if source:
                line += f"\n   Referenced in: `{source}`"
            if reason:
                line += f"\n   Why it matters: {reason}"
            lines.append(line)
        parts.append("\n\n".join(lines))

    if questions:
        lines = ["### Clarification questions"]
        for index, item in enumerate(questions, 1):
            question = str(item.get("question", "")).strip()
            if not question:
                continue
            line = f"{index}. {question}"
            reason = str(item.get("reason", "")).strip()
            if reason:
                line += f"\n   Why I am asking: {reason}"
            lines.append(line)
        if len(lines) > 1:
            parts.append("\n\n".join(lines))

    if confirmations:
        lines = ["### Items requiring confirmation"]
        for item in confirmations:
            question = str(item.get("question", "")).strip()
            if question:
                lines.append(f"- {question}")
        if len(lines) > 1:
            parts.append("\n".join(lines))

    if not decision.follow_up_actions:
        parts.append(
            "I do not currently need further material clarification or "
            "evidence. The case can proceed to controlled legal research "
            "and attorney summary review."
        )

    return "\n\n".join(part for part in parts if part)
