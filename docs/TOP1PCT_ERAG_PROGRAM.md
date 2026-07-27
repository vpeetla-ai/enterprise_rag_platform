# Top-1% Enterprise RAG program

**Status:** ACTIVE — hardening toward ≥8.5  
**Repo:** enterprise_rag_platform  
**Plan:** Cursor plan `top1pct_enterprise_rag` + ROI moves 1–7 from hostile re-review  

## Locked choices

| Decision | Choice |
|----------|--------|
| North star | Phases 1–3 PDF Q&A undeniable; 4–5 control plane |
| Budget | Demo cheap; Strict/prod may use paid Qdrant + embeddings |
| Product PDF bar | **Text-layer PDFs** (OCR optional / not default image) |

## Phase checklist

### Phase 0–5 (core)

See prior log — page ingest, RRF, faithfulness, Strict JWT, panel pack shipped.

### ROI moves → ≥8.5 (2026-07-27)

- [x] **1. Qdrant as corpus of record** — `docker-compose.strict.yml` + `RAG_SEED_DEMO_CORPUS=false` when Qdrant; `scripts/verify_qdrant_persistence.sh`
- [x] **2. Public profile honesty** — Demo banner shows live `/health` embed/rerank/generator/corpus; `product_bar.claim_aligned`
- [x] **3. HITL hard-gate** — Strict / `HITL_HARD_GATE` withholds answer (`pending_approval`)
- [x] **4. Citation-span faithfulness** — replaces bag-of-words novel-token rule
- [x] **5. Prod auth baseline** — Strict requires `RAG_API_KEY` + JWT; optional `aud`/`iss`; metrics gated
- [x] **6. Ingest lifecycle** — replace-by-document_id, `DELETE /v1/documents/{id}`, content_hash dedupe
- [x] **7. OCR product decision** — text-layer is the bar; OCR remains opt-in flag only
- [ ] **Owner:** Wire live Strict to Qdrant Cloud URL + keys so `claim_aligned=true` on a public host
- [ ] Hostile re-score ≥8.5 (after live Strict SoR)

## Progress log

| Date | Note |
|------|------|
| 2026-07-26 | Program started; Phases 0–5 core shipped |
| 2026-07-27 | Gap close vs plan (PR #10) |
| 2026-07-27 | ROI moves 1–7 implemented (Qdrant compose, HITL gate, span faithfulness, auth, lifecycle) |
