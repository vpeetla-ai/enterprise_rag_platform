# Enterprise RAG — GCP Cloud Run (Always Free–friendly)

Alternate deploy path to Render. **Panel warm Demo stays on Render** (Free now; Starter later).  
Use this path for **GCP receipts** and **Strict JWT** while Render Strict twin is pending.

Memory retriever only (no Cloud SQL) → idle ≈ **$0** with `min_instance_count = 0`.

## Cost

| Component | Idle | Notes |
|-----------|------|-------|
| Cloud Run | ≈$0 | Scale-to-zero; Always Free quotas apply |
| Artifact Registry | Small | Delete images after tear-down if unused |
| Cloud SQL | **Not used** | Use FinOps GCP stack if you need SQL |

## Prerequisites

```bash
gcloud auth application-default login
gcloud config set project <PROJECT_ID>
terraform version && docker version
```

## Deploy Demo (review_mode=demo)

```bash
cd deploy/gcp/cloudrun
terraform init

# 1) Registry + APIs only (image must exist before Cloud Run can roll)
terraform apply -var="project_id=<PROJECT_ID>" -var="region=us-central1" \
  -target=google_project_service.artifactregistry \
  -target=google_artifact_registry_repository.erag

# 2) Build & push
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
IMAGE="us-central1-docker.pkg.dev/<PROJECT_ID>/enterprise-rag/enterprise-rag:latest"
docker build -t "$IMAGE" -f ../../../Dockerfile ../../..
docker push "$IMAGE"

# 3) Cloud Run service (name: enterprise-rag)
terraform apply -var="project_id=<PROJECT_ID>" -var="region=us-central1" -var="image_tag=latest"
```

## Deploy Strict (review_mode=strict) — coexists with Demo

Separate Cloud Run service name (`enterprise-rag-strict`) so Demo is not overwritten.

```bash
# From repo root (mints secret if unset):
./scripts/deploy_strict_gcp.sh <PROJECT_ID>

# Or manually:
SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
terraform apply -var="project_id=<PROJECT_ID>" -var="region=us-central1" \
  -var="production_strict=true" -var="rag_jwt_secret=$SECRET"
# service_name defaults to enterprise-rag-strict when production_strict=true
```

Then:

```bash
export RAG_JWT_SECRET="$SECRET"
curl -sS "$(terraform output -raw service_url)/health" | python3 -m json.tool
# expect review_mode=strict
TOKEN=$(python3 ../../../scripts/mint_panel_jwt.py)
# spoof check from docs/STRICT_PANEL_PACK.md
```

## Verify

```bash
curl -sS "$(terraform output -raw service_url)/health" | python3 -m json.tool
```

## Tear down / idle

```bash
# Preferred for receipts day:
terraform destroy -var="project_id=<PROJECT_ID>" -var="region=us-central1" \
  -var="production_strict=true"   # if destroying Strict workspace/state

# Or leave Cloud Run with min instances 0 (≈$0) and delete later
```

Use **separate Terraform workspaces** (`terraform workspace new strict`) if you keep Demo + Strict state side by side.

## Panel honesty (Render Free interim)

- Do not claim Render Free Demo is always-on.
- Prefer this GCP Strict URL or `./scripts/run_strict_local.sh` for JWT anti-spoof in panels.
- After Render Starter: prefer warm Render Demo + Render Strict twin.

See [docs/STRICT_PANEL_PACK.md](../../../docs/STRICT_PANEL_PACK.md).
