"""
Pydantic models untuk validasi & parsing response API PIHPS.
Disesuaikan dengan struktur endpoint yang ditemukan dari DevTools:
  - GetGridDataDaerah → HargaKomoditasRecord
  - GetRefCommodityAndCategory → KomoditasInfo
"""
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator


class HargaKomoditasRecord(BaseModel):
    """Satu record harga komoditas dari GetGridDataDaerah."""

    tanggal:        date
    comcat_id:      str                      # format "cat_1", "cat_2", dll
    komoditas_nama: str
    pasar_tipe:     int = Field(default=1)   # 1=tradisional, 2=modern, dll
    provinsi_id:    int | None = None
    provinsi_nama:  str | None = None
    kota_id:        int | None = None
    kota_nama:      str | None = None
    pasar_nama:     str | None = None
    harga:          float | None = None      # harga dalam Rupiah
    satuan:         str = "kg"

    @field_validator("harga", mode="before")
    @classmethod
    def parse_harga(cls, v: Any) -> float | None:
        """
        Bersihkan format harga dari API PIHPS.

        Format aktual dari API: "15,150" (koma sebagai ribuan, BUKAN desimal).
        Ini format English-style thousands separator.
        Bisa juga: "14.500" (titik sebagai ribuan, format Indonesia).

        Strategi: hapus semua separator ribuan (koma dan titik),
        kecuali jika ada desimal (jarang terjadi untuk harga pangan).
        """
        if v is None or v == "" or v == "-" or v == 0:
            return None
        if isinstance(v, (int, float)):
            val = float(v)
            return val if val > 0 else None
        cleaned = str(v).strip()
        # Hapus semua koma (thousands separator dari API PIHPS)
        cleaned = cleaned.replace(",", "")
        # Hapus titik yang jadi ribuan (format Indonesia: "14.500")
        # Tapi jaga titik desimal jika ada (misal "14500.50")
        # Heuristik: jika ada titik dan digit setelahnya ≤ 2 → desimal
        # Jika digit setelah titik ≥ 3 → ribuan (hapus)
        if "." in cleaned:
            parts = cleaned.split(".")
            if len(parts) == 2 and len(parts[1]) >= 3:
                # Titik sebagai ribuan: "14.500" → "14500"
                cleaned = cleaned.replace(".", "")
        try:
            val = float(cleaned)
            return val if val > 0 else None
        except ValueError:
            return None

    @field_validator("tanggal", mode="before")
    @classmethod
    def parse_tanggal(cls, v: Any) -> date:
        """
        Support berbagai format tanggal yang mungkin dikembalikan API:
        - "2026-04-17"  (YYYY-MM-DD) ← format utama dari DevTools
        - "17/04/2026"  (DD/MM/YYYY) ← format alternatif
        - "2026-04-17T00:00:00"      ← ISO datetime
        - date object
        """
        if isinstance(v, date):
            return v
        v_str = str(v).strip()

        # ISO datetime → ambil bagian tanggal saja
        if "T" in v_str:
            v_str = v_str.split("T")[0]

        # Format YYYY-MM-DD (utama dari DevTools)
        if len(v_str) == 10 and v_str[4] == "-":
            return date.fromisoformat(v_str)

        # Format DD/MM/YYYY
        if "/" in v_str:
            parts = v_str.split("/")
            if len(parts) == 3:
                day, month, year = parts[0], parts[1], parts[2]
                if len(year) == 4:
                    return date(int(year), int(month), int(day))

        # Fallback: coba fromisoformat langsung
        return date.fromisoformat(v_str[:10])

    @field_validator("komoditas_nama", mode="before")
    @classmethod
    def strip_nama(cls, v: Any) -> str:
        return str(v).strip() if v else ""


class KomoditasInfo(BaseModel):
    """Info satu komoditas dari GetRefCommodityAndCategory."""
    comcat_id: str       # misal "cat_1"
    nama:      str
    satuan:    str = "kg"


class ProvinsiRecord(BaseModel):
    provinsi_id:   int
    provinsi_nama: str


class KotaRecord(BaseModel):
    kota_id:     int
    kota_nama:   str
    provinsi_id: int
