# Business Model Canvas

## R.A.D.A.R Pangan — Decision Support Risiko Harga Pangan

> **Model bisnis utama saat ini:** B2G / institutional solution  
> **Bentuk produk awal:** private web application dengan opsi white-label  
> **Nilai inti:** mengubah data harga dan hasil ML menjadi prioritas, bukti, serta bahan koordinasi yang dapat ditinjau manusia.

---

## 1. Status dan Batas Canvas

| Atribut | Nilai |
|---|---|
| Versi | 1.0 |
| Tanggal | 12 Juli 2026 |
| Tahap | MVP hackathon → pilot institusional |
| Primary buyer hypothesis | BI KPw, TPID, atau pemerintah daerah |
| Primary user | Analis/sekretariat TPID |
| Decision user | Pimpinan/anggota pengambil keputusan TPID |
| Model delivery awal | Implementasi privat dan white-label |
| Status validasi bisnis | Hipotesis; belum ada willingness-to-pay atau pilot formal |

Canvas ini membedakan:

- **yang sudah didukung produk/rujukan**;
- **hipotesis bisnis yang masih perlu divalidasi**;
- **visi jangka panjang yang belum menjadi scope MVP**.

R.A.D.A.R Pangan tidak mengklaim sebagai produk resmi Bank Indonesia dan tidak menganggap asumsi internal sebagai SOP pemerintah.

---

## 2. Business Model Canvas — Ringkasan 9 Blok

| Blok | Isi inti |
|---|---|
| **Customer Segments** | BI KPw/TPID/Pemda sebagai buyer; analis TPID sebagai primary user; pimpinan TPID sebagai decision user; Bulog/Dinas/Satgas sebagai co-user potensial |
| **Value Propositions** | prioritas risiko harian, forecast P50/P90, bukti yang dapat ditelusuri, response options yang aman, paket tinjauan bersama, transparansi data/model |
| **Channels** | pilot melalui hackathon, direct institutional outreach, partner/referral, white-label deployment, workshop dan demo berbasis kasus |
| **Customer Relationships** | assisted onboarding, training, konfigurasi wilayah, support/maintenance, review model dan data quality berkala |
| **Revenue Streams** | implementation fee, annual maintenance/retainer, white-label/license per wilayah, custom analytics, API/private deployment pada tahap lanjut |
| **Key Resources** | data pipeline, serving database, ML model, risk/rule engine, UI decision workflow, tim engineering/ML, governance dan domain knowledge |
| **Key Activities** | data quality, model evaluation, deployment, konfigurasi threshold, user training, support, validation, security dan auditability |
| **Key Partners** | BI/TPID sebagai pilot/domain partner; BPS/PIHPS/data owner; Bulog/Dinas sebagai operational validator; cloud/technology sponsor; kampus/domain expert |
| **Cost Structure** | cloud, data pipeline, model training/inference, support, onboarding, security, validation, maintenance, sales/procurement cycle |

---

## 3. Customer Segments

### 3.1 Segmen utama — Buyer

#### A. BI Kantor Perwakilan dan TPID

**Masalah yang dialami:**

- harus memantau banyak komoditas dan wilayah;
- keputusan perlu dibuat dari data harian, bukan hanya angka inflasi bulanan;
- prioritas dan alasan perlu konsisten serta dapat dipertanggungjawabkan;
- waktu analis dan sumber daya koordinasi terbatas.

**Mengapa cocok:**

- memiliki mandat stabilisasi harga;
- menggunakan data dan indikator yang serupa;
- membutuhkan executive summary dan evidence layer;
- dapat menggunakan model private deployment/white-label.

#### B. Pemerintah daerah

**Peran potensial:** buyer, sponsor pilot, atau pemilik deployment lokal.

### 3.2 Segmen pengguna

| Peran | Kebutuhan |
|---|---|
| Analis/sekretariat TPID | ranking, bukti, forecast, bahan rapat |
| Pimpinan TPID | ringkasan cepat, confidence, alasan, batasan |
| Admin/data steward | user management, data quality, pipeline status |

### 3.3 Co-user potensial

- Bulog
- Dinas Perdagangan
- Dinas Ketahanan Pangan
- Satgas Pangan

Mereka dapat memakai sinyal yang sama untuk verifikasi atau koordinasi, tetapi workflow operasional mereka belum menjadi scope MVP.

### 3.4 Beneficiary

- rumah tangga;
- masyarakat berpendapatan rendah;
- UMKM yang tergantung pada bahan pangan.

