from __future__ import annotations

import json
import re
from typing import Any

import dataiku

from .config import TEXT_STRUCTURING_LLM_ID

_JSON_BLOCK = re.compile(r"\{.*\}", flags=re.DOTALL)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)


def _extract_text(response: Any) -> str:
    value = getattr(response, "text", None)
    if isinstance(value, str):
        return value
    if isinstance(response, dict):
        value = response.get("text")
        if isinstance(value, str):
            return value
    return ""


_THINK_OPEN = re.compile(r"<think>", flags=re.IGNORECASE)
_THINK_CLOSE = re.compile(r"</think>", flags=re.IGNORECASE)


def strip_think(text: str) -> str:
    """The answer without the model's reasoning: closed <think> blocks; the
    reasoning before a lone </think> (the chat template already sent the
    opening tag); and an unclosed <think> (the model ran out while still
    reasoning, so nothing after it is answer)."""
    text = _THINK_BLOCK.sub("", str(text or ""))
    closes = list(_THINK_CLOSE.finditer(text))
    if closes:
        text = text[closes[-1].end():]
    opened = _THINK_OPEN.search(text)
    if opened:
        text = text[:opened.start()]
    return text.strip()


def _strip_markdown_fence(text: str) -> str:
    text = strip_think(text)
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


_MAX_STARTS = 200


def _rank(result: dict, expect_keys) -> tuple:
    """Prefer the object that has the expected fields, then the biggest."""
    present = sum(1 for key in expect_keys if key in result)
    return (present, len(json.dumps(result, ensure_ascii=False, default=str)))


def _top_level_starts(cleaned: str) -> list[int]:
    """Positions of the '{' that are not inside another object or a string
    (an object nested in a broken or cut-off bigger one is not a start)."""
    starts, depth, in_string, i = [], 0, False, 0
    while i < len(cleaned):
        char = cleaned[i]
        if in_string:
            if char == "\\":
                i += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "{[":
            if char == "{" and depth == 0:
                starts.append(i)
            depth += 1
        elif char in "}]":
            depth = max(0, depth - 1)
        i += 1
    return starts


def _closing_object(cleaned: str) -> dict | None:
    """The valid JSON object that ends the answer, when prose or an example
    with braces comes before it."""
    decoder, last_close = json.JSONDecoder(strict=False), cleaned.rfind("}")
    for position in _top_level_starts(cleaned)[:_MAX_STARTS]:
        try:
            value, end = decoder.raw_decode(cleaned, position)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and end > last_close:
            return value
    return None


def parse_json_object(text: str) -> dict:
    cleaned = _strip_markdown_fence(text)
    try:
        parsed = json.loads(cleaned, strict=False)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    closing = _closing_object(cleaned)
    if closing is not None:
        return closing

    match = _JSON_BLOCK.search(cleaned)
    if not match:
        raise ValueError("The LLM did not return a JSON object.")

    try:
        parsed = json.loads(match.group(0), strict=False)
    except json.JSONDecodeError as error:
        raise ValueError(
            "The LLM returned malformed JSON: {}".format(error)
        ) from error

    if not isinstance(parsed, dict):
        raise ValueError("The LLM response was not a JSON object.")
    return parsed

_MISSING_COMMA = re.compile(r'(["}\]0-9]|true|false|null)(\s*\n\s*)(["{\[])')
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _escape_inner_quotes(text: str) -> str:
    """Escape quotation marks that sit INSIDE a string value (a quoted
    article title in Arabic legal text, for example): a quote only closes a
    string when what follows it is JSON structure (, : } ] or a line break)."""
    out, in_string, i = [], False, 0
    while i < len(text):
        char = text[i]
        if not in_string:
            in_string = char == '"'
            out.append(char)
        elif char == "\\":
            out.append(text[i:i + 2])
            i += 2
            continue
        elif char == '"':
            rest = text[i + 1:].lstrip(" \t")
            if not rest or rest[0] in ",:}]\r\n":
                in_string = False
                out.append(char)
            else:
                out.append('\\"')
        else:
            out.append(char)
        i += 1
    return "".join(out)


def repair_json_text(text: str) -> str:
    """Fix the slips models make in long JSON answers, without touching
    content: unescaped quotes inside a value, a missing comma between two
    items written on separate lines, and a comma before a closing bracket."""
    fixed = _escape_inner_quotes(text)
    fixed = _MISSING_COMMA.sub(r"\1,\2\3", fixed)
    return _TRAILING_COMMA.sub(r"\1", fixed)


# -----------------------------------------------------------------------------
# A tolerant reader for model answers that are almost JSON
# -----------------------------------------------------------------------------
_VALUE_START = set('"\'{[-0123456789') | set("tfnTFN")
_BAREWORDS = {"true": True, "false": False, "null": None, "none": None}


