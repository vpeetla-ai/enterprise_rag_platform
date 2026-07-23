#!/usr/bin/env bash
# Local Strict ERAG — no Render Starter required (P1 interim).
# Usage: ./scripts/run_strict_local.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SECRET="${RAG_JWT_SECRET:-}"
if [[ -z "$SECRET" ]]; then
  SECRET="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
  echo "Generated RAG_JWT_SECRET for this session (export to reuse):"
  echo "  export RAG_JWT_SECRET='$SECRET'"
fi

export RAG_JWT_SECRET="$SECRET"
export PRODUCTION_STRICT=true
PORT="${PORT:-8080}"

echo "Starting Strict ERAG on http://127.0.0.1:${PORT} (PRODUCTION_STRICT=true)"
echo "Health: curl -sS http://127.0.0.1:${PORT}/health | python3 -m json.tool"
echo "Mint:   python3 scripts/mint_panel_jwt.py"

if command -v docker >/dev/null 2>&1; then
  exec docker run --rm -p "${PORT}:8080" \
    -e PRODUCTION_STRICT=true \
    -e RAG_JWT_SECRET="$SECRET" \
    -e PORT=8080 \
    "$(docker build -q -f Dockerfile .)"
fi

# Fallback: local uvicorn if package installed
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m uvicorn enterprise_rag.api.app:app --host 0.0.0.0 --port "$PORT"
