"""
HTTP client dengan session management, XSRF token handling, retry, dan rate limiting.

Temuan dari DevTools:
- Semua request adalah GET
- Server menggunakan ASP.NET Core antiforgery: butuh cookie WSAntiforgeryCookie
  dan header XSRF-TOKEN yang nilainya diambil dari cookie tersebut
- Ada WAF cookies (TS*) yang di-set otomatis oleh server saat session init
- Session perlu di-refresh jika dapat HTTP 403 atau response tidak valid
"""
import time
from typing import Any

import httpx
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.constants import BASE_HEADERS, SESSION_INIT_PATH, cache_buster
from config.settings import settings

# Nama cookie antiforgery yang dipakai PIHPS
_ANTIFORGERY_COOKIE = "WSAntiforgeryCookie"
_XSRF_HEADER = "XSRF-TOKEN"


class PihpsHttpClient:
    """
    HTTP client untuk BI PIHPS.

    Fitur:
    - Session initialization otomatis (ambil cookies + XSRF token dari halaman utama)
    - Auto-refresh session jika expired (HTTP 403 / response tidak valid)
    - Retry dengan exponential backoff
    - Rate limiting antar request
    - Cookie jar dikelola otomatis oleh httpx
    """

    def __init__(self):
        self._client: httpx.Client | None = None
        self._last_request_time: float = 0.0
        self._xsrf_token: str = ""
        self._session_initialized: bool = False

    # ─────────────────────────────────────────────────────────────────────────
    # Session management
    # ─────────────────────────────────────────────────────────────────────────

    def _build_client(self) -> httpx.Client:
        """Buat httpx Client baru dengan cookie jar kosong."""
        return httpx.Client(
            base_url=settings.base_url,
            headers=BASE_HEADERS,
            timeout=settings.timeout,
            follow_redirects=True,
            # httpx mengelola cookie jar secara otomatis
        )

    def _init_session(self) -> None:
        """
        Inisialisasi session dengan mengunjungi halaman utama PIHPS.
        Server akan set cookie WSAntiforgeryCookie dan TS* (WAF) secara otomatis.
        Kita ekstrak nilai XSRF token dari cookie untuk disertakan di header.
        """
        if self._client is None or self._client.is_closed:
            self._client = self._build_client()

        logger.debug("Inisialisasi session PIHPS...")
        try:
            resp = self._client.get(SESSION_INIT_PATH)
            resp.raise_for_status()

            # Ekstrak XSRF token dari cookie jar
            self._xsrf_token = self._client.cookies.get(_ANTIFORGERY_COOKIE, "")
            if self._xsrf_token:
                logger.debug(f"XSRF token diperoleh ({len(self._xsrf_token)} chars)")
            else:
                logger.warning(
                    "Cookie WSAntiforgeryCookie tidak ditemukan. "
                    "Request mungkin tetap berhasil tanpa XSRF token."
                )

            self._session_initialized = True
            logger.success("Session PIHPS berhasil diinisialisasi.")

        except httpx.HTTPStatusError as e:
            logger.error(f"Gagal inisialisasi session: HTTP {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Gagal inisialisasi session: {e}")
            raise

    def _refresh_session(self) -> None:
        """Tutup client lama dan inisialisasi session baru."""
        logger.info("Refresh session PIHPS...")
        if self._client and not self._client.is_closed:
            self._client.close()
        self._client = None
        self._xsrf_token = ""
        self._session_initialized = False
        self._init_session()

    def _ensure_session(self) -> httpx.Client:
        """Pastikan session sudah aktif sebelum request."""
        if not self._session_initialized or self._client is None or self._client.is_closed:
            self._init_session()
        assert self._client is not None
        return self._client

    def _build_headers(self) -> dict[str, str]:
        """Buat headers lengkap dengan XSRF token jika tersedia."""
        headers: dict[str, str] = {}
        if self._xsrf_token:
            headers[_XSRF_HEADER] = self._xsrf_token
        return headers

    # ─────────────────────────────────────────────────────────────────────────
    # Rate limiting
    # ─────────────────────────────────────────────────────────────────────────

    def _rate_limit(self) -> None:
        """Pastikan jeda minimal antar request agar tidak kena block."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < settings.request_delay:
            sleep_time = settings.request_delay - elapsed
            logger.debug(f"Rate limiting: tidur {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self._last_request_time = time.monotonic()

    # ─────────────────────────────────────────────────────────────────────────
    # HTTP methods
    # ─────────────────────────────────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """
        GET request ke PIHPS endpoint.

        - Otomatis menambahkan cache-buster '_' ke params
        - Otomatis menyertakan XSRF-TOKEN header
        - Auto-refresh session jika dapat 403
        - Return: parsed JSON (dict atau list)
        """
        self._rate_limit()
        client = self._ensure_session()

        # Tambah cache-buster (diperlukan oleh PIHPS)
        full_params = dict(params or {})
        full_params["_"] = cache_buster()

        logger.debug(f"GET {endpoint} | params={params}")  # log tanpa cache-buster

        try:
            response = client.get(
                endpoint,
                params=full_params,
                headers=self._build_headers(),
            )

            # Jika 403, coba refresh session sekali
            if response.status_code == 403:
                logger.warning("HTTP 403 — refresh session dan retry...")
                self._refresh_session()
                client = self._ensure_session()
                full_params["_"] = cache_buster()
                response = client.get(
                    endpoint,
                    params=full_params,
                    headers=self._build_headers(),
                )

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} pada GET {endpoint}")
            raise

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            self._client.close()
        self._session_initialized = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