class _Tolerant:
    """Reads JSON the way a model tends to write it: missing or extra
    commas, quotes inside text, unquoted keys or words, single quotes,
    // and # comments, Python literals, and an answer cut off at the end
    (open objects and lists are closed). Content is never rewritten."""

    def __init__(self, text: str):
        self.s, self.i, self.n = text, 0, len(text)

    def _skip(self):
        while self.i < self.n:
            c = self.s[self.i]
            if c.isspace():
                self.i += 1
            elif self.s.startswith("//", self.i) or (c == "#" and self._line_start()):
                end = self.s.find("\n", self.i)
                self.i = self.n if end < 0 else end + 1
            elif self.s.startswith("/*", self.i):
                end = self.s.find("*/", self.i + 2)
                self.i = self.n if end < 0 else end + 2
            else:
                break

    def _line_start(self) -> bool:
        j = self.i - 1
        while j >= 0 and self.s[j] in " \t":
            j -= 1
        return j < 0 or self.s[j] == "\n"

    def _peek_after(self, j: int) -> str:
        while j < self.n and self.s[j] in " \t\r":
            j += 1
        return self.s[j] if j < self.n else ""

    def value(self):
        self._skip()
        if self.i >= self.n:
            return None
        c = self.s[self.i]
        if c == "{":
            return self.obj()
        if c == "[":
            return self.arr()
        if c in "\"'":
            return self.string(c)
        if c == "-" or c.isdigit():
            match = re.match(r"-?\d+(\.\d+)?([eE][-+]?\d+)?(?![\w.])", self.s[self.i:])
            if match:
                self.i += match.end()
                text = match.group(0)
                return float(text) if any(ch in text for ch in ".eE") else int(text)
        return self.bare()

    def bare(self):
        start = self.i
        while self.i < self.n and self.s[self.i] not in ",:}]\n":
            self.i += 1
        word = self.s[start:self.i].strip()
        return _BAREWORDS[word.lower()] if word.lower() in _BAREWORDS else word

    def string(self, quote: str) -> str:
        self.i += 1
        out = []
        while self.i < self.n:
            c = self.s[self.i]
            if c == "\\" and self.i + 1 < self.n:
                nxt = self.s[self.i + 1]
                out.append({"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}.get(nxt, nxt))
                if nxt == "u" and re.match(r"[0-9a-fA-F]{4}", self.s[self.i + 2:self.i + 6]):
                    out[-1] = chr(int(self.s[self.i + 2:self.i + 6], 16))
                    self.i += 4
                self.i += 2
                continue
            if c == quote and self._closes(self.i + 1):
                self.i += 1
                return "".join(out)
            out.append(c)
            self.i += 1
        return "".join(out)                      # cut off inside the string

    def _closes(self, j: int) -> bool:
        """A quote ends the string only when JSON structure follows it."""
        nxt = self._peek_after(j)
        if nxt in ("", "\n", "}", "]"):
            return True
        if nxt in ",:":
            k = j
            while self.s[k] != nxt:
                k += 1
            after = self._peek_after(k + 1)
            return after in ("", "\n", "}", "]") or after in _VALUE_START
        return False

    def obj(self) -> dict:
        self.i += 1
        out = {}
        while True:
            self._skip()
            if self.i >= self.n:
                return out
            c = self.s[self.i]
            if c == "}":
                self.i += 1
                return out
            if c == ",":
                self.i += 1
                continue
            if c == "]":                          # mismatched close: end the object here
                return out
            key = self.string(c) if c in "\"'" else self.bare()
            self._skip()
            if self.i < self.n and self.s[self.i] == ":":
                self.i += 1
            out[str(key)] = self.value()

    def arr(self) -> list:
        self.i += 1
        out = []
        while True:
            self._skip()
            if self.i >= self.n:
                return out
            c = self.s[self.i]
            if c == "]":
                self.i += 1
                return out
            if c == ",":
                self.i += 1
                continue
            if c == "}":
                return out
            before = self.i
            out.append(self.value())
            if self.i == before:                  # never loop on a character it cannot read
                self.i += 1


_TOLERANT_STARTS = 20


def parse_json_tolerant(text: str, expect_keys=()) -> dict:
    """The JSON object in a model answer, read tolerantly (see _Tolerant).
    It is read from the first '{' and from every '{' outside an object
    (prose or an example may come first), keeping the reading with the
    expected fields, then the biggest."""
    cleaned = _strip_markdown_fence(text)
    first = cleaned.find("{")
    if first < 0:
        raise ValueError("The LLM did not return a JSON object.")
    starts = list(dict.fromkeys([first] + _top_level_starts(cleaned)))[:_TOLERANT_STARTS]
    best = None
    for start in starts:
        try:
            result = _Tolerant(cleaned[start:]).value()
        except Exception:
            continue
        if isinstance(result, dict) and result and (best is None or _rank(result, expect_keys) > _rank(best, expect_keys)):
            best = result
    if best is None:
        raise ValueError("The LLM answer could not be read as a JSON object.")
    return best


def _error_context(text: str, error: Exception, width: int = 160) -> str:
    """The answer around a JSON error, for the log."""
    match = re.search(r"\(char (\d+)\)", str(error))
    cleaned = _strip_markdown_fence(text)
    start = cleaned.find("{")
    if not match or start < 0:
        return cleaned[:2 * width]
    at = start + int(match.group(1))
    return cleaned[max(0, at - width):at] + " <<HERE>> " + cleaned[at:at + width]


class MissingFields(ValueError):
    """The answer is JSON but has none of the fields asked for."""


def _read_json(text: str, expect_keys) -> dict:
    try:
        return parse_json_object(text)
    except ValueError as first_error:
        print("[complete_json] malformed JSON: {} | answer near the error: {!r}".format(
            first_error, _error_context(text, first_error)))
        try:
            repaired = parse_json_object(repair_json_text(_strip_markdown_fence(text)))
            print("[complete_json] malformed JSON repaired in code")
            return repaired
        except ValueError:
            pass
        try:
            result = parse_json_tolerant(text, expect_keys)
            print("[complete_json] malformed JSON read with the tolerant reader")
            return result
        except Exception:
            raise first_error


def parse_json_lenient(text: str, expect_keys=()) -> dict:
    """parse_json_object; then after repair_json_text; then the tolerant
    reader. Raises the first error only if all three fail. With
    `expect_keys`, an object with none of those fields is refused too."""
    result = _read_json(text, expect_keys)
    if expect_keys and not any(key in result for key in expect_keys):
        raise MissingFields("The LLM answer has none of the expected fields ({}).".format(", ".join(expect_keys)))
    return result


NO_THINK = "/no_think"
FIX_JSON_PROMPT = """
/no_think
The text you receive is a model answer that should be ONE JSON object but is
not valid JSON (a missing comma, an unescaped quote, words around it, or cut
off at the end). Return the same content as one valid JSON object: keep
every field and every value exactly as written (same language, same
wording); do not add, drop, translate or summarise anything; close whatever
was left open. Return only the JSON object.
""".strip()
_FIX_MAX_CHARS = 60000


def _execute(llm, llm_id: str, messages: list, temperature: float) -> str:
    """One completion; the answer text (reasoning included)."""
    completion = llm.new_completion()
    try:
        completion.settings["temperature"] = float(temperature)
    except Exception:
        pass
    for text, role in messages:
        completion.with_message(text, role=role)
    response = completion.execute()
    success = getattr(response, "success", True)
    if not success:
        error_message = (
            getattr(response, "error_message", None)
            or getattr(response, "error", None)
            or "The LLM request failed."
        )
        print(
            "[complete_json failure] llm_id={} success={} "
            "error_message={!r} response_type={}".format(
                llm_id,
                success,
                error_message,
                type(response).__name__,
            )
        )
        raise RuntimeError(str(error_message))
    return _extract_text(response)


def complete_json(
    system_prompt: str,
    user_payload: dict,
    llm_id: str = TEXT_STRUCTURING_LLM_ID,
    temperature: float = 0.0,
    expect_keys: tuple = (),
) -> dict:
    """One JSON object from the model. A malformed answer is read
    tolerantly; failing that, the model gets one more call, never bigger
    than the first:
      - an answer with JSON in it: only that answer goes back, to be
        rewritten as valid JSON (the request is not sent again);
      - an answer without JSON (empty, or the model stopped while still
        reasoning) or without the expected fields: the same request again,
        without reasoning.
    `expect_keys`: fields the object should have (at least one of them)."""
    project = dataiku.api_client().get_default_project()
    llm = project.get_llm(llm_id)
    payload_text = json.dumps(
        user_payload,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    print(
        "[complete_json request] llm_id={} payload_chars={}".format(
            llm_id,
            len(payload_text),
        )
    )

    raw = _execute(llm, llm_id, [(system_prompt, "system"), (payload_text, "user")], temperature)
    text = strip_think(raw)
    try:
        return parse_json_lenient(text, expect_keys)
    except ValueError as error:
        first_error = error

    if "{" in text and not isinstance(first_error, MissingFields):
        print("[complete_json] unreadable JSON ({}; answer_chars={}); sending only the answer back to be "
              "rewritten as valid JSON".format(first_error, len(text)))
        start = text.find("{")
        second = _execute(llm, llm_id, [(FIX_JSON_PROMPT, "system"), (text[start:start + _FIX_MAX_CHARS], "user")], 0.0)
    else:
        print("[complete_json] no usable JSON in the answer ({}; answer_chars={} raw_chars={}); asking again "
              "without reasoning".format(first_error, len(text), len(raw or "")))
        system = system_prompt if system_prompt.lstrip().startswith(NO_THINK) else NO_THINK + "\n" + system_prompt
        second = _execute(llm, llm_id, [
            (system, "system"),
            (payload_text + "\n\nReturn only the JSON object described in the instructions, nothing else.", "user"),
        ], temperature)
    try:
        result = parse_json_lenient(strip_think(second), expect_keys)
    except ValueError:
        raise first_error
    print("[complete_json] the second answer was read")
    return result
