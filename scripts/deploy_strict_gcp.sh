#!/usr/bin/env bash
# Deploy Strict ERAG on GCP Cloud Run (scale-to-zero). Coexists with Demo service.
# Usage: ./scripts/deploy_strict_gcp.sh <PROJECT_ID> [REGION]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_ID="${1:-}"
REGION="${2:-us-central1}"
if [[ -z "$PROJECT_ID" ]]; then
  echo "Usage: $0 <PROJECT_ID> [REGION]" >&2
  exit 2
fi

SECRET="${RAG_JWT_SECRET:-}"
if [[ -z "$SECRET" ]]; then
  SECRET="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
  echo "Generated RAG_JWT_SECRET for this deploy:"
  echo "  export RAG_JWT_SECRET='$SECRET'"
fi

cd "$ROOT/deploy/gcp/cloudrun"
terraform init -input=false

# Ensure registry exists, then image
terraform apply -input=false -auto-approve \
  -var="project_id=${PROJECT_ID}" -var="region=${REGION}" \
  -target=google_project_service.artifactregistry \
  -target=google_artifact_registry_repository.erag

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/enterprise-rag/enterprise-rag:latest"
docker build -t "$IMAGE" -f "$ROOT/Dockerfile" "$ROOT"
docker push "$IMAGE"

terraform apply -input=false -auto-approve \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="image_tag=latest" \
  -var="production_strict=true" \
  -var="rag_jwt_secret=${SECRET}"

URL="$(terraform output -raw service_url)"
echo ""
echo "Strict service URL: $URL"
echo "Health:"
curl -sS "${URL}/health" | python3 -m json.tool || true
echo ""
echo "Mint JWT (same secret):"
echo "  export RAG_JWT_SECRET='$SECRET'"
echo "  python3 $ROOT/scripts/mint_panel_jwt.py"
echo "Panel pack: docs/STRICT_PANEL_PACK.md"
