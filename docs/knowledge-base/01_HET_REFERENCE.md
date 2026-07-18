# HET Reference - Harga Eceran Tertinggi Komoditas Pangan

> **Status**: SINTETIS - Estimasi berdasarkan observasi pasar dan berita Bapanas
> **Disclaimer**: Bukan data resmi Bapanas. Perlu validasi dengan Permendag/Perban terbaru.
> **Terakhir diperbarui**: Juli 2026

---

## 1. Dasar Hukum

| Regulasi | Tentang | Relevansi |
|----------|---------|-----------|
| UU No. 18/2012 | Pangan | Dasar hukum utama stabilisasi harga |
| PP No. 17/2015 | Ketahanan Pangan dan Gizi | Turunan UU Pangan |
| Perpres No. 66/2021 | Badan Pangan Nasional | Pembentukan Bapanas |
| Perpres No. 125/2022 | Stabilisasi Pasokan dan Harga Pangan Pokok | Framework stabilisasi |
| Permendag (periodik) | HAP/HET komoditas spesifik | Penetapan ceiling/floor price |

---

## 2. HET Reference per Komoditas (MVP - 6 Komoditas)

### 2.1 Zona Nasional (Default)

Harga dalam Rp/kg. Berlaku sebagai acuan nasional, dengan variasi regional di Section 2.2.

| Komoditas | Kode | HET (Rp/kg) | HAP Beli (Rp/kg) | HAP Jual (Rp/kg) | Catatan |
|-----------|------|-------------|-------------------|-------------------|---------|
| Bawang Merah | com_11 | 40,000 | 25,000 | 38,000 | Fluktuatif musiman, puncak Ramadan |
| Bawang Putih | com_12 | 45,000 | 30,000 | 43,000 | 80% impor, sensitif kurs |
| Cabai Merah Besar | com_13 | 55,000 | 30,000 | 50,000 | Sangat volatil, korelasi cuaca tinggi |
| Cabai Merah Keriting | com_14 | 50,000 | 28,000 | 48,000 | Pola serupa Cabai Merah Besar |
| Cabai Rawit Hijau | com_15 | 60,000 | 35,000 | 58,000 | Musiman, off-season harga bisa 3x |
| Cabai Rawit Merah | com_16 | 70,000 | 40,000 | 65,000 | Paling volatil, kenaikan bisa 200%+ |

**Keterangan**:
- **HET**: Harga Eceran Tertinggi - batas atas harga konsumen
- **HAP Beli**: Harga Acuan Pembelian - floor price di petani/pedagang besar
- **HAP Jual**: Harga Acuan Penjualan - ceiling price di pasar ritel

### 2.2 Variasi Regional

Faktor koreksi HET per wilayah berdasarkan biaya logistik dan ketersediaan lokal:

| Provinsi | Faktor Koreksi | Alasan |
|----------|---------------|--------|
| DKI Jakarta | 1.00x (base) | Pusat distribusi nasional |
| Jawa Barat | 0.95x | Dekat sentra produksi bawang dan cabai |
| Banten | 1.05x | Biaya logistik tambahan dari sentra |
| Sulawesi Selatan | 1.10x | Jarak distribusi lebih jauh, biaya logistik tinggi |

**Contoh**: HET Cabai Rawit Merah di Sulawesi Selatan = 70,000 x 1.10 = Rp 77,000/kg

### 2.3 HET yang Dihitung per Wilayah

| Komoditas | DKI Jakarta | Jawa Barat | Banten | Sulawesi Selatan |
|-----------|-------------|------------|--------|------------------|
| Bawang Merah | 40,000 | 38,000 | 42,000 | 44,000 |
| Bawang Putih | 45,000 | 42,750 | 47,250 | 49,500 |
| Cabai Merah Besar | 55,000 | 52,250 | 57,750 | 60,500 |
| Cabai Merah Keriting | 50,000 | 47,500 | 52,500 | 55,000 |
| Cabai Rawit Hijau | 60,000 | 57,000 | 63,000 | 66,000 |
| Cabai Rawit Merah | 70,000 | 66,500 | 73,500 | 77,000 |

---

## 3. Threshold Monitoring

Status monitoring berdasarkan perbandingan harga aktual vs HET:

| Status | Threshold | Aksi yang Disarankan |
|--------|-----------|---------------------|
| **AMAN** | < 80% HET | Monitor rutin, tidak ada aksi khusus |
| **WASPADA** | >= 80% HET | Tingkatkan frekuensi monitoring, verifikasi data |
| **KRITIS** | >= 95% HET | Koordinasi dengan dinas terkait, siapkan operasi pasar |
| **MELAMPAUI** | > 100% HET | Eskalasi ke TPID, pertimbangkan intervensi segera |

---

## 4. Pola Historis Harga (Observasi)

### 4.1 Pola Musiman Cabai Rawit Merah

| Bulan | Pola Harga | Penyebab |
|-------|-----------|----------|
| Jan-Feb | TINGGI | Off-season, musim hujan, permintaan tinggi (Imlek, Valentine) |
| Mar-Apr | SANGAT TINGGI | Puncak Ramadan, stok menipis |
| Mei-Jun | TURUN | Pasca Ramadan, mulai panen raya |
| Jul-Agu | RENDAH | Panen raya, supply melimpah |
| Sep-Okt | NAIK PERLAHAN | Panen berkurang, permintaan stabil |
| Nov-Des | TINGGI | Natal, Tahun Baru, off-season dimulai |

### 4.2 Korelasi Antar Komoditas

| Komoditas A | Komoditas B | Korelasi | Catatan |
|------------|------------|----------|---------|
| Cabai Merah Besar | Cabai Merah Keriting | 0.92 (sangat tinggi) | Substitusi langsung |
| Cabai Rawit Hijau | Cabai Rawit Merah | 0.88 (tinggi) | Substitusi langsung |
| Bawang Merah | Cabai Merah Besar | 0.65 (sedang) | Sering naik bersamaan di musim tertentu |
| Bawang Putih | Bawang Merah | 0.45 (rendah) | Bawang putih lebih dipengaruhi impor |

---

## 5. Sumber Data dan Validasi

| Sumber | URL | Status |
|--------|-----|--------|
| JDIH Bapanas | https://jdih.badanpangan.go.id/ | Regulasi tersedia |
| Portal PIHPS | https://www.bi.go.id/hargapangan/ | Data harga harian tersedia |
| Open Data Bapanas | https://data.badanpangan.go.id/ | Data terbatas |
| Katalog Data Nasional | https://katalog.data.go.id/ | Referensi metadata |

**Rekomendasi validasi**: Cross-check HET reference dengan data PIHPS real (619K rows)
untuk menentukan apakah threshold yang digunakan realistis terhadap distribusi harga aktual.

---

## 6. Penggunaan di R.A.D.A.R Pangan

### 6.1 HET Monitor Engine
- Input: `comcat_id` + `current_price`
- Proses: Bandingkan harga vs HET reference dari tabel ini
- Output: `HETResult` dengan status AMAN/WASPADA/KRITIS/MELAMPAUI

### 6.2 Priority Engine
- Signal `price_position` = `het_pct / 120.0` (cap 1.0)
- Weight: 25% dari total priority score

### 6.3 Rekomendasi ke Pengguna
- Status WASPADA: "Verifikasi harga dan data"
- Status KRITIS: "Koordinasikan tinjauan dengan dinas terkait"
- Status MELAMPAUI: "Eskalasi untuk evaluasi intervensi oleh pengambil keputusan TPID"
