"""
Targeted verification of doubtful financial facts (phase 2).
Location: lib/python/legal_platform/financial_verify.py

Takes a page read by financial_reader.read_financial_page and checks every
fact marked "needs_check" against the ORIGINAL page:

  1. locate    Where the fact's row sits on the original picture, from the
               strip and position it was read at in phase 1 (rows sharing
               a region are checked together).
  2. crop      A band of the original page around the row, with the rows
               above and below, so the reader sees the value together with
               its date, description, neighbours and balances.
  3. variants  The crop as it is, enlarged, contrast-enhanced and
               sharpened; each read on its own, transcription only.
  4. match     The fact's row is found among the rows read in each crop by
               aligning them with the page's rows (not by position), so a
               row above or below is never mistaken for it.
  5. decide    Crop readings that agree (all, or all but one) give the
               value: the same as before -> "verified"; different ->
               "reverified" (the first reading is kept for audit). Crop
               readings that disagree, a row not found, or money that still
               does not fit the running balance -> "user_review".
  6. recheck   The running balance is checked again with the new values.

Context fields (account number, IBAN, period...) have no row; doubtful
ones are read again from the whole original page in the same variants.
"""

from __future__ import annotations

import copy
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from . import financial_reader as fr
from . import image_tables as it
from .statement_reader import _json, parse_amount, reconcile

CROP_VARIANTS = ("original", "enlarged", "contrast", "sharpened")
WINDOW_LINES = 4               # text lines kept above and below the row
WIDE_WINDOW_LINES = 9          # second try when the row is not found
DONE = ("verified", "reverified")

CROP_PROMPT = """
This is a close-up of part of a financial document page ({variant} copy).
{columns}
Transcribe every table row that is completely visible in this image.
Return JSON only:
{{"rows": [{{"table": 1, "type": "transaction", "cells": ["value of column 1", "value of column 2", ...]}}]}}
Each "cells" list follows the column order given above.

Rules:
- Copy every character exactly as printed: digits (Arabic-Indic digits stay
  Arabic-Indic), thousands and decimal separators, signs and brackets.
- Never calculate, correct, complete or guess. Use "" for an empty cell and
  "?" for a character you cannot read.
- A description that wraps onto a second line belongs to its row.
- Leave out a row cut by the top or bottom edge of the image.
""".strip()

FIELDS_PROMPT = """
Read these fields on this document page ({variant} copy), exactly as printed
(digits, separators and letters exactly; Arabic-Indic digits stay as they
are; never correct or complete):
{fields}
Return JSON only: {{"fields": {{"<field name>": "<value as printed, or empty if not on the page>"}}}}
""".strip()


# ---------------------------------------------------------------------------
# Pictures
# ---------------------------------------------------------------------------
def crop_variants(crop: np.ndarray, names: Tuple[str, ...] = CROP_VARIANTS) -> Dict[str, np.ndarray]:
    """The crop as independent pictures: untouched, enlarged x2,
    contrast-enhanced (CLAHE on grey) and sharpened. Stronger processing is
    acceptable here: the crop is small and only re-read."""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    big = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    out: Dict[str, np.ndarray] = {}
    if "original" in names:
        out["original"] = crop
    if "enlarged" in names:
        out["enlarged"] = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    if "contrast" in names:
        out["contrast"] = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(big)
    if "sharpened" in names:
        blur = cv2.GaussianBlur(big, (0, 0), 1.5)
        out["sharpened"] = cv2.addWeighted(big, 1.8, blur, -0.8, 0)
    return out


def _line_height(bands: List[Tuple[int, int]], default: float) -> float:
    if len(bands) < 3:
        return default
    gaps = [b[0] - a[0] for a, b in zip(bands, bands[1:])]
    return float(np.median(gaps))