Beneficiary menerima dampak tidak langsung melalui respons yang lebih cepat dan terarah.

### 3.5 Segmen jangka menengah/panjang

- Bapanas/Kemendag untuk agregasi lintas wilayah;
- distributor dan retail untuk risk management stok;
- agri-tech atau asuransi untuk API analytics.

Segmen privat memerlukan restrukturisasi produk, lisensi data, dan firewall yang memisahkan sinyal kebijakan dari sinyal komersial.

---

## 4. Value Propositions

### 4.1 Value proposition utama

> **Dari data harga yang tersebar menjadi satu daftar prioritas dan bahan koordinasi yang dapat dijelaskan.**

### 4.2 Nilai untuk analis TPID

- tidak perlu memeriksa seluruh komoditas satu per satu;
- mendapatkan ranking berdasarkan kondisi, forecast, anomali, dan persebaran regional;
- dapat membuka bukti dan sumber ketika rekomendasi dipertanyakan;
- mengetahui data apa yang belum tersedia;
- dapat menandai isu untuk dibahas, ditunda, atau ditolak.

### 4.3 Nilai untuk pimpinan TPID

- memahami situasi dalam waktu singkat;
- melihat risiko dan confidence, bukan hanya angka harga;
- mendapatkan bahasa eksekutif tanpa kehilangan audit trail;
- mengetahui bahwa AI merupakan decision support, bukan pengambil keputusan.

### 4.4 Nilai untuk institusi

- standardisasi prioritas antarperiode;
- proses analisis lebih konsisten;
- potensi pengurangan pekerjaan manual;
- potensi pembahasan beberapa komoditas dalam satu paket;
- data historis keputusan untuk evaluasi.

### 4.5 Nilai yang belum boleh diklaim sebagai fakta

- penghematan anggaran GPM;
- penurunan inflasi secara langsung;
- akurasi intervensi;
- keberhasilan bundling operasional;
- willingness-to-pay institusi.

Semua poin tersebut adalah hipotesis yang memerlukan pilot dan data outcome.

---

## 5. Channels

### 5.1 Akuisisi awal

1. **Hackathon/demo institusional** — menunjukkan masalah, alur keputusan, data transparency, dan bukti ML.
2. **Pilot langsung** — satu wilayah, enam komoditas, 4–8 minggu.
3. **Workshop pengguna** — sesi dengan analis dan decision maker untuk validasi workflow.
4. **Referral antar-KPw/TPID** — setelah ada satu studi kasus yang kredibel.
5. **Partnership channel** — cloud sponsor, universitas, atau konsultan implementasi pemerintah.

### 5.2 Delivery channel

- private cloud deployment;
- deployment pada environment klien;
- white-label web application;
- API/private data service pada tahap lanjut.

### 5.3 Communication channel

- executive demo;
- one-page outcome report;
- workshop data/model transparency;
- periodic review meeting;
- support channel untuk admin dan analis.

---

## 6. Customer Relationships

### 6.1 Model hubungan awal

**High-touch institutional relationship**, bukan self-service SaaS murni.

Komponen:

- discovery dan konfigurasi wilayah;
- onboarding dan training;
- assisted pilot;
- support untuk data quality;
- model review berkala;
- governance review untuk output AI;
- incident handling.

### 6.2 Setelah produk stabil

- standard onboarding package;
- dashboard health report;
- quarterly business review;
- knowledge base;
- service level agreement sesuai tier.

### 6.3 Prinsip hubungan

- tidak menjanjikan keputusan otomatis;
- menampilkan keterbatasan secara terbuka;
- memisahkan konfigurasi produk dari SOP resmi klien;
- seluruh perubahan threshold/policy rule memiliki versioning.

---

## 7. Revenue Streams

### 7.1 Model realistis jangka pendek

| Revenue stream | Bentuk | Catatan |
|---|---|---|
| Implementation fee | biaya setup per wilayah | data mapping, deployment, konfigurasi, training |
| Annual maintenance/retainer | biaya tahunan | monitoring pipeline, bug fix, model refresh, support |
| White-label license | biaya per kantor/wilayah | branding dan konfigurasi lokal |
| Custom analytics | project fee | komoditas, wilayah, atau laporan khusus |
| Training/workshop | fee per sesi/paket | penggunaan, data literacy, model transparency |

### 7.2 Model jangka menengah

