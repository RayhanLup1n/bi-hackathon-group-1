{{
    config(
        materialized='table',
        description='Dimension: kalender tanggal dengan fitur musiman dan hari besar'
    )
}}

/*
  Date dimension — satu baris per tanggal unik yang ada di data.
  Include: kalender features + flag hari besar dari raw.hari_besar.
  Materialized as TABLE karena JOIN ke hari_besar.

  BigQuery notes:
  - EXTRACT(DAYOFWEEK FROM ...) returns 1=Sunday, 7=Saturday
  - DATE_TRUNC(date, WEEK) / DATE_TRUNC(date, MONTH) syntax
  - LOGICAL_OR() instead of BOOL_OR()
  - LOWER() + LIKE instead of ILIKE
  - DATE_SUB/DATE_ADD instead of INTERVAL arithmetic
*/

WITH date_spine AS (
    SELECT DISTINCT CAST(tanggal AS DATE) AS tanggal
    FROM {{ source('raw', 'harga_pangan') }}
    WHERE tanggal IS NOT NULL
      AND tanggal >= '2020-01-01'  -- partition filter required by BigQuery
),

hari_besar_agg AS (
    -- Aggregate hari besar per tanggal (bisa >1 hari besar di tanggal yang sama)
    SELECT
        tanggal,
        TRUE                                    AS is_hari_besar,
        STRING_AGG(nama, '; ' ORDER BY nama)    AS nama_hari_besar,
        -- Flag apakah hari raya yang biasanya spike demand
        LOGICAL_OR(kategori = 'islam')          AS is_hari_raya_islam,
        LOGICAL_OR(kategori = 'cuti_bersama')   AS is_cuti_bersama
    FROM {{ source('raw', 'hari_besar') }}
    GROUP BY tanggal
),

-- Window hari besar: H-14 sebelum dan H+3 setelah hari raya Islam
-- (periode demand spike untuk komoditas pangan)
hari_raya_window AS (
    SELECT tanggal
    FROM {{ source('raw', 'hari_besar') }}
    WHERE kategori = 'islam'
      AND (LOWER(nama) LIKE '%idul fitri%' OR LOWER(nama) LIKE '%idul adha%')
)

SELECT
    ds.tanggal,
    CAST(EXTRACT(YEAR FROM ds.tanggal) AS INT64)      AS tahun,
    CAST(EXTRACT(MONTH FROM ds.tanggal) AS INT64)     AS bulan,
    CAST(EXTRACT(QUARTER FROM ds.tanggal) AS INT64)   AS kuartal,
    CAST(EXTRACT(DAYOFWEEK FROM ds.tanggal) AS INT64) AS hari_dalam_minggu,  -- 1=Sunday, 7=Saturday
    CAST(DATE_TRUNC(ds.tanggal, WEEK) AS DATE)        AS minggu,
    CAST(DATE_TRUNC(ds.tanggal, MONTH) AS DATE)       AS bulan_pertama,

    -- Weekday flag (BigQuery: 1=Sunday, 7=Saturday → weekday = NOT IN (1, 7))
    CASE
        WHEN EXTRACT(DAYOFWEEK FROM ds.tanggal) NOT IN (1, 7) THEN TRUE
        ELSE FALSE
    END                                         AS is_weekday,

    -- Seasonal proxies
    CASE
        WHEN EXTRACT(MONTH FROM ds.tanggal) IN (3, 4, 5) THEN TRUE
        ELSE FALSE
    END                                         AS is_ramadan_season,

    CASE
        WHEN EXTRACT(MONTH FROM ds.tanggal) IN (12, 1) THEN TRUE
        ELSE FALSE
    END                                         AS is_year_end_season,

    -- Hari besar flags
    COALESCE(hb.is_hari_besar, FALSE)           AS is_hari_besar,
    hb.nama_hari_besar,
    COALESCE(hb.is_hari_raya_islam, FALSE)      AS is_hari_raya_islam,
    COALESCE(hb.is_cuti_bersama, FALSE)         AS is_cuti_bersama,

    -- Window hari raya (H-14 s/d H+3 dari Idul Fitri/Adha)
    CASE
        WHEN EXISTS (
            SELECT 1 FROM hari_raya_window hrw
            WHERE ds.tanggal BETWEEN DATE_SUB(hrw.tanggal, INTERVAL 14 DAY)
                                AND DATE_ADD(hrw.tanggal, INTERVAL 3 DAY)
        ) THEN TRUE
        ELSE FALSE
    END                                         AS is_window_hari_raya

FROM date_spine ds
LEFT JOIN hari_besar_agg hb ON ds.tanggal = hb.tanggal
ORDER BY ds.tanggal
