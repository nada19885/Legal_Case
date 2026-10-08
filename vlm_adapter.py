from __future__ import annotations

import re
import time
from typing import Any

import dataiku

from .config import (
    FAILED_PAGE_RECOVERY_ATTEMPTS,
    FAILED_PAGE_RECOVERY_DELAY_SECONDS,
    FALLBACK_OCR_VLM_ID,
    FAST_OCR_VLM_ID,
    FALLBACK_VLM_MAX_ATTEMPTS,
    FAST_VLM_MAX_ATTEMPTS,
    VLM_TEMPERATURE,
)


OCR_SYSTEM_PROMPT = (
    "You are a transcription engine. If the image contains a document, page, "
    "table, or any legible text, transcribe ALL visible text exactly as it "
    "appears, preserving reading order and table structure using markdown "
    "tables where applicable. Do not summarize, comment, or add anything not "
    "present in the image. If the image is not a document (a photo, diagram, "
    "chart, etc.), instead give a factual, detailed visual description and "
    "separately transcribe any visible text verbatim. Output only the "
    "transcription/description, nothing else."
)

_THINK_BLOCK = re.compile(
    r"<think>.*?</think>",
    flags=re.DOTALL | re.IGNORECASE,
)


def strip_think(value: Any) -> str:
    text = str(value or "")
    return _THINK_BLOCK.sub("", text).strip()


def _response_text(response: Any) -> str:
    """Read the actual Dataiku completion text; never stringify the object."""
    if getattr(response, "success", None) is False:
        raise RuntimeError(
            str(
                getattr(response, "error_message", None)
                or "The LLM request failed."
            )
        )

    try:
        text = response.text
    except Exception as error:
        raise RuntimeError(
            "The completion returned, but response.text could not be read: "
            f"{error!r}"
        ) from error

    value = strip_think(text)
    if not value:
        raise RuntimeError(
            "The completion succeeded but response.text was empty."
        )

    if (
        value.startswith("<dataikuapi.")
        and " object at 0x" in value
        and value.endswith(">")
    ):
        raise RuntimeError(
            "A Dataiku response object representation was returned instead "
            "of model text."
        )

    return value


def vlm_transcribe(
    image_b64: str,
    mime: str,
    model_id: str,
) -> tuple[str, str | None]:
    """
    Send one image using the explicit-Base64 contract proven in the user's
    working project.

    image_b64 is already Base64-encoded exactly once by pdf_to_images.py.
    """
    try:
        project = dataiku.api_client().get_default_project()
        llm = project.get_llm(model_id)
        completion = llm.new_completion()

        try:
            completion.settings["temperature"] = float(VLM_TEMPERATURE)
        except Exception:
            pass

        completion.with_message(
            OCR_SYSTEM_PROMPT,
            role="system",
        )

        multipart = completion.new_multipart_message(role="user")
        multipart.with_text("Transcribe/describe this image.")
        multipart.with_inline_image(image_b64, mime)
        multipart.add()

        response = completion.execute()
        return _response_text(response), None

    except Exception as error:
        return "", str(error)


def vision_call(
    prompt: str,
    png_bytes: bytes,
    model_id: str | None = None,
    attempts: int = 3,
    mime: str = "image/png",
) -> str:
    """One image and one instruction to the vision model (the page
    pipeline's reader). Retries transient failures; raises with the last
    error when every attempt failed."""
    import base64

    image_b64 = base64.b64encode(png_bytes).decode("utf-8")
    last_error = ""
    for attempt in range(1, int(attempts) + 1):
        try:
            project = dataiku.api_client().get_default_project()
            completion = project.get_llm(model_id or FAST_OCR_VLM_ID).new_completion()
            try:
                completion.settings["temperature"] = float(VLM_TEMPERATURE)
            except Exception:
                pass
            multipart = completion.new_multipart_message(role="user")
            multipart.with_text(prompt)
            multipart.with_inline_image(image_b64, mime)
            multipart.add()
            return _response_text(completion.execute())
        except Exception as error:
            last_error = repr(error)
            print(f"[vision call failure] attempt={attempt} error={last_error}")
            if attempt < int(attempts):
                time.sleep(2.0 * attempt)
    raise RuntimeError(f"The vision request failed after {attempts} attempts: {last_error}")


