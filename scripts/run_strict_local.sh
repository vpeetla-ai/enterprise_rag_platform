#!/usr/bin/env bash
# Local Strict ERAG — Qdrant corpus of record when Docker is available.
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

API_KEY="${RAG_API_KEY:-}"
if [[ -z "$API_KEY" ]]; then
  API_KEY="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
)"
  echo "Generated RAG_API_KEY for this session:"
  echo "  export RAG_API_KEY='$API_KEY'"
fi

export RAG_JWT_SECRET="$SECRET"
export RAG_API_KEY="$API_KEY"
export PRODUCTION_STRICT=true
export HITL_HARD_GATE=true
export RAG_JWT_AUD="${RAG_JWT_AUD:-enterprise-rag}"
export RAG_JWT_ISS="${RAG_JWT_ISS:-vpeetla-panel}"
PORT="${PORT:-8080}"

if [[ "${ERAG_USE_COMPOSE:-1}" == "1" ]] && command -v docker >/dev/null 2>&1; then
  echo "Starting Strict ERAG + Qdrant via docker-compose.strict.yml on :${PORT}"
  export RAG_JWT_SECRET RAG_API_KEY
  docker compose -f docker-compose.strict.yml up --build -d
  echo "Health: curl -sS http://127.0.0.1:${PORT}/health | python3 -m json.tool"
  echo "Mint:   RAG_JWT_SECRET='$SECRET' python3 scripts/mint_panel_jwt.py"
  echo "Expect corpus_of_record=qdrant and demo_seed_enabled=false"
  exit 0
fi

export QDRANT_BACKEND="${QDRANT_BACKEND:-false}"
export RAG_SEED_DEMO_CORPUS="${RAG_SEED_DEMO_CORPUS:-true}"
echo "Starting Strict ERAG (memory fallback) on http://127.0.0.1:${PORT}"
echo "For Qdrant SoR: ERAG_USE_COMPOSE=1 ./scripts/run_strict_local.sh"

if command -v docker >/dev/null 2>&1 && [[ "${ERAG_USE_COMPOSE:-1}" != "1" ]]; then
  exec docker run --rm -p "${PORT}:8080" \
    -e PRODUCTION_STRICT=true \
    -e RAG_JWT_SECRET="$SECRET" \
    -e RAG_API_KEY="$API_KEY" \
    -e RAG_JWT_AUD="$RAG_JWT_AUD" \
    -e RAG_JWT_ISS="$RAG_JWT_ISS" \
    -e HITL_HARD_GATE=true \
    -e PORT=8080 \
    "$(docker build -q -f Dockerfile .)"
fi

export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m uvicorn enterprise_rag.api.app:app --host 0.0.0.0 --port "$PORT"
