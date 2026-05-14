# ============================================================================
# Outputs
# ============================================================================

output "project_id" {
  description = "GCP project ID"
  value       = var.project_id
}

output "bq_location" {
  description = "BigQuery dataset location"
  value       = var.bq_location
}

output "datasets" {
  description = "BigQuery dataset IDs"
  value = {
    raw     = google_bigquery_dataset.raw.dataset_id
    staging = google_bigquery_dataset.staging.dataset_id
    marts   = google_bigquery_dataset.marts.dataset_id
  }
}

output "raw_tables" {
  description = "All raw table full IDs (project.dataset.table)"
  value = {
    harga_pangan    = "${var.project_id}.raw.${google_bigquery_table.harga_pangan.table_id}"
    cuaca_harian    = "${var.project_id}.raw.${google_bigquery_table.cuaca_harian.table_id}"
    dim_provinsi    = "${var.project_id}.raw.${google_bigquery_table.dim_provinsi.table_id}"
    dim_kota        = "${var.project_id}.raw.${google_bigquery_table.dim_kota.table_id}"
    hari_besar      = "${var.project_id}.raw.${google_bigquery_table.hari_besar.table_id}"
    pipeline_log    = "${var.project_id}.raw.${google_bigquery_table.pipeline_log.table_id}"
    inflasi_bulanan = "${var.project_id}.raw.${google_bigquery_table.inflasi_bulanan.table_id}"
    musim_panen     = "${var.project_id}.raw.${google_bigquery_table.musim_panen.table_id}"
  }
}
