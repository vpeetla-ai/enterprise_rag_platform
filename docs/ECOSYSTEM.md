# Ecosystem — Enterprise RAG Platform

This repository is the **knowledge layer** in the Venkat AI portfolio. It owns access-aware retrieval, context assembly, guardrails at the RAG boundary, and evaluation hooks — not fleet orchestration or enterprise gateway policy.

## Where this repo sits

```mermaid
flowchart TB
  subgraph Governance["Governance — aegisai-enterprise-agent-platform"]
    GW["Gateway + HITL"]
    REG["Agent registry"]
    AUD["Audit cases"]
  end

  subgraph Orchestration["Orchestration — venkat-ai-platform"]
    VAP["3 LangGraph orchestrators"]
    LOOPS["Loop patterns"]
    RAGLAB["RAG strategy lab"]
  end

  subgraph Knowledge["Knowledge — enterprise_rag_platform"]
    ING["PDF + text ingest<br/>page-aware"]
    RET["BM25 + dense + RRF"]
    CTX["Page citations + decline"]
    GR["Guardrails"]
  end

  subgraph AgentOps["AgentOps — aegisloop-agentops-workbench"]
    MIS["Mission fleets"]
    EVAL["Eval gates"]
    TRACE["Traces + replay"]
  end

  User["User / workflow"] --> GW
  GW --> VAP
  VAP --> RAGLAB
  RAGLAB -.->|"strategy experiments"| RET
  VAP --> Knowledge
  GW --> Knowledge
  VAP --> MIS
  Knowledge --> CTX
  GR --> GW
```

## Integration map

| Capability | Owner repo | This repo's role |
| --- | --- | --- |
| Hybrid / multi-query / HyDE RAG experiments | `venkat-ai-platform` | Reference **production-shaped** retrieval port (`Retriever`, `Reranker`) and policy-before-ranking |
| Gateway HITL for notify / destructive tools | `aegisai-enterprise-agent-platform` | Surfaces `human_approval_required` risk flags from guardrails for gateway consumers |
| Content pipeline + publish | `ai-content-factory` | Can call `/v1/answer` with tenant principal for grounded internal policy answers |
| Mission eval + traces | `aegisloop-agentops-workbench` | Shares eval vocabulary (grounding, evidence, policy); offline metrics in `eval/metrics.py` |

## Recommended wiring

1. **VAP RAG lab** — Compare strategies in VAP; promote winners to adapters implementing `enterprise_rag.core.retriever.Retriever`.
2. **AegisAI gateway** — When `human_approval_required` appears in `/v1/answer` risk_flags, route to gateway approval flow before returning to the user.
3. **AgentOps** — Import golden queries from `tests/fixtures/golden_queries.json` into mission regression suites.

## Implementation status (this repo)

| Area | Status |
| --- | --- |
| Access-before-ranking | Implemented (`AccessPolicy` + retriever filter; Strict JWT) |
| Hybrid retrieval (BM25 + dense + RRF) | Implemented (`InMemoryHybridRetriever` + Qdrant BM25+RRF) |
| Page-aware PDF ingest | Implemented (`POST /v1/ingest/pdf`, `Citation.page`) |
| Reranker port | Implemented — CE on Strict image; ScoreBoost for Demo |
| Decline + faithfulness | Implemented — no citation spoof fallback |
| Pipeline telemetry spans | Implemented (`EventRecorder` + audit JSONL + p95) |
| Rate limit | Implemented (`RAG_RATE_LIMIT_*`) |
| OCR | Partial — `RAG_OCR_ENABLED` flag path |
| Langfuse export (`ops/langfuse_export.py`) | Implemented — set `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` |
| HTTP API | `/health`, `/v1/answer`, `/v1/ingest`, `/v1/ingest/pdf`, `/v1/strategies`, `/v1/ops/metrics` |
| Demo vs Strict profiles | Implemented — [PROFILES.md](PROFILES.md) · [COST.md](COST.md) · [TOP1PCT_ERAG_PROGRAM.md](TOP1PCT_ERAG_PROGRAM.md) |
| Online eval feedback loop | Partial — offline metrics + GER CI + page/faithfulness gate |

## Interview playbook

- [02 RAG at scale](https://ai-architect-interview-playbook.vercel.app/q/ai-system-design/02-rag-platform-at-scale/)
- [22 PDF Q&A citations](https://ai-architect-interview-playbook.vercel.app/q/ai-system-design/22-enterprise-pdf-qa-citations-and-grounding/)
- [23 Hybrid RRF](https://ai-architect-interview-playbook.vercel.app/q/ai-system-design/23-enterprise-hybrid-retrieval-and-access-aware-ranking/)

## Related repositories

- [aegisai-enterprise-agent-platform](https://github.com/vpeetla-ai/aegisai-enterprise-agent-platform) — governance gateway
- [venkat-ai-platform](https://github.com/vpeetla-ai/venkat-ai-platform) — orchestration + RAG lab
- [aegisloop-agentops-workbench](https://github.com/vpeetla-ai/aegisloop-agentops-workbench) — AgentOps missions
- [ai-content-factory](https://github.com/vpeetla-ai/ai-content-factory) — content automation
- [ai-architect-interview-playbook](https://github.com/vpeetla-ai/ai-architect-interview-playbook) — Staff+/Principal drills