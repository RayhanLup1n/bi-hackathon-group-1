"""
Load historical PIHPS data ke Supabase PostgreSQL.

Batch strategy: per kota per tahun agar aman dari OOM.
Insert strategy: bulk executemany (bukan row-by-row) agar cepat.

Usage:
    cd etl
    python -X utf8 scripts/load_historical.py
    python -X utf8 scripts/load_historical.py --start-year 2023    # mulai dari 2023
    python -X utf8 scripts/load_historical.py --resume              # lanjut dari checkpoint terakhir
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras
from loguru import logger

from extractors.pihps_extractor import PihpsExtractor
from loaders.postgres_loader import PostgresLoader, _get_dsn


# ── Config ────────────────────────────────────────────────────────────────────

# Import from centralized config
from config.constants import TARGET_PROVINCE_IDS
DEFAULT_START_YEAR = 2020
DEFAULT_END_YEAR = 2026

INSERT_SQL = """
    INSERT INTO raw.harga_pangan
        (tanggal, comcat_id, komoditas_nama, pasar_tipe,
         provinsi_id, provinsi_nama, kota_id, kota_nama,
         pasar_nama, harga, satuan, _source)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def _load_master_data(extractor: PihpsExtractor, loader: PostgresLoader) -> dict:
    """Load master data provinsi + kota, return mapping {prov_id: [kota_ids]}."""
    df_prov = extractor.get_master_provinsi()
    if not df_prov.empty:
        loader.upsert_provinsi(df_prov)
        logger.info(f"Provinsi loaded: {len(df_prov)}")

    prov_kota_map = {}
    for prov_id in TARGET_PROVINCE_IDS:
        df_kota = extractor.get_master_kota(province_id=str(prov_id))
        if not df_kota.empty:
            df_kota["provinsi_id"] = prov_id
            df_kota = df_kota.rename(columns={"id": "kota_id", "name": "kota_nama"})
            loader.upsert_kota(df_kota)
            prov_kota_map[prov_id] = list(df_kota["kota_id"])
            logger.info(f"  Prov {prov_id}: {len(df_kota)} kota")

    return prov_kota_map


def _get_checkpoint(conn) -> tuple[int, int, int] | None:
    """Get last successful checkpoint (year, prov_id, kota_id)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT
            EXTRACT(YEAR FROM tanggal_selesai)::INTEGER as tahun,
            0 as prov_id,
            0 as kota_id
        FROM raw.pipeline_log
        WHERE pipeline_name = 'historical_load'
          AND status = 'success'
        ORDER BY tanggal_selesai DESC
        LIMIT 1
    """)
    result = cur.fetchone()
    cur.close()
    return result


def _bulk_insert(conn, records: list[tuple]) -> int:
    """Bulk insert records using executemany. Returns count inserted."""
    if not records:
        return 0

    cur = conn.cursor()
    try:
        # Use execute_batch for better performance than executemany
        psycopg2.extras.execute_batch(cur, INSERT_SQL, records, page_size=500)
        conn.commit()
        n = len(records)
        return n
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def _extract_prov_year(
    extractor: PihpsExtractor,
    prov_id: int,
    year: int,
) -> list[tuple]:
    """Extract data for one province, one year. Returns list of tuples for insert."""
    tanggal_mulai = date(year, 1, 1)
    tanggal_selesai = min(date(year, 12, 31), date.today() - timedelta(days=1))

    if tanggal_mulai > tanggal_selesai:
        return []

    df = extractor.extract_harga_per_wilayah(
        tanggal_mulai=tanggal_mulai,
        tanggal_selesai=tanggal_selesai,
        province_ids=[prov_id],
    )

    if df.empty:
        return []

    # Deduplicate
    df = df.drop_duplicates(
        subset=["tanggal", "comcat_id", "kota_id", "pasar_nama"],
        keep="last",
    )

    # Convert to list of tuples for bulk insert
    records = []
    for _, row in df.iterrows():
        records.append((
            row.get("tanggal"),
            row.get("comcat_id"),
            row.get("komoditas_nama"),
            row.get("pasar_tipe"),
            row.get("provinsi_id"),
            row.get("provinsi_nama"),
            row.get("kota_id"),
            row.get("kota_nama"),
            row.get("pasar_nama"),
            row.get("harga"),
            row.get("satuan"),
            "bi_pihps",
        ))

    return records


