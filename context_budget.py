from __future__ import annotations

import json
from typing import Any, Callable, Iterable


def serialized_chars(value: Any) -> int:
    """Return the serialized character size of Arabic/English JSON content."""
    text = value if isinstance(value, str) else json.dumps(
        value,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    return len(text)


def truncate_text(text: str, max_chars: int) -> str:
    """Bound input text by characters only; this does not limit model output."""
    value = str(text or "")
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "\n[TRUNCATED FOR INPUT CONTEXT]"


def select_with_char_budget(
    items: Iterable[Any],
    max_chars: int = 50000,
    key: Callable[[Any], Any] | None = None,
) -> list[Any]:
    """Select ordered input items within a character budget."""
    selected: list[Any] = []
    used = 0
    for item in items:
        measured = key(item) if key else item
        cost = serialized_chars(measured)
        if selected and used + cost > max_chars:
            break
        if not selected and cost > max_chars:
            if isinstance(item, str):
                selected.append(truncate_text(item, max_chars))
            else:
                selected.append(item)
            break
        selected.append(item)
        used += cost
    return selected


def make_char_chunks(
    items: list[Any],
    target_chars: int = 34000,
    hard_limit_chars: int = 45000,
    key: Callable[[Any], Any] | None = None,
) -> list[list[Any]]:
    """Group ordered input items by serialized characters, without output caps."""
    chunks: list[list[Any]] = []
    current: list[Any] = []
    current_chars = 0

    for item in items:
        measured = key(item) if key else item
        cost = serialized_chars(measured)

        if current and (
            current_chars + cost > target_chars
            or current_chars + cost > hard_limit_chars
        ):
            chunks.append(current)
            current = []
            current_chars = 0

        current.append(item)
        current_chars += cost

        if current_chars >= hard_limit_chars:
            chunks.append(current)
            current = []
            current_chars = 0

    if current:
        chunks.append(current)

    return chunks