def _row_centre(row: dict, original_height: int, bands: List[Tuple[int, int]]) -> Optional[float]:
    """Estimated y of a row on the original picture. Read in the original
    view: its strip's text lines, counted from the bottom of the strip
    (rows sit below any header). Read only in other views: the same
    fraction of the page height."""
    where = row.get("where") or {}
    if "original" in where:
        w = where["original"]
        inside = [b for b in bands if b[0] >= w["y0"] - 2 and b[1] <= w["y1"] + 2]
        if w["of"] and len(inside) >= w["of"]:
            band = inside[len(inside) - w["of"] + w["pos"]]
            return (band[0] + band[1]) / 2.0
        return w["y0"] + (w["pos"] + 0.5) / max(1, w["of"]) * (w["y1"] - w["y0"])
    fractions = []
    for w in where.values():
        y = w["y0"] + (w["pos"] + 0.5) / max(1, w["of"]) * (w["y1"] - w["y0"])
        fractions.append(y / max(1, w["height"]))
    return float(np.mean(fractions)) * original_height if fractions else None


def _groups(targets: List[Tuple[int, int, float]], half: float, height: int) -> List[dict]:
    """Rows whose crop windows overlap are checked from one crop."""
    groups: List[dict] = []
    for table, index, centre in sorted(targets, key=lambda t: t[2]):
        y0, y1 = max(0, int(centre - half)), min(height, int(centre + half))
        if groups and y0 <= groups[-1]["y1"]:
            groups[-1]["y1"] = max(groups[-1]["y1"], y1)
            groups[-1]["rows"].append((table, index))
        else:
            groups.append({"y0": y0, "y1": y1, "rows": [(table, index)]})
    return groups


# ---------------------------------------------------------------------------
# Matching the crop's rows to the page's rows
# ---------------------------------------------------------------------------
def _consensus_row(table: dict, index: int, number: int) -> dict:
    row = table["rows"][index]
    cells = [row["facts"].get(role, {}).get("raw", "") for role in table["roles"]]
    return {"table": number, "type": row["type"], "cells": cells, "_index": index}


def _find(table: dict, number: int, index: int, crop_rows: List[dict], span: int = 6) -> Optional[dict]:
    """The crop row that is the page's row `index`, found by aligning the
    crop's rows with the page's rows around it."""
    first, last = max(0, index - span), min(len(table["rows"]), index + span + 1)
    page_rows = [_consensus_row(table, i, number) for i in range(first, last)]
    candidates = [r for r in crop_rows if r["table"] == number]
    for slot in fr.align({"page": page_rows, "crop": candidates}, threshold=0.4):
        if slot.get("page", {}).get("_index") == index:
            return slot.get("crop")
    return None


# ---------------------------------------------------------------------------
# Deciding
# ---------------------------------------------------------------------------
def _decide(fact: dict, readings: Dict[str, str], variants: List[str]) -> None:
    """Final status of one fact from its crop readings."""
    present = {v: r for v, r in readings.items() if r is not None}
    vote = fr.vote(present, variants) if present else {"raw": "", "readings": {}, "agreement": "missing"}
    groups: Dict[str, int] = {}
    for value in present.values():
        groups[fr.canon(value)] = groups.get(fr.canon(value), 0) + 1
    best = max(groups.values()) if groups else 0
    strong = bool(present) and best >= max(2, len(variants) - 1)
    fact["verification"] = {"crop_readings": {v: readings.get(v) for v in variants},
                            "crop_consensus": vote["raw"], "crop_agreement": f"{best} of {len(variants)}"}
    if not present:
        fact["status"] = "user_review"
        fact["verification"]["decision"] = "the row was not found in the crops"
    elif not strong:
        fact["status"] = "user_review"
        fact["verification"]["decision"] = "the crop readings disagree"
    elif fr.canon(vote["raw"]) == fr.canon(fact["raw"]):
        fact["status"] = "verified"
        fact["verification"]["decision"] = "confirmed from the source crop"
    else:
        fact["initial_consensus"] = fact["raw"]
        fact["raw"] = vote["raw"]
        fact["status"] = "reverified"
        fact["verification"]["decision"] = "reverified from the source crop (first reading kept)"


def _normalise(fact: dict, role: str, decimals: int) -> None:
    money = role.startswith(fr.MONEY_ROLES) or role.startswith("other_amount")
    if money and fact["raw"]:
        value = parse_amount(fr.canon(fact["raw"]), decimals)
        fact["normalized"] = str(value) if value is not None else None
    elif fact["raw"] and fr._has_digit(fr.canon(fact["raw"])):
        fact["normalized"] = fr.canon(fact["raw"])


