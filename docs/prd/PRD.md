# PRD — R.A.D.A.R Pangan

> **R**eal-time **A**nti-inflation **D**etection, **A**nalysis & **R**esponse
>
> Product Requirements Document
> Tanggal: 16 Mei 2026 | Tim Simatana | Hackathon PIDI
> Tema: Peningkatan Produktivitas, Ketahanan Pangan & Penciptaan Lapangan Kerja
> Kategori: Digitalisasi Ketahanan Pangan | Sub-Topik: Pemantauan Inflasi

---

## 1. Executive Summary

**R.A.D.A.R Pangan** adalah platform *Decision Support System* (DSS) berbasis data untuk **pemantauan, analisis, prediksi, dan respons** terhadap inflasi harga pangan (*volatile food*) di Indonesia.

Platform ini mengintegrasikan:
- **Data harga harian** dari PIHPS (Bank Indonesia / Bapanas)
- **Data cuaca historis** dari Open-Meteo
- **Kalender hari besar nasional** dari python-holidays
- **Model prediksi ML** (LightGBM Quantile)

untuk membantu TPID, Bapanas, dan pengambil kebijakan **mendeteksi anomali harga, mengidentifikasi akar masalah, memprediksi tren, dan merekomendasikan intervensi** sebelum harga melampaui HET.

### Mengapa Ini Penting?

| Fakta | Dampak |
|-------|--------|
| Komponen *volatile food* CPI berfluktuasi −3% s.d. +18% y-o-y (BPS, 2020-2024) | Lonjakan harga pangan langsung menggerus daya beli, terutama kelompok miskin (40-60% pengeluaran untuk pangan) |
| PIHPS memantau 12 komoditas di 514 kab/kota, tapi belum prediktif | Dashboard existing hanya deskriptif — menampilkan harga hari ini tanpa proyeksi risiko |
| HET belum difungsikan sebagai pemicu peringatan dini | Harga melampaui HET hingga 150-200% saat gangguan pasokan tanpa antisipasi |
| Disparitas harga antarwilayah bisa 3-5x lipat (Kemendag, 2023) | Surplus stok di satu wilayah tidak terdeteksi saat wilayah lain kekurangan |

> Sumber: Proposal Tahap 1 — R.A.D.A.R Pangan Final Submission

---

## 2. Problem Statement

### 2.1 Masalah Utama

Inflasi *volatile food* di Indonesia membesar karena **tiga kelemahan** utama dalam sistem pemantauan dan respons:

1. **Data harga dan stok belum terintegrasi dengan acuan HET dalam satu sistem.** Harga harian per wilayah tersedia di PIHPS, namun data stok komoditas masih tersebar dan tidak dibandingkan secara otomatis terhadap HET, sehingga pemerintah daerah sulit mendeteksi risiko lonjakan secara utuh dan lebih awal.

2. **Pemantauan saat ini masih bersifat deskriptif, belum prediktif.** PIHPS dan dashboard harga lain mampu menunjukkan harga hari ini, tetapi belum memberi proyeksi risiko 7-14 hari ke depan untuk komoditas rentan seperti cabai, bawang, telur, dan daging.

3. **HET sebagai acuan resmi belum difungsikan sebagai pemicu peringatan dini.** PIHPS tidak membandingkan harga aktual terhadap HET secara otomatis dan tidak menghasilkan alert ketika harga mendekati batas tersebut.

### 2.2 Hipotesis Solusi

Dengan mengintegrasikan data PIHPS, cuaca, dan kalender ke dalam satu platform yang dilengkapi engine analisis (rule-based RCA + ML), pemerintah dapat:
- Mendeteksi anomali harga **dalam hitungan menit** (bukan hari)
- Memahami **penyebab spesifik** kenaikan harga (demand musiman vs supply disruption vs distribusi)
- **Memprediksi** harga 7-14 hari ke depan dengan confidence interval
- Mendapatkan **rekomendasi intervensi terstruktur** berdasarkan diagnosis

### 2.3 Siapa yang Terdampak

| Stakeholder | Jumlah | Dampak |
|-------------|--------|--------|
| Konsumen rumah tangga | ~280 juta | Daya beli tergerus saat lonjakan harga |
| Petani/produsen | ~29 juta rumah tangga tani | Margin kecil meski harga konsumen tinggi |
| Pemda & TPID | 514 kab/kota | Respons kebijakan terlambat karena belum ada DSS |
| Koperasi & pelaksana lapangan | Ribuan hub | Bergerak setelah harga sudah bergejolak |

