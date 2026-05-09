# ADR 0001: Hybrid Retrieval as the Default

## Status

Accepted

## Context

Enterprise queries often combine semantic intent with exact entities, dates, contract terms, account names, product codes, and metadata constraints. Pure vector retrieval is insufficient for this range.

## Decision

The platform defaults to hybrid retrieval: lexical matching, semantic matching, metadata filtering, freshness signals, and an extension point for reranking and graph expansion.

## Consequences

- Retrieval quality improves for exact and semantic queries.
- The retrieval layer is more operationally complex than a single vector search call.
- Evaluation must measure retrieval recall, context precision, citation accuracy, and grounding.
