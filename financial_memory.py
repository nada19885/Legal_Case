"""
Financial Memory: the case's financial facts, checked against each other
(phase 3 of the verified financial extraction).
Location: lib/python/legal_platform/financial_memory.py

Pages read by financial_reader (phase 1) and checked by financial_verify
(phase 2) are added to the memory. Every transaction row becomes a record
(date, description, reference, debit, credit, balance, account, currency,
and where it came from); context fields (account number, IBAN, period ...)
are kept per page.

The memory never changes a value. It compares related facts and raises an
ANOMALY when a value looks inconsistent with the rest of the case:

  continuity     the last balance of a page and the next page's first row
                 do not chain (same document and account)
  duplicate      the same transaction (same date, same reference or same
                 description) appears twice with different amounts
  total          a table's total / closing row differs from the sum of its
                 rows
  date           a date outside the statement period, or out of the order
                 the rest of the statement follows
  decimals       an amount with more or fewer decimals than its currency
                 uses (3 for JOD, KWD, BHD, OMR, TND; 2 otherwise)
  outlier        an amount far from similar transactions (same account,
                 direction and kind); a ratio close to 10 / 100 / 1000 is
                 the typical misread separator or extra zero

recheck() sends the facts behind each anomaly to the phase 2 crop check
(financial_verify.verify_page) and records the outcome:
  resolved             the re-read value removes the anomaly
  confirmed_as_printed the source shows the value as read; an outlier is
                       genuine and stays verified, a conflict between
                       documents goes to the user (both are evidence)
  user_review          the source could not settle it

Verified facts are added back, so the memory grows stronger with every
document. to_json / from_json store it (e.g. in a Dataiku folder).
"""

from __future__ import annotations

import copy
import difflib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import financial_reader as fr

THREE_DECIMAL_CURRENCIES = ("JOD", "KWD", "BHD", "OMR", "TND", "IQD", "LYD")
CURRENCY_WORDS = {"JOD": ("jod", "دينار اردني", "دينار أردني", "jd"), "KWD": ("kwd", "دينار كويتي"),
                  "BHD": ("bhd", "دينار بحريني"), "OMR": ("omr", "ريال عماني"), "SAR": ("sar", "ريال سعودي", "ر.س"),
                  "EGP": ("egp", "جنيه مصري", "جنيه مصرى", "جنيه"), "AED": ("aed", "درهم"),
                  "USD": ("usd", "دولار", "$"), "EUR": ("eur", "يورو", "€"), "QAR": ("qar", "ريال قطري")}
ACCOUNT_WORDS = ("account", "iban", "حساب", "الحساب", "رقم الحساب", "ايبان", "آيبان")
PERIOD_WORDS = ("period", "from", "to", "الفترة", "الفتره", "من", "الى", "إلى")
OUTLIER_RATIO = 20             # x the typical amount of similar transactions
OUTLIER_MIN_GROUP = 4


