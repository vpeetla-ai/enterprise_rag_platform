# Runtime profiles (Demo vs Strict)

See [ADR-0008](./adr/0008-dual-demo-strict-retrieval-profiles.md) · [COST.md](COST.md).

## Demo (cheap)

```bash
PRODUCTION_STRICT=false
EMBEDDING_PROVIDER=hash          # or local if fastembed installed
RAG_RERANKER=score_boost         # or cross_encoder if image has [rerank]
GENERATOR=extractive             # or llm when GROQ_API_KEY / LLM_GATEWAY_URL set
QDRANT_BACKEND=false
MOCK_LLM=true                    # CI / offline
RAG_RATE_LIMIT_PER_MIN=60
RAG_OCR_ENABLED=false
```

## Strict / prod

```bash
PRODUCTION_STRICT=true
RAG_JWT_SECRET=…
EMBEDDING_PROVIDER=local         # or openai|gateway
RAG_RERANKER=cross_encoder
RAG_RERANKER_WARMUP=true
GENERATOR=llm                    # falls back extractive if no LLM key
QDRANT_BACKEND=true              # only when QDRANT_URL is set
QDRANT_URL=…
RAG_DECLINE_THRESHOLD=0.001
RAG_DECLINE_THRESHOLD_CE=-10.0   # calibrate for cross-encoder logits
CORS_ORIGINS=https://enterprise-rag-platform-eta.vercel.app
RAG_RATE_LIMIT_PER_MIN=60
```

## Cost notes

| Profile | Idle | Variable |
|---------|------|----------|
| Demo memory + hash embed | ≈$0 | Render Free cold starts |
| Strict + CE + local embed | Render Starter | CPU for CE; no embed API |
| Strict + Qdrant Cloud + OpenAI embed + LLM | Qdrant + tokens | Meter in FinOps |

Full one-pager: [COST.md](COST.md).
