"""
Extractor for BMKG public weather forecast API.

BMKG API provides 3-day forecasts (prakiraan cuaca) per administrative area.
Endpoint: https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4={kode_wilayah}

Returns hourly forecasts with:
  - tp : precipitation (mm)
  - t  : temperature (Celsius)
  - ws : wind speed (km/h or knot depending on unit)
  - hu : humidity (%)
  - tcc: cloud cover (%)
  - wd : wind direction

Rate limit: ~60 req/min.

This extractor is for REAL-TIME data only (3-day forecast).
For historical weather, use openmeteo_extractor.py instead.

Usage:
    extractor = BmkgExtractor()
    forecast = extractor.get_forecast(adm4_code="31.71.01.1001")
    alerts = extractor.get_nowcast_alerts()
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import httpx
from loguru import logger


# BMKG public API endpoints
FORECAST_URL = "https://api.bmkg.go.id/publik/prakiraan-cuaca"

# ADM4 codes for MVP cities (kecamatan-level)
# Format: provinsi.kota.kecamatan.kelurahan
# These are representative codes - one kecamatan per target city
ADM4_CODES: dict[str, dict[str, str]] = {
    # DKI Jakarta - Jakarta Pusat
    "jakarta_pusat": {
        "code": "31.71.01.1001",
        "label": "Gambir, Jakarta Pusat",
        "provinsi_id": "13",
    },
    # Banten - Tangerang
    "tangerang": {
        "code": "36.71.01.1001",
        "label": "Tangerang, Banten",
        "provinsi_id": "11",
    },
    # Jawa Barat - Bandung
    "bandung": {
        "code": "32.73.01.1001",
        "label": "Sumur Bandung, Bandung",
        "provinsi_id": "12",
    },
    # Sulawesi Selatan - Makassar
    "makassar": {
        "code": "73.71.01.1001",
        "label": "Mariso, Makassar",
        "provinsi_id": "26",
    },
}


class BmkgExtractor:
    """
    Fetch 3-day weather forecast from BMKG public API.

    BMKG provides forecasts at kelurahan (ADM4) level,
    with hourly data points for temperature, precipitation,
    wind speed, humidity, and cloud cover.

    Rate limited to ~60 req/min. We add 1.5s delay between requests.
    """

    def __init__(self, request_delay: float = 1.5, timeout: float = 30):
        self._client = httpx.Client(timeout=timeout)
        self._delay = request_delay
        self._last_request: float = 0.0

    def _rate_limit(self) -> None:
        """Ensure minimum delay between requests to respect BMKG rate limit."""
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._delay:
            sleep_time = self._delay - elapsed
            time.sleep(sleep_time)
        self._last_request = time.monotonic()

    def get_forecast(self, adm4_code: str) -> dict[str, Any]:
        """
        Fetch 3-day forecast for a specific area (ADM4 code).

        Args:
            adm4_code: Administrative area code (e.g., "31.71.01.1001")

        Returns:
            Raw JSON response from BMKG API. Structure:
            {
                "lokasi": { "provinsi": "...", "kotkab": "...", ... },
                "data": [
                    {
                        "cuaca": [
                            [  # forecasts for each time slot
                                {
                                    "datetime": "2026-05-24T00:00:00Z",
                                    "t": 27, "tp": 0.5, "ws": 10,
                                    "hu": 85, "tcc": 70, "wd": "N",
                                    ...
                                },
                                ...
                            ],
                            ...
                        ]
                    }
                ]
            }
        """
        self._rate_limit()

        logger.debug(f"Fetching BMKG forecast for ADM4={adm4_code}")

        try:
            resp = self._client.get(
                FORECAST_URL,
                params={"adm4": adm4_code},
            )
            resp.raise_for_status()
            data = resp.json()
            logger.debug(f"BMKG forecast received for ADM4={adm4_code}")
            return data

        except httpx.HTTPStatusError as e:
            logger.error(f"BMKG API error: HTTP {e.response.status_code} for ADM4={adm4_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"BMKG request failed for ADM4={adm4_code}: {e}")
            raise

    def extract_daily_summary(self, adm4_code: str) -> list[dict[str, Any]]:
        """
        Fetch forecast and aggregate to daily summary.

        Converts hourly BMKG forecast data into daily summaries
        matching the same metrics we use from Open-Meteo:
        - max precipitation per day (mm)
        - max temperature per day (Celsius)
        - max wind speed per day (km/h)

        Returns:
            List of dicts with keys:
              tanggal, max_precip, max_temp, max_wind, total_precip
        """
        raw = self.get_forecast(adm4_code)

        # Parse BMKG response structure
        data_list = raw.get("data", [])
        if not data_list:
            logger.warning(f"No forecast data from BMKG for ADM4={adm4_code}")
            return []

        # Collect all hourly data points
        hourly: list[dict[str, Any]] = []
        for data_block in data_list:
            cuaca_groups = data_block.get("cuaca", [])
            for group in cuaca_groups:
                if isinstance(group, list):
                    hourly.extend(group)
                elif isinstance(group, dict):
                    hourly.append(group)

        if not hourly:
            logger.warning(f"No hourly forecast entries for ADM4={adm4_code}")
            return []

        # Group by date and aggregate
        daily_data: dict[str, dict[str, float]] = {}
        for entry in hourly:
            dt_str = entry.get("datetime") or entry.get("local_datetime", "")
            if not dt_str:
                continue

            try:
                # BMKG returns ISO format or similar
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                date_key = dt.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                continue

            precip = float(entry.get("tp", 0) or 0)
            temp = float(entry.get("t", 0) or 0)
            wind = float(entry.get("ws", 0) or 0)

            if date_key not in daily_data:
                daily_data[date_key] = {
                    "max_precip": precip,
                    "total_precip": precip,
                    "max_temp": temp,
                    "max_wind": wind,
                }
            else:
                d = daily_data[date_key]
                d["max_precip"] = max(d["max_precip"], precip)
                d["total_precip"] = d["total_precip"] + precip
                d["max_temp"] = max(d["max_temp"], temp)
                d["max_wind"] = max(d["max_wind"], wind)

        # Convert to list
        result = []
        for date_key in sorted(daily_data.keys()):
            d = daily_data[date_key]
            result.append({
                "tanggal": date_key,
                "max_precip": round(d["max_precip"], 1),
                "total_precip": round(d["total_precip"], 1),
                "max_temp": round(d["max_temp"], 1),
                "max_wind": round(d["max_wind"], 1),
            })

        logger.info(f"BMKG forecast: {len(result)} days for ADM4={adm4_code}")
        return result

    def extract_all_cities(self) -> dict[str, list[dict[str, Any]]]:
        """
        Fetch daily forecast summary for all MVP cities.

        Returns:
            Dict of city_name -> list of daily forecast dicts
        """
        results: dict[str, list[dict[str, Any]]] = {}

        for city_name, info in ADM4_CODES.items():
            label = info["label"]
            code = info["code"]
            logger.info(f"Fetching BMKG forecast: {label} (ADM4={code})")

            try:
                daily = self.extract_daily_summary(code)
                if daily:
                    # Add location metadata
                    for d in daily:
                        d["lokasi"] = label
                        d["provinsi_id"] = int(info["provinsi_id"])
                    results[city_name] = daily
                    logger.success(f"  {label}: {len(daily)} days forecast")
                else:
                    logger.warning(f"  {label}: no data returned")

            except Exception as e:
                logger.error(f"  {label}: failed - {e}")
                results[city_name] = []

        return results

    def derive_siaga_level(
        self,
        precip: float,
        wind: float,
    ) -> tuple[int, str, str]:
        """
        Derive BMKG-style warning level from weather metrics.

        Same thresholds used in sync_gold_to_postgres.py for consistency.

        Returns:
            (level, level_label, fenomena)
        """
        if precip >= 150 or wind >= 80:
            level, label = 4, "Awas"
            if precip >= 150:
                fenomena = f"Hujan Sangat Lebat ({precip:.0f}mm)"
            else:
                fenomena = f"Angin Sangat Kencang ({wind:.0f}km/h)"
        elif precip >= 100 or wind >= 60:
            level, label = 3, "Siaga"
            if precip >= 100:
                fenomena = f"Hujan Lebat ({precip:.0f}mm)"
            else:
                fenomena = f"Angin Kencang ({wind:.0f}km/h)"
        elif precip >= 50 or wind >= 40:
            level, label = 2, "Waspada"
            if precip >= 50:
                fenomena = f"Hujan Sedang ({precip:.0f}mm)"
            else:
                fenomena = f"Angin Sedang ({wind:.0f}km/h)"
        else:
            level, label = 1, "Normal"
            fenomena = "Cuaca normal"

        return level, label, fenomena

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# -- Standalone CLI usage -----------------------------------------------------

if __name__ == "__main__":
    """Quick test: fetch forecast for all MVP cities."""

    logger.info("BMKG Forecast Extractor - Test Run")
    logger.info("=" * 50)

    with BmkgExtractor() as extractor:
        results = extractor.extract_all_cities()

        for city, forecasts in results.items():
            logger.info(f"\n{city}:")
            for f in forecasts:
                level, lbl, fenomena = extractor.derive_siaga_level(
                    f["total_precip"], f["max_wind"]
                )
                logger.info(
                    f"  {f['tanggal']}: precip={f['total_precip']}mm, "
                    f"wind={f['max_wind']}km/h, "
                    f"temp={f['max_temp']}C -> {lbl} ({fenomena})"
                )

    logger.success("Done")
