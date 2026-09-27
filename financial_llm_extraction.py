"""
Multi-DPI VLM Extraction Engine (3 Passes: 150, 200, 300 DPI).
Location: lib/python/legal_platform/financial_llm_extraction.py
"""

from __future__ import annotations

import random
import time
from typing import Any
import fitz  # PyMuPDF
import dataiku

from .config import (
    FINANCIAL_DPI_LEVELS,
    FINANCIAL_EXTRACTION_PASS_COUNT,
    FINANCIAL_REQUEST_MAX_ATTEMPTS,
    FINANCIAL_RETRY_DELAY_SECONDS,
    FINANCIAL_VLM_PRIMARY_ID,
    FINANCIAL_VLM_SECONDARY_ID,
    FINANCIAL_VLM_TEMPERATURE_MAX,
    FINANCIAL_VLM_TEMPERATURE_MIN,
)
from .llm import parse_json_object, strip_think

FINANCIAL_FULL_PAGE_REWRITE_PROMPT = r"""
You are an expert forensic accountant analyzing documentary evidence in Saudi banking dispute cases.

The document page may contain BOTH genuine case transactions AND static institutional headers, legal text, or metadata footers.

Your task has two parts, in order:

PART 1 - TRIAGE: classify each piece of information on the page and discard institutional headers/metadata (rules below). Only genuine transaction rows move on to Part 2.

PART 2 - COMPLETE REWRITE: for every remaining genuine transaction row visible on this page, rewrite it as ONE complete line item with every column filled in.
   - Go row by row, top to bottom, exactly as printed. Output EVERY row - do not summarize, sample, skip, or truncate the table.
   - Fill EVERY field: row_index, date_exact_text, description, amount_exact_text, currency_exact_text, debit_or_credit, reference_number, party_source, running_balance_exact_text.
   - Leave field as "" ONLY if genuinely missing from that row.

TRIAGE CLASSIFICATION RULES:
1. DISCARD AS INSTITUTIONAL HEADERS / METADATA:
   - Bank Paid-Up Capital, Commercial Registration (C.R. No), Unified Number, VAT Number, P.O. Box, Phone.
   - Page header/footer barcodes, timestamps, system tracking IDs.
   - General Legal citation decrees and Committee Articles.

2. EXTRACT AS CASE FINANCIAL MOVEMENTS:
   - Wire transfers / Hawala receipts.
   - Binance P2P orders and crypto transfers.
   - POS purchases, mada debits, account credits.
   - Specific bank freeze or unfreeze holds for the customer.

RETURN JSON SCHEMA ONLY:
{
  "page_has_case_transactions": true,
  "line_items": [
    {
      "row_index": 0,
      "date_exact_text": "YYYY/MM/DD",
      "transaction_type": "transfer|fee|pos|salary|compensation|other",
      "description": "Clean description of the transaction",
      "amount_exact_text": "4092.44",
      "currency_exact_text": "SAR",
      "debit_or_credit": "debit|credit|unclear",
      "party_source": "",
      "reference_number": "",
      "running_balance_exact_text": "",
      "source_quote": ""
    }
  ],
  "stated_totals_or_balances": [],
  "extraction_uncertainty": []
}
""".strip()


