"""Retriever port — swap in-memory, vector, or hybrid backends."""

from __future__ import annotations

from typing import Protocol

from enterprise_rag.core.models import Chunk, RetrievalHit, RetrievalQuery


class Retriever(Protocol):
    def search(self, query: RetrievalQuery) -> tuple[RetrievalHit, ...]:
        """Return ranked, access-filtered retrieval hits."""


class MutableRetriever(Retriever, Protocol):
    def upsert(self, chunks: tuple[Chunk, ...]) -> int:
        """Insert or replace chunks; returns count added."""
