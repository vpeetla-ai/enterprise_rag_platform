"""Document ingestion, page-aware chunking, and quality gates (ADR-0007)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from enterprise_rag.core.models import Chunk, SourceDocument

HARD_ISSUE_CODES = frozenset({"missing_owner", "missing_lineage", "low_content", "ocr_required"})


@dataclass(frozen=True)
class IngestionIssue:
    code: str
    message: str
    document_id: str


@dataclass(frozen=True)
class IngestionResult:
    chunks: tuple[Chunk, ...]
    issues: tuple[IngestionIssue, ...]

    @property
    def blocking_issues(self) -> tuple[IngestionIssue, ...]:
        return tuple(issue for issue in self.issues if issue.code in HARD_ISSUE_CODES)


class DocumentChunker:
    def __init__(self, max_words: int = 180, overlap_words: int = 30) -> None:
        if overlap_words >= max_words:
            raise ValueError("overlap_words must be smaller than max_words")
        self.max_words = max_words
        self.overlap_words = overlap_words

    def chunk(self, document: SourceDocument) -> IngestionResult:
        issues = self._validate(document)
        if document.pages:
            return self._chunk_pages(document, issues)
        return self._chunk_flat_body(document, issues)

    def _chunk_pages(
        self, document: SourceDocument, issues: list[IngestionIssue]
    ) -> IngestionResult:
        chunks: list[Chunk] = []
        global_index = 0
        for page_number, page_text in document.pages:
            normalized = re.sub(r"[ \t]+", " ", page_text).strip()
            normalized = re.sub(r"\n{3,}", "\n\n", normalized)
            words = normalized.split()
            if not words:
                continue
            step = self.max_words - self.overlap_words
            char_cursor = 0
            for start in range(0, len(words), step):
                window = words[start : start + self.max_words]
                text = " ".join(window)
                if not text:
                    continue
                char_start = normalized.find(window[0], char_cursor)
                if char_start < 0:
                    char_start = char_cursor
                char_end = char_start + len(text)
                char_cursor = char_start + 1
                chunks.append(
                    self._make_chunk(
                        document,
                        index=global_index,
                        text=text,
                        page_start=page_number,
                        page_end=page_number,
                        char_start=char_start,
                        char_end=char_end,
                    )
                )
                global_index += 1
                if start + self.max_words >= len(words):
                    break
        return IngestionResult(chunks=tuple(chunks), issues=tuple(issues))

    def _chunk_flat_body(
        self, document: SourceDocument, issues: list[IngestionIssue]
    ) -> IngestionResult:
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
            chunks.append(
                self._make_chunk(
                    document,
                    index=index,
                    text=text,
                    page_start=None,
                    page_end=None,
                    char_start=None,
                    char_end=None,
                )
            )
            if start + self.max_words >= len(words):
                break
        return IngestionResult(chunks=tuple(chunks), issues=tuple(issues))

    @staticmethod
    def _make_chunk(
        document: SourceDocument,
        *,
        index: int,
        text: str,
        page_start: int | None,
        page_end: int | None,
        char_start: int | None,
        char_end: int | None,
    ) -> Chunk:
        digest = hashlib.sha256(
            f"{document.document_id}:{index}:{page_start}:{text}".encode("utf-8")
        ).hexdigest()[:16]
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return Chunk(
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
            content_hash=content_hash,
            ingested_at=datetime.now(UTC),
            page_start=page_start,
            page_end=page_end,
            char_start=char_start,
            char_end=char_end,
        )

    @staticmethod
    def _validate(document: SourceDocument) -> list[IngestionIssue]:
        issues: list[IngestionIssue] = []
        if not document.owner:
            issues.append(IngestionIssue("missing_owner", "Document owner is required.", document.document_id))
        if not document.uri:
            issues.append(IngestionIssue("missing_lineage", "Source URI is required.", document.document_id))
        content_len = len(document.body.strip())
        if document.pages:
            content_len = sum(len(t.strip()) for _, t in document.pages)
        if content_len < 40:
            issues.append(IngestionIssue("low_content", "Document body is too short.", document.document_id))
        if "effective_date" not in document.metadata and "source" not in document.metadata:
            issues.append(
                IngestionIssue(
                    "missing_freshness_metadata",
                    "Document should include effective_date metadata.",
                    document.document_id,
                )
            )
        return issues
