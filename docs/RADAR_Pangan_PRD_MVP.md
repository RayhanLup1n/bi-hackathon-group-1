# Product Requirements Document (PRD)

## R.A.D.A.R Pangan — MVP Decision Support Risiko Harga Pangan

> **R.A.D.A.R Pangan**: *Real-time Anti-inflation Detection, Analysis & Response*  
> **Posisi produk MVP**: platform web untuk membantu analis dan pengambil keputusan memantau, memprioritaskan, menjelaskan, dan meninjau risiko harga pangan. Produk **tidak menggantikan keputusan resmi TPID** dan **tidak mengeluarkan instruksi intervensi operasional secara otomatis**.

---

## 1. Kontrol Dokumen

| Atribut | Nilai |
|---|---|
| Versi | 1.0 |
| Status | Baseline produk untuk MVP tahap berikutnya |
| Tanggal | 12 Juli 2026 |
| Pemilik produk | Tim Simatana |
| Timebox implementasi | 7–10 hari kerja efektif |
| Kapasitas aktif | 1 orang FE/UI + Backend + Data Engineering; 1 orang ML + Product Presentation |
| Bentuk produk | Web-based decision-support application |
| Model deployment awal | Private web application; dapat dikembangkan menjadi white-label/private SaaS |
| Target utama MVP | Analis/sekretariat TPID dan pengambil keputusan TPID |

---

## 2. Dasar Dokumen dan Tingkat Kepercayaan

PRD ini disusun dari empat sumber:

1. **Handbook Dashboard Early Warning System BI KPw Sibolga** sebagai referensi resmi mengenai alur data, status harga, tren, protokol, dan fungsi Summary.
2. **FAQ Analisis Produk — EWS Dashboard Inflasi** sebagai analisis internal mengenai problem bundling, pengguna, model bisnis, serta celah produk. Dokumen ini bukan pernyataan resmi Bank Indonesia.
3. **`PROJECT_OVERVIEW.md` R.A.D.A.R Pangan** sebagai baseline teknis produk yang sudah tersedia.
4. **Keputusan diskusi tim** mengenai scope MVP, keterbatasan waktu, kapasitas tim, dan batas tanggung jawab AI.

Seluruh kebutuhan dalam dokumen ini menggunakan label berikut:

| Label | Arti |
|---|---|
| `OFFICIAL_REFERENCE` | Memiliki rujukan pada Handbook resmi atau sumber institusional resmi |
| `TECHNICAL_BASELINE` | Sudah disebut tersedia dalam project overview/repository |
| `INTERNAL_HYPOTHESIS` | Asumsi desain tim yang belum divalidasi pengguna/domain expert |
| `MODEL_OUTPUT` | Hasil inferensi/statistik, bukan fakta pasti |
| `SIMULATION` | Digunakan hanya untuk demo atau pengujian skenario |

### 2.1 Keputusan governance yang telah dikunci

- AI membantu **memprioritaskan risiko, menjelaskan bukti, dan menyajikan langkah verifikasi atau opsi respons**.
- AI tidak boleh menyatakan keputusan kebijakan final.
- AI tidak boleh menentukan volume, anggaran, lokasi, instansi berwenang, atau waktu pelaksanaan intervensi tanpa data dan dasar resmi.
- Seluruh rekomendasi memerlukan **human review**.
- Asumsi internal tidak boleh ditampilkan sebagai SOP resmi.

---

## 3. Ringkasan Eksekutif

TPID dan analis harga pangan harus memantau banyak komoditas serta wilayah dalam waktu yang bersamaan. Data harga, HET, cuaca, kalender, pola regional, dan hasil prediksi dapat tersedia di sistem yang berbeda atau ditampilkan sebagai banyak grafik terpisah. Kondisi tersebut membuat pengguna tetap harus melakukan sintesis manual sebelum mengetahui:

- komoditas dan wilayah mana yang harus ditinjau lebih dahulu;
- seberapa besar urgensinya;
- bukti apa yang mendukung status tersebut;
- informasi apa yang masih kurang;
- langkah verifikasi atau koordinasi apa yang layak dipertimbangkan.

R.A.D.A.R Pangan mengubah kemampuan teknis yang sudah ada menjadi satu alur keputusan sederhana:

```text
DETECT → PRIORITIZE → EXPLAIN → SUGGEST NEXT STEP → HUMAN REVIEW
```

MVP tidak berfokus menambah model baru. MVP berfokus pada:

1. satu daftar prioritas yang dapat dipahami dalam waktu kurang dari satu menit;
2. forecast P50/P90 dan sinyal risiko yang dapat dievaluasi;
3. penjelasan faktor penyebab dan sumber data;
4. opsi respons yang dibatasi aturan;
5. pengelompokan beberapa komoditas menjadi paket tinjauan bersama;
6. transparansi kualitas data, performa model, dan keterbatasan sistem;
7. keputusan akhir tetap berada pada pengguna manusia.

---

## 4. Problem Statement

### 4.1 Problem utama

> **TPID kesulitan menentukan komoditas dan wilayah yang harus diprioritaskan serta ditinjau bersama sebelum tekanan harga meluas, karena data dan sinyal analitik belum selalu diterjemahkan menjadi satu urutan tindakan yang konsisten, mudah dijelaskan, dan dapat dipertanggungjawabkan.**

### 4.2 Konsekuensi

