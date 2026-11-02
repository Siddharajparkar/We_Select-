"""Text helpers shared by Phases 5 and 6."""

from __future__ import annotations


def count_words(text: str | None) -> int:
    """Whitespace-separated tokens; empty strings are ignored."""
    return len(text.split()) if text else 0
