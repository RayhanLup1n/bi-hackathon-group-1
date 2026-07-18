# RCA Knowledge Base - Mapping Penyebab dan Rekomendasi

> **Status**: SINTETIS - Berdasarkan domain knowledge, riset akademik, dan framework BI
> **Disclaimer**: Mapping ini adalah panduan analisis, bukan SOP resmi TPID
> **Terakhir diperbarui**: Juli 2026

---

## 1. Ringkasan RCA Engine

R.A.D.A.R Pangan menggunakan Decision Tree RCA 4-step sequential (early exit):

```
CHECK 1: Hari Raya?
  |-- Ya --> DEMAND SPIKE (skip check 2-4)
  |-- Tidak --> CHECK 2

CHECK 2: Cuaca Ekstrem?
  |-- Ya --> GANGGUAN SUPPLY (skip check 3-4)
  |-- Tidak --> CHECK 3

CHECK 3: Persebaran Kota >= 60%?
  |-- Ya --> SUPPLY NASIONAL (skip check 4)
  |-- Tidak --> CHECK 4

CHECK 4: Stok Pedagang Normal?
  |-- Ya --> BOTTLENECK DISTRIBUSI
  |-- Tidak --> PENYEBAB BELUM TERIDENTIFIKASI
```

---

## 2. Diagnosis Templates

### 2.1 DEMAND - Demand Spike (Hari Raya)

| Aspek | Detail |
|-------|--------|
| **Trigger** | Ada hari besar dalam H-14 s/d H+3 |
| **Diagnosis** | Lonjakan permintaan menjelang hari raya |
| **Sifat** | Musiman, siklikal, biasanya koreksi sendiri |
| **Durasi tipikal** | 2-4 minggu |

**Pola Historis Demand Spike per Hari Raya**:

| Hari Raya | Window Dampak | Komoditas Terdampak | Magnitude Kenaikan |
|-----------|--------------|--------------------|--------------------|
| Ramadan (H-14 s/d H) | 2-3 minggu sebelum | Cabai, Bawang Merah | 15-40% |
| Idul Fitri (H-3 s/d H+3) | 1 minggu sekitar | Semua komoditas | 20-50% |
| Idul Adha | 1-2 minggu sebelum | Bawang Merah, Cabai | 10-25% |
| Natal + Tahun Baru | 2 minggu sebelum | Bawang Putih, Cabai | 10-30% |
| Imlek | 1 minggu sebelum | Bawang Putih, Cabai Merah | 10-20% |
| Nyepi | Minimal | Dampak terlokalisir di Bali | 5-10% |

**Rekomendasi Aksi**:

| Severity | Aksi | Rasionalisasi |
|----------|------|---------------|
| L1 (1 indikator) | Pantau saja, jangan intervensi | Demand spike musiman, akan koreksi sendiri |
| L2 (2 indikator) | Monitor intensif + siapkan stok distribusi | Demand tinggi + faktor lain |
| L3-L4 (3-4 indikator) | Operasi pasar di titik keramaian | Multiple trigger bersamaan |

**Hal yang TIDAK efektif saat demand spike**:
- Balancing stock (masalah bukan di supply, tapi demand memang tinggi)
- Impor darurat (lead time terlalu lama untuk event musiman 2-4 minggu)

---

### 2.2 SUPPLY - Gangguan Supply (Cuaca Ekstrem)

| Aspek | Detail |
|-------|--------|
| **Trigger** | Cuaca ekstrem terdeteksi di daerah produksi |
| **Diagnosis** | Gangguan panen atau distribusi akibat cuaca |
| **Sifat** | Tidak dapat diprediksi jauh, dampak bisa berkepanjangan |
| **Durasi tipikal** | 4-12 minggu (tergantung severity) |

**Threshold Cuaca Ekstrem (Open-Meteo)**:

