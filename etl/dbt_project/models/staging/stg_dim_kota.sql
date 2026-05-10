{{
    config(
        materialized='view',
        description='Dimension: master data kota/kabupaten'
    )
}}

/*
  Dimension kota — dari raw.dim_kota + join provinsi.
*/

SELECT
    k.kota_id,
    TRIM(k.kota_nama)   AS kota_nama,
    k.provinsi_id,
    TRIM(p.provinsi_nama) AS provinsi_nama
FROM {{ source('raw', 'dim_kota') }} k
LEFT JOIN {{ source('raw', 'dim_provinsi') }} p
    ON k.provinsi_id = p.provinsi_id
WHERE k.kota_id IS NOT NULL
