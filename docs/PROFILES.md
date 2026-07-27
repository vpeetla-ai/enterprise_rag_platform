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
MOCK_LLM=true                    # CI / offline
HITL_HARD_GATE=false             # flags only; answer still returned
RAG_RATE_LIMIT_PER_MIN=60
RAG_OCR_ENABLED=false
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
RAG_RERANKER_WARMUP=true
GENERATOR=llm                    # falls back extractive if no LLM key
QDRANT_BACKEND=true
QDRANT_URL=http://qdrant:6333    # or Qdrant Cloud
RAG_SEED_DEMO_CORPUS=false       # corpus of record — no reseed theater
HITL_HARD_GATE=true
RAG_DECLINE_THRESHOLD=0.001
RAG_DECLINE_THRESHOLD_CE=-10.0   # calibrate for cross-encoder logits
CORS_ORIGINS=https://enterprise-rag-platform-eta.vercel.app
RAG_RATE_LIMIT_PER_MIN=60
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
