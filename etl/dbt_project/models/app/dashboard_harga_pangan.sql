{{
    config(
        materialized='table',
        schema='app',
        description='Dashboard table: satu tabel khusus untuk frontend dashboard, denormalized dan pre-computed'
    )
}}

/*
  TABEL DASHBOARD UTAMA — satu-satunya tabel yang dibaca oleh frontend.

  Denormalized star schema: JOIN semua dimensions + pre-computed metrics.
  Grain: satu baris per (tanggal, komoditas, kota, pasar_tipe).

  Frontend cukup SELECT dari tabel ini tanpa perlu JOIN apapun.

  Fitur:
  - Harga terkini + historis (kemarin, minggu lalu, bulan lalu)
  - Delta harga + persentase perubahan
  - Benchmark nasional (rata-rata, min, max)
  - Status harga (Naik/Turun/Stabil)
  - Alert flags (harga tinggi)
  - Konteks hari besar (apakah ada hari raya yang mempengaruhi demand)
*/

WITH fact AS (
    SELECT * FROM {{ ref('stg_fact_harga_pangan') }}
),

dim_komoditas AS (
    SELECT * FROM {{ ref('stg_dim_komoditas') }}
),

dim_kota AS (
    SELECT * FROM {{ ref('stg_dim_kota') }}
),

dim_pasar AS (
    SELECT * FROM {{ ref('stg_dim_pasar_tipe') }}
),

dim_tanggal AS (
    SELECT * FROM {{ ref('stg_dim_tanggal') }}
),

-- Harga + lag features per komoditas-kota
with_lags AS (
    SELECT
        f.tanggal,
        f.comcat_id,
        f.kota_id,
        f.pasar_tipe,
        f.pasar_nama,
        f.harga                                                     AS harga_hari_ini,

        LAG(f.harga, 1) OVER (
            PARTITION BY f.comcat_id, f.kota_id, f.pasar_tipe
            ORDER BY f.tanggal
        )                                                           AS harga_kemarin,

        LAG(f.harga, 7) OVER (
            PARTITION BY f.comcat_id, f.kota_id, f.pasar_tipe
            ORDER BY f.tanggal
        )                                                           AS harga_minggu_lalu,

        LAG(f.harga, 30) OVER (
            PARTITION BY f.comcat_id, f.kota_id, f.pasar_tipe
            ORDER BY f.tanggal
        )                                                           AS harga_bulan_lalu

    FROM fact f
),

-- Benchmark nasional per komoditas per tanggal
avg_nasional AS (
    SELECT
        tanggal,
        comcat_id,
        pasar_tipe,
        ROUND(AVG(harga)::NUMERIC, 2)               AS harga_rata_nasional,
        ROUND(MIN(harga)::NUMERIC, 2)                AS harga_min_nasional,
        ROUND(MAX(harga)::NUMERIC, 2)                AS harga_maks_nasional,
        COUNT(DISTINCT kota_id)                      AS jumlah_kota_dilaporkan
    FROM fact
    GROUP BY tanggal, comcat_id, pasar_tipe
),

-- Gabungkan semua
combined AS (
    SELECT
        -- === Identifiers ===
        wl.tanggal,
        wl.comcat_id,
        dk.komoditas_nama,
        dk.satuan,
        wl.kota_id,
        dko.kota_nama,
        dko.provinsi_id,
        dko.provinsi_nama,
        wl.pasar_tipe,
        dp.pasar_tipe_label,

        -- === Harga ===
        wl.harga_hari_ini,
        wl.harga_kemarin,
        wl.harga_minggu_lalu,
        wl.harga_bulan_lalu,

        -- === Delta ===
        ROUND((wl.harga_hari_ini - wl.harga_kemarin)::NUMERIC, 2)
                                                                    AS delta_1d,
        ROUND((wl.harga_hari_ini - wl.harga_minggu_lalu)::NUMERIC, 2)
                                                                    AS delta_7d,
        ROUND((wl.harga_hari_ini - wl.harga_bulan_lalu)::NUMERIC, 2)
                                                                    AS delta_30d,

        CASE
            WHEN wl.harga_kemarin > 0
            THEN ROUND(
                ((wl.harga_hari_ini - wl.harga_kemarin) / wl.harga_kemarin * 100)::NUMERIC, 2
            )
        END                                                         AS pct_change_1d,

        CASE
            WHEN wl.harga_minggu_lalu > 0
            THEN ROUND(
                ((wl.harga_hari_ini - wl.harga_minggu_lalu) / wl.harga_minggu_lalu * 100)::NUMERIC, 2
            )
        END                                                         AS pct_change_7d,

        -- === Benchmark Nasional ===
        an.harga_rata_nasional,
        an.harga_min_nasional,
        an.harga_maks_nasional,
        an.jumlah_kota_dilaporkan,

        CASE
            WHEN an.harga_rata_nasional > 0
            THEN ROUND((wl.harga_hari_ini / an.harga_rata_nasional)::NUMERIC, 4)
        END                                                         AS rasio_vs_nasional,

        -- === Status Harga ===
        CASE
            WHEN wl.harga_kemarin IS NULL               THEN 'Tidak Ada Data'
            WHEN wl.harga_hari_ini > wl.harga_kemarin   THEN 'Naik'
            WHEN wl.harga_hari_ini < wl.harga_kemarin   THEN 'Turun'
            ELSE                                              'Stabil'
        END                                                         AS status_harga_harian,

        -- === Alert Flags ===
        CASE
            WHEN an.harga_rata_nasional > 0
             AND wl.harga_hari_ini > an.harga_rata_nasional * 1.10
            THEN TRUE
            ELSE FALSE
        END                                                         AS is_harga_tinggi_alert,

        -- === Konteks Hari Besar ===
        COALESCE(dt.is_hari_besar, FALSE)                           AS is_hari_besar,
        dt.nama_hari_besar,
        COALESCE(dt.is_window_hari_raya, FALSE)                     AS is_window_hari_raya,

        -- === Calendar ===
        dt.tahun,
        dt.bulan,
        dt.kuartal,
        dt.hari_dalam_minggu,
        COALESCE(dt.is_weekday, TRUE)                               AS is_weekday

    FROM with_lags wl

    -- JOIN dimensions
    LEFT JOIN dim_komoditas dk    ON wl.comcat_id  = dk.comcat_id
    LEFT JOIN dim_kota dko        ON wl.kota_id    = dko.kota_id
    LEFT JOIN dim_pasar dp        ON wl.pasar_tipe = dp.pasar_tipe
    LEFT JOIN dim_tanggal dt      ON wl.tanggal    = dt.tanggal

    -- JOIN benchmark nasional
    LEFT JOIN avg_nasional an
        ON  wl.tanggal    = an.tanggal
        AND wl.comcat_id  = an.comcat_id
        AND wl.pasar_tipe = an.pasar_tipe
)

SELECT *
FROM combined
ORDER BY tanggal DESC, comcat_id, kota_id
