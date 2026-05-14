"""
src/data/bmkg_db.py
===================
Simulasi database BMKG (Badan Meteorologi, Klimatologi, dan Geofisika).
Meniru struktur & isi data tarikan API BMKG untuk cuaca dan peringatan dini.

Database : data/bmkg_weather.db  (SQLite, auto-created saat init_db dipanggil)

Tabel
-----
wilayah            — 18 wilayah: 12 produksi + 6 kota konsumsi (fokus Pulau Jawa)
cuaca_harian       — prakiraan/observasi cuaca harian (-45 s/d +7 hari dari hari ini)
peringatan_cuaca   — peringatan dini cuaca ekstrem (Waspada / Siaga / Awas)
komoditas_wilayah  — mapping komoditas key → wilayah produksi

Fungsi publik
-------------
init_db()                              → buat tabel & seed data (idempoten)
get_cuaca_komoditas(key, tgl)          → CuacaInfo aktif untuk komoditas
list_peringatan_aktif(tgl)             → semua warning aktif pada tanggal
list_cuaca_wilayah(kode, n_hari)       → n hari cuaca terakhir suatu wilayah
list_all_wilayah()                     → semua wilayah produksi
list_peringatan_history(n_hari)        → semua peringatan N hari terakhir
"""

import hashlib
import random
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

from src.models.schemas import CuacaInfo

# ─────────────────────────────────────────────────────────────────────────────
# KONFIGURASI
# ─────────────────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent.parent.parent / "data" / "bmkg_weather.db"

SEED_DAYS_BACK    = 45   # hari ke belakang dari today untuk seed cuaca_harian
SEED_DAYS_FORWARD = 7    # hari ke depan (prakiraan)

# ─────────────────────────────────────────────────────────────────────────────
# KONDISI CUACA & PROBABILITAS
# ─────────────────────────────────────────────────────────────────────────────

KONDISI_CUACA = [
    "Cerah",
    "Cerah Berawan",
    "Berawan",
    "Hujan Ringan",
    "Hujan Sedang",
    "Hujan Lebat",
    "Hujan Sangat Lebat",
    "Badai Petir",
]

EKSTREM_KONDISI = {"Hujan Lebat", "Hujan Sangat Lebat", "Badai Petir"}

# Bobot probabilitas per kelas iklim (urut sesuai KONDISI_CUACA)
# Representasi cuaca bulan Mei di Indonesia
IKLIM_PROB: dict[str, list[int]] = {
    "basah_tinggi": [5,  10, 15, 25, 20, 15,  8,  2],   # dataran tinggi basah
    "basah_rendah": [10, 15, 20, 25, 15, 10,  4,  1],   # pantai / dataran rendah basah
    "sedang":       [15, 20, 20, 20, 12,  8,  4,  1],   # iklim sedang
    "kering":       [30, 25, 20, 13,  7,  4,  1,  0],   # NTB / Sulsel awal musim kering
}

# ─────────────────────────────────────────────────────────────────────────────
# MASTER DATA WILAYAH
# Format: (kode, nama, provinsi, lat, lon, kelas_iklim)
# Dua kelompok:
#   1. Wilayah produksi  — sentra pertanian/peternakan, dipantau cuaca BMKG
#   2. Kota konsumsi     — 8 kota besar sesuai kota_list di commodity_data.py
# ─────────────────────────────────────────────────────────────────────────────

