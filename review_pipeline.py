from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from typing import Any

from .config import (
    COMPLETENESS_LLM_ID,
    REVIEW_BATCH_MAX_CHARS,
    REVIEW_MERGE_MAX_CHARS,
    REVIEW_MAX_BATCH_ITEMS,
    REVIEW_REQUEST_MAX_ATTEMPTS,
    REVIEW_RETRY_DELAY_SECONDS,
)
from .llm import complete_json

try:
    from .config import REVIEW_BATCH_MAX_WORKERS
except ImportError:
    REVIEW_BATCH_MAX_WORKERS = 4


PIPELINE_VERSION = "parallel-review-v10-payload-compat"

print(
    "[review pipeline loaded] version={} file={} completeness_llm_id={}".format(
        PIPELINE_VERSION,
        __file__,
        COMPLETENESS_LLM_ID,
    )
)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


BATCH_REVIEW_SYSTEM_PROMPT = """
You are a legal case-completeness reviewer. Review only the bounded case section
provided in the user payload. Return exactly one valid JSON object. Do not emit
markdown, analysis tags, explanations before JSON, or text after JSON.

Use exactly this schema:
{
  "completeness_score": 0,
  "is_complete": false,
  "ready_for_analysis": false,
  "summary": "",
  "next_question": "",
  "questions": [],
  "blocking_gaps": [],
  "missing_information": [],
  "contradictions": [],
  "unverified_claims": [],
  "missing_evidence": [],
  "timeline_gaps": [],
  "party_gaps": [],
  "legal_reference_gaps": [],
  "recommended_actions": [],
  "source_ids": []
}

Rules:
- Judge only the supplied bounded section and repeated case metadata.
- Do not treat other sections as missing merely because they are not in this batch.
- Preserve page, document, fact, issue, evidence, event, party, and message IDs.
- Do not invent facts or legal conclusions.
- Keep every list concise and factual.
- completeness_score must be an integer from 0 to 100.
- is_complete and ready_for_analysis must be conservative booleans.
- next_question must be the single most useful follow-up question, or an empty string.
- Output JSON only.
""".strip()


# The merge schema is deliberately smaller than the batch schema. This reduces
# malformed JSON from large merge requests. _normalise_review() restores the
# compatibility fields expected by the rest of the application.
MERGE_SYSTEM_PROMPT = """
You merge partial legal case-completeness reviews into one conservative final
review. Return exactly one valid JSON object. Do not emit markdown, commentary,
analysis tags, or text outside JSON.

Use exactly this schema:
{
  "completeness_score": 0,
  "is_complete": false,
  "ready_for_analysis": false,
  "summary": "",
  "next_question": "",
  "blocking_gaps": [],
  "missing_information": [],
  "contradictions": [],
  "missing_evidence": [],
  "recommended_actions": [],
  "source_ids": []
}

Rules:
- Preserve unique material findings and source identifiers.
- Deduplicate equivalent findings.
- Fold party, timeline, legal-reference, and unverified-claim gaps into either
  blocking_gaps or missing_information.
- Do not invent facts.
- is_complete and ready_for_analysis may be true only when no material blocking
  gap remains across all partial reviews.
- Use a conservative score from 0 to 100.
- next_question must be the highest-priority unresolved question.
- Keep the summary concise.
- Output JSON only.
""".strip()


LIST_FIELDS = (
    "questions",
    "blocking_gaps",
    "missing_information",
    "contradictions",
    "unverified_claims",
    "missing_evidence",
    "timeline_gaps",
    "party_gaps",
    "legal_reference_gaps",
    "recommended_actions",
    "source_ids",
)

FORBIDDEN_REVIEW_KEYS = {
    "page_text",
    "full_text",
    "document_text",
    "extracted_text",
    "transcription",
    "raw_content",
    "raw_text",
    "image_base64",
    "image_bytes",
    "content_base64",
    "binary_content",
    "file_bytes",
    "retrieved_content",
    "document_content",
    "full_document",
}

ALLOWED_SCALAR_KEYS = {
    "case",
    "case_id",
    "case_name",
    "case_status",
    "case_type",
    "jurisdiction",
    "review_mode",
    "review_context",
}

ALLOWED_LIST_SECTIONS = {
    "messages",
    "documents",
    "document_pages",
    "latest_document_pages",
    "parties",
    "facts",
    "fact_candidates",
    "issues",
    "issue_candidates",
    "events",
    "evidence",
    "legal_research",
}

