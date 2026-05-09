# ADR 0003: Versioned Evaluation Gates

## Status

Accepted

## Context

RAG quality can regress when documents, chunking, embeddings, prompts, retrievers, rerankers, or models change. Manual spot checks are not sufficient for production.

## Decision

Prompt, retrieval, embedding, and model changes must be evaluated against versioned offline datasets before promotion. Online quality signals should feed failure analysis and future test cases.

## Consequences

- Releases are slower than prototype iteration but safer.
- Domain teams must maintain representative golden questions.
- Evaluation output becomes a release artifact.
