# ============================================================================
# Terraform Configuration — R.A.D.A.R Pangan
# ============================================================================
# Manages GCP BigQuery infrastructure for the data warehouse layer.
# Raw, staging, and marts data live in BigQuery (free tier: 10 GB + 1 TB/mo).
# Application data (users, HET, ML predictions) stays in Supabase PostgreSQL.
#
# Usage:
#   cd infra/
#   terraform init
#   terraform plan
#   terraform apply
# ============================================================================

terraform {
  required_version = "~> 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.40"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}


# ── Enable Required APIs ─────────────────────────────────────────────────────
# Ensures BigQuery API is enabled before creating resources.
# disable_on_destroy = false → API stays enabled even after terraform destroy.

resource "google_project_service" "bigquery" {
  project            = var.project_id
  service            = "bigquery.googleapis.com"
  disable_on_destroy = false
}
