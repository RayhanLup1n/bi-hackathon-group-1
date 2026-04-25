{{
    config(
        materialized='table',
        description='Mart Modelling: dataset siap pakai untuk pelatihan model ML/forecasting harga pangan'
    )
}}

/*
  TUJUAN:
  Dataset ini dirancang untuk keperluan pemodelan prediktif (forecasting harga pangan).
  Setiap baris = satu kombinasi (tanggal, komoditas, kota) dengan:
    - Fitur lag harga (t-1, t-7, t-30)
    - Fitur statistik rolling (rata-rata, std dev, min, max)
    - Fitur kalender (musiman, hari libur, dll)
    - Target variable: harga hari ini
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
        harga,
        satuan,
        tahun,
        bulan,
        kuartal,
        hari_dalam_minggu
    FROM {{ ref('stg_harga_pangan') }}
    WHERE harga IS NOT NULL
      AND pasar_tipe = 1  -- fokus ke pasar tradisional untuk modelling
),

-- ── Lag features ─────────────────────────────────────────────────────────────
with_lags AS (
    SELECT
        *,
        -- Harga sebelumnya
        LAG(harga, 1)  OVER w  AS harga_lag_1d,    -- kemarin
        LAG(harga, 7)  OVER w  AS harga_lag_7d,    -- seminggu lalu
        LAG(harga, 14) OVER w  AS harga_lag_14d,   -- 2 minggu lalu
        LAG(harga, 30) OVER w  AS harga_lag_30d,   -- sebulan lalu

        -- Perubahan harga
        harga - LAG(harga, 1)  OVER w              AS delta_harga_1d,
        harga - LAG(harga, 7)  OVER w              AS delta_harga_7d,

        -- Perubahan % harga
        CASE
            WHEN LAG(harga, 1) OVER w > 0
            THEN ROUND((harga - LAG(harga, 1) OVER w) / LAG(harga, 1) OVER w * 100, 4)
        END                                         AS pct_change_1d,
        CASE
            WHEN LAG(harga, 7) OVER w > 0
            THEN ROUND((harga - LAG(harga, 7) OVER w) / LAG(harga, 7) OVER w * 100, 4)
        END                                         AS pct_change_7d

    FROM base
    WINDOW w AS (
        PARTITION BY comcat_id, kota_id
        ORDER BY tanggal
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )
),

-- ── Rolling statistics ────────────────────────────────────────────────────────
with_rolling AS (
    SELECT
        *,
        -- Rolling 7 hari
        AVG(harga) OVER (
            PARTITION BY comcat_id, kota_id
            ORDER BY tanggal
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        )                                           AS rolling_avg_7d,

        STDDEV(harga) OVER (
            PARTITION BY comcat_id, kota_id
            ORDER BY tanggal
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        )                                           AS rolling_std_7d,

        -- Rolling 30 hari
        AVG(harga) OVER (
            PARTITION BY comcat_id, kota_id
            ORDER BY tanggal
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                           AS rolling_avg_30d,

        STDDEV(harga) OVER (
            PARTITION BY comcat_id, kota_id
            ORDER BY tanggal
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                           AS rolling_std_30d,

        MIN(harga) OVER (
            PARTITION BY comcat_id, kota_id
            ORDER BY tanggal
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                           AS rolling_min_30d,

        MAX(harga) OVER (
            PARTITION BY comcat_id, kota_id
            ORDER BY tanggal
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                           AS rolling_max_30d,

        -- Harga relatif terhadap rata-rata nasional pada hari yang sama
        AVG(harga) OVER (
            PARTITION BY comcat_id, tanggal
        )                                           AS avg_harga_nasional,

    FROM with_lags
),

-- ── Fitur kalender tambahan ───────────────────────────────────────────────────
with_calendar AS (
    SELECT
        *,
        -- Apakah hari kerja (1=hari kerja, 0=akhir pekan)
        CASE WHEN hari_dalam_minggu NOT IN (0, 6) THEN 1 ELSE 0 END
                                                    AS is_weekday,

        -- Bulan Ramadan/Lebaran (harga cenderung naik) — April/Maret/Mei (variasi tiap tahun)
        -- Sebagai proxy sederhana: tandai bulan ke-3, 4, 5 sebagai musim tinggi
        CASE WHEN bulan IN (3, 4, 5) THEN 1 ELSE 0 END
                                                    AS is_ramadan_season,

        -- Akhir tahun (Desember-Januari: natal, tahun baru)
        CASE WHEN bulan IN (12, 1) THEN 1 ELSE 0 END
                                                    AS is_year_end_season,

        -- Harga dinormalisasi (z-score per komoditas-kota)
        CASE
            WHEN rolling_std_30d > 0
            THEN ROUND((harga - rolling_avg_30d) / rolling_std_30d, 4)
        END                                         AS harga_zscore_30d,

        -- Rasio harga terhadap rata-rata nasional
        CASE
            WHEN avg_harga_nasional > 0
            THEN ROUND(harga / avg_harga_nasional, 4)
        END                                         AS harga_ratio_nasional

    FROM with_rolling
)

SELECT
    -- ── Natural Key ──────────────────────────────────────────────────────
    tanggal,
    comcat_id,
    komoditas_nama,
    provinsi_id,
    provinsi_nama,
    kota_id,
    kota_nama,
    satuan,

    -- ── Target Variable ──────────────────────────────────────────────────
    harga                                           AS harga_aktual,

    -- ── Lag Features ─────────────────────────────────────────────────────
    harga_lag_1d,
    harga_lag_7d,
    harga_lag_14d,
    harga_lag_30d,
    delta_harga_1d,
    delta_harga_7d,
    ROUND(pct_change_1d, 4)                         AS pct_change_1d,
    ROUND(pct_change_7d, 4)                         AS pct_change_7d,

    -- ── Rolling Stats ─────────────────────────────────────────────────────
    ROUND(rolling_avg_7d, 2)                        AS rolling_avg_7d,
    ROUND(rolling_std_7d, 2)                        AS rolling_std_7d,
    ROUND(rolling_avg_30d, 2)                       AS rolling_avg_30d,
    ROUND(rolling_std_30d, 2)                       AS rolling_std_30d,
    rolling_min_30d,
    rolling_max_30d,
    ROUND(avg_harga_nasional, 2)                    AS avg_harga_nasional,
    harga_zscore_30d,
    harga_ratio_nasional,

    -- ── Calendar Features ────────────────────────────────────────────────
    tahun,
    bulan,
    kuartal,
    hari_dalam_minggu,
    is_weekday,
    is_ramadan_season,
    is_year_end_season

FROM with_calendar
ORDER BY comcat_id, kota_id, tanggal
