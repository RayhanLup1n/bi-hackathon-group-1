# Backend Folder Structure

## TLDR

Revamp tahap pertama menggunakan pendekatan layered architecture berbasis bounded
context. Modul canonical dipisahkan berdasarkan tanggung jawabnya, sementara
entrypoint dan struktur runtime lama tetap kompatibel melalui re-export shim.

## Struktur Canonical

~~~text
src/
├── api/                         # HTTP presentation layer
├── application/                 # use-case orchestration
├── core/                        # shared configuration and cross-cutting concerns
├── domain/
│   ├── engines/                 # HET, RCA, and Bowtie business engines
│   └── schemas/                 # domain and validation schemas
├── infrastructure/
│   ├── postgres/                # PostgreSQL database, auth, commodity, weather
│   └── bigquery/                # BigQuery client and data-quality access
├── data/                        # legacy compatibility shims
├── engine/                      # legacy compatibility shims
└── models/                      # legacy compatibility shims
~~~

## Tanggung Jawab Layer

### API

Berisi route dan adapter HTTP. Layer ini menerima request, memanggil domain atau
application service, lalu membentuk response API.

### Application

Menjadi tempat orchestration use case ketika alur bisnis mulai melibatkan
beberapa engine atau sumber data. Folder ini sengaja disiapkan lebih dahulu dan
akan diisi secara bertahap pada fase berikutnya.

### Domain

Berisi logika bisnis utama yang tidak bergantung langsung pada framework HTTP
atau provider database:

- domain/engines/ berisi HET monitoring, RCA, dan Bowtie.
- domain/schemas/ berisi model input dan output domain.

### Infrastructure

Berisi implementasi akses terhadap sistem eksternal:

- infrastructure/postgres/ untuk koneksi dan query PostgreSQL.
- infrastructure/bigquery/ untuk client dan validasi data BigQuery.

## Compatibility Shim

Path lama di src/data, src/engine, dan src/models masih dipertahankan sebagai
modul tipis yang melakukan re-export dari lokasi canonical. Tujuannya adalah
menjaga kompatibilitas terhadap integrasi atau import lama selama proses revamp
berlangsung.

Kode baru sebaiknya menggunakan path canonical. Shim dapat dihapus setelah
seluruh consumer eksternal dan internal sudah bermigrasi.

## Arah Dependensi

Aturan dependensi yang digunakan:

~~~text
API -> Application -> Domain
                         ^
Infrastructure ---------|
~~~

Domain tidak boleh mengimpor route, konfigurasi provider, atau detail koneksi
database secara langsung. Infrastruktur boleh digunakan oleh application layer
atau adapter yang membutuhkan akses data.

## Top-Level Context Lain

Folder berikut belum dipindahkan pada fase pertama karena memiliki lifecycle
deploy atau runtime yang berbeda:

- main.py: entrypoint FastAPI saat ini.
- etl/: pipeline fetch, transform, dan sync data.
- ml/: training dan serving model.
- frontend/: static frontend.
- config/: konfigurasi deployment dan environment.

Pemindahan folder-folder tersebut perlu dilakukan sebagai fase terpisah setelah
kontrak runtime dan deployment disepakati.

## Aturan Penambahan Kode Baru

1. Route HTTP baru ditempatkan di src/api/.
2. Orchestration lintas fitur ditempatkan di src/application/.
3. Logika bisnis murni ditempatkan di src/domain/.
4. Akses PostgreSQL ditempatkan di src/infrastructure/postgres/.
5. Akses BigQuery ditempatkan di src/infrastructure/bigquery/.
6. Hindari menambahkan implementation baru pada path legacy.
7. Setiap perpindahan modul harus mempertahankan test dan kontrak import yang
   relevan.
