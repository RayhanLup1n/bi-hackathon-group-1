# Weather Impact Matrix - Korelasi Cuaca, Komoditas, dan Wilayah

> **Status**: SINTETIS - Berdasarkan riset agronomis, data Open-Meteo, dan observasi lapangan
> **Disclaimer**: Magnitude dan lag time adalah estimasi. Perlu kalibrasi dengan data PIHPS real.
> **Terakhir diperbarui**: Juli 2026

---

## 1. Parameter Cuaca yang Dimonitor

Sumber data: Open-Meteo Historical Weather API (`archive-api.open-meteo.com`)

| Parameter | Unit | Variabel API | Frekuensi |
|-----------|------|-------------|-----------|
| Curah hujan | mm/hari | `precipitation_sum` | Harian |
| Suhu maksimum | Celsius | `temperature_2m_max` | Harian |
| Suhu minimum | Celsius | `temperature_2m_min` | Harian |
| Kecepatan angin maks | km/h | `windspeed_10m_max` | Harian |

### 1.1 Threshold Cuaca Ekstrem (dari `config/settings.py`)

| Fenomena | Parameter | Threshold | Variabel Config |
|----------|-----------|-----------|-----------------|
| Hujan lebat / banjir | Curah hujan | > 100 mm/hari | `WEATHER_PRECIP_EXTREME_MM` |
| Kekeringan | Hari tanpa hujan (< 1mm) | > 14 hari berturut | `WEATHER_DROUGHT_DAYS` |
| Suhu ekstrem | Suhu maksimum | > 38 C | `WEATHER_TEMP_EXTREME_C` |
| Angin kencang | Kecepatan angin | > 60 km/h | `WEATHER_WIND_EXTREME_KMH` |

**Lookback window**: 7 hari terakhir (`WEATHER_LOOKBACK_DAYS`)

---

## 2. Matriks Dampak Cuaca per Komoditas

### 2.1 Sensitivitas Komoditas terhadap Cuaca

Skala dampak: 1 (rendah) - 5 (sangat tinggi)

| Komoditas | Hujan Lebat | Kekeringan | Suhu Ekstrem | Angin Kencang |
|-----------|-------------|------------|--------------|---------------|
| Bawang Merah (com_11) | 4 | 3 | 3 | 2 |
| Bawang Putih (com_12) | 2 | 2 | 2 | 1 |
| Cabai Merah Besar (com_13) | 5 | 4 | 4 | 3 |
| Cabai Merah Keriting (com_14) | 5 | 4 | 4 | 3 |
| Cabai Rawit Hijau (com_15) | 4 | 5 | 3 | 3 |
| Cabai Rawit Merah (com_16) | 4 | 5 | 3 | 3 |

**Catatan**:
- Bawang Putih sensitivitas rendah karena 80% impor - harga lebih dipengaruhi kurs dan supply chain global
- Cabai (semua jenis) paling sensitif cuaca karena murni produksi lokal, tanaman rentan
- Bawang Merah sensitif hujan lebat karena umbi mudah busuk jika tergenang

### 2.2 Lag Time (Hari antara Event Cuaca dan Dampak Harga)

| Komoditas | Hujan Lebat | Kekeringan | Suhu Ekstrem | Angin Kencang |
|-----------|-------------|------------|--------------|---------------|
| Bawang Merah | 7-14 | 21-35 | 14-28 | 3-7 |
| Bawang Putih | 3-7 (distribusi) | minimal | minimal | 3-7 |
| Cabai Merah Besar | 14-30 | 30-60 | 21-45 | 7-14 |
| Cabai Merah Keriting | 14-30 | 30-60 | 21-45 | 7-14 |
| Cabai Rawit Hijau | 14-21 | 21-45 | 14-30 | 7-14 |
| Cabai Rawit Merah | 14-21 | 21-45 | 14-30 | 7-14 |

**Penjelasan lag time**:
- **Hujan lebat**: Dampak cepat jika banjir merusak tanaman siap panen. Lebih lambat jika merusak tanaman muda.
- **Kekeringan**: Dampak paling lambat karena stok existing masih ada. Terasa setelah siklus panen berikutnya gagal.
- **Suhu ekstrem**: Dampak medium. Tanaman stress tapi bisa recover jika singkat.
- **Angin kencang**: Dampak tercepat pada distribusi (jalan tertutup, truk terhambat). Kerusakan tanaman berdampak lebih lambat.

### 2.3 Magnitude Dampak Harga (Estimasi % Kenaikan)