| Parameter | Threshold | Dampak |
|-----------|-----------|--------|
| Curah hujan | > 100mm/hari | Banjir, gagal panen, gangguan logistik |
| Kekeringan | > 14 hari berturut-turut < 1mm | Gagal panen cabai, bawang merah |
| Suhu ekstrem | > 38C | Stress tanaman, penurunan produksi |
| Angin kencang | > 60 km/h | Kerusakan tanaman, gangguan transportasi |

**Korelasi Cuaca-Komoditas**:

| Fenomena | Komoditas Paling Terdampak | Lag (hari) | Magnitude |
|----------|--------------------------|------------|-----------|
| El Nino (kemarau) | Cabai Rawit, Bawang Merah | 30-60 | +30-80% |
| La Nina (hujan lebat) | Cabai Merah Besar, Bawang Merah | 14-30 | +20-50% |
| Banjir regional | Semua komoditas (distribusi) | 3-7 | +15-40% |
| Kekeringan lokal | Cabai (semua jenis) | 21-45 | +25-60% |

**Rekomendasi Aksi per Severity**:

| Severity | Aksi | Detail |
|----------|------|--------|
| L1 | Monitor cuaca + pantau stok | Siaga dini, belum ada dampak terlihat |
| L2 | Koordinasi Bulog/Kementan | Cek stok buffer nasional, identifikasi daerah surplus |
| L3 | Relokasi stok + pertimbangkan impor | Pindahkan stok dari daerah tidak terdampak |
| L4 | Impor darurat fast-track | Percepat izin impor untuk komoditas kritis |

---

### 2.3 SUPPLY - Kenaikan Serempak Antar Kota

| Aspek | Detail |
|-------|--------|
| **Trigger** | >= 60% kota mengalami kenaikan harga serempak |
| **Diagnosis** | Masalah supply nasional, bukan lokal |
| **Sifat** | Sistemik, memerlukan koordinasi nasional |
| **Durasi tipikal** | 4-8 minggu |

**Interpretasi Persebaran**:

| % Kota Naik | Interpretasi | Implikasi |
|-------------|-------------|-----------|
| < 30% | Kenaikan terlokalisir | Masalah distribusi lokal |
| 30-59% | Kenaikan mulai menyebar | Perlu monitoring intensif |
| 60-79% | Kenaikan meluas | Indikasi supply nasional terganggu |
| >= 80% | Kenaikan serempak nasional | Intervensi nasional diperlukan |

**Rekomendasi**:
- Identifikasi kota-kota yang belum naik sebagai sumber supply alternatif
- Koordinasi TPID lintas provinsi
- Eskalasi ke TPI Pusat jika melibatkan > 2 provinsi

---

### 2.4 DISTRIBUSI - Bottleneck Distribusi Lokal

| Aspek | Detail |
|-------|--------|
| **Trigger** | Kenaikan terlokalisir + stok normal + tanpa cuaca/hari raya |
| **Diagnosis** | Hambatan rantai distribusi lokal |
| **Sifat** | Bisa diperbaiki relatif cepat |
| **Durasi tipikal** | 1-3 minggu |

**Penyebab Umum Bottleneck Distribusi**:

| Penyebab | Indikator | Solusi |
|----------|-----------|--------|
| Infrastruktur jalan rusak | Kenaikan di kota terpencil | Fasilitasi logistik alternatif |
| Gangguan pelabuhan/terminal | Kenaikan di kota pelabuhan | Koordinasi dengan Dishub |
| Spekulasi pedagang | Kenaikan tanpa alasan fundamental | Sidak pasar, koordinasi Satgas Pangan |
| Biaya transportasi naik | Kenaikan BBM/tol baru | Subsidi transportasi distribusi |

**Rekomendasi**:
- Balancing stock dari daerah surplus terdekat
- Identifikasi jalur distribusi alternatif
- Cek kondisi jalan atau isu logistik lokal

---

### 2.5 EKSPEKTASI - Tekanan Inflasi Ekspektatif

