{{
    config(
        materialized='view',
        description='Staging: cleaning dan normalisasi data harga pangan mentah'
    )
}}

WITH source AS (
    SELECT * FROM {{ source('raw', 'harga_pangan') }}
),

cleaned AS (
    SELECT
        -- Primary identifiers
        CAST(tanggal AS DATE)                                   AS tanggal,
        comcat_id,
        TRIM(komoditas_nama)                                    AS komoditas_nama,
        CAST(pasar_tipe AS INT64)                               AS pasar_tipe,

        -- Dimensi wilayah
        CAST(provinsi_id AS INT64)                              AS provinsi_id,
        TRIM(provinsi_nama)                                     AS provinsi_nama,
        CAST(kota_id AS INT64)                                  AS kota_id,
        TRIM(kota_nama)                                         AS kota_nama,
        TRIM(pasar_nama)                                        AS pasar_nama,

        -- Harga: filter nilai negatif atau nol yang tidak wajar
        CASE
            WHEN harga <= 0 THEN NULL
            ELSE CAST(harga AS FLOAT64)
        END                                                     AS harga,

        LOWER(TRIM(satuan))                                     AS satuan,

        -- Label tipe pasar
        CASE pasar_tipe
            WHEN 1 THEN 'Pasar Tradisional'
            WHEN 2 THEN 'Pasar Modern'
            WHEN 3 THEN 'Pedagang Besar'
            WHEN 4 THEN 'Produsen'
            ELSE 'Tidak Diketahui'
        END                                                     AS pasar_tipe_label,

        -- Dimensi waktu turunan
        CAST(EXTRACT(YEAR FROM tanggal) AS INT64)               AS tahun,
        CAST(EXTRACT(MONTH FROM tanggal) AS INT64)              AS bulan,
        CAST(EXTRACT(QUARTER FROM tanggal) AS INT64)            AS kuartal,
        CAST(EXTRACT(DAYOFWEEK FROM tanggal) AS INT64)          AS hari_dalam_minggu,
        CAST(DATE_TRUNC(tanggal, WEEK) AS DATE)                 AS minggu,
        CAST(DATE_TRUNC(tanggal, MONTH) AS DATE)                AS bulan_pertama,

        -- Audit
        _extracted_at,
        _source

    FROM source
    WHERE tanggal IS NOT NULL
      AND tanggal >= '2020-01-01'  -- partition filter required by BigQuery
      AND comcat_id IS NOT NULL
      AND comcat_id != ''
),

-- Hilangkan duplikat: ambil record terbaru per natural key
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
    komoditas_nama,
    pasar_tipe,
    provinsi_id,
    provinsi_nama,
    kota_id,
    kota_nama,
    pasar_nama,
    harga,
    satuan,
    pasar_tipe_label,
    tahun,
    bulan,
    kuartal,
    hari_dalam_minggu,
    minggu,
    bulan_pertama,
    _extracted_at,
    _source
FROM deduped
WHERE rn = 1