| Komoditas | Hujan Lebat | Kekeringan | Suhu Ekstrem | Angin Kencang |
|-----------|-------------|------------|--------------|---------------|
| Bawang Merah | +20-40% | +15-30% | +10-20% | +5-15% |
| Bawang Putih | +5-10% | +3-5% | +3-5% | +3-10% |
| Cabai Merah Besar | +30-80% | +40-100% | +20-50% | +10-25% |
| Cabai Merah Keriting | +25-60% | +35-80% | +15-40% | +10-20% |
| Cabai Rawit Hijau | +30-70% | +50-120% | +20-40% | +10-25% |
| Cabai Rawit Merah | +35-80% | +60-150% | +25-50% | +15-30% |

**Faktor pengali**:
- Jika cuaca ekstrem + hari raya: magnitude x 1.5 - 2.0
- Jika cuaca ekstrem > 7 hari: magnitude x 1.3
- Jika multiple wilayah produksi terdampak: magnitude x 1.5

---

## 3. Matriks Dampak per Wilayah

### 3.1 Profil Wilayah MVP

| Provinsi | Peran | Komoditas Utama | Risiko Cuaca Dominan |
|----------|-------|-----------------|---------------------|
| DKI Jakarta | Konsumen utama, pusat distribusi | Semua (bukan produsen) | Banjir (distribusi terganggu) |
| Jawa Barat | Sentra produksi utama | Cabai, Bawang Merah | Longsor, banjir bandang |
| Banten | Transit + konsumen | Campuran | Banjir pesisir, angin |
| Sulawesi Selatan | Sentra produksi sekunder | Bawang Merah, Cabai | Kekeringan, musim kering panjang |

### 3.2 Koordinat Monitoring Cuaca

Titik monitoring per wilayah (centroid sentra produksi/distribusi):

| Provinsi | Latitude | Longitude | Representasi |
|----------|----------|-----------|-------------|
| DKI Jakarta | -6.2088 | 106.8456 | Pasar Induk Kramat Jati |
| Jawa Barat (Garut) | -7.2167 | 107.9000 | Sentra cabai Garut |
| Jawa Barat (Brebes) | -6.8722 | 109.0400 | Sentra bawang merah Brebes |
| Banten (Serang) | -6.1200 | 106.1500 | Pusat distribusi Banten |
| Sulsel (Gowa) | -5.3100 | 119.4900 | Sentra bawang merah Gowa |
| Sulsel (Jeneponto) | -5.6300 | 119.7500 | Sentra cabai Jeneponto |

### 3.3 Dampak Cuaca per Wilayah

| Fenomena di Wilayah | Dampak Lokal | Dampak Nasional |
|---------------------|-------------|-----------------|
| Banjir DKI Jakarta | Distribusi terganggu, harga naik 5-15% | Minimal (supply tidak berubah) |
| Kekeringan Jabar (Garut) | Produksi cabai turun 30-50% | Tinggi - supply nasional turun |
| Banjir Jabar (Brebes) | Bawang merah gagal panen | Tinggi - 30% produksi nasional |
| Angin kencang Banten | Distribusi terganggu | Rendah (transit point) |
| Kekeringan Sulsel | Bawang merah produksi turun | Sedang - dampak ke Indonesia Timur |

---

## 4. Pola Musiman Cuaca Indonesia

### 4.1 Musim dan Dampak

| Periode | Musim | Fenomena | Komoditas Terancam |
|---------|-------|---------|-------------------|
| Nov - Mar | Hujan | Banjir, longsor, humidity tinggi | Bawang Merah (busuk), Cabai (jamur) |
| Apr - Jun | Transisi | Curah hujan tidak menentu | Risiko rendah, masa tanam ideal |
| Jul - Sep | Kemarau | Kekeringan, suhu tinggi | Cabai (semua jenis), Bawang Merah |
| Okt - Nov | Transisi | Awal hujan tidak menentu | Risiko sedang, persiapan tanam |

### 4.2 Fenomena Iklim Global

| Fenomena | Periode Tipikal | Dampak di Indonesia | Komoditas Terdampak |
|----------|----------------|--------------------|--------------------|
| El Nino | Intermiten (2-7 tahun) | Kemarau panjang, penurunan produksi | Cabai (+30-80%), Bawang Merah (+20-40%) |
| La Nina | Intermiten (2-7 tahun) | Hujan lebat berkepanjangan | Cabai (+20-50%), Bawang Merah (+15-30%) |
| IOD Positif | Intermiten | Kemarau lebih kering di Indonesia | Serupa El Nino |
| IOD Negatif | Intermiten | Hujan lebih banyak di Indonesia | Serupa La Nina |
| MJO | 30-60 hari siklus | Hujan lebat intermiten | Dampak jangka pendek pada distribusi |