def main():
    parser = argparse.ArgumentParser(description="Load historical PIHPS data")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    args = parser.parse_args()

    # Init
    conn = psycopg2.connect(_get_dsn())

    with PostgresLoader() as loader:
        loader.init_schema()

    # Check resume
    start_year = args.start_year
    if args.resume:
        checkpoint = _get_checkpoint(conn)
        if checkpoint:
            start_year = max(checkpoint[0], start_year)
            logger.info(f"Resuming from year {start_year}")

    # Load master data
    with PihpsExtractor() as extractor:
        with PostgresLoader() as loader:
            prov_kota_map = _load_master_data(extractor, loader)

    # Build batch list: (year, prov_id)
    batches = []
    for year in range(start_year, args.end_year + 1):
        for prov_id in TARGET_PROVINCE_IDS:
            batches.append((year, prov_id))

    total_batches = len(batches)
    total_inserted = 0
    t_start = time.time()

    logger.info(f"Total batches: {total_batches} (year x province)")
    logger.info(f"Years: {start_year}-{args.end_year}")
    logger.info(f"Provinces: {TARGET_PROVINCE_IDS}")
    print()

    # Process per-province per-year
    with PihpsExtractor() as extractor:
        for i, (year, prov_id) in enumerate(batches, 1):
            batch_label = f"[{i}/{total_batches}] Year={year} Prov={prov_id}"

            try:
                records = _extract_prov_year(extractor, prov_id, year)

                if records:
                    n = _bulk_insert(conn, records)
                    total_inserted += n
                    elapsed = time.time() - t_start
                    rate = total_inserted / elapsed if elapsed > 0 else 0
                    logger.success(
                        f"{batch_label}: {n:,} rows inserted "
                        f"(total: {total_inserted:,}, "
                        f"{rate:.0f} rows/sec, "
                        f"elapsed: {elapsed/60:.1f}min)"
                    )
                else:
                    logger.warning(f"{batch_label}: no data")

                # Log success checkpoint
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO raw.pipeline_log
                        (run_id, pipeline_name, tanggal_mulai, tanggal_selesai,
                         records_inserted, status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, [
                    f"hist_{year}_{prov_id}",
                    "historical_load",
                    date(year, 1, 1),
                    min(date(year, 12, 31), date.today()),
                    len(records),
                    "success",
                ])
                conn.commit()
                cur.close()

            except Exception as e:
                logger.error(f"{batch_label}: FAILED - {e}")
                # Log failure and continue to next batch
                try:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO raw.pipeline_log
                            (run_id, pipeline_name, tanggal_mulai, tanggal_selesai,
                             records_inserted, status, error_message)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, [
                        f"hist_{year}_{prov_id}",
                        "historical_load",
                        date(year, 1, 1),
                        date(year, 12, 31),
                        0,
                        "failed",
                        str(e)[:500],
                    ])
                    conn.commit()
                    cur.close()
                except Exception:
                    pass
                continue

    elapsed_total = time.time() - t_start
    conn.close()

    # Final summary
    print()
    print("=" * 60)
    print("HISTORICAL LOAD COMPLETE")
    print("=" * 60)
    print(f"  Years:          {start_year}-{args.end_year}")
    print(f"  Total inserted: {total_inserted:,} rows")
    print(f"  Duration:       {elapsed_total/60:.1f} minutes")
    print(f"  Avg rate:       {total_inserted/elapsed_total:.0f} rows/sec")
    print("=" * 60)


if __name__ == "__main__":
    main()
