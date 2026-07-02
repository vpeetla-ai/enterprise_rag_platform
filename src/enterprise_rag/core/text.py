"""Shared text normalization for retrieval and generation."""

from __future__ import annotations

import re

_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "who",
        "what",
        "when",
        "where",
        "why",
        "how",
        "does",
        "do",
        "did",
        "for",
        "to",
        "of",
        "in",
        "on",
        "at",
        "by",
        "and",
        "or",
        "it",
        "its",
        "this",
        "that",
        "with",
        "from",
        "be",
        "been",
        "being",
    }
)


def tokenize(text: str) -> list[str]:
    """Split on punctuation/underscores so Venkata_Peetla matches venkata."""
    normalized = re.sub(r"[_\-/]", " ", text.lower())
    return re.findall(r"[a-z0-9]+", normalized)


def query_terms(text: str) -> list[str]:
    return [term for term in tokenize(text) if term not in _STOP_WORDS and len(term) > 1]