# ---------------------------------------------------------------------------
# Normalising
# ---------------------------------------------------------------------------
def to_decimal(value: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except (InvalidOperation, ValueError):
        return None


def currency_code(text: Any) -> str:
    value = str(text or "").strip().lower()
    for code, words in CURRENCY_WORDS.items():
        if value == code.lower() or any(w in value for w in words):
            return code
    return value.upper()[:3] if re.fullmatch(r"[a-z]{3}", value) else ""


def _date_parts(raw: Any) -> Optional[Tuple[int, int, int]]:
    text = fr.canon(raw)
    match = re.search(r"(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{1,4})", text)
    if not match:
        return None
    return tuple(int(x) for x in match.groups())         # type: ignore[return-value]


def parse_date(raw: Any, day_first: bool = True) -> Optional[date]:
    """A printed date as a date: yyyy-mm-dd, or dd/mm/yyyy (mm/dd/yyyy when
    the document is month-first); two-digit years are 20xx."""
    parts = _date_parts(raw)
    if not parts:
        return None
    a, b, c = parts
    try:
        if a > 31:                                       # 2024-03-15
            return date(a, b, c)
        year = c + 2000 if c < 100 else c
        day, month = (a, b) if day_first else (b, a)
        if month > 12 and day <= 12:
            day, month = month, day
        return date(year, month, day)
    except ValueError:
        return None


def day_first_for(raws: List[str]) -> bool:
    """Whether a document writes the day first, from dates that show it
    (a first part above 12 = day first; a second part above 12 = month first)."""
    first = second = 0
    for raw in raws:
        parts = _date_parts(raw)
        if parts and parts[0] <= 31:
            first += parts[0] > 12
            second += parts[1] > 12
    return not (second > first)


def _kind(description: str) -> str:
    """A transaction's kind for comparison: its first words without digits
    or punctuation ("Card purchase 4411 AMMAN" -> "card purchase")."""
    words = re.findall(r"[^\W\d_]+", str(description or "").lower())
    return " ".join(words[:2])


# ---------------------------------------------------------------------------
# The memory
# ---------------------------------------------------------------------------
class FinancialMemory:
    """Records of every financial fact of a case, with the pages they came
    from (to re-check them against the source)."""

    def __init__(self) -> None:
        self.pages: Dict[str, dict] = {}        # key -> page (phase 1/2 result) + document / page number
        self.records: List[dict] = []
        self.anomalies: List[dict] = []
        self.history: List[dict] = []

    # -- adding --------------------------------------------------------------
    @staticmethod
    def page_key(document: str, page_number: Any) -> str:
        return f"{document}#p{page_number}"

    def add_page(self, page: Dict[str, Any], document: str, page_number: Any,
                 account: str = "", currency: str = "") -> List[dict]:
        """Add (or replace) one read page; returns its records."""
        key = self.page_key(document, page_number)
        stored = copy.deepcopy({k: v for k, v in page.items() if k != "debug"})
        stored["_document"], stored["_page_number"] = document, page_number
        self.pages[key] = stored
        self.records = [r for r in self.records if r["page_key"] != key]
        records = self._records(key, stored, account, currency)
        self.records.extend(records)
        return records

    def _context_value(self, page: dict, words: Tuple[str, ...]) -> str:
        for name, fact in (page.get("context") or {}).items():
            if any(w in str(name).lower() for w in words) and fact.get("raw"):
                return fact["raw"]
        return ""

    def _records(self, key: str, page: dict, account: str, currency: str) -> List[dict]:
        document = page["_document"]
        if not account:
            account = fr.canon(self._context_value(page, ACCOUNT_WORDS))
        if not account:                                  # the document's earlier pages
            earlier = [r for r in self.records if r["document"] == document and r["account"]]
            account = earlier[-1]["account"] if earlier else ""
        currency = currency or currency_code(page.get("currency")) or currency_code(
            self._context_value(page, ("currency", "العملة", "عملة")))
        out = []
        for t, table in enumerate(page.get("tables") or []):
            dates = [row["facts"].get("date", {}).get("raw", "") for row in table["rows"]]
            day_first = day_first_for([d for d in dates if d] + [
                r["date_raw"] for r in self.records if r["document"] == document and r["date_raw"]])
            for i, row in enumerate(table["rows"]):
                facts = row["facts"]

                def raw(role):
                    return facts.get(role, {}).get("raw", "")

                def amount(role):
                    fact = facts.get(role)
                    if not fact or not fact.get("raw"):
                        return None
                    return to_decimal(fact.get("normalized")) if fact.get("normalized") else None
                record = {
                    "id": f"{key}#t{t + 1}r{i + 1}", "page_key": key, "document": document,
                    "page": page["_page_number"], "table": t, "row": i, "type": row["type"],
                    "date_raw": raw("date") or raw("value_date"),
                    "date": None, "description": raw("description"), "reference": fr.canon(raw("reference")),
                    "debit": amount("debit"), "credit": amount("credit"), "balance": amount("balance"),
                    "amount": amount("amount"), "account": account, "currency": currency,
                    "decimals": table.get("decimals"),
                    "status": {role: f["status"] for role, f in facts.items() if f.get("raw")},
                    "raw_amounts": {role: facts[role]["raw"] for role in fr.MONEY_ROLES
                                    if facts.get(role, {}).get("raw")},
                }
                parsed = parse_date(record["date_raw"], day_first)
                record["date"] = parsed.isoformat() if parsed else None
                if record["amount"] is not None and record["debit"] is None and record["credit"] is None:
                    record["credit" if record["amount"] >= 0 else "debit"] = abs(record["amount"])
                record["movement"] = (record["credit"] or Decimal(0)) - (record["debit"] or Decimal(0)) \
                    if (record["credit"] is not None or record["debit"] is not None) else None
                out.append(record)
        return out

    # -- the checks ------------------------------------------------------------
    def check(self) -> List[dict]:
        """Every anomaly in the memory now."""
        found: List[dict] = []
        found += self._continuity()
        found += self._duplicates()
        found += self._totals()
        found += self._dates()
        found += self._decimals()
        found += self._outliers()
        self.anomalies = found
        return found

    @staticmethod
    def _anomaly(rule: str, severity: str, message: str, facts: List[Tuple[str, int, int, str]],
                 records: List[str]) -> dict:
        facts = sorted(set(facts))
        return {"id": f"{rule}:" + ",".join(f"{k}/{t}/{r}/{role}" for k, t, r, role in facts),
                "rule": rule, "severity": severity, "message": message,
                "facts": [{"page_key": k, "table": t, "row": r, "role": role} for k, t, r, role in facts],
                "records": records}

    def _transactions(self) -> List[dict]:
        return [r for r in self.records if r["type"] == "transaction"]

    def _continuity(self) -> List[dict]:
        """The last balance of a page chains into the next page's first row."""
        out = []
        by_document: Dict[Tuple[str, str], List[dict]] = {}
        for record in self._transactions():
            by_document.setdefault((record["document"], record["account"]), []).append(record)
        for (document, account), records in by_document.items():
            pages = sorted({r["page"] for r in records}, key=lambda p: (str(type(p)), p))
            for before, after in zip(pages, pages[1:]):
                last = [r for r in records if r["page"] == before and r["balance"] is not None]
                first = [r for r in records if r["page"] == after and r["balance"] is not None]
                if not last or not first:
                    continue
                a = max(last, key=lambda r: (r["table"], r["row"]))
                b = min(first, key=lambda r: (r["table"], r["row"]))
                if b["movement"] is None:
                    continue
                if a["balance"] + b["movement"] != b["balance"]:
                    out.append(self._anomaly(
                        "continuity", "high",
                        f"Page {before} ends with balance {a['balance']}; page {after} starts with "
                        f"movement {b['movement']:+} and balance {b['balance']} "
                        f"(expected {a['balance'] + b['movement']}).",
                        [(a["page_key"], a["table"], a["row"], "balance")] +
                        [(b["page_key"], b["table"], b["row"], role) for role in ("debit", "credit", "amount", "balance")
                         if b["raw_amounts"].get(role)],
                        [a["id"], b["id"]]))
        return out

    def _duplicates(self) -> List[dict]:
        """One transaction seen in two places (two documents, or overlapping
        pages) with different amounts."""
        out = []
        records = [r for r in self._transactions() if r["date"] and r["movement"] is not None]
        for index, a in enumerate(records):
            for b in records[index + 1:]:
                if a["page_key"] == b["page_key"] or a["date"] != b["date"]:
                    continue
                if a["account"] and b["account"] and a["account"] != b["account"]:
                    continue
                same_reference = bool(a["reference"]) and a["reference"] == b["reference"]
                same_text = bool(a["description"]) and difflib.SequenceMatcher(
                    None, a["description"].lower(), b["description"].lower()).ratio() >= 0.85
                if not (same_reference or same_text):
                    continue
                if abs(a["movement"]) != abs(b["movement"]):
                    roles_a = [r for r in ("debit", "credit", "amount") if a["raw_amounts"].get(r)]
                    roles_b = [r for r in ("debit", "credit", "amount") if b["raw_amounts"].get(r)]
                    out.append(self._anomaly(
                        "duplicate", "high",
                        f"The same transaction ({a['date']}, {a['description'] or a['reference']}) shows "
                        f"{abs(a['movement'])} on {a['page_key']} but {abs(b['movement'])} on {b['page_key']}.",
                        [(a["page_key"], a["table"], a["row"], r) for r in roles_a] +
                        [(b["page_key"], b["table"], b["row"], r) for r in roles_b], [a["id"], b["id"]]))
        return out

    def _totals(self) -> List[dict]:
        """Total rows against the sum of their table's rows."""
        out = []
        for key, page in self.pages.items():
            for t, table in enumerate(page.get("tables") or []):
                rows = [r for r in self.records if r["page_key"] == key and r["table"] == t]
                totals = [r for r in rows if r["type"] == "total"]
                moves = [r for r in rows if r["type"] == "transaction"]
                for total in totals:
                    for role in ("debit", "credit", "amount"):
                        if total[role] is None:
                            continue
                        values = [r[role] for r in moves if r[role] is not None]
                        if values and sum(values) != total[role]:
                            out.append(self._anomaly(
                                "total", "high",
                                f"The {role} total on {key} reads {total[role]}, the rows add up to {sum(values)}.",
                                [(key, t, total["row"], role)] +
                                [(key, t, r["row"], role) for r in moves if r[role] is not None
                                 and r["status"].get(role) not in ("verified", "reverified")],
                                [total["id"]]))
        return out

    def _dates(self) -> List[dict]:
        """Dates outside the statement period, or against the statement's order."""
        out = []
        for key, page in self.pages.items():
            rows = [r for r in self._transactions() if r["page_key"] == key and r["date"]]
            period = [parse_date(v["raw"]) for n, v in (page.get("context") or {}).items()
                      if any(w in str(n).lower() for w in PERIOD_WORDS) and parse_date(v.get("raw"))]
            for name, fact in (page.get("context") or {}).items():        # "01/03/2024 - 31/03/2024"
                if any(w in str(name).lower() for w in PERIOD_WORDS):
                    found = re.findall(r"\d{1,4}[/\-.]\d{1,2}[/\-.]\d{1,4}", fr.canon(fact.get("raw")))
                    period += [d for d in (parse_date(x) for x in found) if d]
            if len(period) >= 2:
                start, end = min(period), max(period)
                for r in rows:
                    if not start.isoformat() <= r["date"] <= end.isoformat():
                        out.append(self._anomaly("date", "medium",
                                                 f"{r['date_raw']} on {key} is outside the period {start} to {end}.",
                                                 [(key, r["table"], r["row"], "date")], [r["id"]]))
            dates = [r["date"] for r in rows]
            ups = sum(1 for a, b in zip(dates, dates[1:]) if b > a)
            downs = sum(1 for a, b in zip(dates, dates[1:]) if b < a)
            if len(rows) >= 4 and (ups >= 3 * max(1, downs) or downs >= 3 * max(1, ups)):
                ascending = ups > downs
                for previous, r, following in zip(rows, rows[1:], rows[2:] + [None]):
                    wrong = r["date"] < previous["date"] if ascending else r["date"] > previous["date"]
                    back = following is None or (following["date"] >= previous["date"] if ascending
                                                 else following["date"] <= previous["date"])
                    if wrong and back:          # this one date is out of line with both neighbours
                        out.append(self._anomaly("date", "medium",
                                                 f"{r['date_raw']} on {key} breaks the order of the statement's dates.",
                                                 [(key, r["table"], r["row"], "date")], [r["id"]]))
        return out

    def _decimals(self) -> List[dict]:
        out = []
        for r in self.records:
            if not r["currency"]:
                continue
            places = 3 if r["currency"] in THREE_DECIMAL_CURRENCIES else 2
            for role, raw in r["raw_amounts"].items():
                text = fr.canon(raw).strip("()-+")
                match = re.search(r"[.,](\d+)$", text)
                if match and len(match.group(1)) != places and not (
                        len(match.group(1)) == 3 and places == 2 and "." not in text):
                    out.append(self._anomaly("decimals", "medium",
                                             f"{raw} on {r['page_key']} has {len(match.group(1))} decimals; "
                                             f"{r['currency']} uses {places}.",
                                             [(r["page_key"], r["table"], r["row"], role)], [r["id"]]))
        return out

    def _outliers(self) -> List[dict]:
        """Amounts far from similar transactions; a power-of-ten ratio points
        to a misread separator or an extra / missing zero."""
        out = []
        groups: Dict[Tuple[str, str, str], List[dict]] = {}
        for r in self._transactions():
            if r["movement"]:
                direction = "in" if r["movement"] > 0 else "out"
                groups.setdefault((r["account"], direction, _kind(r["description"])), []).append(r)
        for (account, direction, kind), members in groups.items():
            if len(members) < OUTLIER_MIN_GROUP or not kind:
                continue
            for r in members:
                others = [abs(o["movement"]) for o in members if o is not r]
                typical = median(others)
                if not typical:
                    continue
                value = abs(r["movement"])
                ratio = value / typical
                if ratio >= OUTLIER_RATIO or ratio <= 1 / Decimal(OUTLIER_RATIO):
                    big = ratio if ratio >= 1 else 1 / ratio
                    # Moved by a power of ten, it falls among the similar amounts:
                    # an extra / missing zero or a misread separator.
                    low, high = min(others) / 2, max(others) * Decimal("1.5")
                    shift = any(low <= (value / p if ratio >= 1 else value * p) <= high for p in (10, 100, 1000))
                    role = next(x for x in ("debit", "credit", "amount") if r["raw_amounts"].get(x))
                    out.append(self._anomaly(
                        "outlier", "high" if shift else "low",
                        f"{abs(r['movement'])} for '{kind}' on {r['page_key']} is {big:.0f}x "
                        f"{'more' if ratio >= 1 else 'less'} than the usual {typical}"
                        + (" (a power of ten: a misread separator or zero?)" if shift else "") + ".",
                        [(r["page_key"], r["table"], r["row"], role)], [r["id"]]))
        return out

    # -- re-checking against the source -------------------------------------------
    def recheck(self, vision: fr.VisionCall, load_image: Callable[[str, Any], Optional[bytes]],
                min_severity: str = "medium", parallel: int = 3, debug: bool = False) -> List[dict]:
        """Send the facts behind the anomalies to the phase 2 crop check, add
        the results back, check again, and record each anomaly's outcome."""
        from . import financial_verify as fv
        rank = {"low": 0, "medium": 1, "high": 2}
        before = [a for a in (self.anomalies or self.check()) if rank[a["severity"]] >= rank[min_severity]]
        targets: Dict[str, List[dict]] = {}
        for anomaly in before:
            for fact in anomaly["facts"]:
                targets.setdefault(fact["page_key"], []).append(dict(fact, message=anomaly["message"]))
        checked_pages = {}
        for key, facts in targets.items():
            page = self.pages[key]
            image = load_image(page["_document"], page["_page_number"])
            marked = copy.deepcopy(page)
            for fact_ref in facts:
                fact = marked["tables"][fact_ref["table"]]["rows"][fact_ref["row"]]["facts"].get(fact_ref["role"])
                if fact and fact.get("raw"):
                    fact["status"] = "needs_check"
                    fact.setdefault("reasons", []).append("memory: " + fact_ref["message"])
                    fact.pop("verification", None)
            if image is None:                   # no picture to check against
                for fact_ref in facts:
                    fact = marked["tables"][fact_ref["table"]]["rows"][fact_ref["row"]]["facts"].get(fact_ref["role"])
                    if fact and fact.get("raw"):
                        fact["status"] = "user_review"
                        fact.setdefault("verification", {})["decision"] = "no source image to check against"
                result = marked
            else:
                result = fv.verify_page(image, marked, vision, parallel=parallel, debug=debug)
            checked_pages[key] = result
            self.add_page(result, page["_document"], page["_page_number"])
        after = {a["id"]: a for a in self.check()}
        outcomes = []
        for anomaly in before:
            facts = [self.pages[f["page_key"]]["tables"][f["table"]]["rows"][f["row"]]["facts"].get(f["role"], {})
                     for f in anomaly["facts"]]
            changed = any(f.get("status") == "reverified" for f in facts)
            if anomaly["id"] not in after:
                outcome = "resolved"
            elif any(f.get("status") == "user_review" for f in facts):
                outcome = "user_review"
            else:
                outcome = "confirmed_as_printed"
                if anomaly["rule"] == "outlier":      # unusual, but that is what the document says
                    for fact in facts:
                        if fact.get("raw"):
                            fact["memory_note"] = "unusual but confirmed by the source: " + anomaly["message"]
                else:      # two pieces of evidence disagree: a person decides
                    for ref, fact in zip(anomaly["facts"], facts):
                        if fact.get("raw"):
                            fact["status"] = "user_review"
                            fact.setdefault("verification", {})["decision"] = (
                                "read correctly from the source, but it conflicts with other evidence: "
                                + anomaly["message"])
                    outcome = "user_review"
                    for key in {f["page_key"] for f in anomaly["facts"]}:
                        page = self.pages[key]
                        self.add_page(page, page["_document"], page["_page_number"])
            outcomes.append({"anomaly": anomaly["id"], "rule": anomaly["rule"], "severity": anomaly["severity"],
                             "message": anomaly["message"], "outcome": outcome, "value_changed": changed,
                             "facts": [{"ref": ref, "raw": f.get("raw"), "first": f.get("initial_consensus"),
                                        "status": f.get("status"),
                                        "decision": (f.get("verification") or {}).get("decision")}
                                       for ref, f in zip(anomaly["facts"], facts)]})
        self.history.append({"outcomes": outcomes})
        if debug:
            self.last_checked_pages = checked_pages
        return outcomes

    # -- reading out -------------------------------------------------------------
    def ledger(self) -> List[dict]:
        """Every transaction of the case in date order, for a DataFrame."""
        rows = sorted(self._transactions(), key=lambda r: (r["account"], r["date"] or "", r["document"],
                                                           str(r["page"]), r["table"], r["row"]))
        out = []
        for r in rows:
            statuses = set(r["status"].values())
            out.append({"date": r["date"] or r["date_raw"], "account": r["account"], "description": r["description"],
                        "reference": r["reference"], "debit": r["debit"], "credit": r["credit"],
                        "balance": r["balance"], "currency": r["currency"], "document": r["document"],
                        "page": r["page"], "row": r["row"] + 1,
                        "status": "user review" if "user_review" in statuses else
                                  "needs check" if "needs_check" in statuses else "verified"})
        return out

    def to_json(self) -> str:
        return json.dumps({"pages": self.pages, "anomalies": self.anomalies, "history": self.history},
                          ensure_ascii=False, default=str)

    @classmethod
    def from_json(cls, text: str) -> "FinancialMemory":
        data = json.loads(text)
        memory = cls()
        for key, page in (data.get("pages") or {}).items():
            memory.add_page(page, page["_document"], page["_page_number"])
        memory.anomalies = data.get("anomalies") or []
        memory.history = data.get("history") or []
        return memory
