# ADR 0008: Dual Demo / Strict retrieval profiles

## Status

Accepted

## Context

Portfolio cost ceiling requires a cheap Demo path, while Principal panels need honest hybrid ANN + cross-encoder + (optionally) paid embeddings.

## Decision

| Concern | Demo | Strict / prod |
|---------|------|----------------|
| Embeddings | `EMBEDDING_PROVIDER=hash` or `local` (fastembed) | `local`, `openai`, or `gateway` |
| Fusion | RRF over lexical BM25 + dense | Same |
| Rerank | `score_boost` allowed if labeled; CE preferred when image includes weights | `RAG_RERANKER=cross_encoder` |
| Generator | Extractive when `MOCK_LLM` / no key; LLM when configured | LLM + faithfulness |
| Vector store | In-memory hybrid with embeddings | Qdrant with real vectors + tenant filter |
| Auth | Body Principal + API key | JWT Principal (`exp` required); ingest bound to claims |

`GET /health` reports `retrieval` profile fields so reviewers can verify posture without reading source.

## Consequences

- Two Docker targets: full image (rerank+qdrant+pdf) default; slim Demo optional later.
- README must not mark capabilities Implemented until the live profile actually enables them.
