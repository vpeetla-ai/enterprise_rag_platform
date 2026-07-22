# Strict ERAG panel pack (P1 — 90/100 plan)

**Demo API (body Principal):** `https://enterprise-rag-api-4el1.onrender.com`  
**Strict API (JWT Principal):** `https://enterprise-rag-api-strict.onrender.com` *(create via Blueprint sync / dashboard)*  
**ADR:** [0006-verified-principal-jwt-strict.md](./adr/0006-verified-principal-jwt-strict.md)

## Why dual URL

`PRODUCTION_STRICT` is process environment. One service cannot be Demo and Strict at once without unsafe per-request mode switches. Dual Starter services keep Demo warm for strangers and Strict warm for panels (~+$7/mo).

## Dashboard apply

1. Sync Blueprint from this repo `render.yaml` **or** create web service `enterprise-rag-api-strict` from the same Dockerfile.
2. Plan: **Starter**.
3. Env: `PRODUCTION_STRICT=true`, `RAG_JWT_SECRET=<strong random>`, optional `RAG_API_KEY`.
4. Confirm: `curl -sS https://enterprise-rag-api-strict.onrender.com/health` → `"review_mode":"strict"`.

## Two-minute panel recipe

```bash
export RAG_JWT_SECRET='…'   # same as Render
export RAG_API_KEY='…'      # if gate enabled
TOKEN=$(python3 scripts/mint_panel_jwt.py)

# Health
curl -sS https://enterprise-rag-api-strict.onrender.com/health | python3 -m json.tool

# Body spoof must NOT win — JWT principal wins
curl -sS -X POST https://enterprise-rag-api-strict.onrender.com/v1/answer \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $RAG_API_KEY" \
  -d '{
    "query":"What is the mandatory API key rotation period at Zephyr Corporation?",
    "tenant_id":"attacker","user_id":"attacker","groups":["executives"],
    "mode":"hybrid","rerank":true
  }'
```

Without Bearer under Strict → 401/403. With Bearer → answer uses JWT clearance/groups, not body spoof.

## Portfolio links

- Technical review step 3 → Demo UI + this pack / Strict health
- Spine health notes prefer Strict for panels
