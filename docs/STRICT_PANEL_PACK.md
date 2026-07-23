# Strict ERAG panel pack (P1 — 90/100 plan)

**Demo API (body Principal):** `https://enterprise-rag-api-4el1.onrender.com` *(Render Free — expect cold starts)*  
**Strict API (preferred interim):** local Docker **or** GCP Cloud Run Strict  
**Strict API (later):** `https://enterprise-rag-api-strict.onrender.com` *(Render Starter when owner upgrades)*  
**ADR:** [0006-verified-principal-jwt-strict.md](./adr/0006-verified-principal-jwt-strict.md)

## Why dual process

`PRODUCTION_STRICT` is process environment. One process cannot be Demo and Strict safely.

## Option A — Local Strict (no cloud bill) ← use while Render stays Free

```bash
cd enterprise_rag_platform
./scripts/run_strict_local.sh
# other terminal:
export RAG_JWT_SECRET='…'   # printed by the script
TOKEN=$(python3 scripts/mint_panel_jwt.py)
curl -sS http://127.0.0.1:8080/health | python3 -m json.tool   # review_mode=strict
curl -sS -X POST http://127.0.0.1:8080/v1/answer \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query":"What is the mandatory API key rotation period at Zephyr Corporation?",
    "tenant_id":"attacker","user_id":"attacker","groups":["executives"],
    "mode":"hybrid","rerank":true
  }'
```

## Option B — GCP Cloud Run Strict (~$0 idle)

Creates service **`enterprise-rag-strict`** (does not overwrite Demo `enterprise-rag`).

```bash
./scripts/deploy_strict_gcp.sh <PROJECT_ID>
# or see deploy/gcp/cloudrun/README.md for terraform-only steps
curl -sS "$(cd deploy/gcp/cloudrun && terraform output -raw service_url)/health" | python3 -m json.tool
# expect review_mode=strict
```

## Option C — Render Strict twin (after Starter upgrade)

1. Sync Blueprint / create `enterprise-rag-api-strict` · plan **Starter**  
2. `PRODUCTION_STRICT=true` + `RAG_JWT_SECRET`  
3. `./scripts/setup_strict_render.sh` for secret mint + checklist  

## Capture receipt (any Strict host)

```bash
export ERAG_STRICT_URL=http://127.0.0.1:8080   # or Cloud Run Strict URL
export RAG_JWT_SECRET=…                        # same as Strict process
./scripts/capture_strict_panel_receipt.sh
# → docs/artifacts/strict-receipts/<utc>-strict-receipt.md
```

## Two-minute spoof check (any Strict host)

Without Bearer → 401/403. With Bearer → JWT principal wins; body `tenant_id=attacker` must not escalate clearance.

## Portfolio links

- Technical review → Demo UI + this pack  
- Spine health — Render Free cold starts labeled until Starter