def _transcribe_once(
    rendered_page,
    model_id: str,
    model_role: str,
) -> str:
    image_b64 = str(rendered_page.image_base64 or "")
    if not image_b64:
        raise ValueError("The rendered page has no Base64 image payload.")

    print(
        "[{} request] model={} page={} mime={} png_bytes={} base64_chars={} "
        "dimensions={}x{} sha256={} images=1 explicit_base64=true "
        "native_text_sent=false".format(
            model_role,
            model_id,
            rendered_page.page_number,
            rendered_page.mime_type,
            len(rendered_page.image_bytes),
            len(image_b64),
            rendered_page.width,
            rendered_page.height,
            rendered_page.image_sha256,
        )
    )

    started = time.perf_counter()
    text, error = vlm_transcribe(
        image_b64=image_b64,
        mime=rendered_page.mime_type or "image/png",
        model_id=model_id,
    )
    elapsed = round(time.perf_counter() - started, 2)

    if error:
        raise RuntimeError(error)

    text = strip_think(text)
    if len(text) < 5:
        raise RuntimeError("The model returned an unusable transcription.")

    print(
        "[{} success] page={} seconds={} chars={} preview={!r}".format(
            model_role,
            rendered_page.page_number,
            elapsed,
            len(text),
            text[:500],
        )
    )
    return text


def _transcribe_with_attempts(
    rendered_page,
    model_id: str,
    model_role: str,
    max_attempts: int,
    delay_seconds: float = 0.0,
) -> tuple[str, list[dict]]:
    failures: list[dict] = []

    for attempt in range(1, int(max_attempts) + 1):
        if attempt > 1 and delay_seconds > 0:
            time.sleep(float(delay_seconds))

        started = time.perf_counter()
        try:
            text = _transcribe_once(
                rendered_page=rendered_page,
                model_id=model_id,
                model_role=model_role,
            )
            return text, failures
        except Exception as error:
            failure = {
                "attempt": attempt,
                "elapsed_seconds": round(
                    time.perf_counter() - started,
                    2,
                ),
                "error": repr(error),
            }
            failures.append(failure)
            print(
                "[{} failure] page={} attempt={} error={}".format(
                    model_role,
                    rendered_page.page_number,
                    attempt,
                    repr(error),
                )
            )

    return "", failures


def _empty_result(rendered_page) -> dict:
    return {
        "page_number": rendered_page.page_number,
        "page_text": "",
        "page_summary": "",
        "document_type": "",
        "language": "unknown",
        "parties": [],
        "dates": [],
        "amounts": [],
        "case_numbers": [],
        "claims": [],
        "facts": [],
        "legal_references": [],
        "evidence_items": [],
        "signatures_or_stamps": [],
        "processing_status": "failed",
        "selected_text_source": "none",
        "extraction_warning": "",
        "validation": {},
    }