---

## 3. Vision & Mission

### Vision
> Menjadi platform utama pemerintah Indonesia untuk **early warning** dan **decision support** dalam menjaga stabilitas harga pangan nasional.

### Mission
1. **Detect** — Deteksi anomali harga pangan secara real-time dari data PIHPS
2. **Analyze** — Identifikasi akar penyebab dengan engine analisis multi-faktor (cuaca, hari raya, supply, distribusi)
3. **Predict** — Prediksi tren harga ke depan menggunakan model ML
4. **Respond** — Rekomendasikan intervensi kebijakan yang tepat dan terukur

---

## 4. Target Users

### 4.1 User Segments

| Segment | Contoh Instansi | Kebutuhan Utama | Frekuensi |
|---------|-----------------|-----------------|-----------|
| **TPID & Bapanas** | Tim Pengendalian Inflasi Daerah, Badan Pangan Nasional | Monitoring harian, analisis RCA, rekomendasi intervensi | Harian |
| **Decision Maker** | Deputi Bapanas, Kepala Dinas Perdagangan, TPID Provinsi | Ringkasan eksekutif, status alert, keputusan intervensi cepat | Saat ada alert |
| **Operator Lapangan** | Koperasi Desa Merah Putih, Bulog, Distributor | Status harga wilayah, tren, perbandingan antarwilayah | Mingguan |
| **Publik & Researcher** | Media, akademisi, BPS, masyarakat umum | Data historis, tren harga, transparansi | Ad-hoc |

### 4.2 Role-Based Access (MVP)

| Role | Deskripsi | Akses Fitur |
|------|-----------|-------------|
| **Admin** | Pengelola sistem | Semua fitur + user management |
| **Analyst** | Analis TPID / Bapanas | Dashboard + RCA + Prediksi ML |
| **Viewer** | Pemangku kebijakan / publik | Dashboard read-only |

---

## 5. Product Scope

### 5.1 MVP Scope (Demo June 4, 2026)

#### Komoditas Fokus (6)

| # | Komoditas | comcat_id | Alasan Dipilih |
|---|-----------|-----------|----------------|
| 1 | Bawang Merah | com_11 | Volatile, kontributor inflasi utama |
| 2 | Bawang Putih | com_12 | Demand tinggi, sensitif impor |
| 3 | Cabai Merah Besar | com_13 | Paling volatile, sering jadi headline |
| 4 | Cabai Merah Keriting | com_14 | Sering melampaui HET |
| 5 | Cabai Rawit Hijau | com_15 | Harga ekstrem |
| 6 | Cabai Rawit Merah | com_16 | Paling mahal, high impact |

#### Wilayah Fokus (4 Provinsi, 18 Kota)

| Provinsi | PIHPS ID | Kota Tercakup | Coverage |
|----------|----------|---------------|----------|
| Banten | 11 | Tangerang, dll | Jabodetabek |
| Jawa Barat | 12 | Bandung, Bogor, Depok, Bekasi, Cirebon, dll | Jabodetabek + Jabar |
| DKI Jakarta | 13 | Jakarta Pusat | Pusat ekonomi |
| Sulawesi Selatan | 26 | Makassar, dll | Representasi Indonesia Timur |

#### Data Range
- **Historis**: 2020-01-01 s/d sekarang (~619K+ rows harga, ~11K rows cuaca)
- **Hari besar**: 2024-2027 (91 records)
- **Update**: Daily (target via Airflow DAG)

### 5.2 Extensibility Design

Platform didesain **config-driven** agar mudah di-extend tanpa ubah arsitektur:

| Dimensi | MVP | Extensible To |
|---------|-----|---------------|
| Komoditas | 6 (bawang + cabai) | 12+ (seluruh PIHPS strategis) |
| Wilayah | 4 provinsi, 18 kota | 34 provinsi, 514 kab/kota |
| Sumber data | PIHPS + Open-Meteo + python-holidays | + BPS, + data stok Koperasi, + HET resmi Bapanas |
| Model ML | LightGBM Quantile | Multi-model ensemble, per-komoditas |
| Interface | Web (responsive) | + Notifikasi (email/Telegram) + API publik |

