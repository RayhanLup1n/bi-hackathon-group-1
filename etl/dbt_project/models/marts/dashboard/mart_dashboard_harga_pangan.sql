{{
    config(
        materialized='table',
        description='Mart Dashboard: agregasi harga pangan siap digunakan untuk dashboard monitoring harian'
    )
}}

/*
  TUJUAN:
  Dataset pre-aggregated untuk kebutuhan dashboard monitoring harga pangan.
  Dirancang untuk query cepat tanpa perlu kalkulasi berat di layer BI tool.

  Fitur utama:
  - Harga terkini per komoditas per kota
  - Perubahan harga vs kemarin dan vs minggu lalu
  - Rata-rata nasional
  - Status harga (naik/turun/stabil)
*/

WITH base AS (
    SELECT
        tanggal,
        comcat_id,
        komoditas_nama,
        provinsi_id,
        provinsi_nama,
        kota_id,
        kota_nama,
        pasar_tipe,
        pasar_tipe_label,
        harga,
        satuan,
        tahun,
        bulan,
        kuartal
    FROM {{ ref('stg_harga_pangan') }}
    WHERE harga IS NOT NULL
),

-- ── Harga terkini per komoditas-kota ─────────────────────────────────────────
latest_per_kota AS (
    SELECT
        tanggal,
        comcat_id,
        komoditas_nama,
        provinsi_id,
        provinsi_nama,
        kota_id,
        kota_nama,
        pasar_tipe,
        pasar_tipe_label,
        harga                                                   AS harga_hari_ini,
        satuan,

        -- Harga kemarin
        LAG(harga, 1) OVER (
            PARTITION BY comcat_id, kota_id, pasar_tipe
            ORDER BY tanggal
        )                                                       AS harga_kemarin,

        -- Harga seminggu lalu
        LAG(harga, 7) OVER (
            PARTITION BY comcat_id, kota_id, pasar_tipe
            ORDER BY tanggal
        )                                                       AS harga_minggu_lalu,

        -- Harga sebulan lalu
        LAG(harga, 30) OVER (
            PARTITION BY comcat_id, kota_id, pasar_tipe
            ORDER BY tanggal
        )                                                       AS harga_bulan_lalu,

        tahun,
        bulan,
        kuartal

    FROM base
),

-- ── Rata-rata nasional per komoditas per tanggal ──────────────────────────────
avg_nasional AS (
    SELECT
        tanggal,
        comcat_id,
        pasar_tipe,
        ROUND(AVG(harga)::NUMERIC, 2)                              AS harga_rata_nasional,
        ROUND(MIN(harga)::NUMERIC, 2)                              AS harga_min_nasional,
        ROUND(MAX(harga)::NUMERIC, 2)                              AS harga_maks_nasional,
        COUNT(DISTINCT kota_id)                                 AS jumlah_kota_dilaporkan
    FROM base
    GROUP BY tanggal, comcat_id, pasar_tipe
),

-- ── Gabungkan & hitung derived metrics ───────────────────────────────────────
combined AS (
    SELECT
        lk.*,
        an.harga_rata_nasional,
        an.harga_min_nasional,
        an.harga_maks_nasional,
        an.jumlah_kota_dilaporkan,

        -- Delta & persentase perubahan
        ROUND((lk.harga_hari_ini - lk.harga_kemarin)::NUMERIC, 2)
                                                                AS delta_1d,
        ROUND((lk.harga_hari_ini - lk.harga_minggu_lalu)::NUMERIC, 2)
                                                                AS delta_7d,
        ROUND((lk.harga_hari_ini - lk.harga_bulan_lalu)::NUMERIC, 2)
                                                                AS delta_30d,

        CASE
            WHEN lk.harga_kemarin > 0
            THEN ROUND(
                ((lk.harga_hari_ini - lk.harga_kemarin) / lk.harga_kemarin * 100)::NUMERIC, 2
            )
        END                                                     AS pct_change_1d,

        CASE
            WHEN lk.harga_minggu_lalu > 0
            THEN ROUND(
                ((lk.harga_hari_ini - lk.harga_minggu_lalu) / lk.harga_minggu_lalu * 100)::NUMERIC, 2
            )
        END                                                     AS pct_change_7d,

        -- Rasio harga lokal vs nasional (>1 = lebih mahal dari rata-rata)
        CASE
            WHEN an.harga_rata_nasional > 0
            THEN ROUND((lk.harga_hari_ini / an.harga_rata_nasional)::NUMERIC, 4)
        END                                                     AS rasio_vs_nasional,

        -- Status harga dibanding kemarin
        CASE
            WHEN lk.harga_kemarin IS NULL               THEN 'Tidak Ada Data'
            WHEN lk.harga_hari_ini > lk.harga_kemarin  THEN 'Naik'
            WHEN lk.harga_hari_ini < lk.harga_kemarin  THEN 'Turun'
            ELSE                                             'Stabil'
        END                                                     AS status_harga_harian,

        -- Status vs minggu lalu
        CASE
            WHEN lk.harga_minggu_lalu IS NULL               THEN 'Tidak Ada Data'
            WHEN lk.harga_hari_ini > lk.harga_minggu_lalu  THEN 'Naik'
            WHEN lk.harga_hari_ini < lk.harga_minggu_lalu  THEN 'Turun'
            ELSE                                                 'Stabil'
        END                                                     AS status_harga_mingguan,

        -- Alert: harga > 10% di atas rata-rata nasional
        CASE
            WHEN an.harga_rata_nasional > 0
             AND lk.harga_hari_ini > an.harga_rata_nasional * 1.10
            THEN TRUE
            ELSE FALSE
        END                                                     AS is_harga_tinggi_alert

    FROM latest_per_kota lk
    LEFT JOIN avg_nasional an
        ON  lk.tanggal      = an.tanggal
        AND lk.comcat_id = an.comcat_id
        AND lk.pasar_tipe   = an.pasar_tipe
)

SELECT
    -- ── Identifiers ──────────────────────────────────────────────────────
    tanggal,
    comcat_id,
    komoditas_nama,
    satuan,
    provinsi_id,
    provinsi_nama,
    kota_id,
    kota_nama,
    pasar_tipe,
    pasar_tipe_label,

    -- ── Harga ────────────────────────────────────────────────────────────
    harga_hari_ini,
    harga_kemarin,
    harga_minggu_lalu,
    harga_bulan_lalu,

    -- ── Delta ─────────────────────────────────────────────────────────────
    delta_1d,
    delta_7d,
    delta_30d,
    pct_change_1d,
    pct_change_7d,

    -- ── Benchmark Nasional ────────────────────────────────────────────────
    harga_rata_nasional,
    harga_min_nasional,
    harga_maks_nasional,
    jumlah_kota_dilaporkan,
    rasio_vs_nasional,

    -- ── Status & Alert ───────────────────────────────────────────────────
    status_harga_harian,
    status_harga_mingguan,
    is_harga_tinggi_alert,

    -- ── Waktu ─────────────────────────────────────────────────────────────
    tahun,
    bulan,
    kuartal

FROM combined
ORDER BY tanggal DESC, comcat_id, provinsi_id, kota_id