---

## 5. Decision Matrix untuk RCA Engine

### 5.1 Kapan Cuaca Dianggap Penyebab (Check 2 RCA)

Cuaca dianggap penyebab kenaikan harga jika SEMUA kondisi terpenuhi:

| Kondisi | Threshold | Sumber Data |
|---------|-----------|-------------|
| Ada event cuaca ekstrem | Melampaui threshold di Section 1.1 | Open-Meteo API |
| Dalam lookback window | 7 hari terakhir | `WEATHER_LOOKBACK_DAYS` |
| Komoditas sensitif cuaca | Sensitivitas >= 3 (Section 2.1) | Knowledge base |
| Wilayah terdampak relevan | Sentra produksi, bukan hanya konsumen | Mapping Section 3 |

### 5.2 Scoring Cuaca untuk Priority Engine

Cuaca berkontribusi ke signal `weather_calendar` (weight: 10% dari total priority score):

| Kondisi | Score Kontribusi |
|---------|-----------------|
| Tidak ada cuaca ekstrem | 0.0 |
| Cuaca ekstrem 1 parameter | 0.3 |
| Cuaca ekstrem 2+ parameter | 0.6 |
| Cuaca ekstrem + di sentra produksi | 0.8 |
| Cuaca ekstrem + hari raya bersamaan | 1.0 |

---

## 6. Rekomendasi Aksi per Tipe Cuaca

### 6.1 Hujan Lebat / Banjir

| Timeline | Aksi | Detail |
|----------|------|--------|
| H+0 (Deteksi) | Alert sistem | Notifikasi analis |
| H+1-3 | Verifikasi dampak | Cek laporan Dinas Pertanian lokal |
| H+3-7 | Monitor harga | Pantau kenaikan di pasar terdekat sentra |
| H+7-14 | Siapkan alternatif supply | Identifikasi daerah tidak terdampak |
| H+14+ | Evaluasi intervensi | Jika dampak berkepanjangan, eskalasi |

### 6.2 Kekeringan

| Timeline | Aksi | Detail |
|----------|------|--------|
| Hari ke-7 | Pre-alert | Kekeringan mulai terdeteksi |
| Hari ke-14 | Alert sistem | Threshold tercapai |
| Hari ke-14-21 | Monitor stok | Stok existing masih ada |
| Hari ke-21-30 | Koordinasi supply | Identifikasi sumber alternatif |
| Hari ke-30+ | Eskalasi | Dampak pada siklus panen berikutnya |

### 6.3 Suhu Ekstrem

| Timeline | Aksi | Detail |
|----------|------|--------|
| H+0 | Monitor | Cek apakah suhu bertahan > 3 hari |
| H+3-7 | Alert jika persisten | Suhu ekstrem > 3 hari berpotensi merusak |
| H+14-21 | Pantau produksi | Dampak mulai terasa di pasar |
| H+21+ | Evaluasi | Jika produksi turun signifikan |

### 6.4 Angin Kencang

| Timeline | Aksi | Detail |
|----------|------|--------|
| H+0 | Alert distribusi | Potensi gangguan transportasi |
| H+1-3 | Verifikasi jalur | Cek kondisi jalan dan pelabuhan |
| H+3-7 | Monitor harga distribusi | Kenaikan karena biaya logistik |
| H+7+ | Normalisasi | Biasanya dampak singkat |

---

## 7. Limitasi dan Catatan

| Limitasi | Detail | Mitigasi |
|----------|--------|----------|
| Data historis saja | Open-Meteo = data historis, bukan forecast | Cocok untuk RCA (apa yang terjadi), bukan prediksi |
| Titik monitoring terbatas | 6 titik untuk 4 provinsi | Tambah titik jika akurasi kurang |
| Lag time estimasi | Berdasarkan literatur, bukan kalibrasi lokal | Kalibrasi dengan data PIHPS 619K rows |
| Magnitude estimasi | Range lebar karena banyak faktor | Perlu ML model untuk presisi lebih baik |
| Tidak ada data stok riil | Stok pedagang/Bulog tidak tersedia real-time | RCA step 4 menggunakan asumsi |
| BMKG tidak tersedia | Tidak ada API historis yang bisa diakses | Open-Meteo sebagai alternatif |
