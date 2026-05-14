# ============================================================================
# Input Variables
# ============================================================================

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "asia-southeast2" # Jakarta
}

variable "bq_location" {
  description = "BigQuery dataset location"
  type        = string
  default     = "asia-southeast2" # Jakarta — lower latency for Indonesia
}