def recheck(table: dict) -> Optional[Dict[str, int]]:
    """Running balance checked again on the (re)verified values; money that
    still does not fit goes to the user."""
    roles = table["roles"]
    if not ("balance" in roles and {"debit", "credit", "amount"} & set(roles)):
        return None
    decimals = table["decimals"]

    def money(row, role):
        fact = row["facts"].get(role)
        return parse_amount(fr.canon(fact["raw"]), decimals) if fact and fact["raw"] else None

    rows = [r for r in table["rows"] if r["type"] == "transaction"]
    opening = next((r for r in table["rows"] if r["type"] == "opening"), None)
    shaped = []
    for row in rows:
        item = {r: money(row, r) for r in fr.MONEY_ROLES}
        if item["amount"] is not None and item["debit"] is None and item["credit"] is None:
            item["debit" if item["amount"] < 0 else "credit"] = abs(item["amount"])
        shaped.append(item)
    checked = reconcile(shaped, decimals, money(opening, "balance") if opening else None)
    for row, result in zip(rows, checked):
        row["arithmetic"] = result["status"]
        for role in fr.MONEY_ROLES:
            fact = row["facts"].get(role)
            if not fact or not fact["raw"]:
                continue
            fact["arithmetic"] = {"reconciled": "ok", "first": "ok", "repaired": "repaired",
                                  "unconfirmed": "unconfirmed"}.get(result["status"], "n/a")
            if fact["status"] in DONE and result["status"] in ("unconfirmed", "repaired"):
                fact["status"] = "user_review"
                fact.setdefault("verification", {})["decision"] = (
                    "the value was read consistently but the running balance still does not hold")
                if f"{role}_as_read" in result and result.get(role) is not None:
                    fact["verification"]["balance_suggests"] = str(result[role])
    return {s: sum(1 for r in rows if r.get("arithmetic") == s)
            for s in ("reconciled", "repaired", "first", "unconfirmed", "no_balance")}


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------
def verify_page(image_bytes: bytes, page: Dict[str, Any], vision: fr.VisionCall,
                variants: Tuple[str, ...] = CROP_VARIANTS, parallel: int = 3,
                debug: bool = False) -> Dict[str, Any]:
    """Phase 2 on a page from read_financial_page: every doubtful fact is
    re-read from crops of the original page and gets its final status
    (verified / reverified / user_review). Returns a new page; the input is
    not changed."""
    page = copy.deepcopy({k: v for k, v in page.items() if k != "debug"})
    started = time.time()
    names = list(variants)
    original = fr.make_views(it.decode(image_bytes), ("original",))["original"]
    height = original.shape[0]
    bands = fr.line_bands(original)
    line = _line_height(bands, height / 60.0)
    tables_meta = [{"columns": t["headers"]} for t in page.get("tables") or []]
    columns_text = fr._columns_text(tables_meta)
    log: Dict[str, Any] = {"crops": [], "calls": 0}

    def doubtful(row):
        return [role for role, f in row["facts"].items() if f["raw"] and f["status"] not in DONE]

    pending = [(t, i) for t, table in enumerate(page.get("tables") or [])
               for i, row in enumerate(table["rows"]) if doubtful(row)]

    def read_crop(job):
        name, picture = job
        prompt = CROP_PROMPT.format(variant=name, columns=columns_text)
        try:
            return name, vision(prompt, fr._png(picture)), ""
        except Exception as error:
            return name, "", f"{type(error).__name__}: {error}"

    for attempt, half_lines in enumerate((WINDOW_LINES, WIDE_WINDOW_LINES)):
        targets = []
        for t, i in pending:
            centre = _row_centre(page["tables"][t]["rows"][i], height, bands)
            if centre is not None:
                targets.append((t, i, centre))
        not_found = []
        for group in _groups(targets, (half_lines + 0.5) * line, height):
            crop = original[group["y0"]:group["y1"]]
            pictures = crop_variants(crop, tuple(names))
            with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
                answers = list(pool.map(read_crop, list(pictures.items())))
            log["calls"] += len(answers)
            readings_by_variant = {name: fr.parse_reading("json_rows", answer, tables_meta)[0]
                                   for name, answer, _ in answers}
            entry = {"attempt": attempt + 1, "y0": group["y0"], "y1": group["y1"],
                     "rows": [(t + 1, i + 1) for t, i in group["rows"]],
                     "errors": [e for _, _, e in answers if e]}
            if debug:
                entry["pictures"] = {name: fr._png(p) for name, p in pictures.items()}
                entry["answers"] = {name: answer for name, answer, _ in answers}
            log["crops"].append(entry)
            for t, i in group["rows"]:
                table = page["tables"][t]
                found = {name: _find(table, t, i, rows) for name, rows in readings_by_variant.items()}
                if attempt == 0 and sum(r is not None for r in found.values()) < max(2, len(names) - 1):
                    not_found.append((t, i))           # try once more with a taller crop
                    continue
                row = table["rows"][i]
                for role in doubtful(row):
                    column = table["roles"].index(role)
                    readings = {name: (r["cells"][column] if r is not None and column < len(r["cells"]) else None)
                                for name, r in found.items()}
                    _decide(row["facts"][role], readings, names)
                    _normalise(row["facts"][role], role, table["decimals"])
        pending = not_found
        if not pending:
            break

    # Whatever could not be located or checked goes to the user.
    for table in page.get("tables") or []:
        for row in table["rows"]:
            for role in doubtful(row):
                fact = row["facts"][role]
                fact["status"] = "user_review"
                fact.setdefault("verification", {})["decision"] = "the row could not be located on the page"
    for table in page.get("tables") or []:
        table["check"] = recheck(table) or table.get("check")

    # Context fields: no row to crop, so the whole original page is read again.
    fields = [name for name, f in (page.get("context") or {}).items() if f["raw"] and f["status"] not in DONE]
    if fields:
        whole = crop_variants(original, tuple(n for n in names if n != "enlarged"))
        prompt_fields = "\n".join(f"- {name}" for name in fields)

        def read_fields(job):
            name, picture = job
            try:
                return name, vision(FIELDS_PROMPT.format(variant=name, fields=prompt_fields), fr._png(picture))
            except Exception:
                return name, ""
        with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
            answers = list(pool.map(read_fields, list(whole.items())))
        log["calls"] += len(answers)
        found = {name: (_json(answer).get("fields") or {}) for name, answer in answers}
        for field in fields:
            readings = {name: (str(values[field]) if values.get(field) not in (None, "") else None)
                        for name, values in found.items()}
            _decide(page["context"][field], readings, list(found))
            _normalise(page["context"][field], "context", 2)

    every = [f for t in page.get("tables") or [] for r in t["rows"] for f in r["facts"].values() if f["raw"]] + \
        [f for f in (page.get("context") or {}).values() if f["raw"]]
    page["summary"] = dict(page.get("summary") or {}, **{
        status: sum(f["status"] == status for f in every)
        for status in ("verified", "reverified", "user_review", "needs_check")})
    page["verification"] = {"crops": log["crops"], "calls": log["calls"],
                            "seconds": round(time.time() - started, 1), "line_height": round(line, 1)}
    return page


