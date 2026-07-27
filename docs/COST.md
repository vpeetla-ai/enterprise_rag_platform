# Cost one-pager — Demo vs Strict/prod

| Profile | Idle | Warm panel | Tokens / vectors |
|---------|------|------------|------------------|
| **Demo** (default live) | Near $0 on Free/spin-down | Cold start ~30–90s | `hash` or `local` embed · ScoreBoost · extractive/`MOCK_LLM` |
| **Strict** (JWT) | Render Starter when always-on | CE load + optional local MiniLM | `local`/`openai` embed · `cross_encoder` · `GENERATOR=llm` when keys set |
| **Strict + Qdrant Cloud** | Qdrant cluster min | Persistent corpus (no re-seed theater) | Paid vectors + embed/LLM |

## Honest claims

- Demo may re-seed in-memory corpus on cold start — labeled in UI/README.
- Strict without `QDRANT_URL` still uses memory backend; set `QDRANT_BACKEND=true` + URL for multi-replica corpus of record.
- LLM answers require `GROQ_API_KEY` / gateway; otherwise generator falls back extractive.

See [PROFILES.md](PROFILES.md) for env matrices.
