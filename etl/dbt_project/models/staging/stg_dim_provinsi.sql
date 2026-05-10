{{
    config(
        materialized='view',
        description='Dimension: master data provinsi'
    )
}}

/*
  Dimension provinsi — dari raw.dim_provinsi.
*/

SELECT
    provinsi_id,
    TRIM(provinsi_nama) AS provinsi_nama
FROM {{ source('raw', 'dim_provinsi') }}
WHERE provinsi_id IS NOT NULL