- Analisis cenderung reaktif terhadap kenaikan yang sudah terlihat.
- Analis harus membuka banyak indikator sebelum menyusun rekomendasi.
- Prioritas antarwilayah atau antarkomoditas dapat tidak konsisten.
- Beberapa komoditas yang berisiko pada periode berdekatan tidak mudah dilihat sebagai satu paket tinjauan.
- Pengambil keputusan sulit memahami alasan rekomendasi dalam waktu singkat.
- Kepercayaan terhadap output AI menurun ketika sumber, confidence, dan keterbatasan tidak terlihat.

### 4.3 Peluang produk

> Mengubah data harga dan hasil ML menjadi **decision package** yang ringkas, dapat ditelusuri, dan aman digunakan sebagai bahan rapat atau koordinasi TPID.

---

## 5. Visi, Posisi, dan Prinsip Produk

### 5.1 Visi

> Menjadi lapisan intelijen risiko harga pangan yang membantu pemerintah daerah berpindah dari monitoring terpisah menuju prioritas dan koordinasi berbasis bukti.

### 5.2 Positioning

> **R.A.D.A.R Pangan adalah web-based decision-support platform untuk analis dan pengambil keputusan TPID, bukan dashboard konsumen, marketplace, atau mesin keputusan kebijakan otomatis.**

### 5.3 Product promise

Dalam satu tampilan, pengguna dapat menjawab:

1. Apa komoditas atau wilayah yang paling berisiko?
2. Seberapa mendesak tinjauannya?
3. Bukti apa yang mendukungnya?
4. Informasi apa yang masih kurang?
5. Langkah verifikasi atau opsi respons apa yang dapat dipertimbangkan?

### 5.4 Prinsip desain

1. **Action-first** — informasi terpenting adalah prioritas dan langkah berikutnya.
2. **Evidence on demand** — bukti tersedia melalui drill-down, tidak memenuhi layar utama.
3. **Human accountable** — keputusan resmi selalu dibuat manusia.
4. **Uncertainty visible** — confidence, data hilang, dan keterbatasan model harus terlihat.
5. **Fail safely** — ketika data atau model tidak memadai, sistem menurunkan confidence atau abstain.
6. **No policy overclaim** — output berupa bahan pertimbangan, bukan mandat institusi.
7. **Latest available, not falsely real-time** — UI menampilkan waktu data terbaru yang benar-benar tersedia.

---

## 6. Tujuan dan Non-Tujuan MVP

### 6.1 Tujuan

| ID | Tujuan | Indikator keberhasilan |
|---|---|---|
| G-01 | Mempercepat pemahaman kondisi | Pengguna dapat mengidentifikasi prioritas pertama dan langkah berikutnya dalam ≤60 detik |
| G-02 | Membuat hasil dapat dipertanggungjawabkan | Setiap kartu prioritas menampilkan sumber, waktu pembaruan, confidence, dan alasan |
| G-03 | Membuktikan peran ML | Tersedia evaluasi terhadap baseline serta metrik forecast yang sesuai |
| G-04 | Mengubah insight menjadi bahan koordinasi | Sistem menghasilkan response options dan paket tinjauan bersama |
| G-05 | Menjaga keputusan tetap aman | Seluruh output memiliki human-review state dan larangan instruksi otomatis |
| G-06 | Menjamin demo tetap berjalan | Monitoring dan analisis inti tetap tersedia ketika ML/LLM service gagal |

### 6.2 Non-tujuan

MVP tidak mencakup:

- keputusan GPM atau operasi pasar secara otomatis;
- penentuan volume, anggaran, lokasi, supplier, atau jadwal intervensi;
- aplikasi mobile native;
- marketplace atau procurement;
- cakupan nasional penuh;
- integrasi IoT atau pelacakan fisik supply chain;
- retraining otomatis penuh;
- causal impact evaluation yang kompleks;
- chatbot terbuka yang menjawab di luar sumber terotorisasi;
- penjualan kembali data PIHPS/BPS tanpa hak penggunaan yang jelas.

---

## 7. Scope Data dan Teknis MVP

### 7.1 Scope komoditas

Enam komoditas pada baseline teknis:

1. Bawang Merah Ukuran Sedang
2. Bawang Putih Ukuran Sedang
3. Cabai Merah Besar
4. Cabai Merah Keriting
5. Cabai Rawit Hijau
6. Cabai Rawit Merah

### 7.2 Scope wilayah

- Banten
- Jawa Barat
- DKI Jakarta
- Sulawesi Selatan

Jumlah kota/kabupaten mengikuti metadata yang benar-benar tersedia pada serving database. UI tidak boleh mengklaim cakupan lengkap ketika suatu wilayah tidak memiliki data terbaru.

### 7.3 Baseline teknis yang dipertahankan

- FastAPI
- Frontend HTML + Alpine.js + Chart.js + CSS
- PostgreSQL/Supabase sebagai serving database
- BigQuery sebagai warehouse/batch layer
- Kestra + dbt + extractor Python
- LightGBM quantile forecasting P50/P90 untuk 7 dan 14 hari
- HET breach, change point, z-score, dan regional disparity
- RCA/FTA/Bowtie sebagai evidence engine
- JWT authentication dan RBAC
- Docker/Railway deployment
- graceful degradation ketika ML tidak tersedia

### 7.4 Batas arsitektur sprint

- Tidak melakukan rewrite stack.
- Tidak memigrasikan framework frontend.
- Tidak menambah service baru kecuali benar-benar diperlukan.
- Memprioritaskan satu endpoint agregasi untuk kebutuhan dashboard agar beban FE rendah.

---

## 8. Pengguna dan Stakeholder

### 8.1 Primary user — Analis/sekretariat TPID

**Tujuan:** menyiapkan analisis dan rekomendasi ringkas untuk rapat atau koordinasi.