WILAYAH_DATA: list[tuple] = [
    # ── Wilayah produksi: Cabai Merah ────────────────────────────────────────
    ("3204.garut",       "Garut",         "Jawa Barat",   -7.21,  107.90,  "basah_tinggi"),
    ("3313.boyolali",    "Boyolali",      "Jawa Tengah",  -7.53,  110.60,  "basah_rendah"),
    ("3506.kediri",      "Kediri",        "Jawa Timur",   -7.81,  112.01,  "sedang"),
    # ── Wilayah produksi: Bawang Merah ───────────────────────────────────────
    ("3329.brebes",      "Brebes",        "Jawa Tengah",  -6.87,  108.97,  "basah_rendah"),
    ("3514.probolinggo", "Probolinggo",   "Jawa Timur",   -7.75,  113.21,  "sedang"),
    ("3518.nganjuk",     "Nganjuk",       "Jawa Timur",   -7.60,  111.90,  "sedang"),
    # ── Wilayah produksi: Beras (#1 Indramayu, #2 Karawang, #3 Subang — nasional) ──
    ("3215.karawang",    "Karawang",      "Jawa Barat",   -6.31,  107.34,  "basah_rendah"),
    ("3212.indramayu",   "Indramayu",     "Jawa Barat",   -6.32,  108.32,  "basah_rendah"),
    ("3213.subang",      "Subang",        "Jawa Barat",   -6.57,  107.76,  "basah_rendah"),
    # ── Wilayah produksi: Ayam (peternakan) ──────────────────────────────────
    ("3201.bogor",       "Bogor",         "Jawa Barat",   -6.60,  106.80,  "basah_tinggi"),
    ("3505.blitar",      "Blitar",        "Jawa Timur",   -8.09,  112.17,  "sedang"),
    ("3212.majalengka",  "Majalengka",    "Jawa Barat",   -6.83,  108.23,  "basah_rendah"),
    # ── Kota konsumsi (sama persis dengan kota_list di commodity_data.py) ────
    ("3171.jakarta",     "Jakarta",       "DKI Jakarta",  -6.21,  106.85,  "basah_rendah"),
    ("3578.surabaya",    "Surabaya",      "Jawa Timur",   -7.25,  112.75,  "sedang"),
    ("3273.bandung",     "Bandung",       "Jawa Barat",   -6.92,  107.61,  "basah_tinggi"),
    ("3374.semarang",    "Semarang",      "Jawa Tengah",  -7.00,  110.42,  "basah_rendah"),
    ("3471.yogyakarta",  "Yogyakarta",    "DI Yogyakarta",-7.80,  110.37,  "basah_rendah"),
    ("3573.malang",      "Malang",        "Jawa Timur",   -7.98,  112.63,  "sedang"),
]

# Mapping komoditas → kode wilayah produksi (urut berdasarkan prioritas)
KOMODITAS_WILAYAH_MAP: dict[str, list[str]] = {
    "cabai":  ["3204.garut",     "3313.boyolali",    "3506.kediri"],
    "bawang": ["3329.brebes",    "3514.probolinggo", "3518.nganjuk"],
    "beras":  ["3212.indramayu", "3215.karawang",    "3213.subang"],
    "ayam":   ["3201.bogor",     "3505.blitar",      "3212.majalengka"],
}

# ─────────────────────────────────────────────────────────────────────────────
# PERINGATAN CUACA EKSTREM (PRE-SEED)
# Format: (wilayah_kode, tgl_mulai, tgl_selesai, tipe, level, deskripsi)
# Level: "Waspada" < "Siaga" < "Awas"
# ─────────────────────────────────────────────────────────────────────────────

