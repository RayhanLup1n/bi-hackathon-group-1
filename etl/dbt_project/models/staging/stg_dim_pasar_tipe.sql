{{
    config(
        materialized='view',
        description='Dimension: tipe pasar (static mapping)'
    )
}}

/*
  Dimension tipe pasar — 4 tipe sesuai BI PIHPS.
  Static data, tidak berubah.
*/

SELECT 1 AS pasar_tipe, 'Pasar Tradisional' AS pasar_tipe_label
UNION ALL SELECT 2, 'Pasar Modern'
UNION ALL SELECT 3, 'Pedagang Besar'
UNION ALL SELECT 4, 'Produsen'
