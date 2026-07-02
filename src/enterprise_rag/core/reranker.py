"""Reranking extension point — cross-encoder or LLM rerankers plug in here."""

from __future__ import annotations

from typing import Protocol

from enterprise_rag.core.models import RetrievalHit
from enterprise_rag.core.text import query_terms, tokenize


class Reranker(Protocol):
    def rerank(
        self, query: str, hits: tuple[RetrievalHit, ...], limit: int
    ) -> tuple[RetrievalHit, ...]:
        ...


class ScoreBoostReranker:
    """Reference reranker — boosts hits with title/metadata term overlap (no ML deps)."""

    def rerank(
        self, query: str, hits: tuple[RetrievalHit, ...], limit: int
    ) -> tuple[RetrievalHit, ...]:
        if not hits:
            return hits
        q = set(query_terms(query))
        rescored: list[tuple[float, RetrievalHit]] = []
        for hit in hits:
            meta_text = " ".join(str(v) for v in hit.chunk.metadata.values())
            title = hit.chunk.source_title
            overlap = len(q & set(tokenize(f"{title} {meta_text} {hit.chunk.text[:300]}")))
            title_overlap = len(q & set(tokenize(title)))
            boost = hit.score + overlap * 0.2 + title_overlap * 0.6
            rescored.append((boost, hit))
        rescored.sort(key=lambda x: x[0], reverse=True)
        return tuple(h for _, h in rescored[:limit])
