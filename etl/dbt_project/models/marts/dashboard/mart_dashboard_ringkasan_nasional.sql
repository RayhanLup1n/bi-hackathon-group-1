{{
    config(
        materialized='table',
        description='Mart Dashboard: ringkasan harga per komoditas per hari (level nasional)'
    )
}}

/*
  Tabel ringkasan harian level nasional.
  Cocok untuk:
  - Grafik trend harga komoditas secara nasional
  - Tabel perbandingan antar komoditas
  - KPI cards di dashboard (harga hari ini, delta kemarin, alert)
*/

WITH daily_national AS (
    SELECT
        tanggal,
        comcat_id,
        komoditas_nama,
        satuan,
        pasar_tipe,
        pasar_tipe_label,

        -- Agregasi nasional
        ROUND(AVG(harga_hari_ini)::NUMERIC, 2)               AS rata_harga_nasional,
        ROUND(MIN(harga_hari_ini)::NUMERIC, 2)               AS harga_min,
        ROUND(MAX(harga_hari_ini)::NUMERIC, 2)               AS harga_maks,
        ROUND(STDDEV(harga_hari_ini)::NUMERIC, 2)            AS std_harga,
        COUNT(DISTINCT kota_id)                     AS jumlah_kota,
        COUNT(DISTINCT provinsi_id)                 AS jumlah_provinsi,

        -- Jumlah kota dengan alert harga tinggi
        SUM(CASE WHEN is_harga_tinggi_alert THEN 1 ELSE 0 END)
                                                    AS jumlah_kota_alert,

        -- Distribusi status harga
        SUM(CASE WHEN status_harga_harian = 'Naik'   THEN 1 ELSE 0 END)
                                                    AS kota_harga_naik,
        SUM(CASE WHEN status_harga_harian = 'Turun'  THEN 1 ELSE 0 END)
                                                    AS kota_harga_turun,
        SUM(CASE WHEN status_harga_harian = 'Stabil' THEN 1 ELSE 0 END)
                                                    AS kota_harga_stabil,

        -- Harga rata-rata kemarin (untuk delta nasional)
        ROUND(AVG(harga_kemarin)::NUMERIC, 2)                AS rata_harga_kemarin,
        ROUND(AVG(harga_minggu_lalu)::NUMERIC, 2)            AS rata_harga_minggu_lalu,

        tahun,
        bulan,
        kuartal

    FROM {{ ref('mart_dashboard_harga_pangan') }}
    GROUP BY
        tanggal, comcat_id, komoditas_nama, satuan,
        pasar_tipe, pasar_tipe_label, tahun, bulan, kuartal
)

SELECT
    *,
    -- Delta nasional
    ROUND((rata_harga_nasional - rata_harga_kemarin)::NUMERIC, 2)
                                                    AS delta_nasional_1d,
    CASE
        WHEN rata_harga_kemarin > 0
        THEN ROUND(
            ((rata_harga_nasional - rata_harga_kemarin) / rata_harga_kemarin * 100)::NUMERIC, 2
        )
    END                                             AS pct_change_nasional_1d,

    -- Status nasional (berdasarkan mayoritas kota)
    CASE
        WHEN kota_harga_naik   > kota_harga_turun AND kota_harga_naik > kota_harga_stabil
        THEN 'Naik'
        WHEN kota_harga_turun  > kota_harga_naik  AND kota_harga_turun > kota_harga_stabil
        THEN 'Turun'
        ELSE 'Stabil'
    END                                             AS status_nasional

FROM daily_national
ORDER BY tanggal DESC, comcat_id
