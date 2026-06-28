"""Reranking extension point — cross-encoder or LLM rerankers plug in here."""

from __future__ import annotations

import re
from typing import Protocol

from enterprise_rag.core.models import RetrievalHit


class Reranker(Protocol):
    def rerank(
        self, query: str, hits: tuple[RetrievalHit, ...], limit: int
    ) -> tuple[RetrievalHit, ...]:
        ...


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9][a-z0-9_-]*", text.lower()))


class ScoreBoostReranker:
    """Reference reranker — boosts hits with title/metadata term overlap (no ML deps)."""

    def rerank(
        self, query: str, hits: tuple[RetrievalHit, ...], limit: int
    ) -> tuple[RetrievalHit, ...]:
        if len(hits) <= limit:
            return hits
        q = _tokens(query)
        rescored: list[tuple[float, RetrievalHit]] = []
        for hit in hits:
            meta_text = " ".join(str(v) for v in hit.chunk.metadata.values())
            title = str(hit.chunk.metadata.get("title", hit.chunk.document_id))
            overlap = len(q & _tokens(f"{title} {meta_text} {hit.chunk.text[:200]}"))
            boost = hit.score + overlap * 0.15
            rescored.append((boost, hit))
        rescored.sort(key=lambda x: x[0], reverse=True)
        return tuple(h for _, h in rescored[:limit])