**Kebutuhan utama:**

- mengetahui prioritas tanpa memeriksa seluruh grafik;
- melihat sumber dan freshness;
- menjelaskan mengapa risiko muncul;
- menyimpan status tinjauan;
- mengakses bukti teknis ketika dipertanyakan.

### 8.2 Decision user — Pimpinan/anggota pengambil keputusan TPID

**Tujuan:** memahami kondisi dan memutuskan apakah suatu isu perlu dibahas, diverifikasi, atau dikoordinasikan.

**Kebutuhan utama:**

- ringkasan sangat cepat;
- bahasa nonteknis;
- alasan yang dapat ditelusuri;
- batasan dan informasi yang belum tersedia;
- tidak dipaksa memahami detail algoritma.

### 8.3 Admin

**Tujuan:** memastikan user, data quality, dan status service dapat dikelola.

### 8.4 Co-user potensial

- Dinas Perdagangan
- Dinas Ketahanan Pangan
- Bulog
- Satgas Pangan

Co-user tidak menjadi target workflow penuh dalam sprint ini, tetapi namanya dapat muncul sebagai stakeholder yang perlu dikoordinasikan secara generik apabila dasar kewenangan telah divalidasi.

### 8.5 Beneficiary

- rumah tangga;
- masyarakat berpendapatan rendah;
- UMKM yang sensitif terhadap harga bahan pangan.

Beneficiary bukan pengguna langsung aplikasi pada MVP.

---

## 9. Jobs-to-be-Done

| ID | Ketika... | Pengguna ingin... | Agar... |
|---|---|---|---|
| JTBD-01 | membuka dashboard pada awal hari | melihat komoditas/wilayah paling berisiko | fokus analisis langsung terbentuk |
| JTBD-02 | sebuah alarm muncul | memahami fakta, prediksi, dan inferensi secara terpisah | tidak salah membaca hasil model |
| JTBD-03 | perlu menyusun bahan rapat | mendapatkan ringkasan dan opsi respons | pembahasan lebih cepat dan terarah |
| JTBD-04 | output AI dipertanyakan | membuka sumber, freshness, dan metrik model | rekomendasi dapat dipertanggungjawabkan |
| JTBD-05 | data tidak lengkap | mengetahui apa yang hilang dan dampaknya | keputusan tidak dibuat dengan confidence palsu |
| JTBD-06 | beberapa komoditas berisiko bersamaan | melihat paket tinjauan terkoordinasi | isu terkait dapat dibahas dalam satu forum |

---

## 10. User Journey Utama

```text
Login
  ↓
Executive Dashboard
  ↓
Lihat status wilayah + data freshness
  ↓
Lihat Top 3 Prioritas
  ↓
Buka satu Prioritas
  ↓
Baca Fakta → Prediksi → Faktor → Missing Information
  ↓
Lihat Next Step dan Response Options
  ↓
Tandai: Untuk Dibahas / Ditunda / Ditolak
  ↓
Kembali ke daftar atau buka Paket Tinjauan Bersama
```

### 10.1 Jalur ketika data bermasalah

```text
Data stale / coverage rendah / ML offline
  ↓
Sistem menampilkan confidence rendah atau status service unavailable
  ↓
Forecast/rekomendasi spesifik disembunyikan atau dibatasi
  ↓
Pengguna tetap dapat melihat monitoring historis dan langkah verifikasi data
```

---

## 11. Taksonomi Status yang Disatukan

Untuk menghindari konflik antara status HET, status risiko, dan protokol, UI menggunakan tiga lapisan berbeda.

| Lapisan | Nilai | Arti |
|---|---|---|
| **Kondisi Harga** | Di Bawah Ambang, Mendekati Ambang, Melampaui Ambang | Fakta posisi harga terhadap HET/threshold |
| **Risiko** | Rendah, Sedang, Tinggi, Kritis | Hasil gabungan kondisi sekarang dan proyeksi |
| **Respons Sistem** | Monitor, Verifikasi, Koordinasikan, Pertimbangkan Intervensi | Langkah tinjauan yang disarankan, bukan keputusan final |

### 11.1 Aturan bahasa

- “Pertimbangkan Intervensi” berarti **eskalasi untuk evaluasi manusia**, bukan perintah GPM.
- Label “Intervensi Segera” dari referensi resmi dapat ditampilkan pada evidence layer, tetapi UI harus menjelaskan bahwa implementasi tindakan memerlukan prosedur dan kewenangan resmi.
- Warna tidak boleh menjadi satu-satunya pembeda; selalu sertakan teks dan ikon.

---

## 12. Prioritization Engine

### 12.1 Tujuan

Menghasilkan ranking yang deterministik, dapat dijelaskan, dan dapat dikonfigurasi tanpa bergantung pada LLM.

### 12.2 Input

- posisi harga terhadap HET/threshold;
- perubahan harga 7 dan 30 hari;
- forecast P50/P90;
- probabilitas atau indikator breach;
- change point/z-score;
- regional disparity;
- cuaca dan kalender;
- freshness dan coverage data;
- ketersediaan stok bila tersedia.

### 12.3 Skor prioritas MVP

Bobot berikut adalah `INTERNAL_HYPOTHESIS` dan disimpan di konfigurasi, bukan hard-coded di UI.

| Komponen | Bobot awal |
|---|---:|
| Posisi harga saat ini terhadap ambang | 25% |
| Risiko forecast P90 melampaui ambang | 30% |
| Momentum/anomali/change point | 20% |
| Persebaran kenaikan lintas wilayah | 15% |
| Sinyal konteks cuaca/kalender | 10% |

