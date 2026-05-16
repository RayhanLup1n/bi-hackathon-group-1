# Demo Scenarios — R.A.D.A.R Pangan v0.4

Tanggal: 9 Mei 2026

## Quick Start

```bash
cd B:\project\bi-hackathon-group-1
uv run uvicorn main:app --reload
# Open: http://localhost:8000
# Login: admin / admin123
```

## Scenario 1: Hari Raya (Demand Spike)

**sim_date**: `2026-03-13` (H-7 sebelum Idul Fitri 2026-03-20)

**Yang terjadi**:
- RCA Check 1 **TRIGGERED**: "Idul Fitri dalam 7 hari"
- Diagnosis: **Demand Spike**
- Rekomendasi: "Pantau saja. Balancing stock tidak efektif."

**Cerita demo**:
> "Pada tanggal 13 Maret 2026, sistem mendeteksi bahwa Idul Fitri tinggal 7 hari lagi.
> Harga cabai naik +5.7% — ini pola musiman yang normal.
> Rekomendasi: pantau saja, bukan masalah supply."

**Komoditas**: Cabai Merah Besar, Bawang Merah


## Scenario 2: Cuaca Extreme (Supply Disruption)

**sim_date**: `2021-01-09` (hujan lebat 155mm di Cirebon)

**Yang terjadi**:
- RCA Check 1: Clear (bukan hari raya)
- RCA Check 2 **TRIGGERED**: "Hujan lebat (155mm) terdeteksi di Cirebon"
- Diagnosis: **Gangguan Supply**
- Rekomendasi: "Koordinasi ke Bulog/Kementan untuk cek stok buffer nasional."

**Cerita demo**:
> "Pada 9 Januari 2021, curah hujan 155mm tercatat di Cirebon — jauh melebihi ambang 100mm.
> Ini cuaca ekstrem yang berpotensi mengganggu panen dan distribusi.
> Sistem otomatis merekomendasikan koordinasi dengan Bulog."

**Komoditas**: Cabai Merah Besar, Bawang Merah


## Scenario 3: HET Monitoring

**sim_date**: `2026-05-01`

**Yang terjadi**:
- **Bawang Merah**: MELAMPAUI HET (Rp 46.275 vs HET Rp 40.000 = 115.7%)
- **Cabai Rawit Merah**: WASPADA (Rp 61.140 vs HET Rp 70.000 = 87.3%)
- Summary: 2 MELAMPAUI, 4 WASPADA, 0 AMAN

**Cerita demo**:
> "Per 1 Mei 2026, bawang merah sudah melampaui HET 15.7% — perlu intervensi segera.
> Sementara cabai rawit merah masih dalam zona waspada di 87% HET.
> Dashboard menampilkan status real-time untuk semua 6 komoditas."


## Scenario 4: Normal Day

**sim_date**: `2025-09-15`

**Yang terjadi**:
- Semua 4 check: Clear
- Diagnosis: **Bottleneck Distribusi Lokal**
- Harga stabil, tidak ada trigger

**Cerita demo**:
> "Pada hari normal tanpa hari raya atau cuaca ekstrem, kenaikan harga kecil
> biasanya disebabkan bottleneck distribusi lokal — bukan masalah nasional."


## API Endpoints untuk Demo

| Endpoint | Fungsi |
|----------|--------|
| `GET /api/commodities/detail` | List 6 komoditas MVP |
| `GET /api/commodity/{key}?sim_date=X` | Data + cuaca + sinyal |
| `GET /api/rca/{key}?sim_date=X` | RCA analysis dengan 4-step checklist |
| `GET /api/het/{key}?sim_date=X` | HET status (AMAN/WASPADA/KRITIS/MELAMPAUI) |
| `GET /api/het/summary?sim_date=X` | Ringkasan HET semua komoditas |
| `GET /api/cuaca/{prov_id}?sim_date=X` | Data cuaca per provinsi |
| `GET /api/prices/{comcat_id}/history` | Chart harga 30 hari |

## Komoditas Keys

| Key | Nama |
|-----|------|
| `bawang_merah_ukuran_sedang` | Bawang Merah |
| `bawang_putih_ukuran_sedang` | Bawang Putih |
| `cabai_merah_besar` | Cabai Merah Besar |
| `cabai_merah_keriting` | Cabai Merah Keriting |
| `cabai_rawit_hijau` | Cabai Rawit Hijau |
| `cabai_rawit_merah` | Cabai Rawit Merah |
