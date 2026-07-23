#!/usr/bin/env bash
# Capture Strict ERAG panel receipt (local or GCP). Never prints JWT secret.
# Usage:
#   export ERAG_STRICT_URL=http://127.0.0.1:8080   # or Cloud Run URL
#   export RAG_JWT_SECRET=…                        # required for spoof check
#   ./scripts/capture_strict_panel_receipt.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${ERAG_STRICT_URL:-}"
if [[ -z "$URL" ]]; then
  echo "Set ERAG_STRICT_URL (e.g. http://127.0.0.1:8080)" >&2
  exit 2
fi
URL="${URL%/}"
DAY="$(date -u +%Y%m%dT%H%MZ)"
OUT_DIR="${STRICT_RECEIPT_DIR:-$ROOT/docs/artifacts/strict-receipts}"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/${DAY}-strict-receipt.md"

HEALTH="$(curl -sS --max-time 60 "${URL}/health" || true)"
MODE="$(printf '%s' "$HEALTH" | python3 -c 'import json,sys
raw=sys.stdin.read()
try:
  d=json.loads(raw)
  print(d.get("review_mode","?"))
except Exception:
  print("?")
')"

SPOOF_NOAUTH="skipped"
SPOOF_ATTACK="skipped"
if [[ -n "${RAG_JWT_SECRET:-}" ]]; then
  TOKEN="$(cd "$ROOT" && RAG_JWT_SECRET="$RAG_JWT_SECRET" python3 scripts/mint_panel_jwt.py)"
  SPOOF_NOAUTH="$(curl -sS -o /tmp/erag_noauth.json -w '%{http_code}' --max-time 60 \
    -X POST "${URL}/v1/answer" \
    -H 'Content-Type: application/json' \
    -d '{"query":"ping","tenant_id":"attacker","user_id":"attacker","groups":["executives"],"mode":"hybrid"}' || echo 000)"
  SPOOF_ATTACK="$(curl -sS -o /tmp/erag_attack.json -w '%{http_code}' --max-time 60 \
    -X POST "${URL}/v1/answer" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"query":"What is the mandatory API key rotation period at Zephyr Corporation?","tenant_id":"attacker","user_id":"attacker","groups":["executives"],"mode":"hybrid","rerank":true}' || echo 000)"
fi

HEALTH_JSON="$(printf '%s' "$HEALTH" | python3 -c 'import json,sys
raw=sys.stdin.read()
try:
  d=json.loads(raw)
  keep={k:d[k] for k in ("status","review_mode","principal_source","ok") if k in d}
  if not keep:
    keep={"keys": list(d.keys())[:12]}
  print(json.dumps(keep, indent=2))
except Exception as e:
  print(json.dumps({"parse_error": str(e), "snippet": raw[:200]}))
')"

{
  echo "# Strict ERAG panel receipt — ${DAY}"
  echo
  echo "- URL: \`${URL}\` (host only; no secrets)"
  echo "- review_mode from /health: **${MODE}** (expect \`strict\`)"
  echo "- Without Bearer HTTP: \`${SPOOF_NOAUTH}\` (expect 401/403)"
  echo "- With Bearer + body spoof HTTP: \`${SPOOF_ATTACK}\` (expect 200; principal from JWT)"
  echo
  echo "## /health (redacted)"
  echo
  echo '```json'
  echo "$HEALTH_JSON"
  echo '```'
  echo
  echo "## Notes"
  echo
  if [[ -n "${RAG_JWT_SECRET:-}" ]]; then
    echo "- JWT secret was used locally and **not** written to this file."
    echo "- Body \`tenant_id=attacker\` must not escalate clearance under Strict."
  else
    echo "- Set \`RAG_JWT_SECRET\` and re-run for spoof-check HTTP codes."
  fi
} >"$OUT"

echo "Wrote $OUT"
if [[ "$MODE" != "strict" ]]; then
  echo "WARN: review_mode is '${MODE}', expected 'strict'" >&2
  exit 1
fi