def extract_page_with_vlm_fallback(rendered_page) -> dict:
    """
    Fast normal pass:
    1. Call the recipe-tested OCR model once.
    2. Call the slower model only when the fast model fails or returns empty.
    3. Do not run per-page structured extraction.
    """
    fast_text, fast_failures = _transcribe_with_attempts(
        rendered_page=rendered_page,
        model_id=FAST_OCR_VLM_ID,
        model_role="fast_recipe_vlm",
        max_attempts=FAST_VLM_MAX_ATTEMPTS,
    )

    if fast_text:
        return {
            **_empty_result(rendered_page),
            "page_text": fast_text,
            "processing_status": "completed",
            "selected_text_source": "fast_recipe_vlm",
            "validation": {
                "fast_model_available": True,
                "fallback_used": False,
                "fast_failures": fast_failures,
                "native_text_extracted": False,
                "native_text_sent_to_vlm": False,
                "image_transport": "explicit_base64_via_with_inline_image",
                "image_sha256": rendered_page.image_sha256,
                "base64_character_count": (
                    rendered_page.base64_character_count
                ),
                "requires_review": False,
            },
        }

    fallback_text, fallback_failures = _transcribe_with_attempts(
        rendered_page=rendered_page,
        model_id=FALLBACK_OCR_VLM_ID,
        model_role="fallback_vlm",
        max_attempts=FALLBACK_VLM_MAX_ATTEMPTS,
    )

    if fallback_text:
        return {
            **_empty_result(rendered_page),
            "page_text": fallback_text,
            "processing_status": "completed_review_required",
            "selected_text_source": "fallback_vlm",
            "extraction_warning": (
                "The fast recipe-tested OCR model failed; the fallback "
                "model transcription was used."
            ),
            "validation": {
                "fast_model_available": False,
                "fallback_used": True,
                "fast_failures": fast_failures,
                "fallback_failures": fallback_failures,
                "native_text_extracted": False,
                "native_text_sent_to_vlm": False,
                "image_transport": "explicit_base64_via_with_inline_image",
                "image_sha256": rendered_page.image_sha256,
                "base64_character_count": (
                    rendered_page.base64_character_count
                ),
                "requires_review": True,
            },
        }

    result = _empty_result(rendered_page)
    result.update({
        "processing_status": "failed",
        "selected_text_source": "normal_pass_failed",
        "extraction_warning": "Both OCR models failed during the normal pass.",
        "validation": {
            "fast_failures": fast_failures,
            "fallback_failures": fallback_failures,
            "native_text_extracted": False,
            "native_text_sent_to_vlm": False,
            "image_transport": "explicit_base64_via_with_inline_image",
            "image_sha256": rendered_page.image_sha256,
            "base64_character_count": rendered_page.base64_character_count,
            "requires_review": True,
        },
    })
    return result


def recover_failed_page(rendered_page) -> dict:
    """
    Retry an unresolved page after the normal document pass.

    Recovery uses the same original Base64 image and the fast recipe-tested
    model. Attempts are delayed so a temporary model/connector condition has
    time to clear.
    """
    recovered_text, recovery_failures = _transcribe_with_attempts(
        rendered_page=rendered_page,
        model_id=FAST_OCR_VLM_ID,
        model_role="recovery_recipe_vlm",
        max_attempts=FAILED_PAGE_RECOVERY_ATTEMPTS,
        delay_seconds=FAILED_PAGE_RECOVERY_DELAY_SECONDS,
    )

    if recovered_text:
        return {
            **_empty_result(rendered_page),
            "page_text": recovered_text,
            "processing_status": "completed_review_required",
            "selected_text_source": "recovery_recipe_vlm",
            "extraction_warning": (
                "The page was recovered after the normal OCR pass."
            ),
            "validation": {
                "recovered": True,
                "recovery_failures": recovery_failures,
                "native_text_extracted": False,
                "native_text_sent_to_vlm": False,
                "image_transport": "explicit_base64_via_with_inline_image",
                "image_sha256": rendered_page.image_sha256,
                "base64_character_count": (
                    rendered_page.base64_character_count
                ),
                "requires_review": True,
            },
        }

    result = _empty_result(rendered_page)
    result.update({
        "processing_status": "failed",
        "selected_text_source": "recovery_failed",
        "extraction_warning": (
            "The page failed both the normal OCR pass and delayed recovery."
        ),
        "validation": {
            "recovered": False,
            "recovery_failures": recovery_failures,
            "native_text_extracted": False,
            "native_text_sent_to_vlm": False,
            "image_transport": "explicit_base64_via_with_inline_image",
            "image_sha256": rendered_page.image_sha256,
            "base64_character_count": rendered_page.base64_character_count,
            "requires_review": True,
        },
    })
    return result


# Compatibility name for older imports. It now uses primary-then-fallback,
# not two simultaneous model calls.
def extract_page_with_both_vlms(rendered_page) -> dict:
    return extract_page_with_vlm_fallback(rendered_page)


def extract_page_image_with_vlm(
    image_bytes,
    page_number,
    mime_type="image/png",
    **_,
):
    """Compatibility wrapper for callers that provide raw image bytes."""
    import base64
    import hashlib

    class _SinglePage:
        pass

    page = _SinglePage()
    page.page_number = int(page_number)
    page.image_bytes = image_bytes
    page.image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    page.mime_type = mime_type
    page.width = 0
    page.height = 0
    page.image_sha256 = hashlib.sha256(image_bytes).hexdigest()
    page.base64_character_count = len(page.image_base64)
    return extract_page_with_vlm_fallback(page)