`raw_priority_score` berada pada skala 0–100.

### 12.4 Confidence factor

| Confidence | Kondisi minimum | Faktor tampilan |
|---|---|---:|
| Tinggi | freshness ≤1 hari, coverage ≥90%, model tidak lebih buruk dari baseline | 1.00 |
| Sedang | freshness ≤2 hari, coverage ≥75%, atau performa model borderline | 0.85 |
| Rendah | freshness >2 hari, coverage <75%, history tidak cukup, atau model underperform | 0.65 |

`display_priority_score = raw_priority_score × confidence_factor`

Ketika confidence rendah, sistem tidak boleh memberikan response option yang lebih spesifik daripada “Verifikasi”.

### 12.5 Kategori risiko awal

| Skor | Risiko |
|---:|---|
| 0–24 | Rendah |
| 25–49 | Sedang |
| 50–74 | Tinggi |
| 75–100 | Kritis |

Threshold ini merupakan `INTERNAL_HYPOTHESIS` dan harus ditampilkan pada halaman transparansi.

---

## 13. Fitur MVP — Must Have (P0)

### P0-01 — Authentication dan RBAC

**Deskripsi:** mempertahankan login JWT dan role Viewer, Analyst, serta Admin.

**Acceptance criteria:**

- Viewer hanya melihat dashboard dan detail read-only.
- Analyst dapat memberi status review.
- Admin dapat mengakses user management dan data quality.
- Route sensitif tidak dapat dibuka hanya dengan manipulasi URL.

### P0-02 — Executive Dashboard

**Deskripsi:** halaman utama berorientasi keputusan.

**Isi minimum:**

- status wilayah;
- jumlah komoditas berisiko tinggi/kritis;
- data terakhir dan status pipeline;
- Top 3 prioritas;
- paket tinjauan bersama;
- perubahan risiko dibanding snapshot sebelumnya bila tersedia.

**Acceptance criteria:**

- Prioritas pertama terlihat tanpa scroll pada layar desktop 1366×768.
- Pengguna dapat membuka detail dalam satu klik.
- Tidak lebih dari tiga metrik utama pada baris pertama.

### P0-03 — Data Freshness dan Provenance

**Deskripsi:** trust bar pada dashboard dan setiap detail.

**Field minimum:**

- nama sumber;
- waktu data terbaru;
- waktu pipeline terakhir;
- coverage wilayah;
- jumlah missing record;
- status aktual/imputasi/fallback;
- versi transformasi bila tersedia.

**Acceptance criteria:**

- 100% kartu prioritas memiliki sumber dan timestamp.
- Data stale diberi label eksplisit.
- Sistem tidak menampilkan “real-time” bila sumber hanya harian.

### P0-04 — Ranked Priority Queue

**Deskripsi:** tabel/kartu daftar komoditas dan wilayah yang diurutkan berdasarkan score.

**Field minimum:**

- rank;
- komoditas;
- wilayah;
- kondisi harga;
- risiko;
- horizon;
- confidence;
- response system;
- alasan ringkas.

**Acceptance criteria:**

- Ranking berasal dari engine deterministik.
- Pengguna dapat memfilter provinsi, wilayah, komoditas, dan risiko.
- Ranking tetap tersedia saat LLM offline.

### P0-05 — Detail Prioritas Berbasis Bukti

**Deskripsi:** satu halaman atau drawer yang menyatukan data aktual, forecast, dan RCA.

**Urutan informasi:**

1. Fakta teramati
2. Output model
3. Faktor yang mungkin berkontribusi
4. Data yang belum tersedia
5. Response options
6. Sumber dan metodologi

**Acceptance criteria:**

- Fakta, prediksi, dan inferensi memiliki label berbeda.
- Pengguna dapat melihat histori harga dan threshold.
- Bowtie/FTA berada pada drill-down, bukan elemen utama.

### P0-06 — Forecast P50/P90

**Deskripsi:** visualisasi prediksi 7 dan 14 hari dengan rentang ketidakpastian.

**Acceptance criteria:**

- Grafik membedakan actual, P50, dan P90.
- Tooltip menjelaskan bahwa P90 bukan kepastian harga.
- UI menampilkan horizon, model version, tanggal training, dan confidence.
- Bila model tidak layak, sistem menggunakan baseline/fallback atau menyembunyikan forecast dengan alasan.

### P0-07 — Explainable Risk Factors

**Deskripsi:** ringkasan faktor berdasarkan data dan engine, bukan teks bebas.

**Kategori minimum:**

- kondisi harga;
- tren/anomali;
- forecast;
- persebaran regional;
- cuaca;
- kalender;
- stok bila tersedia.

**Acceptance criteria:**

- Setiap faktor memiliki `type`: FACT, MODEL_OUTPUT, atau INFERENCE.
- Faktor tanpa bukti tidak ditampilkan.
- “Root cause” tidak boleh diklaim pasti bila hanya korelasi.

### P0-08 — Structured Response Options

**Deskripsi:** sistem menyajikan langkah berikutnya dengan batas aman.

| Risiko | Minimum next step | Opsi tambahan |
|---|---|---|
| Rendah | Monitor | Tidak ada |
| Sedang | Verifikasi harga/data | Monitoring intensif |
| Tinggi | Verifikasi harga dan stok; koordinasikan tinjauan | Koordinasi distribusi sebagai opsi |
| Kritis | Eskalasi untuk human review | Pertimbangkan evaluasi intervensi pasar |

**Acceptance criteria:**

- Sistem tidak menggunakan kata “wajib”, “harus dilakukan BI”, atau instruksi eksekusi otomatis.
- Missing information selalu terlihat.
- Response options berasal dari rule engine.

