#!/usr/bin/env bash
# Prove Qdrant is corpus of record: ingest → restart API → retrieve still hits.
# Requires: docker compose -f docker-compose.strict.yml up -d
set -euo pipefail
API="${ERAG_API:-http://127.0.0.1:8080}"
KEY="${RAG_API_KEY:?set RAG_API_KEY}"
SECRET="${RAG_JWT_SECRET:?set RAG_JWT_SECRET}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN="$(RAG_JWT_SECRET="$SECRET" python3 "$ROOT/scripts/mint_panel_jwt.py")"
DOC="persist-$(date +%s)"

echo "== health =="
curl -sS "$API/health" | python3 -c "import sys,json; h=json.load(sys.stdin); assert h.get('corpus_of_record')=='qdrant', h; print('corpus_of_record=qdrant ok')"

echo "== ingest =="
curl -sS -X POST "$API/v1/ingest" \
  -H "Authorization: Bearer $TOKEN" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d "{\"tenant_id\":\"evil\",\"document_id\":\"$DOC\",\"title\":\"Persist\",\"body\":\"Persistence probe says the unique token zebra-mango-42 must survive restart.\",\"uri\":\"u://p\",\"owner\":\"panel\",\"groups\":[\"engineering\"],\"metadata\":{\"effective_date\":\"2026-01-01\"}}" \
  | python3 -m json.tool

echo "== restart API container =="
docker compose -f "$ROOT/docker-compose.strict.yml" restart erag
sleep 5

echo "== retrieve after restart =="
curl -sS -X POST "$API/v1/retrieve" \
  -H "Authorization: Bearer $TOKEN" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"query":"zebra-mango-42","tenant_id":"spoof","user_id":"spoof","groups":["x"]}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); hits=d.get('hits') or []; assert any('zebra-mango-42' in (h.get('text') or '') for h in hits), d; print('persistence ok', len(hits), 'hits')"