- private SaaS subscription per tenant;
- API fee berdasarkan volume request atau jumlah wilayah;
- advanced forecasting tier;
- premium data-quality monitoring;
- enterprise support/SLA.

### 7.3 Model yang tidak boleh dilakukan tanpa izin

- menjual kembali data PIHPS/BPS;
- menjual sinyal kebijakan sensitif kepada pihak swasta;
- mengomersialkan informasi sponsor tanpa lisensi;
- menjadikan nama BI sebagai endorsement komersial tanpa persetujuan.

### 7.4 Cost-avoidance sebagai value, bukan revenue langsung

Potensi penghematan waktu analisis atau kegiatan koordinasi dapat menjadi argumen pembelian, tetapi harus diukur melalui pilot. Jangan memasukkan angka penghematan sebelum ada baseline biaya dan outcome.

---

## 8. Key Resources

### 8.1 Teknologi

- data pipeline PIHPS, cuaca, kalender, HET, dan referensi lain;
- BigQuery warehouse;
- PostgreSQL/Supabase serving database;
- FastAPI backend;
- web frontend;
- LightGBM quantile models;
- detection engine;
- RCA/Bowtie evidence engine;
- rule-based prioritization dan response options;
- authentication/RBAC;
- deployment dan observability.

### 8.2 Data dan knowledge

- data historis harga;
- metadata sumber dan freshness;
- HET/threshold version;
- model evaluation history;
- response option matrix;
- data/model card;
- dokumen resmi yang dapat dipakai untuk RAG.

### 8.3 Manusia

- FE/UI + Backend + Data Engineering;
- ML engineer;
- product/presentation;
- domain expert atau validator;
- institutional relationship owner.

### 8.4 Aset yang dapat menjadi defensible advantage

- end-to-end pipeline dari data hingga review manusia;
- decision workflow yang explainable;
- evaluation and audit trail;
- reusable white-label architecture;
- historical decision/outcome dataset setelah pilot.

Keunggulan ini adalah hipotesis dan belum boleh disamakan dengan endorsement institusi.

---

## 9. Key Activities

### 9.1 Build dan operate

- ekstraksi dan transformasi data;
- data quality monitoring;
- model training, inference, dan evaluation;
- konfigurasi threshold/rule;
- frontend dan backend maintenance;
- security patching;
- deployment dan observability.

### 9.2 Product dan domain

- user research;
- validasi workflow;
- validasi response options;
- dokumentasi data/model;
- guardrail testing;
- training pengguna;
- outcome review.

### 9.3 Commercial

- pilot design;
- proposal institutional;
- procurement/tender support;
- white-label configuration;
- SLA dan support planning;
- case study development.

---

## 10. Key Partners

### 10.1 Partner domain dan pilot

| Partner | Peran yang diharapkan | Nilai bagi partner |
|---|---|---|
| BI KPw/TPID | domain validation, pilot user, governance | analisis lebih terstruktur dan transparan |
| Pemda | sponsor pilot, deployment owner | decision support lokal |
| Bulog | validasi stok/distribusi | prioritas koordinasi lebih jelas |
| Dinas Perdagangan/Ketahanan Pangan | validasi operational response | bahan verifikasi dan rapat |
| Kampus/domain expert | independent review | riset dan evaluasi metodologi |

### 10.2 Partner data

- pemilik/pengelola data PIHPS;
- BPS untuk data inflasi sesuai hak akses;
- penyedia cuaca;
- penyedia referensi HET dan kalender.

### 10.3 Technology partner/sponsor

- cloud credit;
- infrastructure;
- observability;
- security review;
- mentoring AI/ML;
- demo support.

### 10.4 Batas kemitraan

- akses data harus tertulis;
- hak penggunaan ulang dan komersialisasi harus jelas;
- sponsor tidak otomatis bertanggung jawab atas keputusan sistem;
- branding/endorsement memerlukan persetujuan eksplisit;
- data kebijakan sensitif harus dipisahkan dari penggunaan komersial.

---

## 11. Cost Structure

### 11.1 Biaya tetap/berulang

- cloud compute dan storage;
- database/warehouse;
- model inference;
- monitoring/observability;
- domain dan SSL;
- maintenance engineering;
- security dan backup;
- support.

### 11.2 Biaya variabel

- onboarding wilayah baru;
- data mapping;
- konfigurasi threshold;
- training user;
- custom integration;
- model retraining;
- LLM token/inference bila dipakai;
- travel/workshop.

### 11.3 Biaya tersembunyi yang perlu dihitung

