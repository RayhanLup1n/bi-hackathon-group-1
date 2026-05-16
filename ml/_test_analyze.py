import os, traceback, json
from dotenv import load_dotenv
load_dotenv("ml/.env")

from datetime import date
from ml.src.pipeline import RadarPipeline

host = os.environ["SUPABASE_HOST"]
port = os.environ["SUPABASE_PORT"]
db   = os.environ["SUPABASE_DB"]
user = os.environ["SUPABASE_USER"]
pw   = os.environ["SUPABASE_PASSWORD"]
pg   = f"postgresql://{user}:{pw}@{host}:{port}/{db}"

p = RadarPipeline(
    models_dir="ml/models",
    het_csv="ml/data/het_reference.csv",
    llm_api_key=os.environ["LLM_API_KEY"],
    llm_base_url=os.environ["LLM_BASE_URL"],
    llm_model=os.environ["LLM_MODEL"],
)
p.load(pg_conn_string=pg)
print("Rows loaded:", len(p._df))

try:
    result = p.analyze(
        komoditas_nama="Cabai Rawit Merah",
        kota_nama="Kota Jakarta Pusat",
        tanggal=date(2026, 5, 8),
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))
except Exception:
    traceback.print_exc()
