"""
src/data/stok_db.py
===================
Simulasi database stok pedagang (Badan Pangan / Bulog).
Meniru struktur data tarikan API Bulog/Badan Pangan untuk stok per kota.

Database : data/stok.db  (SQLite, auto-created saat init_db_stok dipanggil)

Tabel
-----
stok_harian  — stok aktual per komoditas per kota per tanggal (ton)

Fungsi publik
-------------
init_db_stok()                          → buat tabel & seed data (idempoten)
get_stok_komoditas(key, tanggal)        → (stok_kota, kapasitas) untuk _derive_stok()
list_stok_komoditas(key, tanggal)       → list detail stok per kota (untuk API)
list_semua_stok(tanggal)               → semua komoditas & kota (untuk API)
"""

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "stok.db"

SEED_DAYS_BACK    = 45
SEED_DAYS_FORWARD = 7

# ─────────────────────────────────────────────────────────────────────────────
# BASELINE DATA
# Ganti angka ini saat connect ke API Bulog / Badan Pangan
# Format: komoditas_key → { kapasitas (ton/kota), kota → stok baseline (ton) }
# ─────────────────────────────────────────────────────────────────────────────

STOK_BASELINE: dict[str, dict] = {
    "cabai": {
        "kapasitas": 500,
        "kota": {
            "Jakarta": 430, "Surabaya": 410, "Bandung": 440,
            "Semarang": 400, "Yogyakarta": 390, "Malang": 420,
        },
    },
    "bawang": {
        "kapasitas": 600,
        "kota": {
            "Jakarta": 310, "Surabaya": 280, "Bandung": 290,
            "Semarang": 260, "Yogyakarta": 330, "Malang": 300,
        },
    },
    "beras": {
        "kapasitas": 2000,
        "kota": {
            "Jakarta": 1650, "Surabaya": 1720, "Bandung": 1700,
            "Semarang": 1600, "Yogyakarta": 1580, "Malang": 1640,
        },
    },
    "ayam": {
        "kapasitas": 800,
        "kota": {
            "Jakarta": 590, "Surabaya": 560, "Bandung": 610,
            "Semarang": 570, "Yogyakarta": 540, "Malang": 580,
        },
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# DDL
# ─────────────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS stok_harian (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    komoditas_key   TEXT NOT NULL,
    kota_nama       TEXT NOT NULL,
    tanggal         TEXT NOT NULL,
    stok_ton        REAL NOT NULL,
    kapasitas_ton   REAL NOT NULL,
    UNIQUE(komoditas_key, kota_nama, tanggal)
);

CREATE INDEX IF NOT EXISTS idx_stok_key_tgl ON stok_harian(komoditas_key, tanggal);
"""

# ─────────────────────────────────────────────────────────────────────────────
# KONEKSI DB
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

# ─────────────────────────────────────────────────────────────────────────────
# SEED HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _gen_stok(key: str, kota: str, baseline: float, tanggal: date) -> float:
    """
    Stok harian deterministik berbasis hash(key:kota:tanggal).
    Variasi ±20% dari baseline — mirip pola seed cuaca BMKG.
    """
    seed = hashlib.md5(f"{key}:{kota}:{tanggal}".encode()).digest()
    val  = int.from_bytes(seed[:2], "big") / 65535   # 0.0–1.0
    mult = 0.80 + val * 0.40                          # 0.80–1.20
    return round(baseline * mult, 1)

# ─────────────────────────────────────────────────────────────────────────────
# INIT & SEED
# ─────────────────────────────────────────────────────────────────────────────

def init_db_stok() -> None:
    """
    Buat tabel stok_harian dan isi data harian.
    Idempoten — INSERT OR IGNORE, aman dipanggil berkali-kali.
    Untuk reset: hapus data/stok.db lalu restart server.
    """
    today = date.today()
    start = today - timedelta(days=SEED_DAYS_BACK)
    end   = today + timedelta(days=SEED_DAYS_FORWARD)

    with _conn() as con:
        con.executescript(_DDL)

        cur = start
        while cur <= end:
            tgl_str = cur.isoformat()
            for key, data in STOK_BASELINE.items():
                kapasitas = data["kapasitas"]
                for kota, baseline in data["kota"].items():
                    stok = _gen_stok(key, kota, baseline, cur)
                    con.execute(
                        "INSERT OR IGNORE INTO stok_harian"
                        "(komoditas_key, kota_nama, tanggal, stok_ton, kapasitas_ton)"
                        " VALUES(?,?,?,?,?)",
                        (key, kota, tgl_str, stok, kapasitas),
                    )
            cur += timedelta(days=1)

# ─────────────────────────────────────────────────────────────────────────────
# QUERY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def get_stok_komoditas(key: str, tanggal: date | None = None) -> tuple[dict[str, int], int] | None:
    """
    Kembalikan (stok_kota, kapasitas) untuk dipakai _derive_stok() di commodity_data.py.
    Return None jika komoditas tidak ditemukan.
    """
    if tanggal is None:
        tanggal = date.today()

    with _conn() as con:
        rows = con.execute(
            "SELECT kota_nama, stok_ton, kapasitas_ton "
            "FROM stok_harian WHERE komoditas_key = ? AND tanggal = ?",
            (key, tanggal.isoformat()),
        ).fetchall()

    if not rows:
        return None

    stok_kota = {r["kota_nama"]: int(r["stok_ton"]) for r in rows}
    kapasitas  = int(rows[0]["kapasitas_ton"])
    return stok_kota, kapasitas


def list_stok_komoditas(key: str, tanggal: date | None = None) -> list[dict]:
    """Detail stok per kota untuk satu komoditas pada tanggal tertentu."""
    if tanggal is None:
        tanggal = date.today()
    with _conn() as con:
        rows = con.execute(
            "SELECT komoditas_key, kota_nama, tanggal, stok_ton, kapasitas_ton "
            "FROM stok_harian WHERE komoditas_key = ? AND tanggal = ? ORDER BY kota_nama",
            (key, tanggal.isoformat()),
        ).fetchall()
    return [
        {**dict(r), "pct": round(r["stok_ton"] / r["kapasitas_ton"], 3)}
        for r in rows
    ]


def list_semua_stok(tanggal: date | None = None) -> list[dict]:
    """Semua komoditas dan kota pada tanggal tertentu."""
    if tanggal is None:
        tanggal = date.today()
    with _conn() as con:
        rows = con.execute(
            "SELECT komoditas_key, kota_nama, tanggal, stok_ton, kapasitas_ton "
            "FROM stok_harian WHERE tanggal = ? ORDER BY komoditas_key, kota_nama",
            (tanggal.isoformat(),),
        ).fetchall()
    return [
        {**dict(r), "pct": round(r["stok_ton"] / r["kapasitas_ton"], 3)}
        for r in rows
    ]