PERINGATAN_SEED: list[tuple] = [
    # ── Aktif saat ini (sekitar 2026-05-14) ──────────────────────────────────
    (
        "3506.kediri", "2026-05-12", "2026-05-17",
        "Hujan Lebat", "Siaga",
        "Hujan lebat disertai angin kencang dan kilat selama 5 hari berturut-turut "
        "di dataran tinggi Kediri dan Nganjuk. Risiko gagal panen cabai merah "
        "di area Lereng Wilis. Petani diimbau percepat masa panen.",
    ),
    (
        "3215.karawang", "2026-05-11", "2026-05-15",
        "Banjir", "Waspada",
        "Banjir ringan di lahan sawah dataran rendah Karawang akibat luapan Sungai Citarum. "
        "Petani diminta memantau saluran irigasi dan tunda pemupukan.",
    ),
    (
        "3313.boyolali", "2026-05-13", "2026-05-17",
        "Angin Kencang", "Waspada",
        "Angin kencang 40–55 km/jam disertai hujan deras di lereng Gunung Merbabu. "
        "Potensi kerusakan tanaman cabai dan sayuran di ketinggian > 800 m dpl.",
    ),

    # ── Peringatan masa lalu ──────────────────────────────────────────────────
    (
        "3212.indramayu", "2026-04-14", "2026-04-17",
        "Banjir", "Awas",
        "Banjir parah di sentra padi Indramayu akibat luapan Sungai Cimanuk. "
        "Ratusan hektar sawah siap panen terendam di Kecamatan Losarang dan Kandanghaur. "
        "Petani beras diminta segera panen darurat jika memungkinkan.",
    ),
    (
        "3518.nganjuk", "2026-04-07", "2026-04-10",
        "Angin Kencang", "Waspada",
        "Angin kencang > 45 km/jam berpotensi merobohkan tanaman bawang merah "
        "yang sedang fase generatif di Nganjuk dan Kediri. Petani diminta pasang ajir.",
    ),
    (
        "3204.garut", "2026-03-24", "2026-03-27",
        "Hujan Sangat Lebat", "Siaga",
        "Hujan sangat lebat di dataran tinggi Garut (Cikajang, Cisurupan). "
        "Risiko longsor dan banjir bandang. Jalur distribusi hasil pertanian terhambat.",
    ),
    (
        "3329.brebes", "2026-03-28", "2026-03-31",
        "Hujan Lebat", "Waspada",
        "Hujan lebat merata di sentra bawang merah Brebes. "
        "Potensi busuk akar dan serangan jamur pada tanaman bawang.",
    ),
    (
        "3201.bogor", "2026-04-18", "2026-04-20",
        "Badai Petir", "Siaga",
        "Badai petir intens disertai hujan lebat dan angin kencang > 60 km/jam "
        "di wilayah Bogor dan sekitarnya. Aktivitas peternakan ayam berisiko terganggu.",
    ),
    (
        "3213.subang", "2026-04-22", "2026-04-25",
        "Kekeringan", "Waspada",
        "Curah hujan di bawah normal selama 3 minggu terakhir di Subang dan Purwakarta. "
        "Ancaman kekeringan untuk sawah tadah hujan. Petani diminta hemat air irigasi.",
    ),

    # ── Prakiraan ke depan ────────────────────────────────────────────────────
    (
        "3514.probolinggo", "2026-05-16", "2026-05-20",
        "Hujan Sangat Lebat", "Siaga",
        "Prakiraan hujan sangat lebat selama 4 hari berturut-turut di Probolinggo "
        "dan Lumajang. Potensi banjir bandang dan gagal panen bawang merah.",
    ),
]

# ─────────────────────────────────────────────────────────────────────────────
# DDL
# ─────────────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS wilayah (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    kode     TEXT NOT NULL UNIQUE,
    nama     TEXT NOT NULL,
    provinsi TEXT NOT NULL,
    lat      REAL,
    lon      REAL,
    iklim    TEXT NOT NULL DEFAULT 'sedang'
);

CREATE TABLE IF NOT EXISTS cuaca_harian (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    wilayah_kode TEXT NOT NULL REFERENCES wilayah(kode),
    tanggal      DATE NOT NULL,
    kondisi      TEXT NOT NULL,
    suhu_min     REAL,
    suhu_max     REAL,
    kelembaban   INTEGER,
    curah_hujan  REAL,
    sumber       TEXT NOT NULL DEFAULT 'BMKG-Sim',
    UNIQUE(wilayah_kode, tanggal)
);

