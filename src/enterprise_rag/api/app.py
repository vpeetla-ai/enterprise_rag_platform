"""Optional FastAPI adapter for the RAG pipeline.

The core platform is dependency-light and testable without FastAPI. Install project
dependencies and run `uvicorn enterprise_rag.api.app:app --reload` to expose this adapter.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

try:
    from fastapi import FastAPI
    from pydantic import BaseModel
except ImportError:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment]
    BaseModel = object  # type: ignore[assignment,misc]

from enterprise_rag.core.ingestion import DocumentChunker
from enterprise_rag.core.models import Classification, Principal, RetrievalQuery, SourceDocument
from enterprise_rag.core.pipeline import RagPipeline
from enterprise_rag.core.retrieval import InMemoryHybridRetriever


class QueryRequest(BaseModel):  # type: ignore[misc]
    query: str
    tenant_id: str
    user_id: str
    groups: list[str]
    clearance: Classification = Classification.INTERNAL
    filters: dict[str, str] = {}


def build_demo_pipeline() -> RagPipeline:
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
    return RagPipeline(InMemoryHybridRetriever(chunks))


if FastAPI is not None:
    app = FastAPI(title="Enterprise RAG Platform", version="0.1.0")
    pipeline = build_demo_pipeline()

    @app.post("/v1/answer")
    def answer(request: QueryRequest) -> dict[str, Any]:
        principal = Principal(
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            groups=frozenset(request.groups),
            clearance=request.clearance,
        )
        result = pipeline.answer(
            RetrievalQuery(
                query=request.query,
                tenant_id=request.tenant_id,
                principal=principal,
                filters=request.filters,
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
        }
else:
    app = None
