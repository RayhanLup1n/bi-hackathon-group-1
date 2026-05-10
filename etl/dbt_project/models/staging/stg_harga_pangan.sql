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
        tanggal::DATE                                   AS tanggal,
        comcat_id,
        TRIM(komoditas_nama)                            AS komoditas_nama,
        pasar_tipe::INTEGER                             AS pasar_tipe,

        -- Dimensi wilayah
        provinsi_id::INTEGER                            AS provinsi_id,
        TRIM(provinsi_nama)                             AS provinsi_nama,
        kota_id::INTEGER                                AS kota_id,
        TRIM(kota_nama)                                 AS kota_nama,
        TRIM(pasar_nama)                                AS pasar_nama,

        -- Harga: filter nilai negatif atau nol yang tidak wajar
        CASE
            WHEN harga <= 0 THEN NULL
            ELSE harga::DOUBLE PRECISION
        END                                             AS harga,

        LOWER(TRIM(satuan))                             AS satuan,

        -- Label tipe pasar
        CASE pasar_tipe
            WHEN 1 THEN 'Pasar Tradisional'
            WHEN 2 THEN 'Pasar Modern'
            WHEN 3 THEN 'Pedagang Besar'
            WHEN 4 THEN 'Produsen'
            ELSE 'Tidak Diketahui'
        END                                             AS pasar_tipe_label,

        -- Dimensi waktu turunan
        EXTRACT(YEAR FROM tanggal)::INTEGER             AS tahun,
        EXTRACT(MONTH FROM tanggal)::INTEGER            AS bulan,
        EXTRACT(QUARTER FROM tanggal)::INTEGER          AS kuartal,
        EXTRACT(DOW FROM tanggal)::INTEGER              AS hari_dalam_minggu,
        DATE_TRUNC('week', tanggal)::DATE               AS minggu,
        DATE_TRUNC('month', tanggal)::DATE              AS bulan_pertama,

        -- Audit
        _extracted_at,
        _source

    FROM source
    WHERE tanggal IS NOT NULL
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

-- PostgreSQL: explicit column select instead of EXCLUDE (rn)
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
