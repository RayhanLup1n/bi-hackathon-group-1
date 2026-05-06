from pydantic import BaseModel
from typing import Optional
from enum import Enum


class DiagnosisType(str, Enum):
    DEMAND = "demand"
    SUPPLY = "supply"
    DISTRIBUSI = "distribusi"
    UNKNOWN = "unknown"


class CuacaInfo(BaseModel):
    ekstrem: bool
    desc: str
    daerah: str = ""
    detail: str = ""   # detail tambahan (suhu, kelembaban, atau narasi peringatan)


class StokInfo(BaseModel):
    status: str       # "Normal", "Menipis", "Kritis"
    kelas: str        # "ok", "warn", "danger"
    pct: float = 0.0  # rasio stok aktual / kapasitas normal (0.0 – 1.0)


class KotaInfo(BaseModel):
    nama: str
    naik: bool


class CommodityData(BaseModel):
    key: str
    name: str
    price_now: int          # dalam rupiah
    price_prev: int         # harga periode sebelumnya
    price_threshold: float  # % kenaikan untuk trigger anomali
    ml_pred: Optional[int] = None
    cuaca: CuacaInfo
    kota_list: list[KotaInfo]
    stok: StokInfo
    threshold_kota: float = 0.6  # default 60% kota = spread nasional


class CheckResult(BaseModel):
    step: int
    nama: str
    status: str   # "triggered", "clear", "skip"
    detail: str


class RCAResult(BaseModel):
    commodity_key: str
    commodity_name: str
    diagnosis: DiagnosisType
    title: str
    description: str
    action: str
    checks: list[CheckResult]
    price_delta_pct: float
    is_anomaly: bool


# ── BMKG Response Models ──────────────────────────────────────────────────────

class BmkgWilayah(BaseModel):
    kode: str
    nama: str
    provinsi: str
    lat: float
    lon: float
    iklim: str


class BmkgCuacaHarian(BaseModel):
    tanggal: str
    kondisi: str
    suhu_min: float
    suhu_max: float
    kelembaban: int
    curah_hujan: float
    sumber: str


class BmkgPeringatan(BaseModel):
    kode_peringatan: str
    tipe: str
    level: str
    deskripsi: str
    tgl_mulai: str
    tgl_selesai: str
    nama: str
    provinsi: str


class BmkgPeringatanAktif(BmkgPeringatan):
    wilayah_kode: str
    lat: float
    lon: float