CREATE TABLE IF NOT EXISTS peringatan_cuaca (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kode_peringatan TEXT NOT NULL UNIQUE,
    wilayah_kode    TEXT NOT NULL REFERENCES wilayah(kode),
    tgl_mulai       DATE NOT NULL,
    tgl_selesai     DATE NOT NULL,
    tipe            TEXT NOT NULL,
    level           TEXT NOT NULL,
    deskripsi       TEXT,
    sumber          TEXT NOT NULL DEFAULT 'BMKG'
);

CREATE TABLE IF NOT EXISTS komoditas_wilayah (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    komoditas_key TEXT NOT NULL,
    wilayah_kode  TEXT NOT NULL REFERENCES wilayah(kode),
    prioritas     INTEGER NOT NULL DEFAULT 1,
    UNIQUE(komoditas_key, wilayah_kode)
);

CREATE INDEX IF NOT EXISTS idx_cuaca_wilkode_tgl  ON cuaca_harian(wilayah_kode, tanggal);
CREATE INDEX IF NOT EXISTS idx_peringatan_periode ON peringatan_cuaca(tgl_mulai, tgl_selesai);
CREATE INDEX IF NOT EXISTS idx_kw_key             ON komoditas_wilayah(komoditas_key);
"""

# ─────────────────────────────────────────────────────────────────────────────
# KONEKSI DB
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def _conn():
    """Context manager koneksi SQLite (auto-commit / auto-close)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()

# ─────────────────────────────────────────────────────────────────────────────
# HELPER SEED: GENERATE CUACA DETERMINISTIK
# ─────────────────────────────────────────────────────────────────────────────

def _rng(kode: str, tgl: date) -> random.Random:
    """RNG deterministik — hash(wilayah + tanggal) sebagai seed."""
    raw = hashlib.md5(f"{kode}:{tgl.isoformat()}".encode()).hexdigest()[:8]
    return random.Random(int(raw, 16))


def _gen_cuaca_row(kode: str, iklim: str, tgl: date) -> dict:
    """Bangkitkan baris cuaca_harian secara deterministik berdasarkan wilayah & tanggal."""
    rng = _rng(kode, tgl)
    kondisi = rng.choices(KONDISI_CUACA, weights=IKLIM_PROB[iklim], k=1)[0]

    # Suhu & kelembaban per kelas iklim
    if iklim == "basah_tinggi":
        suhu_min  = round(rng.uniform(15.0, 19.0), 1)
        suhu_max  = round(rng.uniform(22.0, 28.0), 1)
        kelembaban = rng.randint(75, 92)
    elif iklim == "basah_rendah":
        suhu_min  = round(rng.uniform(22.0, 25.0), 1)
        suhu_max  = round(rng.uniform(29.0, 34.0), 1)
        kelembaban = rng.randint(68, 88)
    elif iklim == "sedang":
        suhu_min  = round(rng.uniform(20.0, 24.0), 1)
        suhu_max  = round(rng.uniform(28.0, 33.0), 1)
        kelembaban = rng.randint(60, 80)
    else:  # kering
        suhu_min  = round(rng.uniform(23.0, 26.0), 1)
        suhu_max  = round(rng.uniform(31.0, 36.0), 1)
        kelembaban = rng.randint(45, 68)

    # Curah hujan (mm) berdasarkan kondisi
    curah_range = {
        "Cerah":            (0.0,   0.5),
        "Cerah Berawan":    (0.0,   2.0),
        "Berawan":          (0.0,   5.0),
        "Hujan Ringan":     (2.0,  15.0),
        "Hujan Sedang":     (10.0, 35.0),
        "Hujan Lebat":      (30.0, 80.0),
        "Hujan Sangat Lebat": (70.0, 150.0),
        "Badai Petir":      (100.0, 200.0),
    }
    lo, hi = curah_range.get(kondisi, (0.0, 0.0))
    curah_hujan = round(rng.uniform(lo, hi), 1)

    return {
        "wilayah_kode": kode,
        "tanggal":      tgl.isoformat(),
        "kondisi":      kondisi,
        "suhu_min":     suhu_min,
        "suhu_max":     suhu_max,
        "kelembaban":   kelembaban,
        "curah_hujan":  curah_hujan,
    }

