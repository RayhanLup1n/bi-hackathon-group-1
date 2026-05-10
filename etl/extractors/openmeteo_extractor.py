"""
Extractor for Open-Meteo Historical Weather API.

Free, no API key required. Data from 1940-present for Indonesia.
Rate limit: generous (~600 req/min), but we add small delay to be polite.

Usage:
    extractor = OpenMeteoExtractor()
    df = extractor.extract_daily(
        latitude=-6.92, longitude=107.60,
        start_date=date(2020, 1, 1),
        end_date=date(2026, 5, 9),
    )
"""
from __future__ import annotations

import time
from datetime import date
from typing import Optional

import httpx
import pandas as pd
from loguru import logger


API_URL = "https://archive-api.open-meteo.com/v1/archive"

# Daily weather variables relevant for agricultural commodity price analysis
DAILY_VARIABLES = [
    "precipitation_sum",          # total precipitation (mm)
    "rain_sum",                   # rain only, excluding snow (mm)
    "temperature_2m_max",         # max temperature at 2m height (°C)
    "temperature_2m_min",         # min temperature at 2m height (°C)
    "wind_speed_10m_max",         # max wind speed at 10m height (km/h)
    "et0_fao_evapotranspiration", # reference evapotranspiration (mm) — drought indicator
    "sunshine_duration",          # sunshine duration (seconds)
]


class OpenMeteoExtractor:
    """
    Fetch historical daily weather data from Open-Meteo API.

    Open-Meteo supports wide date ranges per request (unlike PIHPS),
    so extracting 6 years of data for one location takes a single API call.
    """

    def __init__(self, request_delay: float = 0.5):
        self._client = httpx.Client(timeout=60)
        self._delay = request_delay

    def extract_daily(
        self,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Fetch daily weather data for one location.

        Args:
            latitude: Location latitude (e.g., -6.92 for Bandung)
            longitude: Location longitude (e.g., 107.60 for Bandung)
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            DataFrame with columns: tanggal, precipitation_sum, rain_sum,
            temperature_max, temperature_min, wind_speed_max,
            et0_evapotranspiration, sunshine_duration, latitude, longitude
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily": ",".join(DAILY_VARIABLES),
            "timezone": "Asia/Jakarta",
        }

        resp = self._client.get(API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        daily = data.get("daily", {})
        if not daily or "time" not in daily:
            logger.warning(f"No daily data returned for ({latitude}, {longitude})")
            return pd.DataFrame()

        df = pd.DataFrame(daily)
        # Rename API column names to cleaner DB column names
        df.rename(columns={
            "time": "tanggal",
            "temperature_2m_max": "temperature_max",
            "temperature_2m_min": "temperature_min",
            "wind_speed_10m_max": "wind_speed_max",
            "et0_fao_evapotranspiration": "et0_evapotranspiration",
        }, inplace=True)
        df["tanggal"] = pd.to_datetime(df["tanggal"]).dt.date
        df["latitude"] = latitude
        df["longitude"] = longitude

        return df

    def extract_all_locations(
        self,
        start_date: date,
        end_date: date,
        locations: dict[int, list[tuple[float, float, str]]],
    ) -> pd.DataFrame:
        """Fetch weather data for multiple locations.

        Args:
            start_date: Start date
            end_date: End date
            locations: Dict of province_id -> [(lat, lon, label), ...]

        Returns:
            Combined DataFrame with all locations, including
            provinsi_id and lokasi_label columns.
        """
        all_dfs: list[pd.DataFrame] = []

        for prov_id, locs in locations.items():
            for lat, lon, label in locs:
                logger.info(
                    f"  Fetching weather: {label} ({lat}, {lon}) "
                    f"[{start_date} → {end_date}]"
                )
                try:
                    df = self.extract_daily(lat, lon, start_date, end_date)
                    if not df.empty:
                        df["provinsi_id"] = prov_id
                        df["lokasi_label"] = label
                        all_dfs.append(df)
                        logger.success(f"    ✓ {len(df)} rows fetched for {label}")
                except Exception as e:
                    logger.error(f"    ✗ Failed for {label}: {e}")

                # Polite delay between requests
                time.sleep(self._delay)

        if not all_dfs:
            logger.warning("No weather data fetched from any location!")
            return pd.DataFrame()

        return pd.concat(all_dfs, ignore_index=True)

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
