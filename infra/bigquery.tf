# ============================================================================
# BigQuery Datasets + Tables
# ============================================================================
# Three-layer data warehouse architecture:
#   raw.*     — ETL raw extracts (tables created here, data loaded by ETL)
#   staging.* — Cleaned/validated views (created by dbt, dataset created here)
#   marts.*   — Aggregated tables for analytics/ML (created by dbt, dataset here)
#
# Cost: $0 — all within BigQuery free tier (10 GB storage, 1 TB queries/month)
# ============================================================================


# ── Datasets ─────────────────────────────────────────────────────────────────

resource "google_bigquery_dataset" "raw" {
  dataset_id    = "raw"
  friendly_name = "Raw Data Layer"
  description   = "Raw extracts from ETL pipeline (PIHPS prices, Open-Meteo weather, holidays)"
  location      = var.bq_location

  depends_on = [google_project_service.bigquery]

  labels = {
    env     = "production"
    project = "radar-pangan"
    layer   = "raw"
  }
}

resource "google_bigquery_dataset" "staging" {
  dataset_id    = "staging"
  friendly_name = "Staging Layer"
  description   = "Cleaned and validated data — managed by dbt (do not edit manually)"
  location      = var.bq_location

  depends_on = [google_project_service.bigquery]

  labels = {
    env     = "production"
    project = "radar-pangan"
    layer   = "staging"
  }
}

resource "google_bigquery_dataset" "marts" {
  dataset_id    = "marts"
  friendly_name = "Marts Layer"
  description   = "Aggregated tables for dashboard and ML modelling — managed by dbt"
  location      = var.bq_location

  depends_on = [google_project_service.bigquery]

  labels = {
    env     = "production"
    project = "radar-pangan"
    layer   = "marts"
  }
}


# ── raw.harga_pangan ─────────────────────────────────────────────────────────
# Daily commodity prices from BI PIHPS. Largest table (~619K+ rows).
# Partitioned by tanggal (date) for query cost optimization.
# Clustered by comcat_id, provinsi_id, kota_id for common filter patterns.

resource "google_bigquery_table" "harga_pangan" {
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "harga_pangan"
  description         = "Daily commodity prices from BI PIHPS (619K+ rows, 4 provinsi, 18 kota)"
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "tanggal"
  }

  # Prevent accidental full table scan — queries MUST filter by tanggal
  require_partition_filter = true

  clustering = ["comcat_id", "provinsi_id", "kota_id"]

  schema = jsonencode([
    { name = "id",              type = "INT64",     mode = "REQUIRED",  description = "Auto-increment ID" },
    { name = "tanggal",         type = "DATE",      mode = "REQUIRED",  description = "Tanggal harga (partition key)" },
    { name = "comcat_id",       type = "STRING",    mode = "REQUIRED",  description = "Commodity category ID (e.g. com_13)" },
    { name = "komoditas_nama",  type = "STRING",    mode = "REQUIRED",  description = "Nama komoditas (e.g. Cabai Merah Besar)" },
    { name = "pasar_tipe",      type = "INT64",     mode = "REQUIRED",  description = "Tipe pasar (1=Tradisional, 2=Modern, 3=Besar, 4=Produsen)" },
    { name = "provinsi_id",     type = "INT64",     mode = "REQUIRED",  description = "ID provinsi PIHPS" },
    { name = "provinsi_nama",   type = "STRING",    mode = "REQUIRED",  description = "Nama provinsi" },
    { name = "kota_id",         type = "INT64",     mode = "REQUIRED",  description = "ID kota PIHPS" },
    { name = "kota_nama",       type = "STRING",    mode = "REQUIRED",  description = "Nama kota/kabupaten" },
    { name = "pasar_nama",      type = "STRING",    mode = "NULLABLE",  description = "Nama pasar (optional)" },
    { name = "harga",           type = "FLOAT64",   mode = "REQUIRED",  description = "Harga per satuan (Rp)" },
    { name = "satuan",          type = "STRING",    mode = "REQUIRED",  description = "Satuan ukuran (default: kg)" },
    { name = "_extracted_at",   type = "TIMESTAMP", mode = "NULLABLE",  description = "Waktu data di-extract oleh ETL" },
    { name = "_source",         type = "STRING",    mode = "NULLABLE",  description = "Sumber data (bi_pihps)" },
  ])
}