# ─────────────────────────────────────────────────────────────────────────────
# INIT & SEED
# ─────────────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """
    Buat tabel dan isi data awal. Idempoten — aman dipanggil berkali-kali.

    Data yang di-seed:
    • 12 wilayah produksi Jawa (3 per komoditas) + 6 kota konsumsi Jawa
    • Cuaca harian dari H-45 s/d H+7 per wilayah  (total ±1008 baris)
    • 10 peringatan cuaca ekstrem terseeded
    • Mapping komoditas → wilayah produksi
    """
    with _conn() as con:
        con.executescript(_DDL)

        # ── Wilayah ──────────────────────────────────────────────────────────
        for kode, nama, provinsi, lat, lon, iklim in WILAYAH_DATA:
            con.execute(
                "INSERT OR IGNORE INTO wilayah(kode,nama,provinsi,lat,lon,iklim) "
                "VALUES(?,?,?,?,?,?)",
                (kode, nama, provinsi, lat, lon, iklim),
            )

        # ── Komoditas → Wilayah ───────────────────────────────────────────────
        for kom_key, kode_list in KOMODITAS_WILAYAH_MAP.items():
            for prio, kode in enumerate(kode_list, start=1):
                con.execute(
                    "INSERT OR IGNORE INTO komoditas_wilayah"
                    "(komoditas_key, wilayah_kode, prioritas) VALUES(?,?,?)",
                    (kom_key, kode, prio),
                )

        # ── Cuaca harian ─────────────────────────────────────────────────────
        today = date.today()
        cur   = today - timedelta(days=SEED_DAYS_BACK)
        end   = today + timedelta(days=SEED_DAYS_FORWARD)
        iklim_map = {kode: iklim for kode, _, _, _, _, iklim in WILAYAH_DATA}

        while cur <= end:
            for kode, _, _, _, _, iklim in WILAYAH_DATA:
                row = _gen_cuaca_row(kode, iklim, cur)
                con.execute(
                    "INSERT OR IGNORE INTO cuaca_harian"
                    "(wilayah_kode,tanggal,kondisi,suhu_min,suhu_max,kelembaban,curah_hujan) "
                    "VALUES(:wilayah_kode,:tanggal,:kondisi,:suhu_min,:suhu_max,:kelembaban,:curah_hujan)",
                    row,
                )
            cur += timedelta(days=1)

        # ── Peringatan cuaca ──────────────────────────────────────────────────
        for idx, (kode, tgl_mulai, tgl_selesai, tipe, level, deskripsi) in enumerate(
            PERINGATAN_SEED, start=1
        ):
            kode_peringatan = f"BMKG-{tgl_mulai[:7].replace('-','')}-W{idx:03d}"
            con.execute(
                "INSERT OR IGNORE INTO peringatan_cuaca"
                "(kode_peringatan,wilayah_kode,tgl_mulai,tgl_selesai,tipe,level,deskripsi) "
                "VALUES(?,?,?,?,?,?,?)",
                (kode_peringatan, kode, tgl_mulai, tgl_selesai, tipe, level, deskripsi),
            )

# ─────────────────────────────────────────────────────────────────────────────
# QUERY FUNCTIONS — digunakan oleh commodity_data.py dan routes.py
# ─────────────────────────────────────────────────────────────────────────────

def get_cuaca_komoditas(key: str, tanggal: date) -> CuacaInfo:
    """
    Kembalikan CuacaInfo untuk daerah produksi komoditas pada tanggal tertentu.

    Prioritas:
    1. Peringatan ekstrem aktif (level Awas > Siaga > Waspada, prioritas wilayah utama)
    2. Cuaca harian dari wilayah produksi prioritas 1
    3. Fallback minimal jika tidak ada data
    """
    tgl_str = tanggal.isoformat()

    with _conn() as con:
        # ── Cek peringatan aktif ──────────────────────────────────────────────
        row = con.execute(
            """
            SELECT p.tipe, p.level, p.deskripsi, w.nama, w.provinsi
            FROM   peringatan_cuaca p
            JOIN   komoditas_wilayah kw ON kw.wilayah_kode = p.wilayah_kode
            JOIN   wilayah w            ON w.kode = p.wilayah_kode
            WHERE  kw.komoditas_key = ?
              AND  ? BETWEEN p.tgl_mulai AND p.tgl_selesai
            ORDER BY
              CASE p.level WHEN 'Awas' THEN 1 WHEN 'Siaga' THEN 2 ELSE 3 END,
              kw.prioritas
            LIMIT 1
            """,
            (key, tgl_str),
        ).fetchone()

        if row:
            return CuacaInfo(
                ekstrem=True,
                desc=f"{row['tipe']} — Level {row['level']}",
                daerah=f"{row['nama']}, {row['provinsi']}",
                detail=row["deskripsi"],
            )

        # ── Ambil cuaca harian dari wilayah utama ─────────────────────────────
        row = con.execute(
            """
            SELECT ch.kondisi, ch.suhu_max, ch.kelembaban, ch.curah_hujan,
                   w.nama, w.provinsi
            FROM   cuaca_harian ch
            JOIN   komoditas_wilayah kw ON kw.wilayah_kode = ch.wilayah_kode
            JOIN   wilayah w            ON w.kode = ch.wilayah_kode
            WHERE  kw.komoditas_key = ?
              AND  ch.tanggal = ?
            ORDER BY kw.prioritas
            LIMIT  1
            """,
            (key, tgl_str),
        ).fetchone()

        if row:
            ekstrem = row["kondisi"] in EKSTREM_KONDISI
            return CuacaInfo(
                ekstrem=ekstrem,
                desc=row["kondisi"],
                daerah=f"{row['nama']}, {row['provinsi']}",
                detail=(
                    f"Suhu maks {row['suhu_max']}°C · "
                    f"Kelembaban {row['kelembaban']}% · "
                    f"Curah hujan {row['curah_hujan']} mm"
                ),
            )

    # Fallback jika DB kosong / wilayah tidak ditemukan
    return CuacaInfo(ekstrem=False, desc="Data tidak tersedia", daerah="")


def list_peringatan_aktif(tanggal: date) -> list[dict]:
    """Semua peringatan cuaca ekstrem yang aktif pada tanggal tertentu."""
    tgl_str = tanggal.isoformat()
    with _conn() as con:
        rows = con.execute(
            """
            SELECT p.kode_peringatan, p.tipe, p.level, p.deskripsi,
                   p.tgl_mulai, p.tgl_selesai,
                   w.kode AS wilayah_kode, w.nama, w.provinsi, w.lat, w.lon
            FROM   peringatan_cuaca p
            JOIN   wilayah w ON w.kode = p.wilayah_kode
            WHERE  ? BETWEEN p.tgl_mulai AND p.tgl_selesai
            ORDER BY
              CASE p.level WHEN 'Awas' THEN 1 WHEN 'Siaga' THEN 2 ELSE 3 END,
              p.tgl_mulai DESC
            """,
            (tgl_str,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_cuaca_wilayah(kode_wilayah: str, n_hari: int = 14) -> list[dict]:
    """N hari cuaca terakhir (atau prakiraan) untuk suatu wilayah."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT tanggal, kondisi, suhu_min, suhu_max, kelembaban, curah_hujan, sumber
            FROM   cuaca_harian
            WHERE  wilayah_kode = ?
            ORDER  BY tanggal DESC
            LIMIT  ?
            """,
            (kode_wilayah, n_hari),
        ).fetchall()
        return [dict(r) for r in rows]


def list_all_wilayah() -> list[dict]:
    """Semua wilayah produksi beserta metadata."""
    with _conn() as con:
        rows = con.execute(
            "SELECT kode, nama, provinsi, lat, lon, iklim "
            "FROM wilayah ORDER BY provinsi, nama"
        ).fetchall()
        return [dict(r) for r in rows]


def list_peringatan_history(n_hari: int = 30) -> list[dict]:
    """Semua peringatan dalam N hari terakhir (termasuk yang sudah berakhir)."""
    since = (date.today() - timedelta(days=n_hari)).isoformat()
    with _conn() as con:
        rows = con.execute(
            """
            SELECT p.kode_peringatan, p.tipe, p.level, p.deskripsi,
                   p.tgl_mulai, p.tgl_selesai,
                   w.nama, w.provinsi
            FROM   peringatan_cuaca p
            JOIN   wilayah w ON w.kode = p.wilayah_kode
            WHERE  p.tgl_selesai >= ?
            ORDER  BY p.tgl_mulai DESC
            """,
            (since,),
        ).fetchall()
        return [dict(r) for r in rows]


def list_cuaca_semua(tanggal: date, n_hari: int = 7) -> list[dict]:
    """
    Cuaca N hari terakhir untuk semua wilayah (produksi + kota konsumsi),
    diurutkan per wilayah dan tanggal descending.
    """
    start = (tanggal - timedelta(days=n_hari - 1)).isoformat()
    end   = tanggal.isoformat()
    with _conn() as con:
        rows = con.execute(
            """
            SELECT ch.tanggal, ch.kondisi, ch.suhu_min, ch.suhu_max,
                   ch.kelembaban, ch.curah_hujan, ch.sumber,
                   w.kode, w.nama, w.provinsi, w.iklim
            FROM   cuaca_harian ch
            JOIN   wilayah w ON w.kode = ch.wilayah_kode
            WHERE  ch.tanggal BETWEEN ? AND ?
            ORDER  BY w.provinsi, w.nama, ch.tanggal DESC
            """,
            (start, end),
        ).fetchall()
        return [dict(r) for r in rows]


def get_wilayah_produksi(key: str) -> list[dict]:
    """
    Daftar semua wilayah produksi untuk komoditas tertentu,
    diurutkan berdasarkan prioritas.
    """
    with _conn() as con:
        rows = con.execute(
            """
            SELECT w.kode, w.nama, w.provinsi, w.lat, w.lon, kw.prioritas
            FROM   wilayah w
            JOIN   komoditas_wilayah kw ON kw.wilayah_kode = w.kode
            WHERE  kw.komoditas_key = ?
            ORDER  BY kw.prioritas
            """,
            (key,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_cuaca_summary_komoditas(key: str, tanggal: date, n_hari: int = 7) -> list[dict]:
    """
    Ringkasan cuaca N hari terakhir untuk semua wilayah produksi suatu komoditas.
    Berguna untuk tampilan tren cuaca di dashboard.
    """
    start = (tanggal - timedelta(days=n_hari - 1)).isoformat()
    end   = tanggal.isoformat()
    with _conn() as con:
        rows = con.execute(
            """
            SELECT ch.tanggal, ch.kondisi, ch.suhu_max, ch.kelembaban,
                   ch.curah_hujan, w.nama, w.provinsi, kw.prioritas
            FROM   cuaca_harian ch
            JOIN   komoditas_wilayah kw ON kw.wilayah_kode = ch.wilayah_kode
            JOIN   wilayah w            ON w.kode = ch.wilayah_kode
            WHERE  kw.komoditas_key = ?
              AND  ch.tanggal BETWEEN ? AND ?
            ORDER  BY kw.prioritas, ch.tanggal DESC
            """,
            (key, start, end),
        ).fetchall()
        return [dict(r) for r in rows]
