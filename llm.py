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


def strip_think(text: str) -> str:
    return _THINK_BLOCK.sub("", str(text or "")).strip()


def _strip_markdown_fence(text: str) -> str:
    text = strip_think(text)
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_json_object(text: str) -> dict:
    cleaned = _strip_markdown_fence(text)
    try:
        parsed = json.loads(cleaned, strict=False)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

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


def parse_json_tolerant(text: str) -> dict:
    """The JSON object in a model answer, read tolerantly (see _Tolerant)."""
    cleaned = _strip_markdown_fence(text)
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("The LLM did not return a JSON object.")
    result = _Tolerant(cleaned[start:]).value()
    if not isinstance(result, dict) or not result:
        raise ValueError("The LLM answer could not be read as a JSON object.")
    return result


def _error_context(text: str, error: Exception, width: int = 160) -> str:
    """The answer around a JSON error, for the log."""
    match = re.search(r"\(char (\d+)\)", str(error))
    cleaned = _strip_markdown_fence(text)
    start = cleaned.find("{")
    if not match or start < 0:
        return cleaned[:2 * width]
    at = start + int(match.group(1))
    return cleaned[max(0, at - width):at] + " <<HERE>> " + cleaned[at:at + width]


def parse_json_lenient(text: str) -> dict:
    """parse_json_object; then after repair_json_text; then the tolerant
    reader. Raises the first error only if all three fail."""
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
            result = parse_json_tolerant(text)
            print("[complete_json] malformed JSON read with the tolerant reader")
            return result
        except Exception:
            raise first_error


def complete_json(
    system_prompt: str,
    user_payload: dict,
    llm_id: str = TEXT_STRUCTURING_LLM_ID,
    temperature: float = 0.0,
) -> dict:
    # Guard against accidentally routing text-only JSON to the OCR models.
    #if "qwen36-35b-a3b-fp8-1" in str(llm_id) or "qwen3-vl32b" in str(llm_id):
    #    raise RuntimeError(
    #        "Text-only complete_json was configured with a vision OCR model: "
    #        + str(llm_id)
    #    )
#
    project = dataiku.api_client().get_default_project()
    llm = project.get_llm(llm_id)
    completion = llm.new_completion()

    try:
        completion.settings["temperature"] = float(temperature)
    except Exception:
        pass

    completion.with_message(system_prompt, role="system")
    payload_text = json.dumps(
        user_payload,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    completion.with_message(payload_text, role="user")

    print(
        "[complete_json request] llm_id={} payload_chars={}".format(
            llm_id,
            len(payload_text),
        )
    )

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

    text = strip_think(_extract_text(response))
    if not text:
        raise RuntimeError(
            "The completion succeeded but response.text was empty. "
            "llm_id={}".format(llm_id)
        )

    try:
        return parse_json_lenient(text)
    except ValueError as error:
        # One more try: the model resends the same answer as valid JSON.
        print("[complete_json] malformed JSON ({}); asking the model to resend it".format(error))
        retry = llm.new_completion()
        try:
            retry.settings["temperature"] = 0.0
        except Exception:
            pass
        retry.with_message(system_prompt, role="system")
        retry.with_message(payload_text, role="user")
        retry.with_message(text[:60000], role="assistant")
        retry.with_message(
            "Your previous answer is not valid JSON ({}). Return exactly the same answer as one valid JSON "
            "object: every item separated by a comma, no trailing commas, nothing before or after it."
            .format(error),
            role="user",
        )
        second = retry.execute()
        if getattr(second, "success", True) is False:
            raise error
        return parse_json_lenient(strip_think(_extract_text(second)))
