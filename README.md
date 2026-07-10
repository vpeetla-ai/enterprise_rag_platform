# Enterprise RAG Platform



<!-- vpeetla-tech-stack:start -->
[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square)]() [![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square)]() [![Qdrant](https://img.shields.io/badge/Qdrant-DC382D?style=flat-square)]() [![Langfuse](https://img.shields.io/badge/Langfuse-6366F1?style=flat-square)]() [![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square)]() [![Vercel](https://img.shields.io/badge/Vercel-000000?style=flat-square)]() [![Render](https://img.shields.io/badge/Render-46E3B7?style=flat-square)]()
<!-- vpeetla-tech-stack:end -->
## Agent skills (Cursor + Codex)

Org skills: [vpeetla-ai-skills](https://github.com/vpeetla-ai/vpeetla-ai-skills). This repo includes `.cursor/skills/`, `AGENTS.md`, and `CONTEXT.md`.

```bash
git clone https://github.com/vpeetla-ai/vpeetla-ai-skills.git
./vpeetla-ai-skills/scripts/install.sh --cursor --codex --project .
```

---

[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen)](https://enterprise-rag-platform-eta.vercel.app)

[▶ Live demo](https://enterprise-rag-platform-eta.vercel.app) · [🚀 Deploy guide](docs/LIVE_DEMO.md) · [Architecture hub](docs/ARCHITECTURE.md) · [Ecosystem map](docs/ECOSYSTEM.md)

> **First-run note:** The Render API sleeps after inactivity on the free tier — the first request takes ~50s to wake, and the seeded corpus re-ingests on cold start. If a query returns empty, wait and retry once.

Production RAG is a governed intelligence system, not a vector database wrapper. This project is a reference implementation and architecture package for an enterprise retrieval-augmented generation platform with access-aware retrieval, context engineering, evaluation, guardrails, observability, and operational decision records.

**Portfolio:** [Case study](https://github.com/vpeetla-ai/ai-architecture-portfolio/blob/main/case-studies/enterprise-rag-platform.md) · [Architecture](docs/ARCHITECTURE.md) · [Ecosystem](docs/ECOSYSTEM.md) · [Deploy](docs/LIVE_DEMO.md)

## Architecture Principles

- Retrieval strategy is the primary architecture decision; vector database choice is an implementation detail.
- Authorization happens before ranking, not after generation.
- Every answer must carry citations, ownership, freshness, and traceability.
- Prompts, retrieval logic, embeddings, and evaluations are versioned release artifacts.
- The system is designed for continuous improvement through telemetry, feedback, and regression testing.

## Implementation Status

| Capability | Status | Notes |
| --- | --- | --- |
| Access-before-ranking | **Implemented** | `AccessPolicy` before scoring. Demo: Principal from request body (ADR-0004). **`PRODUCTION_STRICT=true` + `RAG_JWT_SECRET`:** Principal from signed HS256 JWT; body spoof ignored (ADR-0006). |
| Hybrid in-memory retrieval | **Implemented** | BM25-like + semantic proxy + freshness |
| Retriever / Reranker ports | **Implemented** | Swap vector DB or cross-encoder behind protocols |
| Reference reranker | **Implemented** | `CrossEncoderReranker` (sentence-transformers) + `ScoreBoostReranker` fallback |
| Decline-to-answer | **Implemented** | `RAG_DECLINE_THRESHOLD` — `declined_low_confidence` risk flag |
| Pipeline telemetry spans | **Implemented** | `EventRecorder` wired through `RagPipeline` |
| Guardrails + HITL risk flags | **Implemented** | PII redaction, `human_approval_required` |
| HTTP API | **Implemented** | `/health`, `/v1/answer`, `/v1/ingest`, `/v1/strategies` |
| Ingestion data contract + real lineage | **Implemented** | `/v1/ingest` rejects (422) documents with no owner/URI/near-empty content instead of silently indexing them; every chunk carries a real `content_hash` + `ingested_at`, preserved through entity-tagging, graph expansion, and the Qdrant round-trip. See [ADR-0005](docs/adr/0005-ingestion-data-contract-and-lineage.md) |
| Golden eval fixtures (local) | **Implemented** | `tests/fixtures/golden_queries.json` |
| Golden eval registry as a real CI gate | **Implemented** | `tests/test_golden_eval_gate.py` runs the shared `enterprise_rag_golden_v1` suite from [golden-eval-registry](https://github.com/vpeetla-ai/golden-eval-registry) against a real, isolated `RagPipeline` — CI checks out that repo and fails the build on regression, not just fixture validation |
| Vector store adapter | **Implemented** | `QdrantHybridRetriever` behind `QDRANT_BACKEND=true` |
| AegisAI gateway bridge | **Implemented** | `integrations/aegis_bridge.py` for ingest + high-risk answers |
| OpenTelemetry exporters | **Removed** | Use **Langfuse** (`LANGFUSE_*`) — same as other platform repos |
| Langfuse trace export | **Implemented** | `ops/langfuse_export.py` — pipeline spans + eval scores on `/v1/answer` |
| Knowledge graph expansion | **Implemented** | `InMemoryGraphExpander` + ingest entity tagging |
| API-key gate on `/v1/ingest`, `/v1/retrieve`, `/v1/answer` | **Implemented** | Set `RAG_API_KEY` on Render — these previously had zero caller auth at all |

See [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md) for how this repo connects to VAP, AegisAI, and AgentOps.

## System Context

Canonical: [`docs/diagrams/canonical-architecture.mmd`](docs/diagrams/canonical-architecture.mmd)

```mermaid
flowchart LR
  User["Enterprise User"] --> App["AI Assistant / Workflow"]
  App --> Gateway["RAG API — FastAPI"]
  Gateway --> Policy["Access Policy<br/>BEFORE ranking"]
  Gateway --> Orchestrator["RagPipeline"]
  Orchestrator --> Retrieval["Hybrid Retriever"]
  Orchestrator --> Rerank["CrossEncoderReranker"]
  Orchestrator --> Decline{"Score ≥ threshold?"}
  Decline -->|no| Refuse["Decline to answer"]
  Decline -->|yes| Gen["Grounded answer + citations"]
  Sources["Enterprise docs"] --> Ingestion["POST /v1/ingest"]
  Ingestion --> Retrieval
  Gateway --> Obs["Pipeline spans → Langfuse"]
```

*Solid boxes are implemented. LLM routers are extension points documented in ADRs.*

## Runtime Request Flow

*Solid path matches Implementation Status. Model Router / Evaluator are extension points — demo uses a single LLM path + golden eval CI, not a full multi-model router fleet.*

```mermaid
sequenceDiagram
  participant U as User
  participant API as RAG API
  participant G as Guardrails
  participant R as Hybrid Retriever
  participant C as Context Assembler
  participant M as Model Router
  participant E as Evaluator
  participant O as Observability

  U->>API: Ask enterprise question
  API->>G: Redact, classify, policy-check input
  G-->>API: Sanitized query + risk flags
  API->>R: Query + tenant + principal + filters
  R->>R: Enforce tenant, clearance, group ACLs
  R->>R: Keyword + semantic + metadata + freshness scoring
  R-->>API: Ranked authorized evidence
  API->>C: Compress, dedupe, budget, map citations
  C-->>API: Prompt-ready context
  API->>M: Generate grounded answer
  M-->>API: Answer draft
  API->>G: Validate citations and output policy
  API->>E: Sample/judge quality signals
  API->>O: Pipeline spans + eval signals
  O->>O: Langfuse export (when LANGFUSE_* set)
  API-->>U: Answer + citations + risk_flags + trace + langfuse_export
```

## Data and Knowledge Lifecycle

*Reference target for enterprise ingestion. Free-tier demo uses in-memory hybrid corpus + optional Qdrant — not every connector / DLP / graph box below ships on Render.*

```mermaid
flowchart TB
  A["Source Connectors"] --> B["Classification and DLP"]
  B --> C["Parsing and Normalization"]
  C --> D["Ownership, Lineage, Retention Metadata"]
  D --> E["Chunking and Deduplication"]
  E --> F["Embedding Versioning"]
  E --> G["Lexical Indexing"]
  E --> H["Entity and Relationship Extraction"]
  F --> I["Vector Store"]
  G --> J["Keyword / Hybrid Index"]
  H --> K["Knowledge Graph"]
  I --> L["Retrieval Layer"]
  J --> L
  K --> L
  L --> M["Evaluation Sets and Drift Checks"]
  M --> N["Ingestion Quality Feedback"]
  N --> C
```

## Component Boundaries

```mermaid
flowchart LR
  subgraph Core["Core Domain"]
    Models["Typed Models"]
    Access["Access Policy"]
    Ingest["Ingestion Quality Gates"]
    Retrieve["Hybrid Retrieval Interface"]
    Context["Context Engineering"]
    Guard["Guardrails"]
    Pipeline["RAG Pipeline"]
  end

  subgraph Platform["Platform Adapters"]
    API["FastAPI Adapter"]
    Obs["Telemetry Adapter"]
    Eval["Evaluation Engine"]
  end

  API --> Pipeline
  Pipeline --> Guard
  Pipeline --> Retrieve
  Pipeline --> Context
  Retrieve --> Access
  Ingest --> Models
  Eval --> Retrieve
  Obs --> Pipeline
```

## Repository Layout

```text
enterprise_rag_platform/
  src/enterprise_rag/
    api/              Optional HTTP adapter
    core/             Business-critical RAG boundaries
    eval/             Offline quality metrics
    ops/              Telemetry facade
  docs/
    adr/              Architecture decision records
    risk-register.md  Production risks and mitigations
    operating-model.md
    scalability.md
  tests/              Standard-library unit tests
```

## Production Decisions

| Area | Decision | Impact |
| --- | --- | --- |
| Retrieval | Use hybrid retrieval with metadata filters and reranking extension point | Improves exact-term, semantic, and business-context recall |
| Security | Apply tenant, group, and classification checks before ranking | Prevents leaking unauthorized context into prompts |
| Context | Dedupe, compress, cite, and token-budget evidence before generation | Reduces hallucination and improves traceability |
| Evaluation | Maintain offline retrieval and grounding metrics plus online feedback | Enables safe iteration instead of anecdotal QA |
| Operations | Trace latency, retrieval scores, citations, risk flags, token/cost events | Makes production behavior debuggable |
| Future Proofing | Keep vector store, LLM, graph, and reranker behind ports/interfaces | Allows model and vendor changes without rewriting workflows |

## Local Verification

The core tests use only the Python standard library:

```bash
cd enterprise_rag_platform
PYTHONPATH=src python -m unittest discover -s tests
```

To run the optional API adapter after installing dependencies:

```bash
cd enterprise_rag_platform
python -m pip install -e ".[dev]"
uvicorn enterprise_rag.api.app:app --reload
```

API surface:

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness |
| `GET /v1/strategies` | Retrieval modes and reranker options |
| `POST /v1/ingest` | Add documents to the in-memory corpus |
| `POST /v1/answer` | Grounded answer with citations, risk flags, and trace |

## Production Hardening Checklist

- **JWT-verified `Principal` under `PRODUCTION_STRICT=1`** — shipped (see
  [ADR-0006](docs/adr/0006-verified-principal-jwt-strict.md) / portfolio ADR-024).
  Default demo still allows client-asserted Principal for lab UX; do not run demo mode
  against real tenants. `RAG_API_KEY` alone is not identity.
- Replace `InMemoryHybridRetriever` with OpenSearch plus vector-store and graph adapters
  for durable multi-tenant corpora (Qdrant adapter exists; free-tier demo stays in-memory).
- Add query rewrite / multi-hop expansion beyond the current hybrid + cross-encoder path.
- Add embedding/model version tables and blue-green index deployment.
- Integrate SIEM audit sinks and cost dashboards (optional — Langfuse covers trace-linked LLMOps today).
- Prompt/version CI gates — golden + adversarial suites via golden-eval-registry (partially shipped).
- Add human approval workflows for destructive or regulated actions (AegisAI HITL bridge exists).
- Add content retention, legal hold, and source-of-truth ownership workflows.
- Expand red-team coverage beyond the adversarial golden suite (injection, citation spoofing).