# ── raw.cuaca_harian ─────────────────────────────────────────────────────────
# Daily weather data from Open-Meteo API. Used by RCA engine for weather checks.
# Partitioned by tanggal, clustered by provinsi_id for RCA query pattern.

resource "google_bigquery_table" "cuaca_harian" {
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "cuaca_harian"
  description         = "Daily weather data from Open-Meteo (11K+ rows, 5 lokasi)"
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "tanggal"
  }

  clustering = ["provinsi_id"]

  schema = jsonencode([
    { name = "id",                      type = "INT64",     mode = "REQUIRED",  description = "Auto-increment ID" },
    { name = "tanggal",                 type = "DATE",      mode = "REQUIRED",  description = "Tanggal cuaca (partition key)" },
    { name = "lokasi_label",            type = "STRING",    mode = "REQUIRED",  description = "Label lokasi (e.g. Bandung, Jakarta)" },
    { name = "provinsi_id",             type = "INT64",     mode = "REQUIRED",  description = "ID provinsi terkait" },
    { name = "latitude",                type = "FLOAT64",   mode = "REQUIRED",  description = "Latitude lokasi" },
    { name = "longitude",               type = "FLOAT64",   mode = "REQUIRED",  description = "Longitude lokasi" },
    { name = "precipitation_sum",       type = "FLOAT64",   mode = "NULLABLE",  description = "Total curah hujan (mm)" },
    { name = "rain_sum",                type = "FLOAT64",   mode = "NULLABLE",  description = "Total hujan (mm)" },
    { name = "temperature_max",         type = "FLOAT64",   mode = "NULLABLE",  description = "Suhu maksimum (°C)" },
    { name = "temperature_min",         type = "FLOAT64",   mode = "NULLABLE",  description = "Suhu minimum (°C)" },
    { name = "wind_speed_max",          type = "FLOAT64",   mode = "NULLABLE",  description = "Kecepatan angin maksimum (km/h)" },
    { name = "et0_evapotranspiration",  type = "FLOAT64",   mode = "NULLABLE",  description = "Evapotranspirasi referensi (mm)" },
    { name = "sunshine_duration",       type = "FLOAT64",   mode = "NULLABLE",  description = "Durasi sinar matahari (detik)" },
    { name = "_extracted_at",           type = "TIMESTAMP", mode = "NULLABLE",  description = "Waktu data di-extract" },
    { name = "_source",                 type = "STRING",    mode = "NULLABLE",  description = "Sumber data (open_meteo)" },
  ])
}


# ── raw.dim_provinsi ─────────────────────────────────────────────────────────

resource "google_bigquery_table" "dim_provinsi" {
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "dim_provinsi"
  description         = "Dimension table: provinsi (4 provinsi MVP)"
  deletion_protection = false

  schema = jsonencode([
    { name = "provinsi_id",     type = "INT64",     mode = "REQUIRED",  description = "ID provinsi PIHPS" },
    { name = "provinsi_nama",   type = "STRING",    mode = "REQUIRED",  description = "Nama provinsi" },
    { name = "_extracted_at",   type = "TIMESTAMP", mode = "NULLABLE",  description = "Waktu data di-extract" },
  ])
}


# ── raw.dim_kota ─────────────────────────────────────────────────────────────

resource "google_bigquery_table" "dim_kota" {
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "dim_kota"
  description         = "Dimension table: kota/kabupaten (18 kota MVP)"
  deletion_protection = false

  schema = jsonencode([
    { name = "kota_id",         type = "INT64",     mode = "REQUIRED",  description = "ID kota PIHPS" },
    { name = "kota_nama",       type = "STRING",    mode = "REQUIRED",  description = "Nama kota/kabupaten" },
    { name = "provinsi_id",     type = "INT64",     mode = "REQUIRED",  description = "FK ke dim_provinsi" },
    { name = "_extracted_at",   type = "TIMESTAMP", mode = "NULLABLE",  description = "Waktu data di-extract" },
  ])
}


# ── raw.hari_besar ───────────────────────────────────────────────────────────

resource "google_bigquery_table" "hari_besar" {
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "hari_besar"
  description         = "Hari libur nasional dan cuti bersama (python-holidays, 91 rows)"
  deletion_protection = false

  schema = jsonencode([
    { name = "id",        type = "INT64",   mode = "REQUIRED",  description = "Auto-increment ID" },
    { name = "tanggal",   type = "DATE",    mode = "REQUIRED",  description = "Tanggal hari besar" },
    { name = "nama",      type = "STRING",  mode = "REQUIRED",  description = "Nama hari besar" },
    { name = "kategori",  type = "STRING",  mode = "REQUIRED",  description = "Kategori (islam, kristen, nasional, cuti_bersama, lainnya)" },
    { name = "tahun",     type = "INT64",   mode = "REQUIRED",  description = "Tahun" },
  ])
}


