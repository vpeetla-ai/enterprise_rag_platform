"""Optional Qdrant retriever — dense ANN + BM25 + RRF (ADR-0008)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from enterprise_rag.core.access import AccessPolicy
from enterprise_rag.core.embeddings import Embedder, build_embedder, cosine
from enterprise_rag.core.models import (
    Chunk,
    Classification,
    RetrievalHit,
    RetrievalMode,
    RetrievalQuery,
)
from enterprise_rag.core.retrieval import bm25_score, build_doc_freq, rrf_fuse
from enterprise_rag.core.text import query_terms, tokenize


def qdrant_available() -> bool:
    try:
        import qdrant_client  # noqa: F401
    except ImportError:
        return False
    return bool(os.getenv("QDRANT_URL"))


def _point_id(chunk_id: str) -> str:
    """Qdrant needs UUID or unsigned int — derive stable UUID5 from chunk_id."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class QdrantHybridRetriever:
    """Hybrid retrieval: tenant-filtered dense ANN + BM25 over payload corpus, fused with RRF.

    Access policy is enforced after fetch. Legacy zero-vector scroll is opt-in only.
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        collection: str | None = None,
        access_policy: AccessPolicy | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qmodels

        self._qmodels = qmodels
        self._client = QdrantClient(
            url=url or os.getenv("QDRANT_URL", "http://localhost:6333"),
            api_key=os.getenv("QDRANT_API_KEY") or None,
        )
        self._collection = collection or os.getenv("QDRANT_COLLECTION", "enterprise_rag")
        self._access_policy = access_policy or AccessPolicy()
        self._embedder = embedder or build_embedder()
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        from qdrant_client.http import models as qmodels

        names = {c.name for c in self._client.get_collections().collections}
        if self._collection in names:
            return
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=qmodels.VectorParams(
                size=self._embedder.dim,
                distance=qmodels.Distance.COSINE,
            ),
        )

    def _tenant_filter(self, tenant_id: str):
        return self._qmodels.Filter(
            must=[
                self._qmodels.FieldCondition(
                    key="tenant_id",
                    match=self._qmodels.MatchValue(value=tenant_id),
                )
            ]
        )

    def _scroll_tenant_chunks(self, tenant_id: str, *, limit: int = 500) -> list[Chunk]:
        """Load tenant payload corpus for BM25 (demo/small-prod scale)."""
        chunks: list[Chunk] = []
        offset = None
        while len(chunks) < limit:
            points, offset = self._client.scroll(
                collection_name=self._collection,
                scroll_filter=self._tenant_filter(tenant_id),
                limit=min(100, limit - len(chunks)),
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break
            for point in points:
                payload = point.payload or {}
                chunk = _payload_to_chunk(str(payload.get("chunk_id") or point.id), payload)
                chunks.append(chunk)
            if offset is None:
                break
        return chunks

    def search(self, query: RetrievalQuery) -> tuple[RetrievalHit, ...]:
        if os.getenv("RAG_ALLOW_LEGACY_SCROLL", "").strip().lower() in {"1", "true", "yes"}:
            return self._legacy_scroll(query)

        corpus = self._scroll_tenant_chunks(query.tenant_id)
        eligible = [
            c
            for c in corpus
            if self._access_policy.can_read(query.principal, c)
            and self._matches_filters(query.filters, c)
        ]
        if not eligible:
            return ()

        by_id = {c.chunk_id: c for c in eligible}
        terms = query_terms(query.query)
        doc_freq = build_doc_freq(eligible)
        lengths = [
            len(tokenize(f"{c.source_title} {c.text}")) for c in eligible
        ]
        avg_len = (sum(lengths) / len(lengths)) if lengths else 1.0

        lexical_ranked: list[tuple[str, float]] = []
        for chunk in eligible:
            chunk_terms = tokenize(
                f"{chunk.source_title} {chunk.text} {' '.join(chunk.metadata.values())}"
            )
            lex = bm25_score(
                terms,
                chunk_terms,
                doc_freq=doc_freq,
                n_docs=len(eligible),
                avg_len=avg_len,
            )
            title_boost = len(set(terms) & set(tokenize(chunk.source_title))) * 0.5
            score = lex + title_boost
            if score > 0:
                lexical_ranked.append((chunk.chunk_id, score))
        lexical_ranked.sort(key=lambda x: x[1], reverse=True)

        dense_ranked: list[tuple[str, float]] = []
        q_vec = self._embedder.embed([query.query])[0]
        results = self._client.search(
            collection_name=self._collection,
            query_vector=q_vec,
            query_filter=self._tenant_filter(query.tenant_id),
            limit=max(query.top_k * 4, 20),
            with_payload=True,
        )
        for point in results:
            payload = point.payload or {}
            chunk = _payload_to_chunk(str(payload.get("chunk_id") or point.id), payload)
            if chunk.chunk_id not in by_id:
                if not self._access_policy.can_read(query.principal, chunk):
                    continue
                by_id[chunk.chunk_id] = chunk
            score = float(point.score or 0.0)
            if score <= 0:
                continue
            dense_ranked.append((chunk.chunk_id, score))
        dense_ranked.sort(key=lambda x: x[1], reverse=True)

        if query.mode == RetrievalMode.KEYWORD:
            fused = {cid: score for cid, score in lexical_ranked}
            reason_sets = {cid: ("bm25", "qdrant") for cid, _ in lexical_ranked}
        elif query.mode == RetrievalMode.SEMANTIC:
            fused = {cid: score for cid, score in dense_ranked}
            reason_sets = {cid: ("qdrant_dense",) for cid, _ in dense_ranked}
        else:
            fused = rrf_fuse(
                [
                    [cid for cid, _ in lexical_ranked],
                    [cid for cid, _ in dense_ranked],
                ]
            )
            lex_ids = {cid for cid, _ in lexical_ranked}
            dense_ids = {cid for cid, _ in dense_ranked}
            reason_sets = {}
            for cid in fused:
                reasons: list[str] = ["rrf", "qdrant"]
                if cid in lex_ids:
                    reasons.append("bm25")
                if cid in dense_ids:
                    reasons.append("dense")
                reason_sets[cid] = tuple(reasons)

        hits: list[RetrievalHit] = []
        for cid, score in sorted(fused.items(), key=lambda x: x[1], reverse=True):
            chunk = by_id.get(cid)
            if not chunk:
                continue
            hits.append(
                RetrievalHit(
                    chunk=chunk,
                    score=score,
                    reasons=reason_sets.get(cid, ("hybrid", "qdrant")),
                )
            )
            if len(hits) >= query.top_k:
                break
        return tuple(hits)

    def _legacy_scroll(self, query: RetrievalQuery) -> tuple[RetrievalHit, ...]:
        """Deprecated path — only when RAG_ALLOW_LEGACY_SCROLL=true."""
        points, _ = self._client.scroll(
            collection_name=self._collection,
            limit=max(query.top_k * 4, 20),
            with_payload=True,
        )
        hits: list[RetrievalHit] = []
        query_term_set = set(query.query.lower().split())
        for point in points:
            payload = point.payload or {}
            if str(payload.get("tenant_id", query.tenant_id)) != query.tenant_id:
                continue
            chunk = _payload_to_chunk(str(point.id), payload)
            if not self._access_policy.can_read(query.principal, chunk):
                continue
            overlap = len(query_term_set & set(chunk.text.lower().split()))
            if overlap <= 0:
                continue
            hits.append(RetrievalHit(chunk=chunk, score=float(overlap), reasons=("legacy_scroll",)))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return tuple(hits[: query.top_k])

    def upsert(self, chunks: tuple[Chunk, ...]) -> int:
        if not chunks:
            return 0
        # Replace existing points for same tenant+document before write
        by_doc: dict[tuple[str, str], None] = {}
        for chunk in chunks:
            by_doc[(chunk.tenant_id, chunk.document_id)] = None
        for tenant_id, document_id in by_doc:
            self.delete_document(document_id=document_id, tenant_id=tenant_id)

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

        vectors = self._embedder.embed([c.text for c in unique])
        points = []
        for chunk, vec in zip(unique, vectors, strict=True):
            points.append(
                self._qmodels.PointStruct(
                    id=_point_id(chunk.chunk_id),
                    vector=vec,
                    payload={
                        "chunk_id": chunk.chunk_id,
                        "tenant_id": chunk.tenant_id,
                        "document_id": chunk.document_id,
                        "text": chunk.text,
                        "title": chunk.source_title,
                        "uri": chunk.source_uri,
                        "owner": chunk.owner,
                        "classification": chunk.classification.value,
                        "allowed_groups": sorted(chunk.allowed_groups),
                        "metadata": chunk.metadata,
                        "updated_at": chunk.updated_at.isoformat(),
                        "content_hash": chunk.content_hash,
                        "ingested_at": chunk.ingested_at.isoformat(),
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "char_start": chunk.char_start,
                        "char_end": chunk.char_end,
                    },
                )
            )
        self._client.upsert(collection_name=self._collection, points=points)
        return len(points)

    def delete_document(self, *, document_id: str, tenant_id: str) -> int:
        """Delete points matching tenant+document. Returns estimated count removed."""
        qfilter = self._qmodels.Filter(
            must=[
                self._qmodels.FieldCondition(
                    key="tenant_id",
                    match=self._qmodels.MatchValue(value=tenant_id),
                ),
                self._qmodels.FieldCondition(
                    key="document_id",
                    match=self._qmodels.MatchValue(value=document_id),
                ),
            ]
        )
        # Count then delete
        points, _ = self._client.scroll(
            collection_name=self._collection,
            scroll_filter=qfilter,
            limit=1000,
            with_payload=False,
            with_vectors=False,
        )
        count = len(points)
        if count:
            self._client.delete(
                collection_name=self._collection,
                points_selector=self._qmodels.FilterSelector(filter=qfilter),
            )
        return count

    @staticmethod
    def _matches_filters(filters: dict[str, str], chunk: Chunk) -> bool:
        return all(chunk.metadata.get(key) == value for key, value in filters.items())


def _payload_to_chunk(point_id: str, payload: dict) -> Chunk:
    groups = payload.get("allowed_groups") or []
    classification = Classification(str(payload.get("classification", Classification.INTERNAL.value)))
    updated_raw = payload.get("updated_at")
    if isinstance(updated_raw, str):
        updated_at = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
    else:
        updated_at = datetime.now(UTC)
    ingested_raw = payload.get("ingested_at")
    if isinstance(ingested_raw, str):
        ingested_at = datetime.fromisoformat(ingested_raw.replace("Z", "+00:00"))
    else:
        ingested_at = updated_at
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    def _opt_int(key: str) -> int | None:
        val = payload.get(key)
        if val is None:
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    return Chunk(
        chunk_id=str(payload.get("chunk_id") or point_id),
        document_id=str(payload.get("document_id", point_id)),
        tenant_id=str(payload.get("tenant_id", "default")),
        text=str(payload.get("text", "")),
        source_title=str(payload.get("title", "")),
        source_uri=str(payload.get("uri", "")),
        owner=str(payload.get("owner", "unknown")),
        classification=classification,
        allowed_groups=frozenset(str(g) for g in groups),
        metadata={str(k): str(v) for k, v in metadata.items()},
        updated_at=updated_at,
        content_hash=str(payload.get("content_hash", "")),
        ingested_at=ingested_at,
        page_start=_opt_int("page_start"),
        page_end=_opt_int("page_end"),
        char_start=_opt_int("char_start"),
        char_end=_opt_int("char_end"),
    )


# Keep cosine import available for unit tests that monkeypatch embedder similarity.
_ = cosine