### P0-09 — Paket Tinjauan Bersama

**Deskripsi:** mengelompokkan beberapa komoditas/wilayah yang layak dibahas dalam satu forum.

**Aturan awal:**

- risiko Tinggi/Kritis;
- berada dalam provinsi atau klaster wilayah yang sama;
- horizon risiko tumpang tindih dalam 7 hari;
- terdapat minimal dua komoditas;
- sistem hanya menyebut “paket tinjauan”, bukan “paket GPM”.

**Output:**

- daftar komoditas;
- wilayah;
- urgensi;
- alasan pengelompokan;
- data yang belum tersedia untuk menilai kelayakan tindakan.

**Acceptance criteria:**

- Paket dapat dijelaskan oleh rule yang terlihat.
- Paket tidak dibuat ketika confidence seluruh anggotanya rendah.
- Sistem menyatakan bahwa kesiapan stok/logistik belum dinilai bila datanya tidak ada.

### P0-10 — Human Review State

**Deskripsi:** Analyst dapat memberi status terhadap rekomendasi.

**Status:**

- Belum Ditinjau
- Untuk Dibahas
- Ditunda
- Ditolak

**Field minimum:**

- reviewer;
- timestamp;
- alasan/catatan singkat;
- snapshot rekomendasi.

**Acceptance criteria:**

- Status dapat disimpan dan ditampilkan kembali.
- Penolakan/penundaan dapat diberi alasan.
- Tidak ada tombol “Jalankan Intervensi”.

### P0-11 — Data & Model Transparency

**Deskripsi:** panel/halaman yang menjelaskan sumber, pipeline, model, metrik, dan batasan.

**Isi minimum:**

- data source dan update cadence;
- data coverage;
- feature set tingkat tinggi;
- model version;
- WAPE/MAE;
- P90 coverage atau pinball loss;
- baseline comparison;
- known limitations;
- threshold dan bobot internal.

**Acceptance criteria:**

- Metrik berasal dari pengujian nyata.
- Tidak ada klaim “akurasi” tanpa definisi metrik.
- Model yang lebih buruk dari baseline diberi label dan tidak disembunyikan.

### P0-12 — Graceful Degradation dan Error State

**Acceptance criteria:**

- ML offline: monitoring, priority berbasis rule, dan histori tetap tersedia.
- LLM offline: explanation menggunakan template deterministik.
- Data source gagal: timestamp terakhir dan status stale terlihat.
- Error tidak menampilkan credential atau stack trace kepada user.

### P0-13 — Auditability Dasar

**Deskripsi:** log minimal untuk model run, data snapshot, dan review user.

**Acceptance criteria:**

- Setiap rekomendasi memiliki `recommendation_id`.
- Model version, timestamp, dan data cutoff dapat ditelusuri.
- Perubahan status review terekam.

---

## 14. Fitur Nice to Have (P1)

| ID | Fitur | Nilai | Catatan |
|---|---|---|---|
| P1-01 | RAG-lite dengan sitasi | Menjelaskan metodologi dan dasar respons | Hanya corpus terotorisasi; bukan penentu tindakan |
| P1-02 | Executive brief otomatis | Mempercepat bahan rapat | Teks harus berasal dari structured object |
| P1-03 | Ekspor PDF/print view | Memudahkan distribusi | Tidak menjadi blocker MVP |
| P1-04 | Perbandingan hari ini vs kemarin | Menunjukkan perubahan prioritas | Memerlukan snapshot stabil |
| P1-05 | Outcome tracking ringan | Menilai tindak lanjut | Hanya catatan awal, bukan causal evaluation |
| P1-06 | Notifikasi | Mengurangi kebutuhan membuka dashboard | Ditunda bila kanal belum jelas |
| P1-07 | Sensitivity view | Menunjukkan dampak perubahan threshold | Berguna untuk transparansi, bukan prioritas sprint |

---

## 15. AI/ML Product Requirements

### 15.1 Arsitektur keputusan

```text
Data Aktual
  ↓
Forecast & Detection Engine
  ↓
Deterministic Prioritization
  ↓
Response Option Rules
  ↓
Structured Recommendation Object
  ↓
Optional RAG/LLM Explanation
  ↓
Human Review
```

### 15.2 Pembagian tanggung jawab

| Komponen | Boleh melakukan | Tidak boleh melakukan |
|---|---|---|
| ML forecast | memprediksi P50/P90 dan risiko | menyatakan masa depan sebagai kepastian |
| Detection engine | mendeteksi anomaly/breach/disparity | menyimpulkan sebab final tanpa bukti |
| Rule engine | menentukan risk label dan response options | menjalankan kebijakan |
| LLM | merangkum dan menjelaskan structured object | menciptakan tindakan baru |
| RAG | mengambil sumber terotorisasi | mengambil internet bebas saat runtime |
| Human | menerima, menunda, menolak, atau mengeskalasi | — |

### 15.3 Evaluasi model wajib

Minimal tersedia:

- baseline `last value` atau moving/seasonal naïve;
- MAE dan/atau WAPE untuk P50;
- pinball loss untuk quantile;
- empirical coverage untuk P90;
- backtest beberapa periode;
- breakdown per komoditas bila sampel memadai;
- tanggal training dan data cutoff.

### 15.4 Kebijakan fallback

- Bila LightGBM lebih buruk dari baseline pada slice tertentu, gunakan baseline atau tandai confidence rendah.
- Bila history tidak cukup, forecast tidak ditampilkan.
- Bila data terbaru terlalu lama, response option dibatasi pada “Verifikasi”.

