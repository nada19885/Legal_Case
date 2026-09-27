from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
import base64
import json
import re
from typing import Any

import dataiku
from langchain_core.messages import HumanMessage, SystemMessage

from .config import (
    PRIMARY_MULTIMODAL_LLM_ID,
    SECONDARY_LLM_ID,
    SECONDARY_LLM_ACCEPTS_IMAGES,
    DUAL_VLM_MIN_TEXT_SIMILARITY,
)


PAGE_PROMPT = r"""
Extract this single legal-document page.

Return valid JSON only:
{
  "page_number": 1,
  "page_text": "",
  "page_summary": "",
  "document_type": "",
  "language": "ar|en|mixed|unknown",
  "parties": [],
  "dates": [],
  "amounts": [
    {
      "exact_text": "",
      "currency_exact_text": "",
      "amount_context": "",
      "source_quote": "",
      "confidence": 0.0
    }
  ],
  "case_numbers": [],
  "claims": [],
  "facts": [],
  "legal_references": [],
  "evidence_items": [],
  "referenced_documents": [],
  "signatures_or_stamps": [],
  "extraction_warning": ""
}

Accuracy rules:
- Process only this page.
- Preserve Arabic and English exactly where legible.
- Monetary values, percentages, dates, account numbers, invoice numbers and
  reference numbers must be strings.
- Preserve every original digit, decimal separator, thousands separator,
  currency symbol and currency code.
- Never round, calculate, infer or convert a monetary amount.
- If any digit is unclear, do not guess. Record the uncertainty.
- Do not use markdown fences.
"""


VALIDATION_PROMPT = r"""
You are validating a legal-page extraction.

Compare the proposed extraction against the supplied page image when an image
is attached. When only transcription text is supplied, validate internal
consistency without pretending to see the image.

Return valid JSON only:
{
  "page_number": 1,
  "page_text": "",
  "page_summary": "",
  "document_type": "",
  "language": "ar|en|mixed|unknown",
  "parties": [],
  "dates": [],
  "amounts": [
    {
      "exact_text": "",
      "currency_exact_text": "",
      "amount_context": "",
      "source_quote": "",
      "confidence": 0.0
    }
  ],
  "case_numbers": [],
  "claims": [],
  "facts": [],
  "legal_references": [],
  "evidence_items": [],
  "referenced_documents": [],
  "signatures_or_stamps": [],
  "extraction_warning": ""
}

Rules:
- Correct only errors you can verify.
- Never invent or round monetary values.
- Preserve exact numeric strings.
- If uncertain, retain the uncertainty in extraction_warning.
"""


_JSON_OBJECT = re.compile(r"\{.*\}", flags=re.DOTALL)
_SPACE = re.compile(r"\s+")


