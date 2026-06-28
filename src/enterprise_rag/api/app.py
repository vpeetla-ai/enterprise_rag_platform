"""Optional FastAPI adapter for the RAG pipeline.

The core platform is dependency-light and testable without FastAPI. Install project
dependencies and run `uvicorn enterprise_rag.api.app:app --reload` to expose this adapter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

try:
    from fastapi import FastAPI
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment]
    BaseModel = object  # type: ignore[assignment,misc]
    Field = lambda *args, **kwargs: None  # type: ignore[assignment,misc]

from enterprise_rag.core.ingestion import DocumentChunker
from enterprise_rag.core.models import Classification, Principal, RetrievalMode, RetrievalQuery, SourceDocument
from enterprise_rag.core.pipeline import RagPipeline
from enterprise_rag.core.reranker import ScoreBoostReranker
from enterprise_rag.core.retrieval import InMemoryHybridRetriever
from enterprise_rag.ops.telemetry import EventRecorder


class QueryRequest(BaseModel):  # type: ignore[misc]
    query: str
    tenant_id: str
    user_id: str
    groups: list[str]
    clearance: Classification = Classification.INTERNAL
    filters: dict[str, str] = Field(default_factory=dict)
    mode: RetrievalMode = RetrievalMode.HYBRID
    top_k: int = 5
    rerank: bool = True


class IngestRequest(BaseModel):  # type: ignore[misc]
    tenant_id: str
    document_id: str
    title: str
    body: str
    uri: str
    owner: str
    classification: Classification = Classification.INTERNAL
    groups: list[str] = Field(default_factory=lambda: ["engineering"])
    metadata: dict[str, str] = Field(default_factory=dict)


class AppState:
    def __init__(self) -> None:
        self.recorder = EventRecorder()
        self.retriever = InMemoryHybridRetriever(())
        self._seed_demo_corpus()
        self.pipeline = RagPipeline(
            self.retriever,
            reranker=ScoreBoostReranker(),
            recorder=self.recorder,
        )

    def _seed_demo_corpus(self) -> None:
        document = SourceDocument(
            document_id="policy-001",
            tenant_id="acme",
            title="Enterprise RAG Production Policy",
            body=(
                "Production RAG requires hybrid retrieval, access-aware filtering, grounded citations, "
                "evaluation, observability, and human approval for high-risk actions. Retrieval strategy "
                "is the architecture decision; vector database selection is an implementation decision."
            ),
            uri="https://example.internal/policies/rag-production",
            owner="ai-platform",
            classification=Classification.INTERNAL,
            allowed_groups=frozenset({"engineering", "ai-platform"}),
            metadata={"effective_date": "2026-01-01", "domain": "ai"},
            updated_at=datetime.now(UTC),
        )
        chunks = DocumentChunker(max_words=80, overlap_words=10).chunk(document).chunks
        self.retriever.upsert(chunks)


if FastAPI is not None:
    app = FastAPI(title="Enterprise RAG Platform", version="0.2.0")
    state = AppState()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "enterprise-rag-platform"}

    @app.get("/v1/strategies")
    def strategies() -> dict[str, list[str]]:
        return {
            "retrieval_modes": [mode.value for mode in RetrievalMode],
            "rerankers": ["score_boost", "none"],
            "notes": [
                "Reference implementation uses in-memory hybrid lexical + semantic proxy scoring.",
                "Set rerank=false on /v1/answer to skip ScoreBoostReranker.",
            ],
        }

    @app.post("/v1/ingest")
    def ingest(request: IngestRequest) -> dict[str, Any]:
        document = SourceDocument(
            document_id=request.document_id,
            tenant_id=request.tenant_id,
            title=request.title,
            body=request.body,
            uri=request.uri,
            owner=request.owner,
            classification=request.classification,
            allowed_groups=frozenset(request.groups),
            metadata=request.metadata,
            updated_at=datetime.now(UTC),
        )
        chunks = DocumentChunker(max_words=80, overlap_words=10).chunk(document).chunks
        added = state.retriever.upsert(chunks)
        return {"document_id": request.document_id, "chunks_added": added}

    @app.post("/v1/answer")
    def answer(request: QueryRequest) -> dict[str, Any]:
        state.recorder.events.clear()
        principal = Principal(
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            groups=frozenset(request.groups),
            clearance=request.clearance,
        )
        pipeline = RagPipeline(
            state.retriever,
            reranker=ScoreBoostReranker() if request.rerank else None,
            recorder=state.recorder,
        )
        result = pipeline.answer(
            RetrievalQuery(
                query=request.query,
                tenant_id=request.tenant_id,
                principal=principal,
                filters=request.filters,
                mode=request.mode,
                top_k=request.top_k,
            )
        )
        return {
            "answer": result.answer,
            "grounded": result.grounded,
            "risk_flags": result.risk_flags,
            "citations": [
                {
                    "id": citation.citation_id,
                    "title": citation.title,
                    "uri": citation.uri,
                    "owner": citation.owner,
                    "updated_at": citation.updated_at.isoformat(),
                }
                for citation in result.citations
            ],
            "trace": state.recorder.events,
        }
else:
    app = None
