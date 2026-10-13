"""
Model reasoning ("thinking") switch for every model call of the backend.
Location: lib/python/legal_platform/thinking.py

The Qwen models reason before they answer unless the request says
/no_think. Reasoning makes a call several times slower (a page reading
that should take 15 s takes 60 s or more and runs into the connection's
timeout), and none of our tasks needs it: transcribing, summarising and
filling a JSON schema are done better without it. Every completion in the
code passes its instruction through no_think(); MODEL_THINKING in config
turns reasoning back on everywhere.
"""

from __future__ import annotations

import re

from .config import MODEL_THINKING

NO_THINK = "/no_think"
_THINK_BLOCK = re.compile(r"<think>(.*?)(?:</think>|$)", re.DOTALL)


def no_think(text: str) -> str:
    """The instruction with /no_think at its start (once)."""
    text = str(text or "")
    if MODEL_THINKING or text.lstrip().startswith(NO_THINK):
        return text
    return f"{NO_THINK}\n{text}"


def report_thinking(raw: str, where: str) -> int:
    """Log when an answer still carries reasoning, so a model that ignores
    /no_think shows up in the backend log. Returns the reasoning length."""
    reasoning = sum(len(block.strip()) for block in _THINK_BLOCK.findall(str(raw or "")))
    if reasoning:
        print(f"[model reasoning] where={where} reasoning_chars={reasoning} (the model reasoned despite /no_think)")
    return reasoning