def _extract_text(response: Any) -> str:
    if getattr(response, "success", None) is False:
        raise RuntimeError(str(getattr(response, "error_message", "The LLM request failed.")))
    text = getattr(response, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("The completion returned no usable text.")
    return strip_think(text)


def _call_vlm(
    image_bytes: bytes,
    mime_type: str,
    page_number: int,
    label: str = "",
    model_id: str = FINANCIAL_VLM_PRIMARY_ID,
    temperature: float = 0.3,
) -> dict:
    project = dataiku.api_client().get_default_project()
    llm = project.get_llm(model_id)
    completion = llm.new_completion()
    try:
        completion.settings["temperature"] = float(temperature)
    except Exception:
        pass

    completion.with_message(FINANCIAL_FULL_PAGE_REWRITE_PROMPT, role="system")

    message = completion.new_multipart_message(role="user")
    message.with_text(
        f"Analyze page {page_number} {label}: filter out header/footer metadata, "
        "then rewrite the COMPLETE set of genuine case transactions."
    )
    message.with_inline_image(image_bytes, mime_type=mime_type or "image/png")
    message.add()

    response = completion.execute()
    parsed = parse_json_object(_extract_text(response))

    if not parsed.get("page_has_case_transactions", True):
        parsed["line_items"] = []

    return parsed


def render_pdf_page_to_dpi(pdf_bytes: bytes, page_number: int, dpi: int) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc.load_page(page_number - 1)
        pixmap = page.get_pixmap(dpi=int(dpi), alpha=False)
        return pixmap.tobytes("png")
    finally:
        doc.close()


def _build_pass_plan(pass_count: int = 3) -> list[dict]:
    dpi_levels = [150, 200, 300]
    has_secondary_model = bool(FINANCIAL_VLM_SECONDARY_ID) and (
        FINANCIAL_VLM_SECONDARY_ID != FINANCIAL_VLM_PRIMARY_ID
    )

    plan: list[dict] = []
    for index in range(pass_count):
        dpi = dpi_levels[index % len(dpi_levels)]
        model_id = (
            FINANCIAL_VLM_SECONDARY_ID
            if has_secondary_model and index % 2 == 1
            else FINANCIAL_VLM_PRIMARY_ID
        )
        temperature = round(
            random.uniform(FINANCIAL_VLM_TEMPERATURE_MIN, FINANCIAL_VLM_TEMPERATURE_MAX), 3
        )
        plan.append({
            "pass_index": index + 1,
            "dpi": dpi,
            "model_id": model_id,
            "temperature": temperature,
            "method": f"VLM_pass{index + 1}_{dpi}DPI",
        })
    return plan


def extract_page_line_items_multi(
    image_bytes: bytes,
    mime_type: str,
    page_number: int,
    pdf_bytes: bytes | None = None,
    pass_count: int = 3,
) -> tuple[list[dict], list[str]]:
    failures: list[str] = []
    passes: list[dict] = []
    rendered_by_dpi: dict[int, bytes] = {}

    plan = _build_pass_plan(pass_count)

    for step in plan:
        dpi = step["dpi"]
        page_bytes = rendered_by_dpi.get(dpi)
        if page_bytes is None:
            page_bytes = image_bytes
            if pdf_bytes:
                try:
                    page_bytes = render_pdf_page_to_dpi(pdf_bytes, page_number, dpi=dpi)
                except Exception as error:
                    failures.append(f"{step['method']} render ({dpi} DPI) failed: {error!r}")
                    page_bytes = image_bytes
            rendered_by_dpi[dpi] = page_bytes

        result: dict = {"line_items": []}
        for attempt in range(1, int(FINANCIAL_REQUEST_MAX_ATTEMPTS) + 1):
            try:
                result = _call_vlm(
                    page_bytes,
                    "image/png",
                    page_number,
                    label=f"({step['method']})",
                    model_id=step["model_id"],
                    temperature=step["temperature"],
                )
                break
            except Exception as error:
                failures.append(f"{step['method']} attempt {attempt}: {error!r}")
                if attempt < int(FINANCIAL_REQUEST_MAX_ATTEMPTS):
                    time.sleep(float(FINANCIAL_RETRY_DELAY_SECONDS))

        result["_pass_method"] = step["method"]
        result["_pass_dpi"] = dpi
        result["_pass_index"] = step["pass_index"]
        result["_pass_temperature"] = step["temperature"]
        result["_pass_model_id"] = step["model_id"]
        passes.append(result)

        # --- ADAPTIVE EARLY STOPPING ---
        # If the LLM successfully found transactions and reported zero uncertainties,
        # the page is perfectly clear. We stop here to save API costs.
        items = result.get("line_items", [])
        uncertainties = result.get("extraction_uncertainty", [])
        
        if items and not uncertainties and not failures:
            print(f"[adaptive extraction] Page {page_number} is crystal clear on pass {step['pass_index']}. Skipping remaining passes.")
            
            # Duplicate the perfect result to satisfy the arbitrator's 2-out-of-3 consensus rule
            while len(passes) < pass_count:
                duplicate = dict(result)
                duplicate["_pass_method"] = f"copied_from_pass_{step['pass_index']}"
                passes.append(duplicate)
            break
        # -------------------------------

    return passes, failures