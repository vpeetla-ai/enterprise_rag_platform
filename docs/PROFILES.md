# Runtime profiles (Demo vs Strict)

See [ADR-0008](./adr/0008-dual-demo-strict-retrieval-profiles.md) · [COST.md](COST.md).

## Demo (cheap — honest)

```bash
PRODUCTION_STRICT=false
EMBEDDING_PROVIDER=hash          # or local if fastembed installed
RAG_RERANKER=score_boost         # ScoreBoost labeled in UI via /health
GENERATOR=extractive             # or llm when GROQ_API_KEY set
QDRANT_BACKEND=false
RAG_SEED_DEMO_CORPUS=true        # reseed OK for Demo only
MOCK_LLM=true
HITL_HARD_GATE=false             # flags only; answer still returned
```

UI banner prints live `embed · rerank · generator · corpus` from `/health`.

## Strict / claim-aligned

```bash
# Preferred: docker compose -f docker-compose.strict.yml up --build
PRODUCTION_STRICT=true
RAG_JWT_SECRET=…
RAG_API_KEY=…                    # required under Strict
RAG_JWT_AUD=enterprise-rag
RAG_JWT_ISS=vpeetla-panel
EMBEDDING_PROVIDER=local         # or openai|gateway
RAG_RERANKER=cross_encoder
GENERATOR=llm
QDRANT_BACKEND=true
QDRANT_URL=http://qdrant:6333    # or Qdrant Cloud
RAG_SEED_DEMO_CORPUS=false       # corpus of record — no reseed theater
HITL_HARD_GATE=true
```

`/health.product_bar.claim_aligned` is true only when embed≠hash, CE, LLM, and Qdrant.

Persistence proof: `scripts/verify_qdrant_persistence.sh`

## Cost notes

| Profile | Idle | Variable |
|---------|------|----------|
| Demo memory + hash embed | ≈$0 | Render Free cold starts |
| Strict + CE + local embed + Qdrant | Render Starter + Qdrant | CPU for CE |
| Strict + Qdrant Cloud + OpenAI embed + LLM | Qdrant + tokens | Meter in FinOps |

Full one-pager: [COST.md](COST.md).
