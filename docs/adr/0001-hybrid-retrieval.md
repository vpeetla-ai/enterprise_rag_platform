# ADR 0001: Hybrid Retrieval as the Default

## Status

Accepted

## In one breath (panel)

I'd default to hybrid — lexical for exact entities and codes, dense for intent — because pure vector search quietly fails the queries enterprises actually ask.

## Context

Enterprise questions mix semantic intent with exact entities: dates, contract clauses, account names, product codes, metadata filters. Pure ANN is great for "vibe" and bad for "find the SKU and the clause dated March."

What I refused: shipping "we use embeddings" as the whole retrieval story.

## Decision

Default to hybrid retrieval: lexical matching, semantic matching, metadata filtering, freshness signals, plus an extension point for reranking and graph expansion.

**Demo vs Strict:** fusion shape is the same (RRF). Demo may use hash embeddings / score-boost; Strict prefers real vectors + cross-encoder when configured ([ADR-0008](./0008-dual-demo-strict-retrieval-profiles.md)).

## Consequences

- Better quality on exact *and* semantic queries
- More operational complexity than one vector call
- Eval must cover recall, context precision, citation accuracy, and grounding — fixtures in golden-eval-registry, not invented SLOs here
