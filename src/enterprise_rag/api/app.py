"""Optional FastAPI adapter for the RAG pipeline.

The core platform is dependency-light and testable without FastAPI. Install project
dependencies and run `uvicorn enterprise_rag.api.app:app --reload` to expose this adapter.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment,misc]
    CORSMiddleware = None  # type: ignore[assignment,misc]
    BaseModel = object  # type: ignore[assignment,misc]
    Field = lambda *args, **kwargs: None  # type: ignore[assignment,misc]

from enterprise_rag.core.entity_extract import extract_entities
from enterprise_rag.core.graph_expander import InMemoryGraphExpander
from enterprise_rag.core.ingestion import DocumentChunker
from enterprise_rag.core.models import Classification, Principal, RetrievalMode, RetrievalQuery, SourceDocument
from enterprise_rag.core.pipeline import RagPipeline
from enterprise_rag.core.reranker import ScoreBoostReranker
from enterprise_rag.core.retrieval import InMemoryHybridRetriever
from enterprise_rag.integrations.aegis_bridge import authorize_high_risk_answer, authorize_ingest
from enterprise_rag.ops.langfuse_export import export_recorder
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
    case_id: str | None = None


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
    case_id: str | None = None


def _build_retriever() -> InMemoryHybridRetriever | Any:
    if os.getenv("QDRANT_BACKEND", "").strip().lower() in {"1", "true", "yes", "on"}:
        from enterprise_rag.adapters.qdrant_retriever import QdrantHybridRetriever, qdrant_available

        if qdrant_available():
            return QdrantHybridRetriever()
    return InMemoryHybridRetriever(())


class AppState:
    def __init__(self) -> None:
        self.recorder = EventRecorder()
        self.retriever = _build_retriever()
        self._all_chunks: list = []
        self._seed_demo_corpus()
        self.graph_expander = InMemoryGraphExpander(tuple(self._all_chunks))
        self.pipeline = RagPipeline(
            self.retriever,
            reranker=ScoreBoostReranker(),
            graph_expander=self.graph_expander,
            recorder=self.recorder,
        )

    def _tag_chunks(self, chunks: tuple) -> tuple:
        tagged = []
        for chunk in chunks:
            entities = extract_entities(chunk.text)
            metadata = dict(chunk.metadata)
            metadata["entities"] = ",".join(entities)
            tagged.append(
                chunk.__class__(
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
            )
        return tuple(tagged)

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
        chunks = self._tag_chunks(chunks)
        self.retriever.upsert(chunks)
        self._all_chunks.extend(chunks)


def _gateway_payload(decision: Any) -> dict[str, Any]:
    return {
        "decision": decision.decision,
        "allowed": decision.allowed,
        "requires_approval": decision.requires_approval,
        "case_id": decision.case_id,
        "reason": decision.reason,
    }


if FastAPI is not None:
    app = FastAPI(title="Enterprise RAG Platform", version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    state = AppState()

    @app.get("/health")
    def health() -> dict[str, str]:
        backend = "qdrant" if os.getenv("QDRANT_BACKEND", "").strip().lower() in {"1", "true", "yes", "on"} else "memory"
        return {"status": "ok", "service": "enterprise-rag-platform", "retriever_backend": backend}

    @app.get("/v1/strategies")
    def strategies() -> dict[str, list[str]]:
        return {
            "retrieval_modes": [mode.value for mode in RetrievalMode],
            "rerankers": ["score_boost", "none"],
            "backends": ["memory", "qdrant"],
            "graph_expansion": ["in_memory"],
            "notes": [
                "Reference implementation uses in-memory hybrid lexical + semantic proxy scoring.",
                "Set QDRANT_BACKEND=true with qdrant-client installed for vector adapter.",
                "Set rerank=false on /v1/answer to skip ScoreBoostReranker.",
            ],
        }

    @app.post("/v1/retrieve")
    def retrieve(request: QueryRequest) -> dict[str, Any]:
        principal = Principal(
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            groups=frozenset(request.groups),
            clearance=request.clearance,
        )
        hits = state.retriever.search(
            RetrievalQuery(
                query=request.query,
                tenant_id=request.tenant_id,
                principal=principal,
                filters=request.filters,
                mode=request.mode,
                top_k=request.top_k,
            )
        )
        if request.rerank:
            hits = ScoreBoostReranker().rerank(request.query, hits, request.top_k)
        return {
            "hits": [
                {
                    "score": hit.score,
                    "reasons": hit.reasons,
                    "document_id": hit.chunk.document_id,
                    "text": hit.chunk.text,
                    "title": hit.chunk.source_title,
                    "uri": hit.chunk.source_uri,
                    "owner": hit.chunk.owner,
                }
                for hit in hits
            ]
        }

    @app.post("/v1/ingest")
    def ingest(request: IngestRequest) -> dict[str, Any]:
        case_id = request.case_id or f"ingest-{request.document_id}-{uuid.uuid4().hex[:8]}"
        gateway = authorize_ingest(case_id=case_id, document_id=request.document_id)
        if gateway.blocked:
            raise HTTPException(status_code=403, detail=gateway.reason)
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
        chunks = state._tag_chunks(chunks)
        added = state.retriever.upsert(chunks)
        state._all_chunks.extend(chunks)
        state.graph_expander = InMemoryGraphExpander(tuple(state._all_chunks))
        return {
            "document_id": request.document_id,
            "chunks_added": added,
            "gateway": _gateway_payload(gateway),
        }

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
            graph_expander=state.graph_expander,
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
        case_id = request.case_id or f"rag-{request.tenant_id}-{uuid.uuid4().hex[:8]}"
        gateway = authorize_high_risk_answer(case_id=case_id, risk_flags=result.risk_flags)
        langfuse_status = export_recorder(
            state.recorder,
            metadata={"tenant_id": request.tenant_id, "case_id": case_id},
            eval_scores={
                "grounded": result.grounded,
                "citation_count": len(result.citations),
                "human_approval_required": "human_approval_required" in result.risk_flags,
            },
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
            "gateway": _gateway_payload(gateway),
            "langfuse_export": langfuse_status,
        }
else:
    app = None
