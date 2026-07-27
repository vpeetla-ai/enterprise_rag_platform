# ADR 0007: Page-aware ingest and citations

## Status

Accepted

## Context

Page-specific citations are a product requirement for PDF Q&A. Flattening PDF pages into a single `body` string and collapsing whitespace destroys page provenance. `Citation` previously had no page field.

## Decision

1. Extend `Chunk` with optional `page_start`, `page_end`, `char_start`, `char_end`.
2. Extend `Citation` with optional `page`, `chunk_id`, and `snippet`.
3. Prefer server-side PDF parse (`POST /v1/ingest/pdf`) via PyMuPDF producing per-page text.
4. Chunk **within** page boundaries (no cross-page windows).
5. Flat `body` ingest remains for fixtures and non-PDF sources with `page=null`.
6. Scanned PDFs with no extractable text return `422` with `code=ocr_required` until an OCR path is enabled.

## Consequences

- Breaking for clients that assumed document-only citations.
- UI must render `Title · p.N` and support page jump.
- Eval gates must measure page citation accuracy.
