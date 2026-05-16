{{
    config(
        materialized='view',
        description='Dimension: master data komoditas (extracted dari raw.harga_pangan)'
    )
}}

/*
  Dimension komoditas — 3NF normalized.
  Satu baris per komoditas unik (comcat_id).
  Derived from raw data karena belum ada master komoditas terpisah.
*/

SELECT DISTINCT
    comcat_id,
    TRIM(komoditas_nama)    AS komoditas_nama,
    LOWER(TRIM(satuan))     AS satuan
FROM {{ source('raw', 'harga_pangan') }}
WHERE comcat_id IS NOT NULL
  AND comcat_id != ''
  AND komoditas_nama IS NOT NULL
  AND tanggal >= '2020-01-01'  -- partition filter required by BigQuery
ORDER BY comcat_id