Extensibility dicapai melalui:
- **Constants file**: komoditas dan wilayah MVP didefinisikan di satu config, bukan hardcoded tersebar
- **Medallion Architecture**: pipeline data modular (Bronze → Silver → Gold), tambah sumber = tambah Bronze layer
- **API-first**: semua data diakses via REST API, frontend terpisah dari backend

### 5.3 Out of Scope (MVP)

| Item | Alasan |
|------|--------|
| React PWA | Timeline tidak cukup; gunakan HTML + Alpine.js (responsive, mobile-first) |
| Real-time stock data (Koperasi Desa Merah Putih) | Data belum tersedia via API, masukkan ke Phase 2 |
| Notification system (Telegram/WA/email) | Nice-to-have, bukan core value untuk demo |
| Multi-language (EN) | Fokus Bahasa Indonesia |
| User self-registration | Admin-managed users (internal government tool) |
| Real-time streaming | Batch daily sufficient untuk kebutuhan monitoring |
| BMKG weather (forecast) | Tidak ada API historis; Open-Meteo sebagai pengganti |
| Peta Risiko (map visualization) | Requires mapping library; explore di Phase 2 |
| Alert Center (dedicated page) | Fitur alert terintegrasi di Dashboard untuk MVP |

---

## 6. Core Features

> Detail teknis, acceptance criteria, dan user stories ada di [FRD](../frd/FRD.md).

### F1: Dashboard Monitoring & Overview

**Tujuan**: Satu halaman untuk melihat status harga pangan terkini, prediksi, dan alert.

| Komponen | Deskripsi |
|----------|-----------|
| **Ringkasan Nasional** | Total komoditas dipantau, rata-rata perubahan harga, jumlah alert aktif |
| **Kartu Komoditas** | Per-komoditas: harga terkini, delta (%) vs kemarin, status HET (badge warna) |
| **HET Monitor** | Perbandingan harga aktual vs HET → status AMAN / WASPADA / KRITIS / MELAMPAUI |
| **Prediksi Ringkas** | Trend prediksi 7 hari ke depan per komoditas (naik/turun/stabil) + confidence |
| **RCA Alert Summary** | Komoditas yang terdeteksi anomali + diagnosis ringkas (demand/supply/distribusi) |
| **Date Filter** | Pilih tanggal untuk review historis / simulasi |

**Design**: Mobile-first, responsive (smartphone → tablet → desktop).

### F2: Analisis RCA (Root Cause Analysis)

**Tujuan**: Jelaskan *mengapa* harga naik — bukan hanya *berapa* naiknya.

| Step | Check | Diagnosis jika Triggered |
|------|-------|--------------------------|
| 1 | Hari Raya (H-14 s/d H+3) | **Demand Spike** musiman |
| 2 | Cuaca Ekstrem (hujan >100mm, drought >14 hari, suhu >38C, angin >60km/h) | **Gangguan Supply** |
| 3 | Persebaran Kota (>60% kota harga naik) | **Supply nasional** terganggu |
| 4 | Level Stok (placeholder MVP) | **Stok menipis** / kritis |

**Sequential early-exit**: Jika Step 1 triggered → diagnosis Demand, skip sisanya.

**Komponen halaman**:
- Filter komoditas & tanggal
- Visualisasi 4-step check (animated, status per step)
- Detail diagnosis + rekomendasi aksi
- Konteks hari besar terdekat
- Detail cuaca (jika triggered)

### F3: Prediksi Harga (ML)

**Tujuan**: Prediksi harga 7-14 hari ke depan agar intervensi bisa **preventif, bukan reaktif**.

| Komponen | Deskripsi |
|----------|-----------|
| **Summary Cards** | Rata-rata prediksi, trend (naik/turun/stabil), komoditas paling volatile |
| **Grafik Tren** | Harga aktual vs prediksi dengan confidence interval (P10-P90) |
| **Tabel Detail** | Prediksi per-komoditas per-tanggal per-wilayah |
| **Model Info** | Versi model, tanggal training, metrik akurasi |

**ML Architecture** (dikembangkan oleh ML Lead):
- **Layer 1** — Forecast Engine: LightGBM Quantile (P50/P90)
- **Layer 2** — Detection Engine: HET threshold + anomaly detection
- **Layer 3** — Decision Engine: Rekomendasi intervensi berbasis multi-kriteria