| Aspek | Detail |
|-------|--------|
| **Trigger** | Anomali harga tanpa trigger RCA apapun |
| **Diagnosis** | Kenaikan didorong ekspektasi pasar |
| **Sifat** | Bisa menjadi self-fulfilling prophecy |
| **Durasi tipikal** | 2-6 minggu |

**Indikator Inflasi Ekspektatif**:
- Inflasi bulanan positif >= 3 bulan berturut-turut
- Tidak ada gangguan supply, cuaca, atau demand
- Pedagang menaikkan harga secara preventif

**Rekomendasi**:
- Komunikasi publik dan transparansi harga
- Operasi pasar terbatas di titik strategis
- Koordinasi Satgas Pangan untuk penertiban jika ada spekulasi

---

### 2.6 UNKNOWN - Penyebab Belum Teridentifikasi

| Aspek | Detail |
|-------|--------|
| **Trigger** | Tidak ada trigger yang cukup kuat |
| **Diagnosis** | Membutuhkan investigasi manual |
| **Sifat** | Mungkin masih dalam batas wajar |

**Rekomendasi**:
- Tingkatkan frekuensi monitoring
- Survei lapangan untuk konfirmasi kondisi supply dan distribusi
- Jangan ambil keputusan intervensi tanpa data tambahan

---

## 3. Severity Scoring

Severity dihitung dari jumlah indikator aktif secara bersamaan (tidak early-exit):

| Indikator | Kode | Deskripsi |
|-----------|------|-----------|
| Anomali Harga | G1 | Delta harga >= threshold (default 10%) |
| Window Hari Raya | D1 | Dalam H-14 s/d H+3 hari besar |
| Cuaca Ekstrem | S1 | Cuaca ekstrem di daerah produksi |
| Stok Menipis | S3 | Stok < 60% kapasitas normal |
| Kenaikan Serempak | T2 | >= 60% kota mengalami kenaikan |

| Level | Indikator Aktif | Label | Aksi Minimum |
|-------|----------------|-------|-------------|
| L0 | 0 | Aman | Monitor rutin |
| L1 | 1 | Waspada | Monitor intensif |
| L2 | 2 | Awas | Verifikasi + koordinasi |
| L3 | 3 | Kritis | Eskalasi TPID |
| L4 | 4+ | Darurat | Intervensi segera |

---

## 4. Mapping Diagnosis ke Response Options

| Diagnosis | Risk Level | Confidence High | Confidence Medium | Confidence Low |
|-----------|-----------|----------------|------------------|----------------|
| DEMAND (L1) | Rendah | Monitor | Monitor | Monitor |
| DEMAND (L2+) | Sedang | Verifikasi | Verifikasi | Verifikasi |
| SUPPLY (L2) | Tinggi | Koordinasikan | Koordinasikan | Verifikasi |
| SUPPLY (L3+) | Kritis | Pertimbangkan Intervensi | Koordinasikan | Verifikasi |
| DISTRIBUSI | Sedang | Verifikasi | Verifikasi | Verifikasi |
| EKSPEKTASI | Tinggi | Koordinasikan | Koordinasikan | Verifikasi |
| UNKNOWN | Rendah | Monitor | Monitor | Monitor |

**Prinsip Confidence Cap**:
- Confidence LOW: maksimal rekomendasi = "Verifikasi" (jangan assertive tanpa data kuat)
- Confidence MEDIUM: maksimal = "Koordinasikan"
- Confidence HIGH: semua opsi tersedia sesuai risk level

---

## 5. Evidence Classification

Setiap rekomendasi dilengkapi evidence yang diklasifikasikan:

| Jenis Evidence | Label | Contoh |
|---------------|-------|--------|
| `fact` | Fakta | "Harga Rp 45,000/kg (PIHPS, 2026-05-26)" |
| `model_output` | Output Model | "Forecast P90: Rp 52,000 dalam 14 hari" |
| `possible_factor` | Faktor Kemungkinan | "Idul Fitri dalam 10 hari" |
| `missing_information` | Informasi Kurang | "Data stok pedagang tidak tersedia" |
