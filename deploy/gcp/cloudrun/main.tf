terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" {
  type        = string
  description = "GCP project id"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "production_strict" {
  type    = bool
  default = false
}

variable "rag_jwt_secret" {
  type      = string
  default   = ""
  sensitive = true
}

resource "google_project_service" "run" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "erag" {
  repository_id = "enterprise-rag"
  location      = var.region
  format        = "DOCKER"
  depends_on    = [google_project_service.artifactregistry]
}

locals {
  image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.erag.repository_id}/enterprise-rag:${var.image_tag}"
}

resource "google_service_account" "erag" {
  account_id   = "enterprise-rag-run"
  display_name = "Enterprise RAG Cloud Run"
}

resource "google_cloud_run_v2_service" "erag" {
  name     = "enterprise-rag"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.erag.email
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = local.image
      ports {
        container_port = 8080
      }
      env {
        name  = "PRODUCTION_STRICT"
        value = var.production_strict ? "true" : "false"
      }
      dynamic "env" {
        for_each = var.production_strict && var.rag_jwt_secret != "" ? [1] : []
        content {
          name  = "RAG_JWT_SECRET"
          value = var.rag_jwt_secret
        }
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  depends_on = [google_project_service.run]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.erag.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "service_url" {
  value = google_cloud_run_v2_service.erag.uri
}

output "image" {
  value = local.image
}

output "push_commands" {
  value = <<-EOT
    gcloud auth configure-docker ${var.region}-docker.pkg.dev --quiet
    docker build -t ${local.image} -f ../../../Dockerfile ../../..
    docker push ${local.image}
  EOT
}
