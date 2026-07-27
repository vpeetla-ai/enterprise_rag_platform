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
- [x] Golden page citation tests + HTTP PDF ingest tests
- [x] Demo UI page jump + truncation honesty on flat upload

### Phase 2 — Real hybrid + shipped rerank

- [x] Embeddings port + RRF fusion + BM25 k1/b
- [x] Qdrant real vectors + **BM25+RRF** hybrid (legacy scroll opt-in only)
- [x] Cross-encoder in Docker; startup warmup (`RAG_RERANKER_WARMUP`)
- [x] `/health` reports retrieval profile
- [x] Paraphrase recall eval (CI)

### Phase 3 — Grounded LLM + faithfulness

- [x] `LlmGroundedGenerator` + extractive for MOCK/CI
- [x] Remove citation spoof fallback
- [x] Faithfulness gate + glass-box `rag.faithfulness` span
- [x] Eval metrics gated in CI: page accuracy + faithfulness

### Phase 4 — Control plane

- [x] Strict ingest auth + JWT `exp`
- [x] Per-request recorder; audit JSONL; p95 metrics
- [x] CORS profile for Strict
- [x] Rate limit ingest/answer (`RAG_RATE_LIMIT_*`)
- [ ] Live Strict + Qdrant Cloud as corpus of record (owner: set `QDRANT_URL`)

### Phase 5 — Polish

- [x] OCR flag path (`RAG_OCR_ENABLED` → PyMuPDF OCR; else `ocr_required`)
- [x] Layout-aware page sections (heading/paragraph splits, still page-bounded)
- [x] Panel pack + PDF Q&A script
- [x] Profiles + [COST.md](COST.md)
- [ ] Hostile re-score ≥8.5 (owner / dual-model)

## Progress log

| Date | Note |
|------|------|
| 2026-07-26 | Program started; Phases 0–5 core shipped |
| 2026-07-27 | Gap close vs plan: Qdrant hybrid RRF, eval CI gates, rate limit, OCR flag, CE warmup, paraphrase eval, honesty fixes |
