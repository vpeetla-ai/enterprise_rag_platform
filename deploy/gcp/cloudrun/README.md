# Enterprise RAG — GCP Cloud Run (Always Free–friendly)

Alternate deploy path to Render. **Primary warm Demo/Strict for panels stays on Render Starter.**

This stack uses the **memory retriever** (no Cloud SQL) so idle cost can stay near **$0** with `min_instance_count = 0`.

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

## Deploy

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

# 3) Cloud Run service
terraform apply -var="project_id=<PROJECT_ID>" -var="region=us-central1" -var="image_tag=latest"
```

## Verify

```bash
curl -sS "$(terraform output -raw service_url)/health" | python3 -m json.tool
```

## Tear down / idle

```bash
# Preferred for receipts day:
terraform destroy -var="project_id=<PROJECT_ID>" -var="region=us-central1"

# Or leave Cloud Run with min instances 0 (≈$0) and delete later
```

## Strict variant

Set `production_strict=true` and provide `rag_jwt_secret` via tfvars / env — or keep Strict on Render Starter for panels (recommended).