def _parse_json(text: str) -> dict:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*```$", "", value)

    try:
        parsed = json.loads(value, strict=False)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = _JSON_OBJECT.search(value)
    if not match:
        raise ValueError("Model response did not contain a JSON object.")

    parsed = json.loads(match.group(0), strict=False)
    if not isinstance(parsed, dict):
        raise ValueError("Model response was not a JSON object.")
    return parsed


def _native_response_text(response: Any) -> str:
    for name in ("text", "completion", "message"):
        value = getattr(response, name, None)
        if isinstance(value, str):
            return value
    for name in ("get_text", "get_completion"):
        method = getattr(response, name, None)
        if callable(method):
            value = method()
            if isinstance(value, str):
                return value
    return str(response)


def _langchain_response_text(response: Any) -> str:
    content = getattr(response, "content", response)

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        values = []
        for item in content:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict) and item.get("text"):
                values.append(str(item["text"]))
        return "\n".join(values)

    return str(content or "")


def _normalise_text(value: Any) -> str:
    return _SPACE.sub(
        " ",
        str(value or "").strip().lower(),
    )


def _text_similarity(left: str, right: str) -> float:
    """
    Lightweight token Jaccard similarity. This is not used to rewrite evidence;
    it only helps determine whether human review is required.
    """
    left_tokens = set(_normalise_text(left).split())
    right_tokens = set(_normalise_text(right).split())

    if not left_tokens and not right_tokens:
        return 1.0

    if not left_tokens or not right_tokens:
        return 0.0

    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _amount_key(item: Any) -> str:
    if isinstance(item, dict):
        value = item.get("exact_text", item.get("value", ""))
    else:
        value = item

    return _normalise_text(value)


def _amounts(payload: dict) -> list[dict]:
    values = payload.get("amounts", [])
    return values if isinstance(values, list) else []


def _amount_map(payload: dict) -> dict[str, Any]:
    result = {}
    for item in _amounts(payload):
        key = _amount_key(item)
        if key:
            result[key] = item
    return result


def _primary_extract(
    image_bytes: bytes,
    page_number: int,
    mime_type: str,
) -> dict:
    project = dataiku.api_client().get_default_project()
    llm = project.get_llm(PRIMARY_MULTIMODAL_LLM_ID)
    completion = llm.new_completion()

    message = completion.new_multipart_message(role="user")
    message.with_text(
        PAGE_PROMPT.replace(
            '"page_number": 1',
            f'"page_number": {page_number}',
        )
    )
    message.with_inline_image(
        image_bytes,
        mime_type=mime_type,
    )
    message.add()

    response = completion.execute()

    if not getattr(response, "success", True):
        raise RuntimeError(
            getattr(
                response,
                "error_message",
                "Primary VLM request failed.",
            )
        )

    return _parse_json(
        _native_response_text(response)
    )


def _secondary_extract_or_validate(
    image_bytes: bytes,
    page_number: int,
    mime_type: str,
    primary_result: dict,
) -> dict:
    project = dataiku.api_client().get_default_project()
    model = (
        project
        .get_llm(SECONDARY_LLM_ID)
        .as_langchain_chat_model(
            temperature=0
        )
    )

    primary_json = json.dumps(
        primary_result,
        ensure_ascii=False,
    )

    if SECONDARY_LLM_ACCEPTS_IMAGES:
        encoded = base64.b64encode(
            image_bytes
        ).decode("ascii")

        human_content = [
            {
                "type": "text",
                "text": (
                    VALIDATION_PROMPT.replace(
                        '"page_number": 1',
                        f'"page_number": {page_number}',
                    )
                    + "\n\nProposed primary extraction:\n"
                    + primary_json
                ),
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": (
                        f"data:{mime_type};base64,{encoded}"
                    )
                },
            },
        ]

    else:
        # qwen3-32b in the user's example is used as a text validator unless
        # its Dataiku model endpoint is genuinely multimodal.
        human_content = (
            VALIDATION_PROMPT.replace(
                '"page_number": 1',
                f'"page_number": {page_number}',
            )
            + "\n\nNo image is available to this secondary model. "
            + "Validate the structured extraction and transcription "
            + "without claiming visual verification.\n\n"
            + "Proposed primary extraction:\n"
            + primary_json
            + "\n\nPrimary page transcription:\n"
            + str(primary_result.get("page_text", ""))
        )

    response = model.invoke([
        SystemMessage(
            content=(
                "You are a precise legal-document extraction validator. "
                "Return valid JSON only."
            )
        ),
        HumanMessage(
            content=human_content
        ),
    ])

    return _parse_json(
        _langchain_response_text(response)
    )


def _consensus(
    page_number: int,
    primary: dict,
    secondary: dict,
) -> dict:
    primary_text = str(
        primary.get("page_text", "")
    ).strip()

    secondary_text = str(
        secondary.get("page_text", "")
    ).strip()

    similarity = _text_similarity(
        primary_text,
        secondary_text,
    )

    primary_amounts = _amount_map(
        primary
    )

    secondary_amounts = _amount_map(
        secondary
    )

    agreed_amount_keys = sorted(
        set(primary_amounts)
        & set(secondary_amounts)
    )

    primary_only = sorted(
        set(primary_amounts)
        - set(secondary_amounts)
    )

    secondary_only = sorted(
        set(secondary_amounts)
        - set(primary_amounts)
    )

    amount_conflict = bool(
        primary_only
        or secondary_only
    )

    # Primary extraction remains the evidence record. Secondary output is used
    # to validate it, never to silently replace disputed monetary evidence.
    final = dict(primary)

    warnings = [
        str(
            primary.get(
                "extraction_warning",
                "",
            )
        ).strip(),
        str(
            secondary.get(
                "extraction_warning",
                "",
            )
        ).strip(),
    ]

    review_reasons = []

    if similarity < float(
        DUAL_VLM_MIN_TEXT_SIMILARITY
    ):
        review_reasons.append(
            "The two models produced materially different transcriptions."
        )

    if amount_conflict:
        review_reasons.append(
            "The models disagreed about one or more monetary values."
        )

    if not primary_text:
        review_reasons.append(
            "The primary VLM returned no page transcription."
        )

    warnings.extend(
        review_reasons
    )

    final["page_number"] = page_number
    final["validation"] = {
        "primary_model_id": (
            PRIMARY_MULTIMODAL_LLM_ID
        ),
        "secondary_model_id": (
            SECONDARY_LLM_ID
        ),
        "secondary_saw_image": bool(
            SECONDARY_LLM_ACCEPTS_IMAGES
        ),
        "text_similarity": round(
            similarity,
            4,
        ),
        "agreed_amounts": (
            agreed_amount_keys
        ),
        "primary_only_amounts": (
            primary_only
        ),
        "secondary_only_amounts": (
            secondary_only
        ),
        "amounts_agree": (
            not amount_conflict
        ),
        "requires_attorney_review": bool(
            review_reasons
        ),
        "review_reasons": (
            review_reasons
        ),
    }

    final["secondary_extraction_json"] = (
        secondary
    )

    final["extraction_warning"] = " | ".join(
        value
        for value in warnings
        if value
    )

    return final


def extract_page_with_dual_validation(
    image_bytes: bytes,
    page_number: int,
    mime_type: str = "image/png",
) -> dict:
    """
    Run the two model calls for the same page concurrently.

    The primary model uses Dataiku multipart image input.
    The secondary uses the user's LangChain-style model adapter. When that
    secondary model supports images it receives the same image; otherwise it
    validates the primary transcription and JSON as a text-only judge.
    """
    with ThreadPoolExecutor(
        max_workers=2
    ) as executor:
        primary_future = executor.submit(
            _primary_extract,
            image_bytes,
            page_number,
            mime_type,
        )

        # Secondary validation depends on the primary result, so first obtain
        # the primary extraction. The secondary call itself uses the alternate
        # Dataiku LangChain model adapter.
        primary = primary_future.result()

        secondary_future = executor.submit(
            _secondary_extract_or_validate,
            image_bytes,
            page_number,
            mime_type,
            primary,
        )

        secondary = secondary_future.result()

    return _consensus(
        page_number,
        primary,
        secondary,
    )