- procurement cycle;
- koordinasi lintas instansi;
- compliance dan legal review;
- data licensing;
- support data quality;
- perubahan SOP atau requirement daerah.

---

## 12. Problem–Solution Fit

### 12.1 Problem yang dipilih

> TPID membutuhkan cara yang cepat dan konsisten untuk mengidentifikasi, memprioritaskan, dan membahas beberapa risiko harga pangan secara bersamaan, karena data dan analitik belum otomatis menjadi bahan keputusan yang ringkas dan dapat ditelusuri.

### 12.2 Alternatif saat ini

- spreadsheet/manual analysis;
- dashboard harga tanpa ranking;
- rapat berdasarkan laporan periodik;
- monitoring terpisah per data source;
- keputusan berbasis pengalaman individu.

### 12.3 Mengapa R.A.D.A.R Pangan berbeda

- memadukan data, detection, forecast, dan review workflow;
- ranking deterministik dan explainable;
- confidence dan missing information terlihat;
- response options dibatasi aturan;
- paket tinjauan beberapa komoditas;
- human-in-the-loop.

---

## 13. Sponsor Collaboration Model

### 13.1 Bentuk kerja sama yang direkomendasikan

#### A. Data & Domain Validation Partner

**Sponsor memberi:**

- dokumen resmi;
- definisi indikator;
- feedback threshold;
- validasi istilah dan workflow.

**Sponsor menerima:**

- prototipe yang dikonfigurasi;
- laporan data quality;
- transparansi model;
- hasil usability/pilot.

#### B. Pilot Partner

**Sponsor memberi:**

- akses 3–5 pengguna;
- kasus penggunaan nyata;
- review mingguan;
- feedback keputusan.

**Sponsor menerima:**

- private pilot;
- support dan training;
- pilot outcome report;
- hak meninjau penggunaan nama/logo.

#### C. Technology Partner

**Sponsor memberi:**

- cloud credit;
- infrastructure;
- mentoring;
- security/architecture review.

**Sponsor menerima:**

- showcase penggunaan teknologi;
- case study teknis setelah persetujuan;
- brand exposure yang disepakati.

#### D. Scale/Commercial Partner

**Sponsor memberi:**

- channel ke wilayah lain;
- procurement support;
- implementation capacity.

**Sponsor menerima:**

- revenue share atau implementation fee sesuai perjanjian;
- white-label/partner tier;
- training dan support package.

### 13.2 Prinsip pertukaran nilai

Kerja sama harus menjawab secara tertulis:

1. data apa yang diberikan;
2. tujuan penggunaannya;
3. siapa yang memiliki IP;
4. apakah hasil boleh dipublikasikan;
5. siapa yang bertanggung jawab terhadap keputusan;
6. berapa lama data disimpan;
7. apakah produk boleh direplikasi;
8. bagaimana penggunaan merek/logo.

---

## 14. Go-to-Market Bertahap

### Fase 1 — Hackathon dan proof of value

**Target:** menunjukkan bahwa produk dapat menghasilkan prioritas dan bukti yang lebih mudah dipahami.

**Output:**

- MVP web;
- model evaluation;
- guardrail test;
- demo scenario;
- BMC dan PRD.

### Fase 2 — Pilot satu institusi

**Target:** validasi problem–solution fit.

**Durasi hipotesis:** 4–8 minggu.

**Yang diukur:**

- waktu menuju insight;
- pemahaman pengguna;
- alert acceptance;
- false positive;
- kualitas data;
- relevansi paket tinjauan.

### Fase 3 — White-label B2G

**Target:** replikasi ke KPw/TPID lain.

**Produk:**

- setup package;
- configurable region/commodity;
- private deployment;
- annual support.

### Fase 4 — Private SaaS/API

Dilakukan hanya setelah:

- data rights jelas;
- model tervalidasi independen;
- security dan tenant isolation siap;
- konflik kepentingan dimitigasi;
- terdapat pola penggunaan berulang.

---

## 15. Key Metrics

### 15.1 Product metrics

- time-to-understand top priority;
- active analyst users;
- priority cards reviewed;
- percentage output with complete provenance;
- recommendation review rate;
- bundle review rate;
- model performance vs baseline;
- data freshness SLA.

### 15.2 Business metrics

- pilot conversion rate;
- implementation cycle time;
- annual contract value;
- maintenance renewal;
- onboarding cost per region;
- gross margin per deployment;
- support tickets per tenant.

### 15.3 Outcome metrics yang masih perlu pilot

