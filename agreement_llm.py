"""
Agreement-review LLM helper — the single dedicated completion call every
agreement_* module routes through (classification, page structuring,
consolidation, clause review, synthesis, discussion).
Location: lib/python/legal_platform/agreement_llm.py
"""

from __future__ import annotations

import json
import time
from typing import Any

import dataiku

from .config import (
    AGREEMENT_REQUEST_MAX_ATTEMPTS,
    AGREEMENT_RETRY_DELAY_SECONDS,
    AGREEMENT_REVIEW_LLM_ID,
)
from .llm import parse_json_object, strip_think


def _extract_text(response: Any) -> str:
    if getattr(response, "success", None) is False:
        raise RuntimeError(str(getattr(response, "error_message", "The LLM request failed.")))
    text = getattr(response, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("The completion returned no usable text.")
    return strip_think(text)


def agreement_complete_json(
    system_prompt: str,
    user_payload: dict,
    temperature: float = 0.0,
    operation: str = "",
    llm_id: str = AGREEMENT_REVIEW_LLM_ID,
) -> dict:
    """Text-only JSON completion for the agreement-review pipeline, with
    the same retry-on-transient-failure behaviour every other pipeline in
    this codebase uses (financial extraction, case mapping, ...).
    """
    payload_text = json.dumps(user_payload, ensure_ascii=False, default=str, separators=(",", ":"))

    last_error: Exception | None = None
    for attempt in range(1, int(AGREEMENT_REQUEST_MAX_ATTEMPTS) + 1):
        try:
            project = dataiku.api_client().get_default_project()
            llm = project.get_llm(llm_id)
            completion = llm.new_completion()
            try:
                completion.settings["temperature"] = float(temperature)
            except Exception:
                pass

            completion.with_message(system_prompt, role="system")
            completion.with_message(payload_text, role="user")

            print(
                "[agreement_complete_json] operation={} llm_id={} payload_chars={} attempt={}".format(
                    operation or "unlabeled", llm_id, len(payload_text), attempt,
                )
            )

            response = completion.execute()
            text = _extract_text(response)
            return parse_json_object(text)
        except Exception as error:
            last_error = error
            print(
                "[agreement_complete_json failure] operation={} attempt={} error={!r}".format(
                    operation or "unlabeled", attempt, error,
                )
            )
            if attempt < int(AGREEMENT_REQUEST_MAX_ATTEMPTS):
                time.sleep(float(AGREEMENT_RETRY_DELAY_SECONDS))

    raise RuntimeError(f"Agreement LLM request failed ({operation or 'unlabeled'}): {last_error!r}")
