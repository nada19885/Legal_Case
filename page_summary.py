from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import time
from typing import Iterable

from .config import (
    PAGE_SUMMARY_LLM_ID,
    PAGE_SUMMARY_MAX_ATTEMPTS,
    PAGE_SUMMARY_MAX_INPUT_CHARS,
    PAGE_SUMMARY_MAX_WORKERS,
    PAGE_SUMMARY_RETRY_DELAY_SECONDS,
)
from .llm import complete_json

PAGE_SUMMARY_SYSTEM_PROMPT = r"""
You extract a compact, factual JSON record from one page of a Saudi legal,
banking, regulatory, evidentiary, or procedural document.
Return one valid JSON object only. Do not return markdown or commentary.

Required schema:
{
  "page_id": "",
  "page_number": 0,
  "document_type": "",
  "document_language": "ar|en|mixed|unknown",
  "summary": "",
  "parties": ["exact person or organisation name"],
  "dates": ["exact visible date"],
  "amounts": ["exact visible amount with currency when present"],
  "case_numbers": ["exact case, complaint, reference or transaction number"],
  "claims": ["concise claim, denial, request or requested outcome"],
  "key_facts": ["concise fact or expressly stated allegation"],
  "legal_references": ["exact article, regulation, circular or legal authority"],
  "evidence": ["document, attachment, statement, transaction, email, table, signature or stamp"],
  "signatures_or_stamps": ["visible signer, signature, seal or stamp"]
}

Rules:
- Extract every visible name, date, amount and identifier that is material.
- Preserve Arabic names and values exactly; do not translate them.
- Treat claimant, defendant, bank, sender, recipient and account holder as parties.
- Treat requests to release/freeze funds, allegations and denials as claims.
- Treat emails, account statements, tables, forms, reports and attachments as evidence.
- Never invent a missing value.
- Use empty arrays only when the category is genuinely absent.
- Keep summary under 120 words and key_facts to at most 10 items.
""".strip()

_DATE_RE = re.compile(
    r"(?<!\d)(?:[٠-٩0-9]{1,4}[\-/][٠-٩0-9]{1,2}[\-/][٠-٩0-9]{1,4})(?!\d)"
)
_AMOUNT_RE = re.compile(
    r"(?<!\w)(?:SAR\s*)?[٠-٩0-9][٠-٩0-9,\.]*\s*(?:ريال(?:اً)?|ر\.س|SAR)(?!\w)",
    flags=re.IGNORECASE,
)
_CASE_RE = re.compile(
    r"(?:(?:رقم|برقم|مرجع|reference|case|complaint|subject)\s*[:#\-]?\s*)"
    r"([A-Za-z0-9٠-٩][A-Za-z0-9٠-٩/\-]{3,})",
    flags=re.IGNORECASE,
)
_LEGAL_RE = re.compile(
    r"(?:المادة|نظام|اللائحة|تعميم|قرار)\s+(?:رقم\s*)?[A-Za-z0-9٠-٩/\-]+[^\n]{0,80}"
)


def _unique(values: Iterable[str], limit: int = 30) -> list[str]:
    seen = set()
    result = []
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value or "")).strip(" |:-")
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
        if len(result) >= limit:
            break
    return result


def _as_list(value) -> list:
    if isinstance(value, list):
        return _unique([str(item) for item in value])
    if value in (None, ""):
        return []
    return _unique([str(value)])


def _extract_label_values(text: str, labels: tuple[str, ...]) -> list[str]:
    found = []
    for line in text.splitlines():
        compact = re.sub(r"\s+", " ", line).strip()
        for label in labels:
            if label in compact:
                value = compact.split(label, 1)[1].strip(" |:-")
                if value:
                    found.append(value)
    return _unique(found)


def _deterministic_fields(text: str) -> dict:
    dates = _unique(_DATE_RE.findall(text))
    amounts = _unique(_AMOUNT_RE.findall(text))
    case_numbers = _unique(match.group(1) for match in _CASE_RE.finditer(text))
    legal_refs = _unique(match.group(0) for match in _LEGAL_RE.finditer(text))

    parties = _extract_label_values(
        text,
        (
            "المدعي", "المدعية", "المدعى عليه", "المدعى عليها",
            "اسم العميل", "Customer Name", "From:", "To:",
        ),
    )
    claims = _unique(
        line for line in text.splitlines()
        if any(word in line for word in (
            "يطلب", "تطلب", "المطالبة", "رفع الحجز", "فك الحجز",
            "يدعي", "تنكر", "ينكر", "request", "claim", "deny",
        ))
    )
    evidence = _unique(
        phrase for phrase in (
            "صفحة مستند" if text.strip() else "",
            "مراسلات بريد إلكتروني" if ("From:" in text or "Subject:" in text) else "",
            "جدول بيانات" if "|" in text else "",
            "كشف حساب" if "كشف الحساب" in text else "",
            "نموذج دعوى" if "صحيفة دعوى" in text else "",
            "مذكرة جوابية" if "مذكرة" in text and "الدعوى" in text else "",
            "توقيع أو ختم" if any(x in text for x in ("التوقيع", "ختم", "موقع")) else "",
        )
    )
    return {
        "parties": parties,
        "dates": dates,
        "amounts": amounts,
        "case_numbers": case_numbers,
        "claims": claims[:10],
        "legal_references": legal_refs,
        "evidence_items": evidence,
    }


