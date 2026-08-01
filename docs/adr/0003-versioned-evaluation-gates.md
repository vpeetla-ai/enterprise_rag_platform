# ADR 0003: Versioned Evaluation Gates

## Status

Accepted

## In one breath (panel)

I'd treat prompt, retrieval, embedding, and model changes as release artifacts that fail CI against versioned goldens — manual spot checks are how regressions ship.

## Context

RAG quality dies quietly when documents, chunking, embeddings, prompts, retrievers, or models change. "Looks fine in the demo UI" is not a gate.

What I refused: promoting retrieval or prompt edits on vibes alone.

## Decision

Prompt, retrieval, embedding, and model changes must pass versioned offline datasets before promotion. Online failure signals feed future cases — they don't replace the offline gate.

Consumer suites live in [golden-eval-registry](https://github.com/vpeetla-ai/golden-eval-registry); this repo runs them in CI against a real pipeline.

## Consequences

- Releases slower than prototype speed — safer
- Domain teams must maintain representative golden questions
- Eval output is a release artifact, not a slide