- penurunan waktu analisis;
- pengurangan duplikasi rapat/kegiatan;
- cost avoidance;
- perubahan harga setelah tindak lanjut;
- kualitas koordinasi lintas instansi.

---

## 16. Critical Assumptions Register

| ID | Asumsi | Status | Cara validasi |
|---|---|---|---|
| A-01 | Analis mengalami kesulitan menentukan prioritas | `INTERNAL_HYPOTHESIS` | wawancara dan task test |
| A-02 | Pimpinan membutuhkan ringkasan ≤1 menit | `INTERNAL_HYPOTHESIS` | usability test |
| A-03 | Paket tinjauan beberapa komoditas bernilai | `INTERNAL_HYPOTHESIS` | pilot dan review kasus |
| A-04 | Institusi bersedia membayar implementasi/maintenance | `INTERNAL_HYPOTHESIS` | pricing interview |
| A-05 | Data dapat digunakan untuk deployment komersial | `UNVALIDATED` | legal/data agreement |
| A-06 | LightGBM memberi nilai lebih dari baseline | `MODEL_OUTPUT_TO_VALIDATE` | backtest |
| A-07 | Response option aman tanpa playbook resmi | `INTERNAL_HYPOTHESIS` | domain validation |
| A-08 | White-label lebih realistis daripada public SaaS awal | `INTERNAL_HYPOTHESIS` | buyer interview |

---

## 17. Risiko Bisnis dan Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Data ownership/reuse tidak jelas | model bisnis terhambat | MoU/lisensi sebelum scale |
| Front-running/conflict of interest | risiko kebijakan | private deployment dan firewall data |
| Kredibilitas bergantung pada nama BI | sulit scale independen | evaluasi model dan pilot independen |
| Procurement cycle panjang | cash flow lambat | retainer, partner implementasi, phased pilot |
| Tidak ada playbook tervalidasi | rekomendasi terlalu generik | response options + domain partner |
| Data quality tidak konsisten | user kehilangan trust | provenance dan quality SLA |
| Customization berlebihan | margin turun | template white-label dan config-driven rules |
| User adoption rendah | produk tidak dipakai | assisted onboarding dan action-first UI |
| Model drift | rekomendasi menurun | monitoring dan scheduled review |
| Sponsor dianggap memberi endorsement | reputational/legal risk | kontrak branding dan disclaimer |

---

## 18. Pricing Hypothesis untuk Validasi

Tidak ada angka harga final pada tahap ini. Struktur yang perlu diuji:

1. **Pilot fee** — setup terbatas dan evaluasi.
2. **Implementation fee** — data mapping, deployment, konfigurasi, training.
3. **Annual maintenance** — support, monitoring, update, model review.
4. **White-label license** — per wilayah atau tenant.
5. **Enterprise/API tier** — setelah data rights dan multi-tenancy siap.

Pricing interview harus menilai:

- siapa pemilik anggaran;
- proses procurement;
- preferred contract type;
- acceptable service level;
- nilai penghematan waktu/koordinasi;
- kebutuhan hosting on-premise/private cloud.

---

## 19. Business Model Recommendation

### 19.1 Model yang direkomendasikan sekarang

> **B2G assisted implementation + annual maintenance, dengan produk private/white-label.**

Alasan:

- cocok dengan kebutuhan data sensitif;
- tidak membutuhkan multi-tenant SaaS dalam sprint;
- memungkinkan konfigurasi lokal;
- lebih realistis untuk pilot institusional;
- memanfaatkan arsitektur yang sudah ada.

### 19.2 Model yang belum direkomendasikan sekarang

- marketplace pasokan;
- public consumer app;
- penjualan insight ke distributor;
- open API berbayar;
- autonomous policy agent.

Model tersebut memerlukan validasi data rights, security, operational playbook, dan conflict-of-interest control.

---

## 20. One-Sentence Pitch

> **R.A.D.A.R Pangan membantu TPID mengubah data harga dan prediksi ML menjadi daftar prioritas, bukti, dan paket tinjauan bersama yang dapat dipahami cepat serta tetap berada di bawah kendali manusia.**

---

## 21. Referensi Internal

- *Handbook Dashboard Early Warning System — BI KPw Sibolga*.
- *FAQ Analisis Produk — EWS Dashboard Inflasi*.
- `PROJECT_OVERVIEW.md` R.A.D.A.R Pangan.
- Keputusan diskusi Tim Simatana, 12 Juli 2026.

