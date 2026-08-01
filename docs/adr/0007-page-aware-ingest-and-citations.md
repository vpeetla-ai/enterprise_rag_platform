# ADR 0007: Page-aware ingest and citations

## Status

Accepted

## In one breath (panel)

I'd chunk PDFs inside page boundaries and put `page` on citations — flattening pages into one body string is how "page 12" becomes a guessing game.

## Context

Page-specific citations are the product bar for PDF Q&A. Collapsing whitespace across pages destroys provenance. `Citation` had no page field.

What I refused: "close enough" document-only cites sold as enterprise PDF Q&A.

## Decision

1. `Chunk`: optional `page_start`, `page_end`, `char_start`, `char_end`.
2. `Citation`: optional `page`, `chunk_id`, `snippet`.
3. Prefer `POST /v1/ingest/pdf` (PyMuPDF) with per-page text.
4. Chunk **within** page boundaries — no cross-page windows.
5. Flat `body` ingest stays for fixtures / non-PDF (`page=null`).
6. Scanned PDFs with no extractable text → `422` `ocr_required` until OCR is enabled (optional, not the default bar).

## Consequences

- Breaking for clients that assumed document-only citations
- UI renders `Title · p.N` with page jump
- Eval gates measure page citation accuracy — no invented accuracy % here
