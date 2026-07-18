# Intervention Playbook - Panduan Eskalasi dan Intervensi

> **Status**: SINTETIS - Berdasarkan framework BI, observasi TPID, dan riset domain
> **Disclaimer**: Bukan SOP resmi TPID/TPI. Template panduan untuk analis.
> **Terakhir diperbarui**: Juli 2026

---

## 1. Struktur Kelembagaan

### 1.1 Hierarki Pengendalian Inflasi

```
TPI PUSAT (Tim Koordinasi Penetapan Sasaran, Pemantauan dan Pengendalian Inflasi)
  |-- Koordinator: Bank Indonesia
  |-- Anggota: Kemenkeu, Kemendagri, Kemendag, Kementan,
  |            Kemenhub, Kemen ESDM, Bappenas, Kemenko Perekonomian,
  |            Kemen PUPR, Kemen BUMN, Setkab, Polri
  |
  +-- TPID PROVINSI (Tim Pengendalian Inflasi Daerah)
       |-- Koordinator: Gubernur / Sekda
       |-- Anggota: OPD terkait, Bank Indonesia KPw, BPS, Bulog
       |
       +-- TPID KOTA/KABUPATEN
            |-- Koordinator: Walikota/Bupati
            |-- Pelaksana harian: Sekretariat TPID
```

### 1.2 Peran R.A.D.A.R Pangan dalam Alur TPID

| Peran | Deskripsi | Batasan |
|-------|-----------|---------|
| Decision Support | Membantu analis memprioritaskan komoditas/wilayah | Tidak menggantikan keputusan resmi |
| Early Warning | Deteksi dini risiko harga | Tidak menentukan volume/anggaran intervensi |
| Evidence Packaging | Mengemas data, analisis, dan bukti | Tidak mengeluarkan instruksi operasional |
| Review Facilitation | Membantu pengelompokan tinjauan bersama | Keputusan tetap di tangan manusia |

---

## 2. Alur Eskalasi

### 2.1 Matriks Eskalasi berdasarkan Severity

| Severity | Cakupan | Eskalasi Ke | Timeline Aksi |
|----------|---------|-------------|---------------|
| L0 (Aman) | - | Tidak ada eskalasi | Monitoring rutin |
| L1 (Waspada) | 1 kota | Sekretariat TPID Kota | 3-5 hari kerja |
| L2 (Awas) | 1 provinsi | TPID Provinsi | 2-3 hari kerja |
| L3 (Kritis) | > 1 provinsi | TPID Provinsi + TPI Pusat | 1-2 hari kerja |
| L4 (Darurat) | Nasional | TPI Pusat langsung | Dalam 24 jam |

### 2.2 Alur Eskalasi Detail

```
DETEKSI (R.A.D.A.R)
  |
  +-- Severity L0-L1?
  |     |-- Ya --> Monitor harian oleh analis
  |     |         Report mingguan ke Sekretariat TPID
  |
  +-- Severity L2?
  |     |-- Ya --> Verifikasi lapangan (2 hari)
  |     |         Rapat koordinasi TPID Kota
  |     |         Siapkan data untuk TPID Provinsi
  |
  +-- Severity L3?
  |     |-- Ya --> Rapat darurat TPID Provinsi
  |     |         Koordinasi lintas kota/kabupaten
  |     |         Laporan ke TPI Pusat
  |
  +-- Severity L4?
        |-- Ya --> TPI Pusat emergency meeting
        |         Instruksi koordinasi nasional
        |         Mobilisasi Bulog + Kemendag
```

---

## 3. Response Options per Situasi

### 3.1 MONITOR - Pemantauan Rutin

**Kapan**: Risk rendah, tidak ada anomali signifikan

| Aksi | Frekuensi | Penanggung Jawab |
|------|-----------|------------------|
| Cek harga PIHPS | Harian | Analis/Sekretariat TPID |
| Update data stok | Mingguan | Bulog regional |
| Review tren 7 hari | Mingguan | Analis |
| Laporan kondisi | Bulanan | Sekretariat TPID ke Kepala Daerah |

### 3.2 VERIFIKASI - Verifikasi Data dan Kondisi Lapangan

**Kapan**: Risk sedang, ATAU confidence rendah pada situasi tinggi

| Aksi | Timeline | Detail |
|------|----------|--------|
| Cross-check harga di 3+ pasar | 1-2 hari | Bandingkan PIHPS vs survei langsung |
| Konfirmasi stok pedagang besar | 1-2 hari | Hubungi 5-10 pedagang besar |
| Verifikasi kondisi cuaca lapangan | 1 hari | Konfirmasi dengan Dinas Pertanian |
| Dokumentasi temuan | 1 hari | Format standar untuk bahan rapat |

### 3.3 KOORDINASIKAN - Koordinasi dengan Dinas Terkait

**Kapan**: Risk tinggi, confidence medium-high

| Aksi | Timeline | Pihak Terlibat |
|------|----------|----------------|
| Rapat koordinasi TPID | 2-3 hari | Dinas Perdagangan, Pertanian, BPS |
| Identifikasi daerah surplus | 2 hari | Dinas Pertanian lintas wilayah |
| Siapkan opsi logistik | 2-3 hari | Dinas Perhubungan, Bulog |
| Siapkan data stok buffer | 1 hari | Bulog, Kemendag regional |

### 3.4 PERTIMBANGKAN INTERVENSI - Eskalasi ke Pengambil Keputusan

**Kapan**: Risk kritis, confidence high

