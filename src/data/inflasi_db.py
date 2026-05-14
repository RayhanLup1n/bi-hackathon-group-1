"""
Inflasi M-to-M data layer.
Reads from: data/Inflasi Bulanan (M-to-M), {YEAR}.csv
ETL team handles CSV updates — this module is read-only.
"""

import csv
from pathlib import Path
from datetime import date

DATA_DIR = Path(__file__).parent.parent.parent / "data"

# BPS publish data inflasi dengan lag ~1 bulan (data April tersedia di awal Mei).
# Naikkan ke 2-3 jika sumber data yang dipakai lebih lambat.
INFLASI_LAG_MONTHS = 1

MONTHS_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

# kota_list display name → possible CSV row names (uppercase)
KOTA_MAP: dict[str, list[str]] = {
    "Jakarta":    ["DKI JAKARTA"],
    "Surabaya":   ["KOTA SURABAYA"],
    "Bandung":    ["KOTA BANDUNG"],
    "Semarang":   ["KOTA SEMARANG"],
    "Yogyakarta": ["KOTA YOGYAKARTA"],
    "Malang":     ["KOTA MALANG"],
}
_NATIONAL = "INDONESIA"


def _load_csv(year: int) -> dict[str, list[float | None]]:
    """Parse CSV → {KOTA_UPPER: [jan_val, ..., dec_val]} (0-indexed, len=12)."""
    path = DATA_DIR / f"Inflasi Bulanan (M-to-M), {year}.csv"
    if not path.exists():
        return {}

    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))

    # Find header row containing "Januari"
    col_map: dict[int, int] = {}   # month 1-based → CSV column index
    data_start = 0
    for i, row in enumerate(rows):
        cells = [c.strip() for c in row]
        if "Januari" in cells:
            for m_idx, m_name in enumerate(MONTHS_ID, start=1):
                if m_name in cells:
                    col_map[m_idx] = cells.index(m_name)
            data_start = i + 1
            break

    if not col_map:
        return {}

    result: dict[str, list[float | None]] = {}
    for row in rows[data_start:]:
        if not row or not row[0].strip():
            continue
        kota = row[0].strip().upper()
        series: list[float | None] = []
        for m in range(1, 13):
            idx = col_map.get(m)
            raw = row[idx].strip() if (idx is not None and idx < len(row)) else "-"
            series.append(float(raw) if raw not in ("-", "", "n/a", "N/A") else None)
        result[kota] = series
    return result


def _resolve(data: dict[str, list], kota_nama: str) -> list[float | None] | None:
    """Resolve a kota display name to its inflasi series."""
    candidates = KOTA_MAP.get(kota_nama, [kota_nama.upper(), f"KOTA {kota_nama.upper()}"])
    for c in candidates:
        if c in data:
            return data[c]
    return None


def get_inflasi_tren(kota_names: list[str], tanggal: date) -> tuple[bool, str]:
    """
    Cek apakah 3 bulan terakhir berturut-turut memiliki inflasi M-to-M positif.

    Matching: iterasi kota_names, fallback ke baris INDONESIA.
    Returns: (triggered, detail_string)
    """
    data = _load_csv(tanggal.year)
    if not data:
        data = _load_csv(tanggal.year - 1)   # fallback tahun sebelumnya
    if not data:
        return False, "Data inflasi bulanan tidak tersedia"

    # Cari series — pakai kota pertama yang cocok
    series: list[float | None] | None = None
    matched = "—"
    for kota in kota_names:
        s = _resolve(data, kota)
        if s is not None:
            series = s
            matched = kota
            break

    # Fallback ke INDONESIA
    if series is None:
        national = data.get(_NATIONAL)
        if national:
            series = national
            matched = "Indonesia (nasional)"

    if series is None:
        return False, "Tidak ada data kota yang cocok"

    # Geser window mundur sesuai lag publikasi BPS
    end_bulan = tanggal.month - INFLASI_LAG_MONTHS
    if end_bulan < 3:
        return False, (
            f"Data 3 bulan penuh belum tersedia "
            f"(periode terbaru yang dipakai: {MONTHS_ID[max(end_bulan, 1) - 1]})"
        )

    months_3 = [end_bulan - 2, end_bulan - 1, end_bulan]  # contoh Mei (lag=1) → [2, 3, 4]
    vals: list[float] = []
    for m in months_3:
        v = series[m - 1]   # 0-indexed
        if v is None:
            return False, f"Data {MONTHS_ID[m - 1]} belum tersedia ({matched})"
        vals.append(v)

    names_3 = [MONTHS_ID[m - 1] for m in months_3]
    val_str = " → ".join(f"{v:+.2f}%" for v in vals)

    if all(v > 0 for v in vals):
        return True, (
            f"⚠ Inflasi positif 3 bulan berturut ({', '.join(names_3)}): "
            f"{val_str} ({matched})"
        )
    return False, (
        f"Inflasi {', '.join(names_3)}: {val_str} — tidak ada tren naik konsisten ({matched})"
    )
