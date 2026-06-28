"""Optional Qdrant retriever adapter behind the Retriever port."""

from __future__ import annotations

import os
from datetime import UTC, datetime

from enterprise_rag.core.access import AccessPolicy
from enterprise_rag.core.models import (
    Chunk,
    Classification,
    RetrievalHit,
    RetrievalMode,
    RetrievalQuery,
)


def qdrant_available() -> bool:
    try:
        import qdrant_client  # noqa: F401
    except ImportError:
        return False
    return bool(os.getenv("QDRANT_URL"))


class QdrantHybridRetriever:
    """Vector retriever with post-fetch access policy enforcement."""

    def __init__(
        self,
        *,
        url: str | None = None,
        collection: str | None = None,
        access_policy: AccessPolicy | None = None,
    ) -> None:
        from qdrant_client import QdrantClient

        self._client = QdrantClient(url=url or os.getenv("QDRANT_URL", "http://localhost:6333"))
        self._collection = collection or os.getenv("QDRANT_COLLECTION", "enterprise_rag")
        self._access_policy = access_policy or AccessPolicy()

    def search(self, query: RetrievalQuery) -> tuple[RetrievalHit, ...]:
        # Reference implementation uses scroll + lexical proxy when vectors are unavailable.
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
            text_tokens = set(chunk.text.lower().split())
            overlap = len(query_terms & text_tokens)
            if query.mode == RetrievalMode.SEMANTIC:
                score = float(getattr(point, "score", 0.0) or overlap)
            else:
                score = overlap + float(getattr(point, "score", 0.0) or 0.0) * 0.3
            if score <= 0:
                continue
            hits.append(RetrievalHit(chunk=chunk, score=score, reasons=("qdrant_payload",)))
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return tuple(hits[: query.top_k])

    def upsert(self, chunks: tuple[Chunk, ...]) -> int:
        from qdrant_client.http import models as qmodels

        if not chunks:
            return 0
        points = [
            qmodels.PointStruct(
                id=chunk.chunk_id,
                vector=[0.0] * 8,
                payload={
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
                },
            )
            for chunk in chunks
        ]
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
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
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
    )