### F4: Admin & User Management

**Tujuan**: Kontrol akses role-based untuk keamanan.

| Komponen | Deskripsi |
|----------|-----------|
| RBAC | 3 level: Viewer, Analyst, Admin |
| User CRUD | Admin bisa tambah, edit, aktifkan/nonaktifkan user |
| Auth | JWT HS256 (8 jam expire), bcrypt password hashing |

### F5: Data Pipeline — Medallion Architecture

**Tujuan**: Pipeline data modular, reliable, auditable, dan extensible.

| Layer | Nama | Konvensi | Isi |
|-------|------|----------|-----|
| **Bronze** | `raw.*` | As-is, immutable | Data mentah dari sumber (PIHPS, Open-Meteo, python-holidays) |
| **Silver** | `staging.*` | Cleaned, validated | Deduplicated, enriched, normalized — single source of truth |
| **Gold** | `marts.*` / `app.*` | Consumption-ready | Agregasi untuk dashboard, features untuk ML, tabel untuk frontend |

Prinsip Medallion:
- Bronze **tidak pernah diubah** setelah di-load (append-only, immutable)
- Silver menambahkan validasi, dedup, dan enrichment
- Gold didesain dari **kebutuhan konsumer** (UI, ML, reporting) — bukan dari struktur sumber

---

## 7. Non-Functional Requirements

### 7.1 Performance

| Metrik | Target | Catatan |
|--------|--------|---------|
| Dashboard load time | < 3 detik | Dengan caching (Gold layer pre-computed) |
| RCA analysis time | < 5 detik | Single komoditas, termasuk BigQuery round-trip |
| API response time (p95) | < 2 detik | Cached queries |
| Data freshness | T-1 (harga kemarin) | Daily batch pipeline |
| Concurrent users | ~50 | MVP scale |

### 7.2 Responsiveness

| Device | Viewport | Priority |
|--------|----------|----------|
| **Smartphone** | 320-480px | **Primary** (design first) |
| **Tablet** | 768-1024px | Secondary |
| **Desktop** | 1280px+ | Tertiary (most features shown) |

Approach: **Mobile-first design** — layout dirancang untuk smartphone terlebih dahulu, lalu progressively enhanced untuk tablet dan desktop.

### 7.3 Security

| Aspek | Requirement |
|-------|-------------|
| Authentication | JWT token (HS256, 8 jam), bcrypt password |
| Authorization | RBAC server-side enforcement (Viewer/Analyst/Admin) |
| Data | No PII stored; secrets via env vars |
| Transport | HTTPS saat deployed (production) |
| SQL | Parameterized queries only — no string interpolation |

### 7.4 Cost Constraint

> **$0 infrastructure cost** (free tier only) — hard constraint.

| Service | Free Tier | Current Usage |
|---------|-----------|---------------|
| BigQuery Storage | 10 GB | ~250 MB (2.5%) |
| BigQuery Queries | 1 TB/bulan | Minimal |
| Supabase PostgreSQL | 500 MB | ~50 MB |
| Compute | Local / Docker | $0 |

---

## 8. Success Metrics

### 8.1 Hackathon Demo (June 4, 2026)

| Metrik | Target |
|--------|--------|
| Demo 4 skenario (hari raya, cuaca, HET, normal day) tanpa error | 100% |
| Dashboard load < 5 detik | Yes |
| RCA memberikan diagnosis akurat untuk semua skenario demo | 100% |
| ML prediksi menampilkan data dengan confidence interval | Yes |
| Responsive di smartphone (375px viewport) | Yes |

### 8.2 Target KPI (dari Proposal)

| KPI | Target | Timeframe |
|-----|--------|-----------|
| Persentase hari harga di bawah HET pada komoditas pilot | ≥ 85% | 3-6 bulan pilot |
| Disparitas harga antarwilayah turun | ≥ 15% | 3-6 bulan pilot |
| Lead time respons alert → keputusan intervensi | ≤ 24 jam | 3 bulan |
| Akurasi prediksi (MAPE, 7 hari) | ≤ 12% | 6 bulan |

---

## 9. Constraints & Assumptions

### 9.1 Constraints

