"""Knowledge graph expansion port — query-time neighbor enrichment."""

from __future__ import annotations

import re
from typing import Protocol

from enterprise_rag.core.access import AccessPolicy
from enterprise_rag.core.models import Chunk, RetrievalHit, RetrievalQuery


class GraphExpander(Protocol):
    def expand(
        self, query: RetrievalQuery, hits: tuple[RetrievalHit, ...], limit: int
    ) -> tuple[RetrievalHit, ...]:
        ...


def _entities(text: str) -> set[str]:
    return {m.lower() for m in re.findall(r"\b[A-Z][a-zA-Z0-9_-]{2,}\b", text)}


class InMemoryGraphExpander:
    """Reference graph expander using co-occurrence edges stored in chunk metadata."""

    def __init__(self, corpus: tuple[Chunk, ...], access_policy: AccessPolicy | None = None) -> None:
        self._corpus = corpus
        self._access_policy = access_policy or AccessPolicy()
        self._entity_index = self._build_entity_index(corpus)

    @staticmethod
    def _build_entity_index(chunks: tuple[Chunk, ...]) -> dict[str, list[Chunk]]:
        index: dict[str, list[Chunk]] = {}
        for chunk in chunks:
            entities = chunk.metadata.get("entities", "")
            for entity in entities.split(","):
                key = entity.strip().lower()
                if not key:
                    continue
                index.setdefault(key, []).append(chunk)
        return index

    def register_entities(self, chunk: Chunk, entities: tuple[str, ...]) -> Chunk:
        metadata = dict(chunk.metadata)
        metadata["entities"] = ",".join(entities)
        return Chunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            tenant_id=chunk.tenant_id,
            text=chunk.text,
            source_title=chunk.source_title,
            source_uri=chunk.source_uri,
            owner=chunk.owner,
            classification=chunk.classification,
            allowed_groups=chunk.allowed_groups,
            metadata=metadata,
            updated_at=chunk.updated_at,
        )

    def expand(
        self, query: RetrievalQuery, hits: tuple[RetrievalHit, ...], limit: int
    ) -> tuple[RetrievalHit, ...]:
        if not hits:
            return hits
        seen = {hit.chunk.chunk_id for hit in hits}
        expanded = list(hits)
        query_entities = _entities(query.query)
        for hit in hits:
            for entity in _entities(hit.chunk.text):
                if entity not in query_entities and entity not in hit.chunk.metadata.get("entities", ""):
                    continue
                for neighbor in self._entity_index.get(entity, []):
                    if neighbor.chunk_id in seen:
                        continue
                    if not self._access_policy.can_read(query.principal, neighbor):
                        continue
                    seen.add(neighbor.chunk_id)
                    expanded.append(
                        RetrievalHit(
                            chunk=neighbor,
                            score=hit.score * 0.75,
                            reasons=("graph_neighbor", entity),
                        )
                    )
                    if len(expanded) >= limit:
                        return tuple(expanded[:limit])
        return tuple(expanded[:limit])
