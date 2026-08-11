# Strict panel receipt — Acme embed (synthetic / operator-run)

**Date:** 2026-08-11  
**Mode:** Operator checklist (live Strict twin may be cold / undeployed on Render)

## Honest status

`enterprise-rag-api-strict.onrender.com` may return host 404 until Render Starter Strict is provisioned.
Panel-ready path: `scripts/run_strict_local.sh` or `scripts/setup_strict_render.sh` then
`scripts/capture_strict_panel_receipt.sh`.

## Expected Strict health shape

```json
{
  "review_mode": "strict",
  "principal_source": "jwt"
}
```

## Break tests (from ADR-032 rubric)

| Test | Expected |
|------|----------|
| Spoof body `tenant_id` under Strict | 403 / JWT tenant wins |
| Valid JWT for `acme` ingest + answer | citations + audit |
| Missing Bearer under Strict | 401 |

## Capture command

```bash
export ERAG_STRICT_URL=https://<strict-host>
export RAG_JWT_SECRET=...
./scripts/capture_strict_panel_receipt.sh
```

Commit the dated receipt here; never commit secrets or raw JWTs.