# ── raw.pipeline_log ─────────────────────────────────────────────────────────

resource "google_bigquery_table" "pipeline_log" {
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "pipeline_log"
  description         = "Audit trail for ETL pipeline runs"
  deletion_protection = false

  time_partitioning {
    type  = "DAY"
    field = "started_at"
  }

  clustering = ["pipeline_name", "status"]

  schema = jsonencode([
    { name = "id",                type = "INT64",     mode = "REQUIRED",  description = "Auto-increment ID" },
    { name = "run_id",            type = "STRING",    mode = "REQUIRED",  description = "Unique run identifier" },
    { name = "pipeline_name",     type = "STRING",    mode = "REQUIRED",  description = "Nama pipeline" },
    { name = "tanggal_mulai",     type = "DATE",      mode = "NULLABLE",  description = "Tanggal mulai data range" },
    { name = "tanggal_selesai",   type = "DATE",      mode = "NULLABLE",  description = "Tanggal selesai data range" },
    { name = "records_inserted",  type = "INT64",     mode = "NULLABLE",  description = "Jumlah records yang di-insert" },
    { name = "status",            type = "STRING",    mode = "REQUIRED",  description = "Status run (running, success, failed)" },
    { name = "error_message",     type = "STRING",    mode = "NULLABLE",  description = "Error message jika gagal" },
    { name = "started_at",        type = "TIMESTAMP", mode = "NULLABLE",  description = "Waktu mulai run" },
    { name = "finished_at",       type = "TIMESTAMP", mode = "NULLABLE",  description = "Waktu selesai run" },
  ])
}


# ── raw.inflasi_bulanan ──────────────────────────────────────────────────────

resource "google_bigquery_table" "inflasi_bulanan" {
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "inflasi_bulanan"
  description         = "Monthly inflation rates per commodity (dummy data, 174 rows)"
  deletion_protection = false

  schema = jsonencode([
    { name = "id",            type = "INT64",   mode = "REQUIRED",  description = "Auto-increment ID" },
    { name = "tahun",         type = "INT64",   mode = "REQUIRED",  description = "Tahun" },
    { name = "bulan",         type = "INT64",   mode = "REQUIRED",  description = "Bulan (1-12)" },
    { name = "komoditas_id",  type = "STRING",  mode = "REQUIRED",  description = "ID komoditas (e.g. com_13)" },
    { name = "inflasi_mtm",   type = "FLOAT64", mode = "REQUIRED",  description = "Inflasi Month-to-Month (%)" },
    { name = "inflasi_ytd",   type = "FLOAT64", mode = "NULLABLE",  description = "Inflasi Year-to-Date (%)" },
    { name = "sumber",        type = "STRING",  mode = "NULLABLE",  description = "Sumber data (dummy/bps)" },
  ])
}


# ── raw.musim_panen ──────────────────────────────────────────────────────────

resource "google_bigquery_table" "musim_panen" {
  dataset_id          = google_bigquery_dataset.raw.dataset_id
  table_id            = "musim_panen"
  description         = "Harvest season calendar per commodity per region (18 rows)"
  deletion_protection = false

  schema = jsonencode([
    { name = "id",              type = "INT64",   mode = "REQUIRED",  description = "Auto-increment ID" },
    { name = "komoditas_id",    type = "STRING",  mode = "REQUIRED",  description = "ID komoditas (e.g. com_11)" },
    { name = "komoditas_nama",  type = "STRING",  mode = "REQUIRED",  description = "Nama komoditas" },
    { name = "bulan_mulai",     type = "INT64",   mode = "REQUIRED",  description = "Bulan mulai panen (1-12)" },
    { name = "bulan_selesai",   type = "INT64",   mode = "REQUIRED",  description = "Bulan selesai panen (1-12)" },
    { name = "daerah_utama",    type = "STRING",  mode = "REQUIRED",  description = "Daerah sentra produksi" },
    { name = "catatan",         type = "STRING",  mode = "NULLABLE",  description = "Catatan tambahan" },
  ])
}