| # | Constraint | Dampak |
|---|-----------|--------|
| C1 | Demo deadline: 4 Juni 2026 (< 3 minggu) | Scope strict, prioritize demo flow |
| C2 | $0 cost (free tier only) | Tidak bisa pakai dedicated server / premium API |
| C3 | Tim 4 orang (1 backend, 1 ML, 1 product, 1 data) | Parallelisasi terbatas |
| C4 | Frontend: HTML + Alpine.js (bukan React PWA seperti di Proposal 1) | Lebih cepat develop, tapi less interactive |
| C5 | Data stok pedagang belum tersedia | RCA Step 4 pakai placeholder |
| C6 | HET reference masih estimasi | Perlu data resmi Bapanas untuk akurasi penuh |

### 9.2 Assumptions

| # | Assumption | Risk jika Salah |
|---|-----------|-----------------|
| A1 | Data PIHPS terus tersedia dan reliable | Pipeline gagal → dashboard stale |
| A2 | Open-Meteo Historical API tetap gratis | Perlu cari alternatif cuaca |
| A3 | BigQuery free tier cukup untuk MVP | Perlu optimasi query jika mendekati limit |
| A4 | ML teammate deliver predictions sebelum demo | Halaman prediksi akan empty state |
| A5 | User pemerintah punya akses browser modern + internet | Responsive web cukup, tidak perlu offline mode |

---

## 10. Risks & Mitigations

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R1 | ML model belum ready untuk demo | Medium | High | Tampilkan dummy predictions + jelaskan arsitektur |
| R2 | BigQuery latency tinggi saat demo | Medium | High | Implement caching layer (Gold layer pre-computed) |
| R3 | PIHPS API down saat demo | Low | High | Data sudah di-load ke BigQuery, tidak real-time dependent |
| R4 | Demo flow tidak smooth di mobile | Medium | Medium | Test di 3 device types sebelum demo |
| R5 | Juri tanya soal gap Proposal vs Implementasi | High | Medium | Siapkan penjelasan: evolusi desain berdasarkan data riil |
| R6 | Juri tanya soal scalability | High | Medium | Siapkan diagram arsitektur Medallion + extensibility pitch |

---

## 11. Roadmap & Phasing

### Phase 1: MVP / PoC — Hackathon (Current → June 4, 2026)

| Sprint | Fokus | Status |
|--------|-------|--------|
| S1-S12 | Data pipeline + BigQuery + ETL + dbt | ✅ Done |
| S1-S12 | RCA Engine + HET Monitor + Weather | ✅ Done (36 unit tests) |
| S1-S12 | Frontend 5 pages (neobrutalism, Alpine.js) | ✅ Done |
| S1-S12 | Auth + RBAC (JWT + boolean flags) | ✅ Done |
| **Now** | **Dokumentasi (PRD/FRD/ERD/SDA) + Wireframe** | **🔄 In Progress** |
| Next | Caching + UI polish + responsive + demo prep | ⬜ Planned |

### Phase 2: Pilot (Post-Hackathon, 3-6 bulan)

- Extend ke 12 komoditas + 10 provinsi
- Integrasi data stok dari Koperasi Desa Merah Putih
- ML model v2 (multi-komoditas, ensemble)
- Notification system (email/Telegram)
- Cloud deployment (GCP Cloud Run / Fly.io)
- Evaluasi migrasi frontend ke React PWA
- CI/CD pipeline

### Phase 3: Scale-up (6-24 bulan)

- Full 21+ komoditas + 34 provinsi
- Integrasi dengan TPID daerah dan Bapanas pusat
- HET reference dari regulasi resmi (Permendag)
- Peta Risiko (map visualization)
- Public API
- Multi-bahasa (ID + EN)

---

## 12. Perbedaan dari Proposal Tahap 1

> Bagian ini mendokumentasikan perubahan yang dilakukan dari Proposal Final Submission ke implementasi aktual, beserta justifikasinya.

