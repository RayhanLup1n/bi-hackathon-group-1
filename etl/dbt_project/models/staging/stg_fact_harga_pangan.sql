{{
    config(
        materialized='view',
        description='Fact: harga pangan normalized — hanya FK + measure (harga)'
    )
}}

/*
  FACT TABLE — 3NF normalized.
  Hanya menyimpan foreign keys ke dimension tables + measure (harga).
  Cleaned dan deduplicated dari raw.harga_pangan.

  Grain: satu baris per (tanggal, comcat_id, kota_id, pasar_tipe, pasar_nama)
*/

WITH cleaned AS (
    SELECT
        CAST(tanggal AS DATE)                   AS tanggal,
        comcat_id,
        CAST(kota_id AS INT64)                  AS kota_id,
        CAST(pasar_tipe AS INT64)               AS pasar_tipe,
        TRIM(pasar_nama)                        AS pasar_nama,
        CASE
            WHEN harga <= 0 THEN NULL
            ELSE CAST(harga AS FLOAT64)
        END                                     AS harga,
        _extracted_at
    FROM {{ source('raw', 'harga_pangan') }}
    WHERE tanggal IS NOT NULL
      AND tanggal >= '2020-01-01'  -- partition filter required by BigQuery
      AND comcat_id IS NOT NULL
      AND comcat_id != ''
),

-- Deduplicate: keep latest extraction per natural key
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY tanggal, comcat_id, kota_id, pasar_nama
            ORDER BY _extracted_at DESC
        ) AS rn
    FROM cleaned
)

SELECT
    tanggal,
    comcat_id,
    kota_id,
    pasar_tipe,
    pasar_nama,
    harga
FROM deduped
WHERE rn = 1
  AND harga IS NOT NULL