| Jenis Intervensi | Prasyarat | Lead Time | Pihak Berwenang |
|-----------------|-----------|-----------|-----------------|
| Operasi Pasar (OP) | Stok tersedia, lokasi teridentifikasi | 3-5 hari | Bulog + Pemda |
| Gerakan Pangan Murah (GPM) | Budget tersedia, vendor siap | 5-7 hari | Bapanas + Pemda |
| Importasi Darurat | Regulasi impor clear, supplier ready | 14-30 hari | Kemendag |
| Release Cadangan Bulog | Surat Perintah dari Mendag/Bapanas | 2-3 hari | Bulog pusat |
| Subsidi Transportasi | Budget tersedia, rute teridentifikasi | 3-5 hari | Kemenhub + Pemda |

---

## 4. Jenis Intervensi per Diagnosis

### 4.1 Mapping Diagnosis ke Intervensi yang Efektif

| Diagnosis | Intervensi Efektif | Intervensi TIDAK Efektif |
|-----------|-------------------|--------------------------|
| DEMAND (Hari Raya) | Optimasi distribusi ke titik keramaian | Balancing stock (bukan masalah supply) |
| SUPPLY (Cuaca) | Relokasi stok, impor darurat | Operasi pasar (stok belum ada) |
| SUPPLY (Serempak) | Koordinasi TPID lintas provinsi, impor | OP lokal (masalah nasional) |
| DISTRIBUSI | Balancing stock, perbaiki logistik | Impor darurat (stok ada, distribusi macet) |
| EKSPEKTASI | Komunikasi publik, OP terbatas, sidak | Impor (bukan masalah supply/demand riil) |
| UNKNOWN | Investigasi dulu, jangan intervensi | Semua intervensi (data belum cukup) |

### 4.2 Bowtie Model - Prevention dan Mitigation Barriers

**6 FTA Threats**:

| ID | Threat | Tipe | Prevention | Mitigation |
|----|--------|------|------------|------------|
| D1 | Hari Raya | Demand | P1: Early Warning H-14 | M1: Operasi Pasar Darurat |
| D2 | Tekanan Ekonomi | Demand | P2: Monitor IHK | M1: OP, M5: Komunikasi Publik |
| S1 | Cuaca Ekstrem | Supply | P3: Monitor Open-Meteo | M2: Impor Darurat, M6: Diversifikasi |
| S2 | Defisit Stok | Supply | P4: Monitor Stok Mingguan | M2: Impor, M3: Release Bulog |
| S3 | Ketimpangan Distribusi | Supply | P5: Monitor Harga Antar Kota | M4: Koordinasi Transportasi |
| S4 | Off-Season | Supply | P6: Kalender Panen | M3: Release Bulog, M6: Diversifikasi |

---

## 5. Template Pelaporan

### 5.1 Format Laporan Situasi Harian

```
LAPORAN SITUASI HARGA PANGAN
Tanggal: [YYYY-MM-DD]
Wilayah: [Provinsi/Kota]
Severity: [L0-L4]

1. RINGKASAN
   - [X] komoditas dipantau
   - [X] risiko tinggi/kritis
   - [X] melampaui HET

2. KOMODITAS PRIORITAS
   #1. [Komoditas] - [Wilayah]
       Status: [AMAN/WASPADA/KRITIS/MELAMPAUI]
       Harga: Rp [X] / HET Rp [Y] ([Z]%)
       Diagnosis: [DEMAND/SUPPLY/DISTRIBUSI/...]
       Next Step: [Rekomendasi]

3. FAKTOR PENDUKUNG
   - Hari raya: [Ya/Tidak] - [Detail]
   - Cuaca: [Normal/Ekstrem] - [Detail]
   - Persebaran: [X]% kota naik
   - Stok: [Normal/Menipis/Kritis]

4. REKOMENDASI AKSI
   - [Aksi 1]
   - [Aksi 2]

5. INFORMASI YANG KURANG
   - [Item 1]
   - [Item 2]
```

### 5.2 Format Eskalasi ke TPID

```
ESKALASI RISIKO HARGA PANGAN
Severity: [L3/L4]
Tanggal: [YYYY-MM-DD]
Dari: Sekretariat TPID [Kota/Provinsi]
Kepada: [TPID Provinsi / TPI Pusat]

URGENSI: [Kritis/Darurat]

SITUASI:
- [Deskripsi singkat situasi]

BUKTI PENDUKUNG:
- [Evidence 1 - dengan sumber]
- [Evidence 2 - dengan sumber]

DIAGNOSIS R.A.D.A.R:
- Penyebab utama: [Diagnosis]
- Indikator aktif: [List]
- Confidence: [High/Medium/Low]

OPSI RESPONS:
1. [Opsi 1] - Lead time [X] hari
2. [Opsi 2] - Lead time [X] hari

KEPUTUSAN YANG DIPERLUKAN:
- [Keputusan 1]
- [Keputusan 2]

CATATAN: Analisis ini dihasilkan oleh sistem R.A.D.A.R Pangan
sebagai bahan pertimbangan. Keputusan intervensi tetap
berada pada otoritas resmi.
```

---

## 6. Frekuensi Monitoring berdasarkan Kondisi

| Kondisi | Frekuensi Monitoring | Frekuensi Laporan |
|---------|---------------------|-------------------|
| Normal (L0) | Harian (otomatis) | Mingguan |
| Waspada (L1) | Harian + manual spot-check | 2x seminggu |
| Awas (L2) | 2x sehari | Harian |
| Kritis (L3) | Setiap 6 jam | Harian + ad-hoc |
| Darurat (L4) | Real-time | Setiap update |