| Aspek | Proposal Tahap 1 | Implementasi Aktual | Justifikasi |
|-------|-------------------|---------------------|-------------|
| **Frontend** | React.js (PWA) | HTML + Alpine.js (responsive) | Lebih cepat develop, no build step, timeline < 3 minggu |
| **Database** | PostgreSQL + Redis | BigQuery (warehouse) + Supabase PostgreSQL (app) | BigQuery gratis untuk analytics scale besar; dual-DB lebih sesuai workload |
| **Halaman MVP** | Dashboard, Peta Risiko, Alert Center, Admin | Dashboard, RCA, Prediksi ML, Admin, Login | RCA & Prediksi lebih actionable daripada Peta Risiko untuk MVP |
| **Sumber cuaca** | Tidak spesifik | Open-Meteo Historical API | Gratis, reliable, data historis 1940-sekarang |
| **Sumber harga** | Bapanas (panelharga) | BI PIHPS (bi.go.id) | Data sama, sumber BI lebih stable untuk scraping |
| **IaC** | Tidak disebutkan | Terraform (BigQuery infra) | Best practice, reproducible infrastructure |
| **Pipeline** | Tidak detail | Medallion Architecture (dbt + Airflow) | Industry standard, modular, auditable |

---

## 13. Tim & Responsibilities

| Nama | Role | Fokus |
|------|------|-------|
| Muhammad Enzi Muzakki | Lead AI/ML | Model prediksi, deteksi anomali, risk scoring |
| Fariz Risqi Maulana | Product & Domain Lead | Kebutuhan kebijakan, desain fitur, alur intervensi |
| Muhammat Rayyan Nasution | Data & Quant Analyst | Olah data harga-stok, validasi metrik, evaluasi model |
| Rayhan Ananda Resky | Cloud & Backend Engineer | API, database, pipeline, deployment cloud |

---

## Appendix A: Glossary

| Istilah | Definisi |
|---------|----------|
| **PIHPS** | Pusat Informasi Harga Pangan Strategis — sistem BI untuk monitoring harga |
| **HET** | Harga Eceran Tertinggi — batas harga yang ditetapkan pemerintah |
| **RCA** | Root Cause Analysis — analisis akar penyebab |
| **TPID** | Tim Pengendalian Inflasi Daerah |
| **Medallion Architecture** | Pattern data lake: Bronze (raw) → Silver (clean) → Gold (aggregated) |
| **comcat_id** | Commodity Category ID dari PIHPS (e.g., com_11 = Bawang Merah) |
| **DSS** | Decision Support System — sistem pendukung keputusan |
| **Anomali** | Kenaikan harga melebihi threshold (default: >10% dari hari sebelumnya) |
| **Volatile Food** | Komoditas pangan yang harganya sangat fluktuatif (cabai, bawang, dll) |
| **PIDI** | Program Inovasi Digital Indonesia (penyelenggara hackathon) |
| **Koperasi Desa Merah Putih** | Jaringan koperasi desa/kelurahan (Perpres No. 9/2025) |

## Appendix B: Related Documents

| Dokumen | Status | Path |
|---------|--------|------|
| Proposal Tahap 1 (Final Submission) | ✅ Reference | `R.A.D.A.R Pangan Final Submission Pemantauan Inflasi.md` |
| FRD (Functional Requirements) | 🔜 Next | `docs/frd/` |
| Wireframe / Prototype | 🔜 Planned | `docs/wireframe/` |
| ERD | 🔜 Planned | `docs/erd/` |
| System Design Architecture | 🔜 Planned | `docs/sda/` |
| Demo Scenarios | ✅ Ada | `docs/demo-scenarios.md` |
| Testing Report | ✅ Ada | `docs/NEED_TO_FIX.md` |

## Appendix C: Data Sources

| Sumber | Jenis Data | Status | URL / API |
|--------|-----------|--------|-----------|
| **BI PIHPS** | Harga harian 12+ komoditas, 514 kab/kota | ✅ 619K rows loaded | `bi.go.id/hargapangan` |
| **Open-Meteo** | Cuaca historis (curah hujan, suhu, angin) | ✅ 11K rows loaded | `open-meteo.com` |
| **python-holidays** | Hari libur nasional Indonesia | ✅ 91 rows (2024-2027) | Package Python |
| **HET Bapanas** | Harga Eceran Tertinggi per komoditas | ⚠️ Dummy (estimasi) | `bapanas.go.id` |
| **BPS** | Produksi/konsumsi pangan per provinsi | 🔜 Phase 2 | `bps.go.id` |
| **Koperasi Desa MP** | Stok, volume komoditas, kesiapan pasok | 🔜 Phase 2 | Input via form operator |
