"""Optional Qdrant retriever — real vectors + filtered search (ADR-0008)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from enterprise_rag.core.access import AccessPolicy
from enterprise_rag.core.embeddings import Embedder, build_embedder
from enterprise_rag.core.models import (
    Chunk,
    Classification,
    RetrievalHit,
    RetrievalQuery,
)


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
    """Dense ANN search with tenant filter; access policy still enforced post-fetch."""

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

    def search(self, query: RetrievalQuery) -> tuple[RetrievalHit, ...]:
        if os.getenv("RAG_ALLOW_LEGACY_SCROLL", "").strip().lower() in {"1", "true", "yes"}:
            return self._legacy_scroll(query)

        q_vec = self._embedder.embed([query.query])[0]
        qfilter = self._qmodels.Filter(
            must=[
                self._qmodels.FieldCondition(
                    key="tenant_id",
                    match=self._qmodels.MatchValue(value=query.tenant_id),
                )
            ]
        )
        results = self._client.search(
            collection_name=self._collection,
            query_vector=q_vec,
            query_filter=qfilter,
            limit=max(query.top_k * 4, 20),
            with_payload=True,
        )
        hits: list[RetrievalHit] = []
        for point in results:
            payload = point.payload or {}
            chunk = _payload_to_chunk(str(payload.get("chunk_id") or point.id), payload)
            if not self._access_policy.can_read(query.principal, chunk):
                continue
            score = float(point.score or 0.0)
            if score <= 0:
                continue
            hits.append(
                RetrievalHit(
                    chunk=chunk,
                    score=score,
                    reasons=("qdrant_dense", "tenant_filter"),
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
        query_terms = set(query.query.lower().split())
        for point in points:
            payload = point.payload or {}
            if str(payload.get("tenant_id", query.tenant_id)) != query.tenant_id:
                continue
            chunk = _payload_to_chunk(str(point.id), payload)
            if not self._access_policy.can_read(query.principal, chunk):
                continue
            overlap = len(query_terms & set(chunk.text.lower().split()))
            if overlap <= 0:
                continue
            hits.append(RetrievalHit(chunk=chunk, score=float(overlap), reasons=("legacy_scroll",)))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return tuple(hits[: query.top_k])

    def upsert(self, chunks: tuple[Chunk, ...]) -> int:
        if not chunks:
            return 0
        vectors = self._embedder.embed([c.text for c in chunks])
        points = []
        for chunk, vec in zip(chunks, vectors, strict=True):
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
