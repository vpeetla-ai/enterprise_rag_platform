"""Optional FastAPI adapter for the RAG pipeline.

The core platform is dependency-light and testable without FastAPI. Install project
dependencies and run `uvicorn enterprise_rag.api.app:app --reload` to expose this adapter.
"""

from __future__ import annotations

import os
import secrets
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Annotated, Any

try:
    from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover
    Depends = None  # type: ignore[assignment]
    FastAPI = None  # type: ignore[assignment]
    File = None  # type: ignore[assignment]
    Form = None  # type: ignore[assignment]
    Header = None  # type: ignore[assignment]
    UploadFile = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment,misc]
    CORSMiddleware = None  # type: ignore[assignment,misc]
    BaseModel = object  # type: ignore[assignment,misc]
    Field = lambda *args, **kwargs: None  # type: ignore[assignment,misc]

from enterprise_rag.api.principal_auth import production_strict, resolve_principal
from enterprise_rag.api.rate_limit import get_limiter
from enterprise_rag.core.entity_extract import extract_entities
from enterprise_rag.core.generator import build_generator
from enterprise_rag.core.graph_expander import InMemoryGraphExpander
from enterprise_rag.core.ingestion import DocumentChunker
from enterprise_rag.core.models import Classification, RetrievalMode, RetrievalQuery, SourceDocument
from enterprise_rag.core.pdf_ingest import PdfExtractError, extract_pdf_pages
from enterprise_rag.core.pipeline import RagPipeline
from enterprise_rag.core.reranker import build_reranker
from enterprise_rag.core.retrieval import InMemoryHybridRetriever, retrieval_profile
from enterprise_rag.integrations.aegis_bridge import authorize_high_risk_answer, authorize_ingest
from enterprise_rag.ops.langfuse_export import export_recorder
from enterprise_rag.ops.telemetry import EventRecorder, LatencyTracker, append_audit_event
from enterprise_rag.vpeetla_observability.middleware import TraceRequestMiddleware


class QueryRequest(BaseModel):  # type: ignore[misc]
    """tenant_id/user_id/groups/clearance are client-asserted in Demo mode.
    Under PRODUCTION_STRICT they are ignored; JWT claims win (ADR-0006/0009)."""

    query: str
    tenant_id: str
    user_id: str
    groups: list[str]
    clearance: Classification = Classification.INTERNAL
    filters: dict[str, str] = Field(default_factory=dict)
    mode: RetrievalMode = RetrievalMode.HYBRID
    top_k: int = 5
    rerank: bool = True
    agentic: bool = True
    case_id: str | None = None


class IngestRequest(BaseModel):  # type: ignore[misc]
    """Flat-body ingest (non-page). Prefer /v1/ingest/pdf for page citations."""

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
    pages: list[dict[str, Any]] | None = None


def _qdrant_backend() -> bool:
    return os.getenv("QDRANT_BACKEND", "").strip().lower() in {"1", "true", "yes", "on"}


