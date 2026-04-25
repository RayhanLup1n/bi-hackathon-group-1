"""
Playwright-based scraper sebagai fallback jika API endpoint tidak accessible.
Menggunakan headless Chromium untuk render halaman dinamis dan ekstrak tabel.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger

from config.constants import KOMODITAS, TIPE_PASAR
from extractors.models import HargaKomoditasRecord

PIHPS_URL = "https://www.bi.go.id/hargapangan/TabelHarga/PasarTradisionalKomoditas"


class PlaywrightScraper:
    """
    Headless browser scraper untuk BI PIHPS menggunakan Playwright.

    Alur kerja:
    1. Buka halaman PIHPS
    2. Set filter: tanggal, komoditas, tipe pasar
    3. Klik "Lihat Laporan"
    4. Tunggu tabel ter-render
    5. Parse HTML tabel → list of dict
    """

    def __init__(self):
        self._browser = None
        self._playwright_ctx = None

    def _start(self):
        """Lazy-start Playwright browser."""
        from playwright.sync_api import sync_playwright
        if self._playwright_ctx is None:
            self._playwright_ctx = sync_playwright().start()
            self._browser = self._playwright_ctx.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],  # needed for Docker
            )

    def scrape_harga_komoditas(
        self,
        tanggal: date,
        komoditas_ids: list[int],
        tipe_pasar: int = TIPE_PASAR["pasar_tradisional"],
    ) -> list[dict]:
        """Scrape data harga untuk satu tanggal via headless browser."""
        self._start()
        assert self._browser is not None

        records = []
        tanggal_str = tanggal.strftime("%d/%m/%Y")

        for komoditas_id in komoditas_ids:
            komoditas_info = next(
                (v for v in KOMODITAS.values() if v["id"] == komoditas_id), None
            )
            if not komoditas_info:
                continue

            try:
                page_records = self._scrape_single_komoditas(
                    tanggal_str=tanggal_str,
                    komoditas_id=komoditas_id,
                    komoditas_info=komoditas_info,
                    tipe_pasar=tipe_pasar,
                    target_date=tanggal,
                )
                records.extend(page_records)
                logger.debug(
                    f"  Playwright: {len(page_records)} record untuk "
                    f"{komoditas_info['nama']} tanggal {tanggal}"
                )
            except Exception as e:
                logger.warning(
                    f"  Playwright gagal untuk komoditas {komoditas_id}: {e}"
                )

        return records

    def _scrape_single_komoditas(
        self,
        tanggal_str: str,
        komoditas_id: int,
        komoditas_info: dict,
        tipe_pasar: int,
        target_date: date,
    ) -> list[dict]:
        """Scrape satu halaman untuk satu komoditas."""
        assert self._browser is not None
        page = self._browser.new_page()
        records = []

        try:
            # Buka halaman
            page.goto(PIHPS_URL, wait_until="networkidle", timeout=30_000)

            # Intercept network untuk capture API calls
            api_responses: list[dict] = []

            def handle_response(response):
                """Tangkap response JSON dari API calls yang terjadi."""
                if response.url and any(
                    kw in response.url for kw in ["WebAjax", "api", "Ajax", "GetData"]
                ):
                    try:
                        data = response.json()
                        api_responses.append({"url": response.url, "data": data})
                        logger.debug(f"Intercepted API: {response.url}")
                    except Exception:
                        pass

            page.on("response", handle_response)

            # ── Isi form filter ──────────────────────────────────────────
            # Set tanggal (format DD/MM/YYYY)
            self._safe_fill(page, "#tanggalAwal", tanggal_str)
            self._safe_fill(page, "#tanggalAkhir", tanggal_str)

            # Set komoditas dropdown
            self._safe_select(page, "#komoditas", str(komoditas_id))

            # Set tipe pasar dropdown
            self._safe_select(page, "#tipePasar", str(tipe_pasar))

            # Klik tombol "Lihat Laporan" / "Tampilkan"
            submit_selectors = [
                "button:has-text('Lihat Laporan')",
                "button:has-text('Tampilkan')",
                "input[type='submit']",
                "#btnLihat",
                ".btn-lihat",
            ]
            for selector in submit_selectors:
                try:
                    page.click(selector, timeout=3_000)
                    break
                except Exception:
                    continue

            # Tunggu tabel loading selesai
            page.wait_for_timeout(3_000)

            # ── Jika ada API response yang tertangkap, parse itu ─────────
            if api_responses:
                for resp in api_responses:
                    parsed = self._parse_intercepted_response(
                        data=resp["data"],
                        tanggal=target_date,
                        komoditas_id=komoditas_id,
                        komoditas_info=komoditas_info,
                    )
                    records.extend(parsed)
                # Catat endpoint yang ditemukan untuk update constants.py
                logger.info(
                    f"[ENDPOINT DITEMUKAN] {[r['url'] for r in api_responses]}"
                )
            else:
                # ── Fallback: parse tabel HTML langsung ──────────────────
                records = self._parse_html_table(
                    page=page,
                    tanggal=target_date,
                    komoditas_id=komoditas_id,
                    komoditas_info=komoditas_info,
                )

        finally:
            page.close()

        return records

    def _parse_intercepted_response(
        self,
        data: Any,
        tanggal: date,
        komoditas_id: int,
        komoditas_info: dict,
    ) -> list[dict]:
        """Parse data yang diintercept dari API response."""
        if isinstance(data, dict):
            for key in ("data", "Data", "result", "rows"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
        if not isinstance(data, list):
            return []

        records = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                record = HargaKomoditasRecord(
                    tanggal=item.get("tanggal", tanggal),
                    komoditas_id=komoditas_id,
                    komoditas_nama=item.get("namaKomoditas", komoditas_info["nama"]),
                    pasar_tipe=item.get("tipePasar", 1),
                    provinsi_id=item.get("provinsiId"),
                    provinsi_nama=item.get("namaProvinsi"),
                    kota_id=item.get("kotaId"),
                    kota_nama=item.get("namaKota"),
                    pasar_nama=item.get("namaPasar"),
                    harga=item.get("harga") or item.get("hargaRata"),
                    satuan=komoditas_info.get("satuan", "kg"),
                )
                records.append(record.model_dump())
            except Exception as e:
                logger.debug(f"Skip record: {e}")
        return records

    def _parse_html_table(
        self,
        page: Any,
        tanggal: date,
        komoditas_id: int,
        komoditas_info: dict,
    ) -> list[dict]:
        """Parse tabel HTML dari halaman yang sudah di-render."""
        from bs4 import BeautifulSoup

        html = page.content()
        soup = BeautifulSoup(html, "lxml")
        records = []

        # Cari tabel data harga
        tables = soup.find_all("table")
        if not tables:
            logger.warning("Tidak ditemukan tabel di halaman")
            return []

        # Biasanya tabel pertama atau tabel dengan class tertentu
        for table in tables:
            headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
            if not any(kw in str(headers) for kw in ["harga", "provinsi", "kota"]):
                continue

            rows = table.find_all("tr")[1:]  # skip header
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) < 2:
                    continue
                try:
                    record = HargaKomoditasRecord(
                        tanggal=tanggal,
                        komoditas_id=komoditas_id,
                        komoditas_nama=komoditas_info["nama"],
                        provinsi_nama=cells[0] if len(cells) > 0 else None,
                        kota_nama=cells[1] if len(cells) > 1 else None,
                        harga=cells[2] if len(cells) > 2 else None,
                        satuan=komoditas_info.get("satuan", "kg"),
                    )
                    records.append(record.model_dump())
                except Exception as e:
                    logger.debug(f"Skip HTML row: {e}")

        return records

    @staticmethod
    def _safe_fill(page: Any, selector: str, value: str) -> None:
        try:
            page.fill(selector, value, timeout=3_000)
        except Exception:
            pass

    @staticmethod
    def _safe_select(page: Any, selector: str, value: str) -> None:
        try:
            page.select_option(selector, value=value, timeout=3_000)
        except Exception:
            pass

    def close(self) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright_ctx:
            self._playwright_ctx.stop()