### 15.5 RAG-lite

**Corpus yang diizinkan:**

1. Handbook resmi EWS;
2. Data & Model Card;
3. AI Output Policy;
4. Response Option Matrix;
5. dokumen sponsor/domain expert yang kemudian divalidasi dan diberi versi.

**Corpus yang tidak boleh dianggap resmi:**

- asumsi internal;
- skenario simulasi;
- hasil generasi LLM sebelumnya;
- sumber internet yang tidak dikurasi.

### 15.6 Structured recommendation schema

```json
{
  "recommendation_id": "rec_20260712_001",
  "commodity": "Cabai Rawit Merah",
  "region": "Jawa Barat",
  "price_condition": "MENDEKATI_AMBANG",
  "risk_level": "TINGGI",
  "time_horizon_days": 7,
  "confidence": "SEDANG",
  "observed_facts": [
    "Harga meningkat 8,1% dalam tujuh hari"
  ],
  "model_outputs": [
    "Forecast P90 berada di atas ambang risiko"
  ],
  "possible_factors": [
    {
      "factor": "Curah hujan tinggi",
      "evidence_type": "INFERENCE"
    }
  ],
  "next_step": "VERIFY_AND_COORDINATE",
  "response_options": [
    "Verifikasi harga pada sumber alternatif",
    "Konfirmasi ketersediaan stok",
    "Koordinasikan tinjauan distribusi"
  ],
  "missing_information": [
    "Volume stok",
    "Kapasitas logistik"
  ],
  "sources": [
    {
      "name": "PIHPS",
      "data_cutoff": "2026-07-12"
    }
  ],
  "knowledge_status": "INTERNAL_MVP_HYPOTHESIS",
  "requires_human_review": true
}
```

### 15.7 AI guardrails

- Pisahkan FACT, MODEL_OUTPUT, dan INFERENCE.
- Tidak mengarang stok, kewenangan, biaya, volume, atau jadwal.
- Tidak mengklaim korelasi sebagai kausalitas.
- Tidak menampilkan sumber yang tidak benar-benar dipakai.
- Fail closed ketika bukti tidak cukup.
- Seluruh output dapat dirender tanpa paragraf bebas.

---

## 16. Data Requirements

### 16.1 Sumber utama

| Data | Sumber | Peran | Risiko |
|---|---|---|---|
| Harga pangan | PIHPS | kondisi aktual dan training | keterlambatan/missing wilayah |
| HET/threshold | referensi internal/resmi | klasifikasi kondisi | versi dan tanggal berlaku |
| Cuaca | Open-Meteo | contextual feature | bukan bukti sebab tunggal |
| Hari besar | `python-holidays`/kalender | seasonality context | pergeseran pola lokal |
| Musim panen | referensi | contextual feature | cakupan/validitas belum seragam |
| Stok | endpoint/data yang tersedia | feasibility check | kelengkapan belum terjamin |
| Prediksi | ML service | risk horizon | drift dan underperformance |

### 16.2 Field provenance minimum

Setiap response utama harus membawa:

- `source_name`
- `source_version` bila ada
- `data_cutoff`
- `pipeline_run_id`
- `ingested_at`
- `coverage_ratio`
- `missing_count`
- `imputation_status`
- `model_version`

### 16.3 Data quality gate

| Gate | Kondisi | Dampak |
|---|---|---|
| Freshness | >2 hari | confidence rendah |
| Coverage | <75% | forecast/rekomendasi dibatasi |
| Missing consecutive | melewati batas konfigurasi | tidak melakukan inference |
| Outlier unresolved | terdeteksi dan belum diverifikasi | tampilkan warning |
| Source mismatch | unit/komoditas/wilayah tidak konsisten | blokir publish |

---

## 17. Information Architecture dan UI

### 17.1 Halaman MVP

| Halaman | Tujuan |
|---|---|
| Login | authentication |
| Executive Dashboard | melihat status, prioritas, dan paket tinjauan |
| Detail Prioritas | melihat bukti dan response options |
| Transparency | melihat data/model card dan batasan |
| Admin | user dan data quality |

Implementasi boleh mempertahankan route `/analysis` dan `/prediksi`, tetapi pengalaman pengguna harus terasa sebagai satu alur detail, bukan dua produk terpisah.

### 17.2 Susunan Executive Dashboard

```text
[Header: Wilayah | Data Terakhir | Status Pipeline]

[Status Wilayah] [Jumlah Risiko Tinggi/Kritis] [Confidence Data]

Top Priorities
1. Komoditas A — Risiko Kritis — 7 hari — Lihat Detail
2. Komoditas B — Risiko Tinggi — 7 hari — Lihat Detail
3. Komoditas C — Risiko Tinggi — 14 hari — Lihat Detail

Paket Tinjauan Bersama
- Komoditas A + B
- Alasan pengelompokan
- Missing information

[Data & Model Transparency]
```

### 17.3 Susunan Detail Prioritas

```text
Judul + Risiko + Confidence + Data Cutoff

Apa yang terjadi?        → fakta harga
Apa yang diprediksi?     → P50/P90
Mengapa perlu perhatian? → faktor terstruktur
Apa yang belum diketahui?→ missing information
Apa langkah berikutnya?  → verify/coordinate/options
Apa dasarnya?            → source, method, model metric

[Untuk Dibahas] [Tunda] [Tolak]
```

### 17.4 UI quality bar