def _seed_demo_corpus_enabled() -> bool:
    raw = os.getenv("RAG_SEED_DEMO_CORPUS", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    # Default: seed memory Demo only; never treat reseed as corpus-of-record on Qdrant
    return not _qdrant_backend()


def _build_retriever() -> InMemoryHybridRetriever | Any:
    if _qdrant_backend():
        from enterprise_rag.adapters.qdrant_retriever import QdrantHybridRetriever, qdrant_available

        if qdrant_available():
            return QdrantHybridRetriever()
    return InMemoryHybridRetriever(())


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if production_strict() and raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    if production_strict() and not raw:
        return [
            "https://enterprise-rag-platform-eta.vercel.app",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    return ["*"]


class AppState:
    def __init__(self) -> None:
        self.latency = LatencyTracker()
        self.retriever = _build_retriever()
        self._all_chunks: list = []
        self.query_count = 0
        self.ingest_count = 0
        self.answer_count = 0
        self.declined_count = 0
        self.reranker = build_reranker()
        self.generator = build_generator()
        warmup = getattr(self.reranker, "warmup", None)
        if callable(warmup) and os.getenv("RAG_RERANKER", "").strip().lower() == "cross_encoder":
            if os.getenv("RAG_RERANKER_WARMUP", "true").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                try:
                    warmup()
                except Exception:  # noqa: BLE001 — boot should not die if CE weights missing
                    pass
        if _seed_demo_corpus_enabled():
            self._seed_demo_corpus()
        self.graph_expander = InMemoryGraphExpander(tuple(self._all_chunks))

    def _tag_chunks(self, chunks: tuple) -> tuple:
        tagged = []
        for chunk in chunks:
            entities = extract_entities(chunk.text)
            metadata = dict(chunk.metadata)
            metadata["entities"] = ",".join(entities)
            tagged.append(replace(chunk, metadata=metadata))
        return tuple(tagged)

    def _drop_local_document(self, *, document_id: str, tenant_id: str) -> None:
        self._all_chunks = [
            c
            for c in self._all_chunks
            if not (c.document_id == document_id and c.tenant_id == tenant_id)
        ]

    def _seed_demo_corpus(self) -> None:
        documents = [
            SourceDocument(
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
            ),
            SourceDocument(
                document_id="zephyr-policy-2026",
                tenant_id="acme",
                title="Zephyr Cloud Security Policy",
                body=(
                    "Zephyr Corporation requires all production deployments to pass AegisAI gateway approval "
                    "before email or Slack notifications. The mandatory rotation period for API keys is 90 days. "
                    "Engineering teams must enable hybrid retrieval with citation grounding for customer-facing "
                    "answers. Incident response playbooks require human approval for restricted documents."
                ),
                uri="demo://fixtures/zephyr-policy.txt",
                owner="demo-user",
                classification=Classification.INTERNAL,
                allowed_groups=frozenset({"engineering", "ai-platform"}),
                metadata={"source": "demo-fixture", "domain": "security"},
                updated_at=datetime.now(UTC),
                pages=(
                    (
                        1,
                        "Zephyr Corporation requires all production deployments to pass AegisAI gateway approval "
                        "before email or Slack notifications.",
                    ),
                    (
                        2,
                        "The mandatory rotation period for API keys is 90 days. Engineering teams must enable "
                        "hybrid retrieval with citation grounding for customer-facing answers.",
                    ),
                    (
                        3,
                        "Incident response playbooks require human approval for restricted documents.",
                    ),
                ),
            ),
        ]
        for document in documents:
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


def _require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    expected = os.getenv("RAG_API_KEY")
    if production_strict() and not expected:
        raise HTTPException(
            status_code=503,
            detail="PRODUCTION_STRICT requires RAG_API_KEY (prod auth baseline)",
        )
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def _require_ops_auth(x_api_key: Annotated[str | None, Header()] = None) -> None:
    """Protect metrics — require API key whenever configured, or always under Strict."""
    expected = os.getenv("RAG_API_KEY", "").strip()
    if production_strict() or expected:
        _require_api_key(x_api_key)
        return


def _enforce_rate_limit(route: str, identity: str) -> None:
    if os.getenv("RAG_RATE_LIMIT_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return
    key = f"{route}:{identity or 'anon'}"
    if not get_limiter().allow(key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded — retry shortly")


def _pages_from_request(pages: list[dict[str, Any]] | None) -> tuple[tuple[int, str], ...]:
    if not pages:
        return ()
    out: list[tuple[int, str]] = []
    for row in pages:
        try:
            num = int(row.get("page_number") or row.get("page") or 0)
        except (TypeError, ValueError):
            continue
        text = str(row.get("text") or "")
        if num > 0 and text.strip():
            out.append((num, text))
    return tuple(out)


if FastAPI is not None:
    app = FastAPI(title="Enterprise RAG Platform", version="0.4.0")
    app.add_middleware(
        TraceRequestMiddleware,
        service_name="enterprise-rag-platform",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    state = AppState()

    @app.get("/health")
    def health() -> dict[str, Any]:
        backend = "qdrant" if _qdrant_backend() else "memory"
        strict = production_strict()
        profile = retrieval_profile()
        generator = os.getenv("GENERATOR", "extractive")
        claim_aligned = (
            profile.get("embedding_provider") not in {None, "hash"}
            and profile.get("reranker") == "cross_encoder"
            and generator == "llm"
            and backend == "qdrant"
        )
        return {
            "status": "ok",
            "service": "enterprise-rag-platform",
            "retriever_backend": backend,
            "corpus_of_record": backend,
            "demo_seed_enabled": _seed_demo_corpus_enabled(),
            "production_strict": strict,
            "principal_source": "jwt" if strict else "request_body",
            "review_mode": "strict" if strict else "demo",
            "retrieval": profile,
            "generator": generator,
            "page_citations": True,
            "product_bar": {
                "pdf": "text_layer_page_citations",
                "ocr": "optional_flag_only",
                "claim_aligned": bool(claim_aligned),
            },
            "hitl_hard_gate": strict
            or os.getenv("HITL_HARD_GATE", "").strip().lower() in {"1", "true", "yes", "on"},
        }

    @app.get("/v1/observability/status")
    def observability_status() -> dict[str, Any]:
        """Compose-plane honesty — Demo vs Strict, retrieval SoT, optional Langfuse export."""
        strict = production_strict()
        backend = "qdrant" if _qdrant_backend() else "memory"
        profile = retrieval_profile()
        langfuse_keys = bool(
            (os.getenv("LANGFUSE_PUBLIC_KEY") or "").strip()
            and (os.getenv("LANGFUSE_SECRET_KEY") or "").strip()
        )
        return {
            "source_of_truth": (
                f"Retriever corpus ({backend}) + access-before-ranking principal filter; "
                "not Langfuse"
            ),
            "exporters": [
                {
                    "name": "OpsMetrics",
                    "state": "live",
                    "detail": "GET /v1/ops/metrics (API-key gated when PRODUCTION_STRICT or OPS key set)",
                },
                {
                    "name": "Langfuse",
                    "state": "configured" if langfuse_keys else "unconfigured",
                    "detail": "Optional answer-path export adapter — not the authorization ledger",
                },
            ],
            "planes": {
                "review_mode": "strict" if strict else "demo",
                "production_strict": strict,
                "principal_source": "jwt" if strict else "request_body",
                "retriever_backend": backend,
                "corpus_of_record": backend,
                "retrieval": profile,
                "generator": os.getenv("GENERATOR", "extractive"),
                "hitl_hard_gate": strict
                or os.getenv("HITL_HARD_GATE", "").strip().lower()
                in {"1", "true", "yes", "on"},
                "langfuse_configured": langfuse_keys,
                "access_before_ranking": True,
            },
            "recommendation": (
                "Demo uses request-body principal; Strict requires JWT. "
                "Decline-to-answer and access-before-ranking stay product features, not bugs."
            ),
        }

    @app.get("/v1/ops/metrics", dependencies=[Depends(_require_ops_auth)])
    def ops_metrics() -> dict[str, Any]:
        total = state.query_count + state.answer_count
        finished = state.answer_count or 1
        success = (
            round(100.0 * (state.answer_count - state.declined_count) / finished, 1)
            if state.answer_count
            else 100.0
        )
        return {
            "service": "enterprise-rag-platform",
            "collected_at": datetime.now(UTC).isoformat(),
            "total_runs": total,
            "success_rate_pct": success,
            "p95_latency_ms": state.latency.p95(),
            "active_entities": len(state._all_chunks),
            "slo": {"target_uptime_pct": 99.5, "success_target_pct": 95.0},
            "extra": {
                "ingest_count": state.ingest_count,
                "answer_count": state.answer_count,
                "declined_count": state.declined_count,
                "retriever_backend": "qdrant" if _qdrant_backend() else "memory",
                "corpus_of_record": "qdrant" if _qdrant_backend() else "memory",
            },
        }

    @app.get("/v1/strategies")
    def strategies() -> dict[str, Any]:
        return {
            "retrieval_modes": [mode.value for mode in RetrievalMode],
            "rerankers": ["score_boost", "cross_encoder", "none"],
            "backends": ["memory", "qdrant"],
            "fusion": "rrf",
            "embedding_providers": ["hash", "local", "openai", "gateway"],
            "generators": ["extractive", "llm"],
            "graph_expansion": ["in_memory"],
            "decline_threshold": os.getenv("RAG_DECLINE_THRESHOLD", "0.001"),
            "notes": [
                "Hybrid uses BM25 (k1/b) + dense embeddings fused with RRF.",
                "PDF ingest: POST /v1/ingest/pdf for page-level citations (ADR-0007).",
                "Set RAG_RERANKER=cross_encoder with image extras [rerank].",
                "Set GENERATOR=llm with GROQ_API_KEY or LLM_GATEWAY_URL.",
            ],
        }

    def _do_ingest(
        *,
        tenant_id: str,
        document_id: str,
        title: str,
        body: str,
        uri: str,
        owner: str,
        classification: Classification,
        groups: list[str],
        metadata: dict[str, str],
        case_id: str | None,
        pages: tuple[tuple[int, str], ...],
        authorization: str | None,
        body_user_id: str = "ingest",
    ) -> dict[str, Any]:
        state.ingest_count += 1
        principal = resolve_principal(
            authorization=authorization,
            body_user_id=body_user_id,
            body_tenant_id=tenant_id,
            body_groups=groups,
            body_clearance=classification,
        )
        _enforce_rate_limit("ingest", principal.user_id)
        effective_tenant = principal.tenant_id
        effective_groups = list(principal.groups) if production_strict() else groups
        cid = case_id or f"ingest-{document_id}-{uuid.uuid4().hex[:8]}"
        gateway = authorize_ingest(case_id=cid, document_id=document_id)
        if gateway.blocked:
            raise HTTPException(status_code=403, detail=gateway.reason)
        document = SourceDocument(
            document_id=document_id,
            tenant_id=effective_tenant,
            title=title,
            body=body,
            uri=uri,
            owner=owner,
            classification=classification,
            allowed_groups=frozenset(effective_groups),
            metadata=metadata,
            updated_at=datetime.now(UTC),
            pages=pages,
        )
        result = DocumentChunker(max_words=80, overlap_words=10).chunk(document)
        if result.blocking_issues:
            raise HTTPException(
                status_code=422,
                detail=[{"code": issue.code, "message": issue.message} for issue in result.blocking_issues],
            )
        chunks = state._tag_chunks(result.chunks)
        state._drop_local_document(document_id=document_id, tenant_id=effective_tenant)
        added = state.retriever.upsert(chunks)
        state._all_chunks.extend(chunks)
        state.graph_expander = InMemoryGraphExpander(tuple(state._all_chunks))
        append_audit_event(
            {
                "event": "ingest",
                "document_id": document_id,
                "tenant_id": effective_tenant,
                "principal": principal.user_id,
                "chunks_added": added,
                "pages": bool(pages),
                "ts": datetime.now(UTC).isoformat(),
            }
        )
        return {
            "document_id": document_id,
            "chunks_added": added,
            "tenant_id": effective_tenant,
            "principal_source": "jwt" if production_strict() else "request_body",
            "gateway": _gateway_payload(gateway),
            "warnings": [{"code": issue.code, "message": issue.message} for issue in result.issues],
            "lineage": [
                {
                    "chunk_id": chunk.chunk_id,
                    "content_hash": chunk.content_hash,
                    "ingested_at": chunk.ingested_at.isoformat(),
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                }
                for chunk in chunks
            ],
        }

    @app.post("/v1/ingest", dependencies=[Depends(_require_api_key)])
    def ingest(
        request: IngestRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        pages = _pages_from_request(request.pages)
        return _do_ingest(
            tenant_id=request.tenant_id,
            document_id=request.document_id,
            title=request.title,
            body=request.body,
            uri=request.uri,
            owner=request.owner,
            classification=request.classification,
            groups=request.groups,
            metadata=request.metadata,
            case_id=request.case_id,
            pages=pages,
            authorization=authorization,
        )

    @app.post("/v1/ingest/pdf", dependencies=[Depends(_require_api_key)])
    async def ingest_pdf(
        file: UploadFile = File(...),
        document_id: str = Form(...),
        title: str = Form(...),
        tenant_id: str = Form("acme"),
        owner: str = Form("demo-user"),
        uri: str = Form(""),
        classification: str = Form("internal"),
        groups: str = Form("engineering,ai-platform"),
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        data = await file.read()
        try:
            extracted = extract_pdf_pages(data)
        except PdfExtractError as exc:
            raise HTTPException(status_code=422, detail=[{"code": exc.code, "message": exc.message}]) from exc
        group_list = [g.strip() for g in groups.split(",") if g.strip()]
        try:
            cls = Classification(classification.strip().lower())
        except ValueError:
            cls = Classification.INTERNAL
        body = "\n\n".join(t for _, t in extracted.pages)
        result = _do_ingest(
            tenant_id=tenant_id,
            document_id=document_id,
            title=title,
            body=body,
            uri=uri or f"upload://{file.filename or document_id}",
            owner=owner,
            classification=cls,
            groups=group_list,
            metadata={
                "source": "pdf-upload",
                "filename": file.filename or "",
                "page_count": str(extracted.page_count),
            },
            case_id=None,
            pages=extracted.pages,
            authorization=authorization,
        )
        result["pdf"] = {
            "page_count": extracted.page_count,
            "char_count": extracted.char_count,
            "warnings": list(extracted.warnings),
        }
        return result

    @app.delete("/v1/documents/{document_id}", dependencies=[Depends(_require_api_key)])
    def delete_document(
        document_id: str,
        tenant_id: str = "acme",
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        principal = resolve_principal(
            authorization=authorization,
            body_user_id="delete",
            body_tenant_id=tenant_id,
            body_groups=["engineering"],
            body_clearance=Classification.INTERNAL,
        )
        _enforce_rate_limit("delete", principal.user_id)
        effective_tenant = principal.tenant_id
        removed = 0
        delete_fn = getattr(state.retriever, "delete_document", None)
        if callable(delete_fn):
            removed = int(delete_fn(document_id=document_id, tenant_id=effective_tenant))
        state._drop_local_document(document_id=document_id, tenant_id=effective_tenant)
        state.graph_expander = InMemoryGraphExpander(tuple(state._all_chunks))
        append_audit_event(
            {
                "event": "delete_document",
                "document_id": document_id,
                "tenant_id": effective_tenant,
                "principal": principal.user_id,
                "chunks_removed": removed,
                "ts": datetime.now(UTC).isoformat(),
            }
        )
        return {
            "document_id": document_id,
            "tenant_id": effective_tenant,
            "chunks_removed": removed,
            "principal_source": "jwt" if production_strict() else "request_body",
        }

    @app.post("/v1/retrieve", dependencies=[Depends(_require_api_key)])
    def retrieve(
        request: QueryRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        state.query_count += 1
        principal = resolve_principal(
            authorization=authorization,
            body_user_id=request.user_id,
            body_tenant_id=request.tenant_id,
            body_groups=request.groups,
            body_clearance=request.clearance,
        )
        _enforce_rate_limit("retrieve", principal.user_id)
        hits = state.retriever.search(
            RetrievalQuery(
                query=request.query,
                tenant_id=principal.tenant_id,
                principal=principal,
                filters=request.filters,
                mode=request.mode,
                top_k=request.top_k,
            )
        )
        if request.rerank:
            hits = state.reranker.rerank(request.query, hits, request.top_k)
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
                    "page_start": hit.chunk.page_start,
                    "page_end": hit.chunk.page_end,
                }
                for hit in hits
            ],
            "principal_source": "jwt" if production_strict() else "request_body",
        }

    @app.post("/v1/answer", dependencies=[Depends(_require_api_key)])
    def answer(
        request: QueryRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        state.answer_count += 1
        recorder = EventRecorder()
        principal = resolve_principal(
            authorization=authorization,
            body_user_id=request.user_id,
            body_tenant_id=request.tenant_id,
            body_groups=request.groups,
            body_clearance=request.clearance,
        )
        _enforce_rate_limit("answer", principal.user_id)
        pipeline = RagPipeline(
            state.retriever,
            generator=state.generator,
            reranker=state.reranker if request.rerank else None,
            graph_expander=state.graph_expander if request.agentic else None,
            recorder=recorder,
        )
        result = pipeline.answer(
            RetrievalQuery(
                query=request.query,
                tenant_id=principal.tenant_id,
                principal=principal,
                filters=request.filters,
                mode=request.mode,
                top_k=request.top_k,
            )
        )
        case_id = request.case_id or f"rag-{principal.tenant_id}-{uuid.uuid4().hex[:8]}"
        gateway = authorize_high_risk_answer(case_id=case_id, risk_flags=result.risk_flags)
        hard_gate = production_strict() or os.getenv("HITL_HARD_GATE", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        pending_hitl = hard_gate and (
            gateway.blocked or gateway.requires_approval or not gateway.allowed
        )
        if "declined_low_confidence" in result.risk_flags or "declined_unfaithful" in result.risk_flags:
            state.declined_count += 1
        latency_ms = (time.perf_counter() - started) * 1000
        state.latency.observe(latency_ms)
        append_audit_event(
            {
                "event": "answer",
                "tenant_id": principal.tenant_id,
                "principal": principal.user_id,
                "grounded": result.grounded,
                "declined": "declined_low_confidence" in result.risk_flags,
                "hitl_pending": pending_hitl,
                "citation_ids": [c.citation_id for c in result.citations],
                "pages": [c.page for c in result.citations],
                "latency_ms": round(latency_ms, 2),
                "ts": datetime.now(UTC).isoformat(),
            }
        )
        langfuse_status = export_recorder(
            recorder,
            metadata={"tenant_id": principal.tenant_id, "case_id": case_id},
            eval_scores={
                "grounded": result.grounded,
                "citation_count": len(result.citations),
                "human_approval_required": "human_approval_required" in result.risk_flags,
            },
        )
        if pending_hitl:
            return {
                "answer": "",
                "grounded": False,
                "declined": False,
                "pending_approval": True,
                "risk_flags": tuple(
                    dict.fromkeys((*result.risk_flags, "human_approval_required", "hitl_pending"))
                ),
                "principal_source": "jwt" if production_strict() else "request_body",
                "citations": [],
                "trace": recorder.events,
                "gateway": _gateway_payload(gateway),
                "langfuse_export": langfuse_status,
                "latency_ms": round(latency_ms, 2),
            }
        return {
            "answer": result.answer,
            "grounded": result.grounded,
            "declined": "declined_low_confidence" in result.risk_flags
            or "declined_unfaithful" in result.risk_flags,
            "pending_approval": False,
            "risk_flags": result.risk_flags,
            "principal_source": "jwt" if production_strict() else "request_body",
            "citations": [
                {
                    "id": citation.citation_id,
                    "document_id": citation.document_id,
                    "title": citation.title,
                    "uri": citation.uri,
                    "owner": citation.owner,
                    "updated_at": citation.updated_at.isoformat(),
                    "page": citation.page,
                    "chunk_id": citation.chunk_id,
                    "snippet": citation.snippet,
                }
                for citation in result.citations
            ],
            "trace": recorder.events,
            "gateway": _gateway_payload(gateway),
            "langfuse_export": langfuse_status,
            "latency_ms": round(latency_ms, 2),
        }
else:
    app = None
