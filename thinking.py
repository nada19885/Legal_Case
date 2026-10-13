"""
Reasoning ("thinking") switch for the VISION model.
Location: lib/python/legal_platform/thinking.py

The Qwen models reason before they answer unless the request says
/no_think. A transcription needs no reasoning, and with it a page reading
that should take 15 s takes 60 s or more and runs into the connection's
60 s timeout. Every vision call (an image in the request) passes its
instruction through no_think(); VISION_THINKING in config turns reasoning
back on. Text-model calls are not changed here: they keep their reasoning.
"""

from __future__ import annotations

import re

from .config import VISION_THINKING

NO_THINK = "/no_think"
_THINK_BLOCK = re.compile(r"<think>(.*?)(?:</think>|$)", re.DOTALL)


def no_think(text: str) -> str:
    """A vision instruction with /no_think at its start (once)."""
    text = str(text or "")
    if VISION_THINKING or text.lstrip().startswith(NO_THINK):
        return text
    return f"{NO_THINK}\n{text}"


def report_thinking(raw: str, where: str) -> int:
    """Log when an answer still carries reasoning, so a model that ignores
    /no_think shows up in the backend log. Returns the reasoning length."""
    reasoning = sum(len(block.strip()) for block in _THINK_BLOCK.findall(str(raw or "")))
    if reasoning:
        print(f"[model reasoning] where={where} reasoning_chars={reasoning} (the model reasoned despite /no_think)")
    return reasoning
