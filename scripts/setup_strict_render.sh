#!/usr/bin/env bash
# Operator helper: print exact Render dashboard steps + generate a JWT secret locally.
# Does not call Render APIs (MCP workspace auth often unavailable).
set -euo pipefail

echo "=== P1 Strict ERAG — dashboard checklist ==="
echo "1. Open https://dashboard.render.com → your workspace"
echo "2. New Web Service → repo vpeetla-ai/enterprise_rag_platform (Docker, same Dockerfile as Demo)"
echo "   OR Blueprint Sync from render.yaml (service name: enterprise-rag-api-strict)"
echo "3. Instance type: Starter"
echo "4. Env vars:"
echo "   PRODUCTION_STRICT=true"
echo "   RAG_JWT_SECRET=<paste generated secret below>"
echo "   RAG_API_KEY=<same as Demo if gated>"
echo "5. Health check path: /health"
echo "6. After deploy: curl -sS https://enterprise-rag-api-strict.onrender.com/health | python3 -m json.tool"
echo "   Expect: review_mode=strict, production_strict=true"
echo
SECRET=$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)
echo "=== Generated RAG_JWT_SECRET (copy once; do not commit) ==="
echo "$SECRET"
echo
echo "Save locally: export RAG_JWT_SECRET='$SECRET'"
echo "Panel mint:   cd enterprise_rag_platform && python3 scripts/mint_panel_jwt.py"
