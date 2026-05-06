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

SELECT * FROM (
    VALUES
        (1, 'Pasar Tradisional'),
        (2, 'Pasar Modern'),
        (3, 'Pedagang Besar'),
        (4, 'Produsen')
) AS t (pasar_tipe, pasar_tipe_label)
