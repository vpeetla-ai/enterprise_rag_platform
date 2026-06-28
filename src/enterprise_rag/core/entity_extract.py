"""Lightweight entity extraction for graph indexing at ingest time."""

from __future__ import annotations

import re


def extract_entities(text: str, *, limit: int = 8) -> tuple[str, ...]:
    """Extract capitalized phrases and domain terms for graph edges."""
    candidates = re.findall(r"\b[A-Z][a-zA-Z0-9_-]{2,}\b", text)
    stop = {"The", "This", "That", "When", "With", "From", "Production", "Enterprise"}
    ordered: list[str] = []
    for item in candidates:
        if item in stop:
            continue
        if item not in ordered:
            ordered.append(item)
        if len(ordered) >= limit:
            break
    lower_terms = re.findall(r"\b(?:rag|retrieval|evaluation|governance|hybrid)\b", text, re.I)
    for term in lower_terms:
        normalized = term.lower()
        if normalized not in {x.lower() for x in ordered}:
            ordered.append(normalized)
    return tuple(ordered[:limit])
