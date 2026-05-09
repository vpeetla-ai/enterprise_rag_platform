"""Document ingestion, chunking, and quality gates."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from enterprise_rag.core.models import Chunk, SourceDocument


@dataclass(frozen=True)
class IngestionIssue:
    code: str
    message: str
    document_id: str


@dataclass(frozen=True)
class IngestionResult:
    chunks: tuple[Chunk, ...]
    issues: tuple[IngestionIssue, ...]


class DocumentChunker:
    def __init__(self, max_words: int = 180, overlap_words: int = 30) -> None:
        if overlap_words >= max_words:
            raise ValueError("overlap_words must be smaller than max_words")
        self.max_words = max_words
        self.overlap_words = overlap_words

    def chunk(self, document: SourceDocument) -> IngestionResult:
        issues = self._validate(document)
        normalized = re.sub(r"\s+", " ", document.body).strip()
        words = normalized.split()
        if not words:
            return IngestionResult(chunks=(), issues=tuple(issues))

        chunks: list[Chunk] = []
        step = self.max_words - self.overlap_words
        for index, start in enumerate(range(0, len(words), step)):
            text = " ".join(words[start : start + self.max_words])
            if not text:
                continue
            digest = hashlib.sha256(
                f"{document.document_id}:{index}:{text}".encode("utf-8")
            ).hexdigest()[:16]
            chunks.append(
                Chunk(
                    chunk_id=f"{document.document_id}:{digest}",
                    document_id=document.document_id,
                    tenant_id=document.tenant_id,
                    text=text,
                    source_title=document.title,
                    source_uri=document.uri,
                    owner=document.owner,
                    classification=document.classification,
                    allowed_groups=document.allowed_groups,
                    metadata=document.metadata,
                    updated_at=document.updated_at,
                )
            )
            if start + self.max_words >= len(words):
                break

        return IngestionResult(chunks=tuple(chunks), issues=tuple(issues))

    @staticmethod
    def _validate(document: SourceDocument) -> list[IngestionIssue]:
        issues: list[IngestionIssue] = []
        if not document.owner:
            issues.append(IngestionIssue("missing_owner", "Document owner is required.", document.document_id))
        if not document.uri:
            issues.append(IngestionIssue("missing_lineage", "Source URI is required.", document.document_id))
        if len(document.body.strip()) < 40:
            issues.append(IngestionIssue("low_content", "Document body is too short.", document.document_id))
        if "effective_date" not in document.metadata:
            issues.append(
                IngestionIssue(
                    "missing_freshness_metadata",
                    "Document should include effective_date metadata.",
                    document.document_id,
                )
            )
        return issues
