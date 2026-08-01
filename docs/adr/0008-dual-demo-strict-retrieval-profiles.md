# ADR 0008: Dual Demo / Strict retrieval profiles

## Status

Accepted

## In one breath (panel)

I'd ship two honest profiles — cheap Demo for the free-tier ceiling, Strict for hybrid ANN + cross-encoder + JWT — and never mark a capability Implemented unless the live `/health` profile actually enables it.

## Context

Portfolio cost ceiling needs a cheap Demo path. Principal panels need hybrid + real vectors + (optionally) paid embeddings without lying that the public Vercel/Render demo is that stack.

What I refused: one ambiguous "production RAG" badge that mixes hash embeddings with enterprise claims.

## Decision

| Concern | Demo | Strict / prod |
|---------|------|----------------|
| Embeddings | `hash` or `local` (fastembed) | `local`, `openai`, or `gateway` |
| Fusion | RRF over BM25 + dense | Same |
| Rerank | `score_boost` allowed if labeled; CE when weights in image | `RAG_RERANKER=cross_encoder` |
| Generator | Extractive / `MOCK_LLM` when no key | LLM + faithfulness |
| Vector store | In-memory hybrid | Qdrant + tenant filter |
| Auth | Body Principal + API key | JWT Principal (`exp` required); ingest bound to claims |

`GET /health` reports retrieval profile fields so reviewers verify posture without reading source.

## Consequences

- Two Docker targets: full image default; slim Demo optional later
- README must not claim Implemented until the live profile enables it
- No invented p95/SLO numbers for free-tier Demo — measure what's configured
