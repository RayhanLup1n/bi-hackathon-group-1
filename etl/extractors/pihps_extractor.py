"""
Extractor utama untuk data harga pangan dari BI PIHPS.

Berdasarkan hasil inspeksi DevTools, endpoint yang digunakan:

  DATA UTAMA:
    GET /WebSite/TabelHarga/GetGridDataDaerah
      ?price_type_id=1          → tipe pasar (1=tradisional)
      &comcat_id=               → kategori komoditas ("" = semua, "cat_1" = kategori tertentu)
      &province_id=             → provinsi ("" = semua, angka = filter provinsi)
      &regency_id=              → kabupaten/kota ("" = semua)
      &market_id=               → pasar ("" = semua)
      &tipe_laporan=1           → tipe laporan (1=rata-rata)
      &start_date=2026-04-17   → tanggal mulai (format YYYY-MM-DD)
      &end_date=2026-04-25     → tanggal selesai (format YYYY-MM-DD)
      &_=<timestamp>            → cache-buster

  MASTER DATA:
    GET /WebSite/TabelHarga/GetRefCommodityAndCategory   → daftar komoditas & kategori
    GET /WebSite/TabelHarga/GetRefProvince               → daftar provinsi
    GET /WebSite/TabelHarga/GetRefRegency?price_type_id=1&ref_prov_id=   → kab/kota
    GET /WebSite/TabelHarga/GetRefMarket?ref_regency_id=&price_type_id=1 → pasar

Strategi:
  1. Init session (GET halaman utama → dapat cookies + XSRF token)
  2. Load master data komoditas (dapat peta comcat_id)
  3. Tarik GetGridDataDaerah per rentang tanggal (satu call = semua komoditas + semua daerah)
  4. Parse & validasi response → simpan ke DuckDB
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
from loguru import logger

from config.constants import COMCAT_ALL, ENDPOINTS, TIPE_LAPORAN, TIPE_PASAR
from config.settings import settings
from extractors.http_client import PihpsHttpClient
from extractors.models import HargaKomoditasRecord, KomoditasInfo


class PihpsExtractor:
    """
    Extractor data harga pangan dari BI PIHPS.

    Contoh pemakaian:
        with PihpsExtractor() as extractor:
            # Ambil semua komoditas, semua provinsi, rentang tanggal
            df = extractor.extract_harga(
                tanggal_mulai=date(2024, 1, 1),
                tanggal_selesai=date(2024, 1, 31),
            )
    """

    # Batas maksimal rentang per request (hindari timeout untuk rentang panjang)
    _MAX_DAYS_PER_REQUEST = 30

    def __init__(self):
        self._http = PihpsHttpClient()
        # Cache master data agar tidak perlu re-fetch setiap request
        self._komoditas_map: dict[str, KomoditasInfo] = {}  # comcat_id → info
        self._provinsi_map: dict[int, str] = {}             # provinsi_id → nama
        self._name_to_comcat_id: dict[str, str] = {}        # nama (lowercase) → comcat_id

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def load_master_data(self) -> None:
        """
        Muat master data komoditas dan provinsi.
        Dipanggil sekali di awal sebelum extract data harga.
        """
        self._load_komoditas()
        self._load_provinsi()

    def extract_harga(
        self,
        tanggal_mulai: date,
        tanggal_selesai: date,
        price_type_id: int = TIPE_PASAR["pasar_tradisional"],
        comcat_id: str = COMCAT_ALL,
        province_id: str = "",
        regency_id: str = "",
        market_id: str = "",
        tipe_laporan: int = TIPE_LAPORAN["harga_rata"],
    ) -> pd.DataFrame:
        """
        Tarik data harga dari GetGridDataDaerah.

        Satu call ke endpoint ini sudah mengembalikan SEMUA komoditas
        dan SEMUA daerah dalam rentang tanggal yang diminta.
        Untuk efisiensi, rentang panjang dipecah per _MAX_DAYS_PER_REQUEST hari.

        Args:
            tanggal_mulai   : Tanggal awal (inklusif)
            tanggal_selesai : Tanggal akhir (inklusif)
            price_type_id   : Tipe pasar (default: 1 = pasar tradisional)
            comcat_id       : ID kategori komoditas ("" = semua)
            province_id     : ID provinsi ("" = semua)
            regency_id      : ID kab/kota ("" = semua)
            market_id       : ID pasar ("" = semua)
            tipe_laporan    : Tipe laporan harga (default: 1 = rata-rata)

        Returns:
            DataFrame berisi data harga yang sudah dinormalisasi
        """
        if not self._komoditas_map:
            logger.info("Master data komoditas belum dimuat, loading...")
            self._load_komoditas()

        all_records: list[dict] = []
        total_days = (tanggal_selesai - tanggal_mulai).days + 1
        logger.info(
            f"Mulai extract harga: {tanggal_mulai} → {tanggal_selesai} "
            f"({total_days} hari)"
        )

        # Pecah rentang menjadi chunk agar tidak timeout
        chunk_start = tanggal_mulai
        while chunk_start <= tanggal_selesai:
            chunk_end = min(
                chunk_start + timedelta(days=self._MAX_DAYS_PER_REQUEST - 1),
                tanggal_selesai,
            )
            logger.info(f"  Chunk: {chunk_start} → {chunk_end}")

            try:
                records = self._fetch_grid_data(
                    start_date=chunk_start,
                    end_date=chunk_end,
                    price_type_id=price_type_id,
                    comcat_id=comcat_id,
                    province_id=province_id,
                    regency_id=regency_id,
                    market_id=market_id,
                    tipe_laporan=tipe_laporan,
                )
                all_records.extend(records)
                logger.success(
                    f"  ✓ {len(records)} record untuk "
                    f"{chunk_start} → {chunk_end}"
                )
            except Exception as exc:
                logger.error(f"  ✗ Gagal chunk {chunk_start} → {chunk_end}: {exc}")

            chunk_start = chunk_end + timedelta(days=1)

        if not all_records:
            logger.warning("Tidak ada data yang berhasil ditarik!")
            return pd.DataFrame()

        df = pd.DataFrame(all_records)
        return self._normalize_dataframe(df)

    def extract_today(self) -> pd.DataFrame:
        """Shortcut: tarik data hari ini (untuk daily pipeline)."""
        today = date.today()
        return self.extract_harga(tanggal_mulai=today, tanggal_selesai=today)

    def extract_yesterday(self) -> pd.DataFrame:
        """Shortcut: tarik data kemarin (lebih aman karena data D+0 kadang belum lengkap)."""
        yesterday = date.today() - timedelta(days=1)
        return self.extract_harga(tanggal_mulai=yesterday, tanggal_selesai=yesterday)

    def extract_harga_per_wilayah(
        self,
        tanggal_mulai: date,
        tanggal_selesai: date,
        province_ids: list[int] | None = None,
        price_type_id: int = TIPE_PASAR["pasar_tradisional"],
        tipe_laporan: int = TIPE_LAPORAN["harga_rata"],
    ) -> pd.DataFrame:
        """
        Tarik data harga per kota untuk provinsi tertentu.

        Strategi:
          1. Load master provinsi & komoditas
          2. Untuk setiap provinsi → ambil daftar kota
          3. Untuk setiap kota → tarik GetGridDataDaerah per chunk tanggal
          4. Gabungkan semua → DataFrame

        Args:
            tanggal_mulai   : Tanggal awal
            tanggal_selesai : Tanggal akhir
            province_ids    : List PIHPS province ID (None = semua provinsi)
            price_type_id   : Tipe pasar (default: 1 = tradisional)
            tipe_laporan    : Tipe laporan (default: 1 = rata-rata)

        Returns:
            DataFrame berisi data harga per kota yang sudah dinormalisasi
        """
        # Pastikan master data sudah dimuat
        if not self._komoditas_map:
            self._load_komoditas()
        if not self._provinsi_map:
            self._load_provinsi()

        # Tentukan provinsi yang akan di-crawl
        if province_ids:
            target_provinces = {
                pid: self._provinsi_map.get(pid, f"Provinsi_{pid}")
                for pid in province_ids
            }
        else:
            target_provinces = dict(self._provinsi_map)

        logger.info(
            f"Extract per-wilayah: {len(target_provinces)} provinsi, "
            f"{tanggal_mulai} → {tanggal_selesai}"
        )

        all_records: list[dict] = []

        for prov_id, prov_nama in target_provinces.items():
            # Ambil daftar kota untuk provinsi ini
            kota_list = self._get_kota_list(str(prov_id))
            logger.info(
                f"  Provinsi {prov_nama} (ID={prov_id}): {len(kota_list)} kota"
            )

            for kota in kota_list:
                kota_id = str(kota["id"])
                kota_nama = kota["name"]
                logger.info(f"    → {kota_nama} (ID={kota_id})")

                # Pecah rentang tanggal menjadi chunks
                chunk_start = tanggal_mulai
                while chunk_start <= tanggal_selesai:
                    chunk_end = min(
                        chunk_start + timedelta(days=self._MAX_DAYS_PER_REQUEST - 1),
                        tanggal_selesai,
                    )

                    try:
                        records = self._fetch_grid_data_with_context(
                            start_date=chunk_start,
                            end_date=chunk_end,
                            price_type_id=price_type_id,
                            province_id=str(prov_id),
                            province_name=prov_nama,
                            regency_id=kota_id,
                            regency_name=kota_nama,
                            tipe_laporan=tipe_laporan,
                        )
                        all_records.extend(records)
                        logger.debug(
                            f"      ✓ {len(records)} record "
                            f"({chunk_start} → {chunk_end})"
                        )
                    except Exception as exc:
                        logger.error(
                            f"      ✗ Gagal {kota_nama} "
                            f"({chunk_start} → {chunk_end}): {exc}"
                        )

                    chunk_start = chunk_end + timedelta(days=1)

        logger.info(f"Total records: {len(all_records)}")

        if not all_records:
            logger.warning("Tidak ada data per-wilayah yang berhasil ditarik!")
            return pd.DataFrame()

        df = pd.DataFrame(all_records)
        return self._normalize_dataframe(df)

    def _fetch_grid_data_with_context(
        self,
        start_date: date,
        end_date: date,
        price_type_id: int,
        province_id: str,
        province_name: str,
        regency_id: str,
        regency_name: str,
        tipe_laporan: int,
    ) -> list[dict]:
        """
        Fetch grid data dengan province/regency context yang sudah diketahui.
        Berbeda dari _fetch_grid_data yang harus lookup nama provinsi.
        """
        params = {
            "price_type_id": price_type_id,
            "comcat_id":     "",
            "province_id":   province_id,
            "regency_id":    regency_id,
            "market_id":     "",
            "tipe_laporan":  tipe_laporan,
            "start_date":    start_date.strftime("%Y-%m-%d"),
            "end_date":      end_date.strftime("%Y-%m-%d"),
        }

        raw = self._http.get(ENDPOINTS["harga_daerah"], params=params)

        return self._parse_grid_response(
            raw=raw,
            price_type_id=price_type_id,
            province_id=province_id,
            province_name=province_name,
            regency_id=regency_id,
            regency_name=regency_name,
        )

    def _get_kota_list(self, province_id: str) -> list[dict]:
        """Ambil list kota untuk satu provinsi. Returns list of {id, name}."""
        try:
            raw = self._http.get(
                ENDPOINTS["ref_kota"],
                params={"price_type_id": 1, "ref_prov_id": province_id},
            )
            items = self._to_list(raw)
            return [
                {"id": item["id"], "name": item["name"]}
                for item in items
                if isinstance(item, dict) and "id" in item and "name" in item
            ]
        except Exception as exc:
            logger.warning(f"Gagal ambil kota untuk provinsi {province_id}: {exc}")
            return []

    def get_master_komoditas(self) -> pd.DataFrame:
        """Ambil master data komoditas sebagai DataFrame."""
        if not self._komoditas_map:
            self._load_komoditas()
        if not self._komoditas_map:
            return pd.DataFrame()
        return pd.DataFrame([v.model_dump() for v in self._komoditas_map.values()])

    def get_master_provinsi(self) -> pd.DataFrame:
        """Ambil master data provinsi sebagai DataFrame."""
        if not self._provinsi_map:
            self._load_provinsi()
        return pd.DataFrame(
            [{"provinsi_id": k, "provinsi_nama": v} for k, v in self._provinsi_map.items()]
        )

    def get_master_kota(self, province_id: str = "") -> pd.DataFrame:
        """Ambil master data kab/kota, opsional filter per provinsi."""
        try:
            raw = self._http.get(
                ENDPOINTS["ref_kota"],
                params={"price_type_id": 1, "ref_prov_id": province_id},
            )
            return pd.DataFrame(self._to_list(raw))
        except Exception as exc:
            logger.warning(f"Gagal ambil master kota: {exc}")
            return pd.DataFrame()

    def get_master_pasar(self, regency_id: str = "") -> pd.DataFrame:
        """Ambil master data pasar, opsional filter per kab/kota."""
        try:
            raw = self._http.get(
                ENDPOINTS["ref_pasar"],
                params={"ref_regency_id": regency_id, "price_type_id": 1},
            )
            return pd.DataFrame(self._to_list(raw))
        except Exception as exc:
            logger.warning(f"Gagal ambil master pasar: {exc}")
            return pd.DataFrame()

    # ─────────────────────────────────────────────────────────────────────────
    # Internal: fetch
    # ─────────────────────────────────────────────────────────────────────────

    def _fetch_grid_data(
        self,
        start_date: date,
        end_date: date,
        price_type_id: int,
        comcat_id: str,
        province_id: str,
        regency_id: str,
        market_id: str,
        tipe_laporan: int,
    ) -> list[dict]:
        """
        Panggil GetGridDataDaerah dan parse hasilnya.
        Format tanggal: YYYY-MM-DD (sesuai temuan DevTools).
        """
        params = {
            "price_type_id": price_type_id,
            "comcat_id":     comcat_id,
            "province_id":   province_id,
            "regency_id":    regency_id,
            "market_id":     market_id,
            "tipe_laporan":  tipe_laporan,
            "start_date":    start_date.strftime("%Y-%m-%d"),
            "end_date":      end_date.strftime("%Y-%m-%d"),
        }

        raw = self._http.get(ENDPOINTS["harga_daerah"], params=params)

        # Resolve province/regency names for context
        province_name = self._provinsi_map.get(int(province_id)) if province_id else None
        regency_name = None  # Not available in simple flow

        return self._parse_grid_response(
            raw=raw,
            price_type_id=price_type_id,
            province_id=province_id,
            province_name=province_name or "",
            regency_id=regency_id,
            regency_name=regency_name or "",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Internal: master data loaders
    # ─────────────────────────────────────────────────────────────────────────

    def _load_komoditas(self) -> None:
        """
        Muat daftar komoditas & kategori dari API, simpan ke cache.

        Response format dari GetRefCommodityAndCategory:
        {"data": [
            {"id": "cat_1", "name": "Beras", "cat_id": null, "denomination": "kg", "sort": 1},
            {"id": "com_1", "name": "Beras Kualitas Bawah I", "cat_id": "cat_1", "denomination": "kg", "sort": 1},
            ...
        ]}
        """
        try:
            raw = self._http.get(ENDPOINTS["ref_komoditas"])
            items = self._to_list(raw)
            logger.debug(f"Raw komoditas response ({len(items)} items): {items[:2]}")

            self._komoditas_map = {}
            self._name_to_comcat_id = {}

            for item in items:
                if not isinstance(item, dict):
                    continue
                comcat_id = str(item.get("id") or "")
                nama = str(item.get("name") or "").strip()
                satuan = str(item.get("denomination") or "kg")

                if comcat_id and nama:
                    self._komoditas_map[comcat_id] = KomoditasInfo(
                        comcat_id=comcat_id,
                        nama=nama,
                        satuan=satuan,
                    )
                    # Reverse mapping: nama (lowercase) → comcat_id
                    self._name_to_comcat_id[nama.lower()] = comcat_id

            logger.success(f"Master komoditas dimuat: {len(self._komoditas_map)} item")
            if self._komoditas_map:
                logger.debug(f"Contoh: {list(self._komoditas_map.items())[:3]}")

        except Exception as exc:
            logger.warning(f"Gagal load master komoditas: {exc}")

    def _load_provinsi(self) -> None:
        """Muat daftar provinsi dari API, simpan ke cache."""
        try:
            raw = self._http.get(ENDPOINTS["ref_provinsi"])
            items = self._to_list(raw)

            self._provinsi_map = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                prov_id = (
                    item.get("province_id") or
                    item.get("provinsi_id") or
                    item.get("id")
                )
                prov_nama = (
                    item.get("province_name") or
                    item.get("provinsi_nama") or
                    item.get("nama") or
                    item.get("name")
                )
                if prov_id and prov_nama:
                    self._provinsi_map[int(prov_id)] = str(prov_nama)

            logger.success(f"Master provinsi dimuat: {len(self._provinsi_map)} provinsi")

        except Exception as exc:
            logger.warning(f"Gagal load master provinsi: {exc}")

    # ─────────────────────────────────────────────────────────────────────────
    # Internal: parsing
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_grid_response(
        self,
        raw: Any,
        price_type_id: int,
        province_id: str = "",
        province_name: str = "",
        regency_id: str = "",
        regency_name: str = "",
    ) -> list[dict]:
        """
        Parse response dari GetGridDataDaerah.

        Format response PIHPS adalah pivot table:
        {
          "data": [
            {
              "no": "I" / 1,
              "name": "Beras" / "Beras Kualitas Bawah I",
              "level": 1 / 2,
              "22/04/2026": "15,150",    ← tanggal sebagai KEY
              "23/04/2026": "15,150",
              "24/04/2026": "15,150"
            },
            ...
          ]
        }

        - level 1 = kategori (header/ringkasan) → skip, gunakan level 2 saja
        - level 2 = komoditas individual → ini data yang kita ambil
        - Tanggal dalam format DD/MM/YYYY sebagai key columns
        - Harga berformat string dengan koma ribuan: "15,150"
        """
        items = self._to_list(raw)
        if not items:
            logger.warning(f"Response kosong atau format tidak dikenal: {str(raw)[:200]}")
            return []

        records = []
        # Keys yang bukan tanggal (metadata columns)
        meta_keys = {"no", "name", "level"}

        for item in items:
            if not isinstance(item, dict):
                continue

            level = item.get("level", 0)
            name = str(item.get("name", "")).strip()

            if not name:
                continue

            # Skip level 1 (kategori/header) — hanya ambil level 2 (komoditas)
            if level == 1:
                continue

            # Cari comcat_id dari master data berdasarkan nama
            comcat_id = self._find_comcat_id(name)
            satuan = self._find_satuan(name)

            # Unpivot: iterasi setiap date-column → 1 record per tanggal
            for key, value in item.items():
                if key in meta_keys:
                    continue

                # Cek apakah key berformat tanggal DD/MM/YYYY
                if not self._is_date_key(key):
                    continue

                try:
                    record = HargaKomoditasRecord(
                        tanggal=key,  # DD/MM/YYYY — diparse oleh validator
                        comcat_id=comcat_id,
                        komoditas_nama=name,
                        pasar_tipe=price_type_id,
                        provinsi_id=int(province_id) if province_id else None,
                        provinsi_nama=province_name or None,
                        kota_id=int(regency_id) if regency_id else None,
                        kota_nama=regency_name or None,
                        pasar_nama=None,
                        harga=value,
                        satuan=satuan,
                    )
                    records.append(record.model_dump())
                except Exception as e:
                    logger.debug(f"Skip: {name} @ {key}: {e}")

        return records

    def _find_comcat_id(self, name: str) -> str:
        """Cari comcat_id dari master data berdasarkan nama komoditas."""
        return self._name_to_comcat_id.get(name.strip().lower(), "")

    def _find_satuan(self, name: str) -> str:
        """Cari satuan dari master data berdasarkan nama komoditas."""
        comcat_id = self._find_comcat_id(name)
        if comcat_id and comcat_id in self._komoditas_map:
            return self._komoditas_map[comcat_id].satuan
        return "kg"

    @staticmethod
    def _is_date_key(key: str) -> bool:
        """Cek apakah key berformat tanggal DD/MM/YYYY."""
        if "/" not in key:
            return False
        parts = key.split("/")
        return (
            len(parts) == 3
            and len(parts[0]) == 2
            and len(parts[1]) == 2
            and len(parts[2]) == 4
            and all(p.isdigit() for p in parts)
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_list(raw: Any) -> list[dict]:
        """Ekstrak list dari berbagai format response PIHPS."""
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            for key in ("data", "Data", "result", "Result", "items", "rows", "records"):
                val = raw.get(key)
                if isinstance(val, list):
                    return val
        return []

    @staticmethod
    def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """Normalisasi tipe data dan deduplikasi."""
        if df.empty:
            return df

        col_types: dict[str, str] = {
            "tanggal":     "datetime64[ns]",
            "pasar_tipe":  "Int64",
            "provinsi_id": "Int64",
            "kota_id":     "Int64",
            "harga":       "float64",
        }
        for col, dtype in col_types.items():
            if col in df.columns:
                try:
                    df[col] = df[col].astype(dtype)
                except Exception:
                    pass

        return df.drop_duplicates().reset_index(drop=True)

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