- Desktop-first, tetap terbaca pada tablet.
- Prioritas pertama tampil tanpa scroll.
- Grafik maksimum satu grafik utama per detail.
- Gunakan progressive disclosure.
- Jangan menggunakan warna saja untuk risiko.
- Gunakan bahasa Indonesia nonteknis pada layer utama.
- Istilah P50/P90 memiliki tooltip.
- Skeleton/loading dan empty state tersedia.
- Setiap error memberikan langkah pemulihan yang jelas.

---

## 18. API dan Kontrak Backend

### 18.1 Endpoint agregasi yang direkomendasikan

```text
GET  /api/mvp/overview
GET  /api/mvp/priorities
GET  /api/mvp/priorities/{recommendation_id}
POST /api/mvp/priorities/{recommendation_id}/review
GET  /api/mvp/transparency
GET  /api/mvp/service-status
```

### 18.2 `GET /api/mvp/overview`

Response minimum:

- selected region;
- data freshness;
- service health;
- summary counts;
- top priorities;
- review bundles;
- latest reviews.

Tujuan endpoint agregasi adalah mengurangi orkestrasi banyak API di frontend dalam sprint singkat.

### 18.3 Tabel baru minimum

`decision_review`

| Field | Tipe |
|---|---|
| id | UUID/string |
| recommendation_id | string |
| status | enum |
| reviewer_user_id | FK/string |
| note | text nullable |
| recommendation_snapshot | JSON |
| created_at | timestamp |
| updated_at | timestamp |

Tidak diperlukan workflow approval kompleks pada MVP.

---

## 19. Non-Functional Requirements

### 19.1 Performance

- Dashboard cached/served dalam target p95 ≤3 detik pada environment demo.
- Detail prioritas target p95 ≤4 detik termasuk ML proxy.
- Timeout ML/LLM tidak boleh memblokir seluruh halaman.

### 19.2 Reliability

- Health endpoint untuk app dan ML.
- Graceful fallback untuk ML/LLM.
- Pipeline status terlihat.
- Demo dataset/snapshot tersedia untuk kondisi darurat dan diberi label `SIMULATION`.

### 19.3 Security

- JWT secret dan credential tidak masuk repository.
- RBAC pada backend, bukan hanya menyembunyikan tombol.
- Security headers dan CORS tetap aktif.
- Tidak menampilkan data sensitif atau sinyal kebijakan kepada role yang tidak sesuai.

### 19.4 Auditability

- Data cutoff, model version, dan recommendation ID tersimpan.
- Review user dapat ditelusuri.
- Bobot/threshold dicatat sebagai konfigurasi versi.

### 19.5 Accessibility

- Contrast memadai.
- Label teks pada status.
- Keyboard focus pada aksi utama.
- Grafik memiliki ringkasan teks.

---

## 20. Success Metrics

### 20.1 MVP product metrics

| Metrik | Target MVP |
|---|---:|
| Pengguna uji dapat menyebut prioritas #1 dan next step dalam 60 detik | ≥80% |
| Kartu prioritas dengan source + timestamp + confidence | 100% |
| Skenario AI yang hanya memakai response option terotorisasi | 100% |
| Skenario data tidak cukup yang berhasil abstain/menurunkan confidence | 100% |
| Output AI yang memisahkan fact/model/inference | 100% |
| Jalur utama demo dapat selesai tanpa error | 100% pada rehearsal final |
| Test rule engine dan schema utama | Lulus |

### 20.2 Model metrics

- WAPE/MAE P50 dilaporkan.
- Pinball loss atau coverage P90 dilaporkan.
- Hasil dibanding baseline.
- Tidak ada target angka fiktif; hasil aktual ditampilkan apa adanya.

### 20.3 Pilot metrics pasca-hackathon

- waktu analisis sebelum vs sesudah;
- jumlah alert yang ditinjau;
- acceptance rate rekomendasi;
- false-positive rate;
- jumlah isu yang dapat dibahas sebagai satu paket;
- potensi cost avoidance, setelah data biaya tersedia.

---

## 21. Testing dan Validation Plan

### 21.1 Test teknis

- unit test risk score;
- unit test confidence gate;
- unit test response option rules;
- schema contract test;
- endpoint auth/RBAC;
- ML timeout/fallback;
- data stale/fallback;
- E2E login → dashboard → detail → review.

### 21.2 Test AI/RAG

Gunakan 10–15 skenario, termasuk:

1. harga tinggi tetapi tren menurun;
2. forecast tinggi tetapi data stale;
3. risiko tinggi tetapi stok tidak tersedia;
4. kenaikan hanya di satu wilayah;
5. beberapa komoditas berisiko bersamaan;
6. penyebab tidak jelas;
7. ML offline;
8. LLM offline;
9. dokumen tidak memuat dasar yang relevan;
10. user meminta rekomendasi volume/jadwal yang tidak tersedia.

Kriteria penilaian:

- groundedness;
- action validity;
- citation correctness;
- constraint compliance;
- abstention;
- consistency of structured output.

### 21.3 Test usability singkat

Uji kepada minimal 3 orang non-engineer menggunakan tiga tugas:

1. temukan prioritas tertinggi;
2. jelaskan alasan risikonya;
3. tentukan langkah berikutnya menurut sistem.

Catat waktu, kesalahan, dan istilah yang membingungkan.

---

## 22. Rencana Sprint 7–10 Hari