def changes(page: Dict[str, Any]) -> List[dict]:
    """Every fact phase 2 looked at, for the notebook: before, crop
    readings, after, decision."""
    out = []
    for t, table in enumerate(page.get("tables") or [], start=1):
        for i, row in enumerate(table["rows"], start=1):
            for role, fact in row["facts"].items():
                if "verification" not in fact:
                    continue
                record = {"table": t, "row": i, "column": role,
                          "first reading": fact.get("initial_consensus", fact["raw"]), "final": fact["raw"],
                          "status": fact["status"]}
                record.update({f"crop {k}": v if v is not None else "—"
                               for k, v in fact["verification"].get("crop_readings", {}).items()})
                record["crop agreement"] = fact["verification"].get("crop_agreement")
                record["decision"] = fact["verification"].get("decision")
                if fact["verification"].get("balance_suggests"):
                    record["balance suggests"] = fact["verification"]["balance_suggests"]
                out.append(record)
    for name, fact in (page.get("context") or {}).items():
        if "verification" in fact:
            out.append({"table": "context", "row": "", "column": name,
                        "first reading": fact.get("initial_consensus", fact["raw"]), "final": fact["raw"],
                        "status": fact["status"], "crop agreement": fact["verification"].get("crop_agreement"),
                        "decision": fact["verification"].get("decision")})
    return out