def _merge_lists(primary, fallback) -> list:
    return _unique([*_as_list(primary), *_as_list(fallback)])


def _normalise_summary(payload: dict, page: dict) -> dict:
    text = str(page.get("page_text", "") or "")
    deterministic = _deterministic_fields(text)
    summary = str(payload.get("summary", "") or "").strip()
    facts = _as_list(payload.get("key_facts"))[:10]
    if not facts and summary:
        facts = [summary]

    return {
        "page_id": str(page.get("page_id", "")),
        "page_number": page.get("page_number", ""),
        "document_type": str(payload.get("document_type", "") or "").strip(),
        "document_language": str(payload.get("document_language", "") or "unknown").strip(),
        "page_summary": summary,
        "parties": _merge_lists(payload.get("parties"), deterministic["parties"]),
        "dates": _merge_lists(payload.get("dates"), deterministic["dates"]),
        "amounts": _merge_lists(payload.get("amounts"), deterministic["amounts"]),
        "case_numbers": _merge_lists(payload.get("case_numbers"), deterministic["case_numbers"]),
        "claims": _merge_lists(payload.get("claims"), deterministic["claims"]),
        "facts": facts,
        "legal_references": _merge_lists(payload.get("legal_references"), deterministic["legal_references"]),
        "evidence_items": _merge_lists(payload.get("evidence"), deterministic["evidence_items"]),
        "signatures_or_stamps": _as_list(payload.get("signatures_or_stamps")),
        "summary_status": "completed",
        "summary_warning": "",
    }


def _fallback_summary(page: dict, errors: list[str]) -> dict:
    text = re.sub(r"\s+", " ", str(page.get("page_text", "") or "")).strip()
    deterministic = _deterministic_fields(str(page.get("page_text", "") or ""))
    excerpt = text[:900]
    return {
        "page_id": str(page.get("page_id", "")),
        "page_number": page.get("page_number", ""),
        "document_type": "",
        "document_language": "unknown",
        "page_summary": excerpt,
        "parties": deterministic["parties"],
        "dates": deterministic["dates"],
        "amounts": deterministic["amounts"],
        "case_numbers": deterministic["case_numbers"],
        "claims": deterministic["claims"],
        "facts": [excerpt] if excerpt else [],
        "legal_references": deterministic["legal_references"],
        "evidence_items": deterministic["evidence_items"],
        "signatures_or_stamps": [],
        "summary_status": "fallback_deterministic",
        "summary_warning": " | ".join(errors),
    }


def summarise_page(page: dict) -> dict:
    text = str(page.get("page_text", "") or "").strip()
    if not text:
        return _fallback_summary(page, ["No OCR text was available."])

    bounded_text = text[: int(PAGE_SUMMARY_MAX_INPUT_CHARS)]
    errors: list[str] = []

    for attempt in range(1, int(PAGE_SUMMARY_MAX_ATTEMPTS) + 1):
        try:
            payload = complete_json(
                llm_id=PAGE_SUMMARY_LLM_ID,
                system_prompt=PAGE_SUMMARY_SYSTEM_PROMPT,
                user_payload={
                    "page_id": page.get("page_id", ""),
                    "page_number": page.get("page_number", ""),
                    "page_text": bounded_text,
                },
                temperature=0.0,
            )
            result = _normalise_summary(payload, page)
            if not result["page_summary"]:
                raise ValueError("Summary JSON did not contain summary text.")

            print(
                "[page summary success] page={} model={} attempt={} "
                "input_chars={} summary_chars={} parties={} dates={} "
                "amounts={} case_numbers={} claims={} facts={} legal_refs={} evidence={}".format(
                    page.get("page_number", ""), PAGE_SUMMARY_LLM_ID, attempt,
                    len(bounded_text), len(result["page_summary"]),
                    len(result["parties"]), len(result["dates"]),
                    len(result["amounts"]), len(result["case_numbers"]),
                    len(result["claims"]), len(result["facts"]),
                    len(result["legal_references"]), len(result["evidence_items"]),
                )
            )
            return result
        except Exception as error:
            errors.append("attempt {}: {}".format(attempt, repr(error)))
            print(
                "[page summary failure] page={} model={} attempt={} error={!r}".format(
                    page.get("page_number", ""), PAGE_SUMMARY_LLM_ID, attempt, error
                )
            )
            if attempt < int(PAGE_SUMMARY_MAX_ATTEMPTS):
                time.sleep(float(PAGE_SUMMARY_RETRY_DELAY_SECONDS))

    return _fallback_summary(page, errors)


def summarise_pages(pages: Iterable[dict]) -> dict[str, dict]:
    usable = [page for page in pages if str(page.get("page_text", "") or "").strip()]
    if not usable:
        return {}

    workers = min(int(PAGE_SUMMARY_MAX_WORKERS), len(usable))
    print(
        "[page summary phase] pages={} workers={} llm_id={} "
        "full_document_text_sent=false".format(
            len(usable), workers, PAGE_SUMMARY_LLM_ID
        )
    )

    result_by_id: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_page = {executor.submit(summarise_page, page): page for page in usable}
        for future in as_completed(future_to_page):
            page = future_to_page[future]
            try:
                result = future.result()
            except Exception as error:
                result = _fallback_summary(page, [repr(error)])
            result_by_id[str(page.get("page_id", ""))] = result

    return result_by_id
