# Session Log - 2026-05-23 - Kestra Pipeline Testing & BigQuery Reset

**Tanggal:** 23 Mei 2026
**Branch:** `feat/workflow-integration`
**Dikerjakan oleh:** Rayhan + Claude AI

---

## Ringkasan

Session ini melanjutkan pekerjaan migrasi Kestra dari session sebelumnya (22 Mei). Fokus:
1. Fix Terraform deletion_protection chicken-and-egg problem
2. Reset BigQuery data (destroy + recreate semua tables kosong)
3. Hapus `marts` dataset dari Terraform (dev mode: marts di Supabase saja)
4. Fix Kestra basic-auth configuration
5. Test full pipeline via Kestra UI
6. Fix null harga issue pada BigQuery batch load

---

## 1. Terraform BigQuery Reset

### Masalah
`terraform apply` gagal karena schema drift (FLOAT vs FLOAT64, INTEGER vs INT64) memaksa table replacement, tapi remote tables masih punya `deletion_protection=true`. Chicken-and-egg: tidak bisa apply perubahan karena harus destroy dulu, tapi destroy diblokir oleh deletion_protection.

### Solusi
1. Hapus 2 tabel bermasalah langsung via `bq rm -f -t`
2. `terraform apply` berhasil recreate 2 tabel
3. `terraform destroy` untuk semua resource
4. Error lagi: `staging` dan `marts` datasets "still in use" (berisi tabel dbt)
5. Tambah `delete_contents_on_destroy = true` di dataset staging
6. Hapus `marts` dataset dari Terraform (dev mode: marts hanya di Supabase)
7. `bq rm -r -f` untuk staging dan marts datasets
8. `terraform state rm` untuk resource yang sudah dihapus manual
9. `terraform apply` berhasil recreate semua (raw + staging + 8 tabel kosong)

### File Diubah
| File | Perubahan |
|------|-----------|
| `infra/bigquery.tf` | `deletion_protection = false`, `delete_contents_on_destroy = true` di staging, hapus `marts` dataset |
| `infra/outputs.tf` | Hapus reference ke `marts` dataset |

---

## 2. Kestra Basic-Auth Fix

### Masalah
Kestra UI tidak bisa login - beberapa masalah bertahap:
1. Username harus format email (bukan plain "admin")
2. Config path salah: `kestra.server.basic-auth` -> `kestra.security.basic-auth`
3. Password harus memenuhi requirement: 8+ chars, 1 uppercase, 1 lowercase, 1 number
4. Karakter `!` di YAML bisa di-parse sebagai YAML tag - perlu di-quote

### Solusi Final
```yaml
kestra:
  security:
    basic-auth:
      enabled: true
      username: admin@radar-pangan.local
      password: "Admin1234"
```

### File Diubah
| File | Perubahan |
|------|-----------|
| `docker-compose.yml` | Kestra basic-auth config fixed (email format, security path, password requirements) |

---

## 3. Full Pipeline Test via Kestra

### Hasil
- Pipeline berhasil dijalankan via Kestra UI (http://localhost:8080)
- Data fetching dari PIHPS API berjalan normal (log menunjukkan GET requests sukses)
- Ditemukan error pada beberapa batch: `Required field harga cannot be null`

### Root Cause
Data PIHPS kadang return `harga = null` (pasar tutup, data belum masuk). BigQuery schema mendefinisikan `harga` sebagai `REQUIRED` (NOT NULL), sehingga seluruh batch di-reject.

---

## 4. Fix Null Harga Issue

### Solusi
Tambah `dropna()` pada kolom REQUIRED sebelum load ke BigQuery + log warning.

### File Diubah
| File | Perubahan |
|------|-----------|
| `etl/scripts/load_historical.py` | Tambah `dropna(subset=required_cols)` di `_prepare_dataframe()`, re-assign IDs setelah drop |
| `etl/scripts/load_weather_historical.py` | Sama - tambah `dropna()` untuk kolom REQUIRED cuaca |

### Detail Fix
```python
# Drop rows with null REQUIRED fields (BQ rejects nulls on REQUIRED columns)
required_cols = ["tanggal", "comcat_id", "komoditas_nama", "provinsi_id", "kota_id", "harga", "satuan"]
existing_required = [c for c in required_cols if c in df.columns]
before = len(df)
df = df.dropna(subset=existing_required)
dropped = before - len(df)
if dropped > 0:
    logger.warning(f"Dropped {dropped} rows with null required fields (harga, etc.)")

# Re-assign sequential IDs after dropping rows
df["id"] = range(start_id, start_id + len(df))
```

---

## 5. Arsitektur Update: marts Hanya di Supabase

### Keputusan
Untuk development mode, `marts` dataset dihapus dari BigQuery Terraform:
- **BigQuery**: `raw` + `staging` saja (managed by Terraform)
- **Supabase PostgreSQL**: `marts` (gold layer) + `app.*` tables

dbt tetap bisa create `marts` dataset di BigQuery secara otomatis saat `dbt run --select marts` jika diperlukan, tapi tidak di-manage oleh Terraform.

---

## Sync Gold Script Behavior (Untuk Referensi)

| Script | Tabel Supabase | Strategi |
|--------|---------------|----------|
| `sync_gold_to_postgres.py` | `app.harga_pangan` | TRUNCATE + INSERT |
| `sync_gold_to_postgres.py` | `app.cuaca_harian` | TRUNCATE + INSERT |
| `sync_gold_to_postgres.py` | `app.hari_besar` | TRUNCATE + INSERT |
| `sync_musim_panen_to_supabase.py` | `app.musim_panen` | UPSERT (ON CONFLICT) |
| `sync_inflasi_bulanan_to_supabase.py` | `app.inflasi_bulanan` | UPSERT (ON CONFLICT) |

Data `app.users`, `app.het_reference`, `app.ml_predictions`, `app.komoditas_config` tidak terpengaruh.

---

## Status Pipeline (Belum Selesai)

Pipeline dihentikan sementara karena user ada urusan. Status terakhir:
- `extract_harga_historis`: running (beberapa batch error karena null harga, tapi continue ke batch berikutnya)
- Step 2-11: belum dijalankan

### Next Steps
1. Restart container setelah fix null harga di-apply (`docker compose --profile etl restart kestra`)
2. Reset BigQuery data lagi (karena ada partial data dari run yang gagal)
3. Re-run full pipeline dari awal
4. Verifikasi semua 11 steps hijau di Kestra UI
5. Verifikasi data di BigQuery (row counts)
6. Commit semua perubahan

---

## Commits Session Ini

Belum ada commit - menunggu testing selesai sebelum commit.

### Perubahan Pending (Belum Di-commit)
- `infra/bigquery.tf` - deletion_protection false, delete_contents_on_destroy, hapus marts
- `infra/outputs.tf` - hapus marts reference
- `docker-compose.yml` - Kestra basic-auth fix
- `etl/scripts/load_historical.py` - dropna() untuk null REQUIRED fields
- `etl/scripts/load_weather_historical.py` - dropna() untuk null REQUIRED fields
