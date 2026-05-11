import sys, os
sys.path.insert(0, "D:/Enzi-Folder/personal-project/hackathon-project/bi-hackathon-group-1/etl")
os.chdir("D:/Enzi-Folder/personal-project/hackathon-project/bi-hackathon-group-1/etl")

import duckdb

db_path = "D:/Enzi-Folder/personal-project/hackathon-project/bi-hackathon-group-1/etl/data/pihps.duckdb"
conn = duckdb.connect(db_path)

tables = conn.execute(
    "SELECT table_schema, table_name FROM information_schema.tables ORDER BY 1, 2"
).fetchall()
print("Tables in DuckDB:")
for t in tables:
    print(f"  {t[0]}.{t[1]}")

try:
    c = conn.execute("SELECT COUNT(*) FROM raw.harga_pangan").fetchone()[0]
    print(f"\nraw.harga_pangan rows: {c:,}")
except Exception as e:
    print(f"raw.harga_pangan error: {e}")

try:
    logs = conn.execute(
        "SELECT pipeline_name, status, records_inserted, tanggal_mulai, tanggal_selesai FROM raw.pipeline_log ORDER BY started_at DESC LIMIT 5"
    ).fetchall()
    print("\nPipeline log (last 5 runs):")
    for row in logs:
        print(f"  {row}")
except Exception as e:
    print(f"pipeline_log error: {e}")

conn.close()
print("\nDone.")
