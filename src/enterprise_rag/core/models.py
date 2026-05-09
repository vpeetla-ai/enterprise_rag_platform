"""Shared domain models for the enterprise RAG platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class Classification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class RetrievalMode(str, Enum):
    HYBRID = "hybrid"
    KEYWORD = "keyword"
    SEMANTIC = "semantic"


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    groups: frozenset[str]
    clearance: Classification = Classification.INTERNAL


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    tenant_id: str
    title: str
    body: str
    uri: str
    owner: str
    classification: Classification
    allowed_groups: frozenset[str]
    metadata: dict[str, str] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    tenant_id: str
    text: str
    source_title: str
    source_uri: str
    owner: str
    classification: Classification
    allowed_groups: frozenset[str]
    metadata: dict[str, str]
    updated_at: datetime


@dataclass(frozen=True)
class RetrievalQuery:
    query: str
    tenant_id: str
    principal: Principal
    mode: RetrievalMode = RetrievalMode.HYBRID
    filters: dict[str, str] = field(default_factory=dict)
    top_k: int = 6


@dataclass(frozen=True)
class RetrievalHit:
    chunk: Chunk
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Citation:
    citation_id: str
    document_id: str
    title: str
    uri: str
    owner: str
    updated_at: datetime


@dataclass(frozen=True)
class AssembledContext:
    query: str
    context: str
    citations: tuple[Citation, ...]
    token_estimate: int
    retrieval_trace: dict[str, Any]


@dataclass(frozen=True)
class Answer:
    answer: str
    citations: tuple[Citation, ...]
    grounded: bool
    risk_flags: tuple[str, ...] = ()