TEXT_FIELD_LIMITS = {
    "page_summary": 1200,
    "summary": 1200,
    "description": 1000,
    "content": 700,
    "message_text": 700,
    "fact_text": 600,
    "fact": 600,
    "issue_text": 600,
    "issue": 600,
    "event_text": 600,
    "event": 600,
    "research_summary": 1000,
    "title": 250,
    "name": 250,
}


class ReviewDecision(dict):
    """Dictionary result with backwards-compatible attribute access."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value



def _json_chars(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )
    )



def _normalise_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalised = value.strip().lower()
        if normalised in {"true", "yes", "y", "1"}:
            return True
        if normalised in {"false", "no", "n", "0", ""}:
            return False
    return default



def _dedupe_list(values: list[Any]) -> list[Any]:
    output: list[Any] = []
    seen: set[str] = set()

    for value in values:
        marker = json.dumps(
            value,
            ensure_ascii=False,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        if marker in seen:
            continue
        seen.add(marker)
        output.append(value)

    return output




def _normalise_follow_up_actions(value: Any) -> list[dict[str, Any]]:
    """Return formatter-safe action objects; never bare strings."""
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    output: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            action_text = str(
                item.get("action")
                or item.get("text")
                or item.get("description")
                or item.get("title")
                or ""
            ).strip()
            if not action_text:
                continue
            normalised = dict(item)
            normalised["action"] = action_text
            normalised.setdefault("text", action_text)
            normalised.setdefault("label", action_text)
            normalised.setdefault("priority", "medium")

            payload = normalised.get("payload")
            if not isinstance(payload, dict):
                payload = {
                    "action": action_text,
                    "text": action_text,
                }
            else:
                payload = dict(payload)
                payload.setdefault("action", action_text)
                payload.setdefault("text", action_text)
            normalised["payload"] = payload

            output.append(normalised)
        else:
            action_text = str(item or "").strip()
            if action_text:
                output.append({
                    "action": action_text,
                    "text": action_text,
                    "label": action_text,
                    "priority": "medium",
                    "payload": {
                        "action": action_text,
                        "text": action_text,
                    },
                })
    return _dedupe_list(output)

def _normalise_review(value: dict) -> ReviewDecision:
    if not isinstance(value, dict):
        raise TypeError("Review result must be a dictionary.")

    result: dict[str, Any] = dict(value)

    for field in LIST_FIELDS:
        field_value = result.get(field)
        if field_value is None:
            result[field] = []
        elif isinstance(field_value, list):
            result[field] = field_value
        else:
            result[field] = [field_value]
        result[field] = _dedupe_list(result[field])

    try:
        score = int(float(result.get("completeness_score", 0) or 0))
    except (TypeError, ValueError):
        score = 0

    result["completeness_score"] = max(0, min(100, score))
    result["is_complete"] = _normalise_bool(
        result.get("is_complete"),
        default=False,
    )
    result["ready_for_analysis"] = _normalise_bool(
        result.get("ready_for_analysis"),
        default=False,
    )
    result["summary"] = str(result.get("summary", "") or "").strip()
    result["next_question"] = str(
        result.get("next_question", "") or ""
    ).strip()

    if not result["questions"] and result["next_question"]:
        result["questions"] = [result["next_question"]]
    elif not result["next_question"] and result["questions"]:
        result["next_question"] = str(result["questions"][0])
    elif (
        result["next_question"]
        and result["next_question"] not in result["questions"]
    ):
        result["questions"].insert(0, result["next_question"])

    result["acknowledgement"] = str(
        result.get("acknowledgement", "")
        or result["summary"]
        or "I reviewed the available case information."
    ).strip()
    result["reasoning_summary"] = str(
        result.get("reasoning_summary", "") or result["summary"]
    ).strip()
    result["missing_items"] = _dedupe_list(
        list(result.get("missing_items") or result["missing_information"])
    )
    result["follow_up_question"] = str(
        result.get("follow_up_question", "") or result["next_question"]
    ).strip()
    result["follow_up_actions"] = _normalise_follow_up_actions(
        result.get("follow_up_actions")
        or result.get("recommended_actions")
        or []
    )

    # Compatibility payload used by older chat/interview formatters. Keep this
    # as a separate shallow dictionary to avoid a recursive self-reference.
    existing_payload = result.get("payload")
    if isinstance(existing_payload, dict):
        payload = dict(existing_payload)
    else:
        payload = {}
    payload.update({
        "acknowledgement": result["acknowledgement"],
        "summary": result["summary"],
        "reasoning_summary": result["reasoning_summary"],
        "next_question": result["next_question"],
        "follow_up_question": result["follow_up_question"],
        "follow_up_actions": result["follow_up_actions"],
        "missing_items": result["missing_items"],
        "blocking_gaps": result["blocking_gaps"],
        "missing_information": result["missing_information"],
        "completeness_score": result["completeness_score"],
        "is_complete": result["is_complete"],
        "ready_for_analysis": result["ready_for_analysis"],
    })
    result["payload"] = payload

    # Compatibility aliases for existing interview formatters.
    result["complete"] = result["is_complete"]
    result["ready"] = result["ready_for_analysis"]
    result["score"] = result["completeness_score"]

    return ReviewDecision(result)



def _deterministic_merge_reviews(reviews: list[dict]) -> ReviewDecision:
    if not reviews:
        return _normalise_review({})

    normalised = [_normalise_review(review) for review in reviews]
    result = _normalise_review({})

    for field in LIST_FIELDS:
        merged: list[Any] = []
        for review in normalised:
            merged.extend(review.get(field, []))
        result[field] = _dedupe_list(merged)

    scores = [review["completeness_score"] for review in normalised]
    result["completeness_score"] = min(scores) if scores else 0
    result["is_complete"] = all(review["is_complete"] for review in normalised)
    result["ready_for_analysis"] = all(
        review["ready_for_analysis"] for review in normalised
    )

    summaries = [review["summary"] for review in normalised if review["summary"]]
    result["summary"] = "\n".join(dict.fromkeys(summaries))

    questions = result.get("questions", [])
    result["next_question"] = str(questions[0]) if questions else ""
    return _normalise_review(result)



def _truncate_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"



def _remove_forbidden_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _remove_forbidden_fields(item)
            for key, item in value.items()
            if key not in FORBIDDEN_REVIEW_KEYS
        }
    if isinstance(value, list):
        return [_remove_forbidden_fields(item) for item in value]
    return value



def _compact_review_item(item: Any) -> Any:
    if not isinstance(item, dict):
        return _truncate_text(item, 2500)

    compact = _remove_forbidden_fields(deepcopy(item))

    for key, limit in TEXT_FIELD_LIMITS.items():
        if key in compact:
            compact[key] = _truncate_text(compact[key], limit)

    for key, value in list(compact.items()):
        if isinstance(value, list) and len(value) > 25:
            compact[key] = value[:25]

    return compact



def sanitise_review_state(state: dict) -> dict:
    if not isinstance(state, dict):
        raise TypeError("Completeness review state must be a dictionary.")

    clean: dict[str, Any] = {}

    for key in ALLOWED_SCALAR_KEYS:
        if key in state:
            clean[key] = _remove_forbidden_fields(deepcopy(state[key]))

    for key in ALLOWED_LIST_SECTIONS:
        value = state.get(key)
        if isinstance(value, list) and value:
            clean[key] = [_compact_review_item(item) for item in value]

    return clean



def _base_state(state: dict) -> dict:
    return {
        key: deepcopy(value)
        for key, value in state.items()
        if not isinstance(value, list)
    }



def _list_sections(state: dict) -> list[tuple[str, list[Any]]]:
    return [
        (key, value)
        for key, value in state.items()
        if isinstance(value, list) and value
    ]



def _split_section(base: dict, section_name: str, items: list[Any]) -> list[dict]:
    batches: list[dict] = []
    current: list[Any] = []

    def candidate(candidate_items: list[Any]) -> dict:
        return {
            **deepcopy(base),
            "review_scope": {
                "section": section_name,
                "instruction": (
                    "Assess only this bounded section. Do not infer that other "
                    "sections are absent; they are reviewed separately."
                ),
            },
            section_name: candidate_items,
        }

    for raw_item in items:
        item = _compact_review_item(raw_item)
        single_state = candidate([item])
        single_chars = _json_chars(single_state)

        if single_chars > REVIEW_BATCH_MAX_CHARS:
            raise ValueError(
                "A compact review item still exceeds REVIEW_BATCH_MAX_CHARS. "
                "section={!r} chars={} limit={}".format(
                    section_name,
                    single_chars,
                    REVIEW_BATCH_MAX_CHARS,
                )
            )

        proposed = current + [item]
        proposed_state = candidate(proposed)

        if current and (
            len(proposed) > REVIEW_MAX_BATCH_ITEMS
            or _json_chars(proposed_state) > REVIEW_BATCH_MAX_CHARS
        ):
            batches.append(candidate(current))
            current = [item]
        else:
            current = proposed

    if current:
        batches.append(candidate(current))

    return batches



def build_review_batches(state: dict) -> list[dict]:
    clean_state = sanitise_review_state(state)
    base = _base_state(clean_state)
    sections = _list_sections(clean_state)

    if not sections:
        only_state = {
            **base,
            "review_scope": {
                "section": "case",
                "instruction": "Assess this bounded case metadata only.",
            },
        }
        if _json_chars(only_state) > REVIEW_BATCH_MAX_CHARS:
            raise ValueError(
                "The scalar completeness state exceeds REVIEW_BATCH_MAX_CHARS."
            )
        return [only_state]

    batches: list[dict] = []
    for section_name, items in sections:
        batches.extend(_split_section(base, section_name, items))

    print(
        "[completeness batching] sections={} batches={} total_state_chars={} "
        "sanitised_state_chars={} raw_page_text_sent=false".format(
            len(sections),
            len(batches),
            _json_chars(state),
            _json_chars(clean_state),
        )
    )
    return batches



def _review_with_retries(state: dict, batch_label: str) -> ReviewDecision:
    failures: list[str] = []
    thread_name = threading.current_thread().name

    for attempt in range(1, REVIEW_REQUEST_MAX_ATTEMPTS + 1):
        started_at = time.monotonic()
        try:
            chars = _json_chars(state)
            print(
                "[completeness batch START] timestamp={} thread={} label={} "
                "attempt={} chars={}".format(
                    _utc_timestamp(),
                    thread_name,
                    batch_label,
                    attempt,
                    chars,
                ),
                flush=True,
            )

            decision = complete_json(
                system_prompt=BATCH_REVIEW_SYSTEM_PROMPT,
                user_payload={
                    "instruction": (
                        "Return the bounded partial completeness review as JSON."
                    ),
                    "case_section": state,
                },
                llm_id=COMPLETENESS_LLM_ID,
                temperature=0.0,
            )

            elapsed = time.monotonic() - started_at
            print(
                "[completeness batch END] timestamp={} thread={} label={} "
                "attempt={} elapsed_seconds={:.3f} status=success".format(
                    _utc_timestamp(),
                    thread_name,
                    batch_label,
                    attempt,
                    elapsed,
                ),
                flush=True,
            )
            return _normalise_review(decision)

        except Exception as error:
            elapsed = time.monotonic() - started_at
            failures.append(repr(error))
            print(
                "[completeness batch END] timestamp={} thread={} label={} "
                "attempt={} elapsed_seconds={:.3f} status=failure error={}".format(
                    _utc_timestamp(),
                    thread_name,
                    batch_label,
                    attempt,
                    elapsed,
                    repr(error),
                ),
                flush=True,
            )
            if attempt < REVIEW_REQUEST_MAX_ATTEMPTS:
                time.sleep(REVIEW_RETRY_DELAY_SECONDS)

    raise RuntimeError(
        "Completeness batch {} failed: {}".format(batch_label, failures)
    )



def _compact_partial_for_merge(partial: dict) -> dict:
    review = _normalise_review(partial)
    return {
        "completeness_score": review["completeness_score"],
        "is_complete": review["is_complete"],
        "ready_for_analysis": review["ready_for_analysis"],
        "summary": _truncate_text(review["summary"], 1200),
        "next_question": _truncate_text(review["next_question"], 500),
        "blocking_gaps": review["blocking_gaps"][:12],
        "missing_information": _dedupe_list(
            review["missing_information"]
            + review["party_gaps"]
            + review["timeline_gaps"]
            + review["legal_reference_gaps"]
            + review["unverified_claims"]
        )[:18],
        "contradictions": review["contradictions"][:12],
        "missing_evidence": review["missing_evidence"][:12],
        "recommended_actions": review["recommended_actions"][:12],
        "source_ids": review["source_ids"][:40],
    }



def _group_for_merge(partials: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    current: list[dict] = []

    for raw_partial in partials:
        partial = _compact_partial_for_merge(raw_partial)
        single_chars = _json_chars({"partial_reviews": [partial]})
        if single_chars > REVIEW_MERGE_MAX_CHARS:
            raise ValueError(
                "A compact partial review exceeds REVIEW_MERGE_MAX_CHARS. "
                "chars={} limit={}".format(
                    single_chars,
                    REVIEW_MERGE_MAX_CHARS,
                )
            )

        proposed = current + [partial]
        if current and _json_chars({"partial_reviews": proposed}) > REVIEW_MERGE_MAX_CHARS:
            groups.append(current)
            current = [partial]
        else:
            current = proposed

    if current:
        groups.append(current)

    return groups



def _merge_group(
    partials: list[dict],
    merge_level: int,
    group_number: int,
) -> ReviewDecision:
    result = complete_json(
        system_prompt=MERGE_SYSTEM_PROMPT,
        user_payload={
            "instruction": "Merge all partial reviews into one JSON review.",
            "merge_level": merge_level,
            "group_number": group_number,
            "partial_reviews": partials,
        },
        llm_id=COMPLETENESS_LLM_ID,
        temperature=0.0,
    )
    return _normalise_review(result)



def merge_partial_reviews(partials: list[dict]) -> ReviewDecision:
    if not partials:
        return _normalise_review({})
    if len(partials) == 1:
        return _normalise_review(partials[0])

    level = 1
    current = [_normalise_review(partial) for partial in partials]

    while len(current) > 1:
        groups = _group_for_merge(current)
        next_level: list[ReviewDecision] = []

        for group_number, group in enumerate(groups, 1):
            if len(group) == 1:
                next_level.append(_normalise_review(group[0]))
                continue

            try:
                print(
                    "[completeness merge request] level={} group={} partials={} "
                    "chars={}".format(
                        level,
                        group_number,
                        len(group),
                        _json_chars({"partial_reviews": group}),
                    )
                )
                next_level.append(_merge_group(group, level, group_number))
            except Exception as error:
                print(
                    "[completeness merge fallback] level={} group={} error={}".format(
                        level,
                        group_number,
                        repr(error),
                    )
                )
                next_level.append(_deterministic_merge_reviews(group))

        if len(next_level) >= len(current):
            print(
                "[completeness merge deterministic final] level={} entries={}".format(
                    level,
                    len(current),
                )
            )
            return _deterministic_merge_reviews(current)

        current = next_level
        level += 1

    return _normalise_review(current[0])



def assess_case_completeness_multi_request(state: dict) -> ReviewDecision:
    batches = build_review_batches(state)
    failures: list[dict] = []
    partials_by_index: dict[int, ReviewDecision] = {}

    worker_count = max(
        1,
        min(int(REVIEW_BATCH_MAX_WORKERS or 1), len(batches)),
    )

    print(
        "[completeness parallel execution] timestamp={} version={} "
        "batches={} workers={} file={}".format(
            _utc_timestamp(),
            PIPELINE_VERSION,
            len(batches),
            worker_count,
            __file__,
        ),
        flush=True,
    )

    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix="review-worker",
    ) as executor:
        future_metadata = {}

        for index, batch in enumerate(batches, 1):
            review_scope = batch.get("review_scope", {})
            if isinstance(review_scope, dict):
                section_name = str(review_scope.get("section", "case") or "case")
            else:
                section_name = str(review_scope or "case")
            label = "{}/{}:{}".format(index, len(batches), section_name)

            print(
                "[completeness batch SUBMIT] timestamp={} label={}".format(
                    _utc_timestamp(),
                    label,
                ),
                flush=True,
            )

            future = executor.submit(_review_with_retries, batch, label)
            future_metadata[future] = {
                "index": index,
                "label": label,
            }

        completed = 0
        for future in as_completed(future_metadata):
            metadata = future_metadata[future]
            index = metadata["index"]
            label = metadata["label"]

            try:
                partials_by_index[index] = future.result()
            except Exception as error:
                failures.append({
                    "batch": label,
                    "error": repr(error),
                })

            completed += 1
            print(
                "[completeness parallel progress] timestamp={} completed={}/{} "
                "batch={} successful={} failed={}".format(
                    _utc_timestamp(),
                    completed,
                    len(batches),
                    label,
                    len(partials_by_index),
                    len(failures),
                ),
                flush=True,
            )

    partials = [
        partials_by_index[index]
        for index in sorted(partials_by_index)
    ]

    if not partials:
        raise RuntimeError(
            "All completeness batches failed: {}".format(failures)
        )

    final = merge_partial_reviews(partials)

    if failures:
        final["review_processing_warnings"] = failures

    print(
        "[completeness multi-request complete] timestamp={} version={} "
        "batches={} successful={} failed={}".format(
            _utc_timestamp(),
            PIPELINE_VERSION,
            len(batches),
            len(partials),
            len(failures),
        ),
        flush=True,
    )

    return ReviewDecision(final)

