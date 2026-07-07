"""Reranking extension point — cross-encoder or LLM rerankers plug in here."""

from __future__ import annotations

import os
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
        out: list[RetrievalHit] = []
        for score, hit in rescored[:limit]:
            out.append(RetrievalHit(chunk=hit.chunk, score=score, reasons=(*hit.reasons, "score_boost")))
        return tuple(out)


class CrossEncoderReranker:
    """Optional cross-encoder reranker — install with pip install -e '.[rerank]'."""

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        min_score: float = 0.0,
    ) -> None:
        self.model_name = model_name
        self.min_score = min_score
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(
        self, query: str, hits: tuple[RetrievalHit, ...], limit: int
    ) -> tuple[RetrievalHit, ...]:
        if not hits:
            return hits
        model = self._load()
        pairs = [(query, hit.chunk.text) for hit in hits]
        scores = model.predict(pairs)
        rescored: list[tuple[float, RetrievalHit]] = []
        for score, hit in zip(scores, hits, strict=True):
            rescored.append((float(score), hit))
        rescored.sort(key=lambda x: x[0], reverse=True)
        out: list[RetrievalHit] = []
        for score, hit in rescored:
            if score < self.min_score:
                continue
            out.append(
                RetrievalHit(
                    chunk=hit.chunk,
                    score=score,
                    reasons=(*hit.reasons, "cross_encoder"),
                )
            )
            if len(out) >= limit:
                break
        return tuple(out)


def build_reranker() -> Reranker:
    kind = os.getenv("RAG_RERANKER", "score_boost").strip().lower()
    if kind == "cross_encoder":
        return CrossEncoderReranker(
            model_name=os.getenv(
                "CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
            ),
            min_score=float(os.getenv("RAG_RERANK_THRESHOLD", "0.0")),
        )
    return ScoreBoostReranker()
