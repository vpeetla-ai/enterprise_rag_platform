# Risk Register

| Risk | Likelihood | Impact | Mitigation | Owner |
| --- | --- | --- | --- | --- |
| Unauthorized content retrieved into prompt | Medium | Critical | Pre-ranking tenant, group, and classification enforcement; audit every citation | Security Architecture |
| Stale or superseded documents used | High | High | Freshness metadata, source lineage, recency scoring, stale-content dashboards | Data Governance |
| Semantic search misses exact business terms | High | High | Hybrid retrieval, metadata filters, entity-aware query rewriting | AI Platform |
| Hallucinated answer without evidence | Medium | High | Citation validation, grounding checks, refusal path when no authorized evidence exists | AI Safety |
| Duplicated chunks dominate context | Medium | Medium | Deduplication during ingestion and context assembly | Knowledge Engineering |
| Prompt injection in retrieved content | Medium | High | Instruction hierarchy, content isolation, output validation, tool authorization | AI Safety |
| Cost spike from long contexts or high-volume usage | Medium | Medium | Token budgeting, caching, model routing, tenant-level cost attribution | Platform Operations |
| Evaluation blind spots hide regressions | High | High | Golden datasets, online feedback sampling, retrieval and generation regression gates | Quality Engineering |
| Vendor lock-in limits future migration | Medium | Medium | Ports/adapters for LLM, vector store, reranker, graph, telemetry | Architecture |
| Real-time ingestion overloads indexes | Medium | Medium | Queue-based ingestion, backpressure, batch compaction, blue-green indexes | Data Platform |

## Residual Risk

Even with guardrails, enterprise RAG remains probabilistic. High-risk workflows such as refunds, account deletion, compliance decisions, customer-facing commitments, and financial transactions require explicit human approval and deterministic policy engines outside the LLM.
