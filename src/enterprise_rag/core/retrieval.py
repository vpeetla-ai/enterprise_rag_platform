"""Access-aware hybrid retrieval with lexical, semantic, metadata, and recency signals."""

from __future__ import annotations

import math
from collections import Counter
from datetime import UTC, datetime

from enterprise_rag.core.access import AccessPolicy
from enterprise_rag.core.models import Chunk, RetrievalHit, RetrievalMode, RetrievalQuery
from enterprise_rag.core.text import query_terms, tokenize


class InMemoryHybridRetriever:
    """Reference retriever.

    Production deployments should back this interface with OpenSearch/BM25,
    a vector store, metadata indexes, rerankers, and graph expansion.
    """

    def __init__(self, chunks: tuple[Chunk, ...], access_policy: AccessPolicy | None = None) -> None:
        self._chunks = chunks
        self._access_policy = access_policy or AccessPolicy()
        self._doc_freq = self._build_doc_freq(chunks)

    def upsert(self, chunks: tuple[Chunk, ...]) -> int:
        if not chunks:
            return 0
        self._chunks = self._chunks + chunks
        self._doc_freq = self._build_doc_freq(self._chunks)
        return len(chunks)

    def search(self, query: RetrievalQuery) -> tuple[RetrievalHit, ...]:
        terms = query_terms(query.query)
        hits: list[RetrievalHit] = []
        for chunk in self._chunks:
            if not self._access_policy.can_read(query.principal, chunk):
                continue
            if not self._matches_filters(query.filters, chunk):
                continue
            score, reasons = self._score(terms, chunk, query.mode)
            if score > 0:
                hits.append(RetrievalHit(chunk=chunk, score=score, reasons=tuple(reasons)))

        hits.sort(key=lambda hit: hit.score, reverse=True)
        return tuple(hits[: query.top_k])

    def _score(
        self, terms: list[str], chunk: Chunk, mode: RetrievalMode
    ) -> tuple[float, list[str]]:
        chunk_terms = tokenize(
            f"{chunk.source_title} {chunk.text} {' '.join(chunk.metadata.values())}"
        )
        title_terms = set(tokenize(chunk.source_title))
        lexical = self._bm25_like(terms, chunk_terms)
        semantic = self._semantic_proxy(terms, chunk_terms)
        recency = self._recency_boost(chunk.updated_at)
        score = 0.0
        reasons: list[str] = []

        if mode in (RetrievalMode.HYBRID, RetrievalMode.KEYWORD):
            score += lexical * 0.65
            if lexical:
                reasons.append("keyword_match")
        if mode in (RetrievalMode.HYBRID, RetrievalMode.SEMANTIC):
            score += semantic * 0.30
            if semantic:
                reasons.append("semantic_similarity")
        title_overlap = len(set(terms) & title_terms)
        if title_overlap:
            score += title_overlap * 0.5
            reasons.append("title_match")
        if score > 0 and recency:
            score += recency * 0.05
            reasons.append("freshness_boost")

        return score, reasons

    def _bm25_like(self, query_terms: list[str], chunk_terms: list[str]) -> float:
        if not query_terms or not chunk_terms:
            return 0.0
        counts = Counter(chunk_terms)
        total = 0.0
        for term in set(query_terms):
            if term not in counts:
                continue
            idf = math.log((1 + len(self._chunks)) / (1 + self._doc_freq.get(term, 0))) + 1
            total += counts[term] * idf
        return total / math.sqrt(len(chunk_terms))

    @staticmethod
    def _semantic_proxy(query_terms: list[str], chunk_terms: list[str]) -> float:
        query_set = set(query_terms)
        chunk_set = set(chunk_terms)
        if not query_set or not chunk_set:
            return 0.0
        return len(query_set & chunk_set) / len(query_set | chunk_set)

    @staticmethod
    def _recency_boost(updated_at: datetime) -> float:
        age_days = max((datetime.now(UTC) - updated_at).days, 0)
        return 1 / (1 + age_days / 90)

    @staticmethod
    def _matches_filters(filters: dict[str, str], chunk: Chunk) -> bool:
        return all(chunk.metadata.get(key) == value for key, value in filters.items())

    @staticmethod
    def _build_doc_freq(chunks: tuple[Chunk, ...]) -> dict[str, int]:
        freq: Counter[str] = Counter()
        for chunk in chunks:
            freq.update(
                set(tokenize(f"{chunk.source_title} {chunk.text} {' '.join(chunk.metadata.values())}"))
            )
        return dict(freq)
