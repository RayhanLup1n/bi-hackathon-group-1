# BI Hackathon Group 1 — Deteksi Inflasi Harga Pangan

Sistem deteksi inflasi berdasarkan HET (Harga Eceran Tertinggi) per wilayah menggunakan data harga pangan dari **Bank Indonesia PIHPS**.

**Cakupan wilayah:** Jawa Barat & DKI Jakarta (10 kota)  
**Sumber data:** https://www.bi.go.id/hargapangan

---

## Struktur Project

```
bi-hackathon-group-1/
├── etl/            ← Data pipeline (Airflow + DuckDB + dbt)
└── README.md
```

## Komponen

### `etl/` — Data Pipeline

Pipeline end-to-end untuk ekstraksi, transformasi, dan penyimpanan data harga pangan.

- **Extraction:** API scraping dari BI PIHPS (21 komoditas, 10 kota, data harian sejak 2020)
- **Storage:** DuckDB (file-based OLAP database)
- **Transformation:** dbt (staging → mart layer)
- **Orchestration:** Apache Airflow (2 DAG: modelling + dashboard)
- **Deployment:** Docker Compose (3 service: scheduler, webserver, postgres)

Lihat [`etl/README.md`](etl/README.md) untuk dokumentasi lengkap, cara setup, dan cara akses data.

### Quick Access Data

Setelah pipeline berjalan, data bisa diakses langsung:

```bash
# Masuk ke DuckDB CLI
cd etl
docker exec -it pihps-airflow-scheduler duckdb /opt/airflow/data/pihps.duckdb

# Query data modelling (ML-ready)
SELECT * FROM marts.mart_modelling_harga_pangan LIMIT 10;

# Query data dashboard
SELECT * FROM marts.mart_dashboard_harga_pangan LIMIT 10;

# Export ke CSV
COPY marts.mart_modelling_harga_pangan TO '/opt/airflow/data/export.csv' (HEADER);
```

```bash
# Copy hasil export ke lokal
docker cp pihps-airflow-scheduler:/opt/airflow/data/export.csv ./
```

Atau copy seluruh database dan buka dengan Python:

```python
import duckdb
conn = duckdb.connect("pihps.duckdb", read_only=True)
df = conn.execute("SELECT * FROM marts.mart_modelling_harga_pangan").fetchdf()
```

Lihat [`etl/README.md`](etl/README.md) untuk opsi akses lengkap.
