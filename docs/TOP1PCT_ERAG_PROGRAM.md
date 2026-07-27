# Top-1% Enterprise RAG program

**Status:** ACTIVE  
**Repo:** enterprise_rag_platform  
**Plan:** Cursor plan `top1pct_enterprise_rag` (C+C: PDF flagship first, dual Demo/Strict posture)  
**Baseline:** Principal review PDF Q&A ~2/10 · overall ~3/10  

## Locked choices

| Decision | Choice |
|----------|--------|
| North star | Phases 1–3 PDF Q&A undeniable; 4–5 control plane |
| Budget | Demo cheap; Strict/prod may use paid Qdrant + embeddings |

## Phase checklist

### Phase 0 — Honesty reset

- [x] README status table honest (Partial / Not shipped where true)
- [x] This tracker
- [x] [ADR-0007](./adr/0007-page-aware-ingest-and-citations.md)
- [x] [ADR-0008](./adr/0008-dual-demo-strict-retrieval-profiles.md)
- [x] Glass-box: demo_fallback only when API unreachable

### Phase 1 — Page provenance + PDF ingest

- [x] Chunk/Citation page fields
- [x] Page-aware chunker + `/v1/ingest/pdf`
- [x] Golden page citation tests
- [x] Demo UI page jump

### Phase 2 — Real hybrid + shipped rerank

- [x] Embeddings port + RRF fusion + BM25 k1/b
- [x] Qdrant real vectors + search (no zero-vector scroll default)
- [x] Cross-encoder in Docker; startup load
- [x] `/health` reports retrieval profile

### Phase 3 — Grounded LLM + faithfulness

- [x] `LlmGroundedGenerator` + extractive for MOCK/CI
- [x] Remove citation spoof fallback
- [x] Faithfulness gate
- [x] Eval metrics: page accuracy, faithfulness

### Phase 4 — Control plane

- [x] Strict ingest auth + JWT `exp`
- [x] Per-request recorder; audit JSONL; p95 metrics
- [x] CORS profile for Strict

### Phase 5 — Polish

- [x] OCR flag (`ocr_required` path documented)
- [x] Panel pack + PDF Q&A script
- [x] Profiles + cost notes
- [ ] Hostile re-score ≥8.5 (owner / dual-model)

## Progress log

| Date | Note |
|------|------|
| 2026-07-26 | Program started; Phases 0–5 implemented in repo |
