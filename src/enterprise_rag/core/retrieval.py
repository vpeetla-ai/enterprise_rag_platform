"""Access-aware hybrid retrieval: BM25 (k1/b) + dense + RRF fusion (ADR-0001/0008)."""

from __future__ import annotations

import math
import os
from collections import Counter
from datetime import UTC, datetime

from enterprise_rag.core.access import AccessPolicy
from enterprise_rag.core.embeddings import Embedder, build_embedder, cosine
from enterprise_rag.core.models import Chunk, RetrievalHit, RetrievalMode, RetrievalQuery
from enterprise_rag.core.text import query_terms, tokenize

RRF_K = 60
BM25_K1 = 1.2
BM25_B = 0.75


def rrf_fuse(
    ranked_lists: list[list[str]],
    *,
    k: int = RRF_K,
) -> dict[str, float]:
    """Reciprocal rank fusion over lists of chunk_ids (best-first)."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def bm25_score(
    query_terms_list: list[str],
    chunk_terms: list[str],
    *,
    doc_freq: dict[str, int],
    n_docs: int,
    avg_len: float,
    k1: float = BM25_K1,
    b: float = BM25_B,
) -> float:
    """Okapi BM25 with k1/b saturation — shared by memory and Qdrant hybrid paths."""
    if not query_terms_list or not chunk_terms:
        return 0.0
    counts = Counter(chunk_terms)
    dl = len(chunk_terms)
    total = 0.0
    n_docs = max(n_docs, 1)
    for term in set(query_terms_list):
        tf = counts.get(term, 0)
        if tf == 0:
            continue
        df = doc_freq.get(term, 0)
        idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
        denom = tf + k1 * (1 - b + b * dl / max(avg_len, 1.0))
        total += idf * (tf * (k1 + 1)) / denom
    return total


def build_doc_freq(chunks: tuple[Chunk, ...] | list[Chunk]) -> dict[str, int]:
    freq: Counter[str] = Counter()
    for chunk in chunks:
        freq.update(
            set(tokenize(f"{chunk.source_title} {chunk.text} {' '.join(chunk.metadata.values())}"))
        )
    return dict(freq)


class InMemoryHybridRetriever:
    """Hybrid retriever with access-before-ranking and RRF fusion."""

    def __init__(
        self,
        chunks: tuple[Chunk, ...] = (),
        access_policy: AccessPolicy | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._access_policy = access_policy or AccessPolicy()
        self._embedder = embedder or build_embedder()
        self._chunks: tuple[Chunk, ...] = ()
        self._vectors: dict[str, list[float]] = {}
        self._doc_freq: dict[str, int] = {}
        self._avg_len = 1.0
        if chunks:
            self.upsert(chunks)

    def upsert(self, chunks: tuple[Chunk, ...]) -> int:
        if not chunks:
            return 0
        # Replace existing chunks for the same tenant+document (ingest lifecycle)
        by_doc: dict[tuple[str, str], list[Chunk]] = {}
        for chunk in chunks:
            by_doc.setdefault((chunk.tenant_id, chunk.document_id), []).append(chunk)
        for tenant_id, document_id in by_doc:
            self.delete_document(document_id=document_id, tenant_id=tenant_id)

        # Dedupe identical content_hash within this batch
        seen_hash: set[str] = set()
        unique: list[Chunk] = []
        for chunk in chunks:
            if chunk.content_hash and chunk.content_hash in seen_hash:
                continue
            if chunk.content_hash:
                seen_hash.add(chunk.content_hash)
            unique.append(chunk)
        if not unique:
            return 0

        self._chunks = self._chunks + tuple(unique)
        texts = [c.text for c in unique]
        vectors = self._embedder.embed(texts)
        for chunk, vec in zip(unique, vectors, strict=True):
            self._vectors[chunk.chunk_id] = vec
        self._doc_freq = self._build_doc_freq(self._chunks)
        lengths = [
            len(tokenize(f"{c.source_title} {c.text}"))
            for c in self._chunks
        ]
        self._avg_len = (sum(lengths) / len(lengths)) if lengths else 1.0
        return len(unique)

    def delete_document(self, *, document_id: str, tenant_id: str) -> int:
        """Remove all chunks for a document in a tenant. Returns count removed."""
        keep: list[Chunk] = []
        removed = 0
        for chunk in self._chunks:
            if chunk.document_id == document_id and chunk.tenant_id == tenant_id:
                self._vectors.pop(chunk.chunk_id, None)
                removed += 1
            else:
                keep.append(chunk)
        if removed:
            self._chunks = tuple(keep)
            self._doc_freq = self._build_doc_freq(self._chunks)
            lengths = [
                len(tokenize(f"{c.source_title} {c.text}")) for c in self._chunks
            ]
            self._avg_len = (sum(lengths) / len(lengths)) if lengths else 1.0
        return removed

    def search(self, query: RetrievalQuery) -> tuple[RetrievalHit, ...]:
        terms = query_terms(query.query)
        eligible: list[Chunk] = []
        for chunk in self._chunks:
            if not self._access_policy.can_read(query.principal, chunk):
                continue
            if not self._matches_filters(query.filters, chunk):
                continue
            eligible.append(chunk)
        if not eligible:
            return ()

        lexical_ranked: list[tuple[str, float]] = []
        dense_ranked: list[tuple[str, float]] = []
        q_vec = self._embedder.embed([query.query])[0]

        for chunk in eligible:
            chunk_terms = tokenize(
                f"{chunk.source_title} {chunk.text} {' '.join(chunk.metadata.values())}"
            )
            lex = self._bm25(terms, chunk_terms)
            title_boost = len(set(terms) & set(tokenize(chunk.source_title))) * 0.5
            lex_score = lex + title_boost
            if lex_score > 0:
                lexical_ranked.append((chunk.chunk_id, lex_score))
            dense = cosine(q_vec, self._vectors.get(chunk.chunk_id, []))
            if dense > 0:
                dense_ranked.append((chunk.chunk_id, dense))

        lexical_ranked.sort(key=lambda x: x[1], reverse=True)
        dense_ranked.sort(key=lambda x: x[1], reverse=True)

        if query.mode == RetrievalMode.KEYWORD:
            fused = {cid: score for cid, score in lexical_ranked}
            reason_sets = {cid: ("bm25",) for cid, _ in lexical_ranked}
        elif query.mode == RetrievalMode.SEMANTIC:
            fused = {cid: score for cid, score in dense_ranked}
            reason_sets = {cid: ("dense",) for cid, _ in dense_ranked}
        else:
            lists = [
                [cid for cid, _ in lexical_ranked],
                [cid for cid, _ in dense_ranked],
            ]
            fused = rrf_fuse(lists)
            reason_sets = {}
            lex_ids = {cid for cid, _ in lexical_ranked}
            dense_ids = {cid for cid, _ in dense_ranked}
            for cid in fused:
                reasons: list[str] = ["rrf"]
                if cid in lex_ids:
                    reasons.append("bm25")
                if cid in dense_ids:
                    reasons.append("dense")
                reason_sets[cid] = tuple(reasons)

        by_id = {c.chunk_id: c for c in eligible}
        hits: list[RetrievalHit] = []
        for cid, score in sorted(fused.items(), key=lambda x: x[1], reverse=True):
            chunk = by_id.get(cid)
            if not chunk:
                continue
            recency = self._recency_boost(chunk.updated_at)
            final = score + recency * 0.01
            hits.append(
                RetrievalHit(
                    chunk=chunk,
                    score=final,
                    reasons=reason_sets.get(cid, ("hybrid",)),
                )
            )
            if len(hits) >= query.top_k:
                break
        return tuple(hits)

    def _bm25(self, query_terms_list: list[str], chunk_terms: list[str]) -> float:
        return bm25_score(
            query_terms_list,
            chunk_terms,
            doc_freq=self._doc_freq,
            n_docs=len(self._chunks),
            avg_len=self._avg_len,
        )

    @staticmethod
    def _recency_boost(updated_at: datetime) -> float:
        age_days = max((datetime.now(UTC) - updated_at).days, 0)
        return 1 / (1 + age_days / 90)

    @staticmethod
    def _matches_filters(filters: dict[str, str], chunk: Chunk) -> bool:
        return all(chunk.metadata.get(key) == value for key, value in filters.items())

    @staticmethod
    def _build_doc_freq(chunks: tuple[Chunk, ...]) -> dict[str, int]:
        return build_doc_freq(chunks)


def retrieval_profile() -> dict[str, str | bool]:
    return {
        "dense": True,
        "fusion": "rrf",
        "embedding_provider": os.getenv("EMBEDDING_PROVIDER", "hash"),
        "reranker": os.getenv("RAG_RERANKER", "score_boost"),
    }