| Hari | Fokus | Person A: FE/BE/Data | Person B: ML/Product |
|---:|---|---|---|
| 1 | Scope freeze dan audit | audit endpoint/data/UI | audit model dan metrik |
| 2 | Kontrak keputusan | schema + endpoint agregasi | risk score + rule matrix |
| 3 | Transparansi data/model | provenance + data quality | backtest + baseline |
| 4 | Executive dashboard | implementasi layout | copy dan test scenario |
| 5 | Detail prioritas | grafik + evidence blocks | explainability mapping |
| 6 | Response options + review | review API/UI | guardrail validation |
| 7 | Paket tinjauan + fallback | grouping + error state | test model/AI |
| 8 | Integration test | E2E + bug fix | pitch narrative + results |
| 9 | Usability dan polish | UI refinement | demo rehearsal |
| 10 | Buffer | critical bug only | final metrics dan deck |

### 22.1 Scope cut rule

Bila waktu tersisa kurang dari tiga hari, urutan yang dipertahankan:

1. Executive Dashboard
2. Priority Queue
3. Detail Evidence
4. Data/Model Transparency
5. Structured Response Options
6. Human Review
7. Paket Tinjauan
8. RAG-lite/Export

---

## 23. Risiko dan Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Tidak ada intervention playbook tervalidasi | rekomendasi dianggap kebijakan resmi | gunakan response options dan human review |
| Data terlambat/missing | confidence palsu | freshness/coverage gate |
| Model lebih buruk dari baseline | kepercayaan turun | benchmark transparan dan fallback |
| UI terlalu teknis | pengguna gagal memahami | action-first dan progressive disclosure |
| LLM berhalusinasi | rekomendasi tidak aman | structured object, whitelist action, fail closed |
| ML service gagal saat demo | fitur utama hilang | graceful degradation dan cached snapshot |
| Scope terlalu besar | MVP tidak selesai | freeze P0 dan cut P1 |
| Data ownership tidak jelas | hambatan komersialisasi | validasi lisensi sebelum scale |
| Sinyal sensitif bocor | konflik kepentingan/front-running | RBAC, private deployment, data firewall |
| Klaim “real-time” tidak akurat | kredibilitas turun | gunakan “latest available”/daily intelligence |

---

## 24. Ketergantungan Sponsor dan Domain Partner

MVP dapat berjalan tanpa sponsor operasional baru, tetapi kualitas produk meningkat bila sponsor menyediakan:

- validasi definisi risiko dan response option;
- SOP atau panduan resmi yang dapat dijadikan corpus;
- akses pilot user;
- data stok/logistik yang berizin;
- feedback terhadap UI dan interpretasi model;
- cloud credit atau infrastructure support.

Produk tidak boleh menganggap dukungan teknis sponsor sebagai endorsement kebijakan.

---

## 25. Demo Scenario Utama

### Skenario

Dua komoditas pada provinsi yang sama menunjukkan risiko tinggi dalam tujuh hari, tetapi data stok belum tersedia.

### Alur demo

1. User login sebagai Analyst.
2. Dashboard menampilkan dua komoditas sebagai Top Priority.
3. Sistem membuat “Paket Tinjauan Bersama”.
4. User membuka detail komoditas pertama.
5. UI memisahkan harga aktual, forecast P50/P90, dan faktor cuaca/regional.
6. Sistem menyatakan data stok belum tersedia.
7. Next step: verifikasi harga dan stok; koordinasikan tinjauan distribusi.
8. User menandai “Untuk Dibahas”.
9. User membuka transparency panel untuk melihat data cutoff dan performa model.

### Pesan utama demo

> R.A.D.A.R Pangan tidak mengambil alih keputusan TPID. Sistem mempersempit ruang analisis, menunjukkan bukti dan ketidakpastian, lalu membantu manusia menentukan isu mana yang perlu dibahas terlebih dahulu.

---

## 26. Definition of Done

MVP dinyatakan siap tahap berikutnya ketika:

- [ ] User journey utama dapat diselesaikan end-to-end.
- [ ] Dashboard menampilkan Top 3 Priority dan data freshness.
- [ ] Detail memisahkan fact, model output, dan inference.
- [ ] Forecast P50/P90 memiliki metrik dan baseline comparison.
- [ ] Response options berasal dari rule engine.
- [ ] Human review dapat disimpan.
- [ ] Data stale dan ML/LLM outage memiliki fallback.
- [ ] Minimal 10 skenario guardrail diuji.
- [ ] Tidak ada klaim intervention playbook resmi.
- [ ] Demo rehearsal selesai tanpa critical error.
- [ ] Semua asumsi internal diberi label.

---

## 27. Validasi Pasca-MVP

Pertanyaan yang perlu diuji kepada pengguna/domain expert setelah tahap hackathon:

1. Apakah ranking sistem selaras dengan cara analis memilih prioritas?
2. Informasi minimum apa yang dibutuhkan sebelum isu layak dibawa ke rapat TPID?
3. Siapa yang berwenang memvalidasi response option per instansi?
4. Apakah paket tinjauan beberapa komoditas benar-benar menghemat waktu atau biaya koordinasi?
5. Data stok/logistik apa yang realistis tersedia?
6. Bagaimana keberhasilan tindak lanjut seharusnya diukur?
7. Berapa frekuensi penggunaan dan willingness-to-pay untuk deployment/maintenance?

---

## 28. Referensi Internal

- *Handbook Dashboard Early Warning System — BI KPw Sibolga*, khususnya alur dashboard, menu PMI, PIHPS, dan Summary.
- *FAQ Analisis Produk — EWS Dashboard Inflasi*, khususnya problem bundling, MVP, pain point, user mapping, dan strategi bisnis.
- `PROJECT_OVERVIEW.md` R.A.D.A.R Pangan, versi aplikasi 0.7.0 dan baseline arsitektur/fitur.
- Keputusan diskusi Tim Simatana, 12 Juli 2026.

