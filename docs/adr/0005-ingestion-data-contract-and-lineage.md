# ADR-0005: Ingestion Data Contract Enforcement + Real Lineage Metadata

## Status

Accepted — 2026-07-05

## Context

`DocumentChunker._validate()` already computed `IngestionIssue`s for missing owner, missing
lineage URI, near-empty content, and missing freshness metadata — but `/v1/ingest` in
`api/app.py` discarded them entirely, only ever reading `.chunks`. A document with no owner or
no source URI was silently accepted and indexed. Separately, `Chunk` had no real per-chunk
lineage: `chunk_id` embeds a hash, but nothing recorded a content hash a caller could compare
across re-ingestions, or a real "when was this actually ingested" timestamp distinct from
`updated_at` (the source document's own, caller-supplied timestamp).

## Decision

1. `Chunk` gains `content_hash: str` (a real sha256 of the chunk's text, position-independent —
   unlike `chunk_id`'s hash, which embeds chunk index and so changes even when the text doesn't)
   and `ingested_at: datetime` (set at chunking time, independent of the source document's
   `updated_at`).
2. `IngestionResult.blocking_issues` distinguishes hard issues (`missing_owner`,
   `missing_lineage`, `low_content`) from soft ones (`missing_freshness_metadata` stays a
   warning, not a rejection — real documents may reasonably omit it).
3. `/v1/ingest` now rejects (422) when `blocking_issues` is non-empty, and returns `lineage`
   (content_hash + ingested_at per chunk) and `warnings` (soft issues) in its response instead
   of silently discarding both.
4. Fixed three places that reconstruct a `Chunk` explicitly and would otherwise silently drop
   the new fields back to their defaults: `AppState._tag_chunks` (entity tagging on ingest),
   `InMemoryGraphExpander.register_entities`, and the Qdrant adapter's `upsert`/
   `_payload_to_chunk` round-trip (the persisted vector store would have lost lineage on every
   read).

## Consequences

### Positive
- A real data contract now exists at the ingestion boundary, not just computed-and-ignored
  validation logic.
- Lineage metadata survives every reconstruction path in the codebase, including a full
  round-trip through the optional Qdrant-backed persistent store — verified with new tests
  (`tests/test_ingestion_contract.py`, 9 cases) covering hash stability across re-ingestion,
  hash change on real content change, and blocking-vs-warning issue classification.
- **Found and fixed a real, pre-existing CI gap while writing these tests**: this repo's
  `.github/workflows/tests.yml` ran `python -m unittest discover -s tests`, which only
  discovers `unittest.TestCase`-based tests. `tests/test_api_auth.py` (the RAG_API_KEY auth-gate
  tests from an earlier security fix) uses bare pytest-style functions with a `monkeypatch`
  fixture — `unittest discover` silently found 0 tests in that file and reported overall
  success anyway, since the *other* files' `TestCase`-based tests still passed. That auth-gate
  test file had never actually run in CI. Fixed by switching the workflow to
  `python -m pytest tests/`, which discovers both styles — now 32 tests run instead of 16.

### Negative
- The 422 rejection is a behavior change: a caller who previously got a 200 with 0 useful
  chunks from a document with no owner/URI now gets a hard error instead. This is the intended
  fix (the contract violation was always real, just silently ignored), but is a breaking change
  for any existing caller relying on the old silent-accept behavior.

## References
- `src/enterprise_rag/core/ingestion.py` (`IngestionResult.blocking_issues`)
- `src/enterprise_rag/core/models.py` (`Chunk.content_hash`, `Chunk.ingested_at`)
- `src/enterprise_rag/api/app.py` (`/v1/ingest`, `AppState._tag_chunks`)
- `src/enterprise_rag/core/graph_expander.py` (`register_entities`)
- `src/enterprise_rag/adapters/qdrant_retriever.py` (`upsert`, `_payload_to_chunk`)
- `tests/test_ingestion_contract.py`
- `.github/workflows/tests.yml`
