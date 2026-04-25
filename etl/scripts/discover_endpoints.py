#!/usr/bin/env python3
"""
Helper: test koneksi ke BI PIHPS dan coba temukan endpoint API.
Jalankan dari dalam container:
  docker compose exec airflow-scheduler python scripts/discover_endpoints.py
"""
import json
import sys

import httpx
from loguru import logger

sys.path.insert(0, "/opt/airflow")

from config.constants import DEFAULT_HEADERS
from config.settings import settings

# Daftar endpoint kandidat untuk dicoba
CANDIDATE_ENDPOINTS = [
    "/WebAjax/GetListHargaKomoditas",
    "/WebAjax/GetHargaKomoditas",
    "/WebAjax/GetPasarTradisionalKomoditas",
    "/WebAjax/GetDataHarga",
    "/WebAjax/GetListProvinsi",
    "/WebAjax/GetListKomoditas",
    "/api/GetHarga",
    "/api/harga-komoditas",
    "/Home/GetData",
    "/TabelHarga/GetData",
]

SAMPLE_PAYLOAD = {
    "tanggalAwal": "01/01/2024",
    "tanggalAkhir": "01/01/2024",
    "komoditasId": "1",
    "tipeHarga": "1",
}


def test_endpoint(client: httpx.Client, endpoint: str) -> bool:
    """Coba POST ke endpoint dan cek apakah response-nya JSON."""
    url = settings.base_url + endpoint
    try:
        resp = client.post(url, data=SAMPLE_PAYLOAD, timeout=10)
        content_type = resp.headers.get("content-type", "")
        if "json" in content_type or resp.text.strip().startswith(("{", "[")):
            logger.success(f"✓ ENDPOINT DITEMUKAN: {endpoint}")
            logger.info(f"  Status : {resp.status_code}")
            logger.info(f"  Preview: {resp.text[:300]}")
            return True
        else:
            logger.debug(f"✗ {endpoint} → {resp.status_code} ({content_type[:50]})")
    except Exception as e:
        logger.debug(f"✗ {endpoint} → Error: {e}")
    return False


def main():
    logger.info(f"Testing koneksi ke: {settings.base_url}")

    with httpx.Client(headers=DEFAULT_HEADERS, follow_redirects=True) as client:
        # Test koneksi dasar
        try:
            resp = client.get(settings.base_url, timeout=10)
            logger.success(f"Koneksi OK: HTTP {resp.status_code}")
        except Exception as e:
            logger.error(f"Gagal konek ke {settings.base_url}: {e}")
            return

        logger.info("\nMencoba endpoint kandidat...")
        found = []
        for ep in CANDIDATE_ENDPOINTS:
            if test_endpoint(client, ep):
                found.append(ep)

    print("\n" + "=" * 60)
    if found:
        print(f"Endpoint yang berhasil ditemukan ({len(found)}):")
        for ep in found:
            print(f"  {settings.base_url}{ep}")
        print("\nUpdate config/constants.py dengan endpoint yang ditemukan!")
    else:
        print("Tidak ada endpoint yang ditemukan via POST.")
        print("Coba gunakan Playwright scraper (strategi 2) atau")
        print("inspect Network tab di browser secara manual.")
    print("=" * 60)


if __name__ == "__main__":
    main()
