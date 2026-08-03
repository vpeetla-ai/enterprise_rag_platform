# ADR-0005: Ingestion Data Contract Enforcement + Real Lineage Metadata

## Status

Accepted — 2026-07-05

## In one breath (panel)

I'd reject ingest that fails the data contract at the boundary — computing issues and then discarding them is how empty owners and missing lineage sneak into the index.

## Context

`DocumentChunker._validate()` already flagged missing owner, missing lineage URI, near-empty content, and missing freshness — but `/v1/ingest` only read `.chunks` and silently indexed junk. Chunks also lacked a stable content hash and a real `ingested_at` distinct from caller-supplied `updated_at`.

What I refused: "validation for show, accept anyway."

## Decision

1. `Chunk` gains `content_hash` (sha256 of text, position-independent) and `ingested_at`.
2. `blocking_issues` vs soft warnings — missing owner/lineage/low content hard-fail; missing freshness stays a warning.
3. `/v1/ingest` returns **422** on blocking issues, plus `lineage` and `warnings` in the response.
4. Fix every reconstruction path that would drop the new fields (entity tagging, graph expander, Qdrant round-trip).

Bonus scar while writing tests: CI used `unittest discover`, which never ran the pytest-style auth-gate file. Switched to `pytest` — honesty about what CI actually executed.

## Consequences

### Positive

- Real contract at the ingest boundary
- Lineage survives Qdrant round-trip; covered by `tests/test_ingestion_contract.py`
- Auth-gate tests actually run in CI now

### Negative

- Breaking for callers who relied on silent 200-with-useless-chunks — intentional

## References

- `src/enterprise_rag/core/ingestion.py`, `models.py`, `api/app.py`, `adapters/qdrant_retriever.py`
- `tests/test_ingestion_contract.py`
- `.github/workflows/tests.yml`
