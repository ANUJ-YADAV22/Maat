"""Deterministic paraphrases of a witness input (templates keep the task parseable)."""

from __future__ import annotations

TEMPLATES = [
    "Please answer this: {x}",
    "Quick question. {x}",
    "{x} Keep it brief.",
    "For the site record: {x}",
    "Supervisor asks: {x}",
    "Urgent. {x} Thanks.",
]


def paraphrases(text: str, n: int = 5) -> list[str]:
    """Up to ``n`` template paraphrases, always different from ``text``."""
    return [t.format(x=text) for t in TEMPLATES[:n]]
