"""
Tests for weather data layer (src/data/weather_data.py).

Uses mock bq_query to avoid needing real BigQuery connection.
Tests all extreme weather detection paths:
  - Heavy rain (>100mm)
  - Extreme heat (>38 C)
  - Damaging winds (>60 km/h)
  - Drought (>14 dry days)
  - Normal weather
  - No data fallback
"""
from datetime import date
from unittest.mock import patch

import pytest

from src.data.weather_data import get_weather_for_rca


def _make_weather_rows(overrides: list[dict]) -> list[dict]:
    """Helper: create mock weather rows (newest first, like ORDER BY DESC)."""
    base = {
        "tanggal": date(2026, 5, 1),
        "lokasi_label": "Bandung",
        "precipitation_sum": 5.0,
        "temperature_max": 30.0,
        "wind_speed_max": 15.0,
    }
    return [{**base, **row} for row in overrides]


@patch("src.data.weather_data.bq_query")
def test_extreme_heavy_rain(mock_bq):
    """Heavy rain >100mm should trigger extreme weather."""
    mock_bq.return_value = _make_weather_rows([
        {"precipitation_sum": 120.0, "tanggal": date(2026, 5, 5)},
        {"precipitation_sum": 10.0, "tanggal": date(2026, 5, 4)},
    ])

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 5))

    assert result.ekstrem is True
    assert "120" in result.desc  # should mention the precipitation value
    assert "Bandung" in result.daerah


@patch("src.data.weather_data.bq_query")
def test_extreme_temperature(mock_bq):
    """Temperature >38 C should trigger extreme weather."""
    mock_bq.return_value = _make_weather_rows([
        {"temperature_max": 39.5, "precipitation_sum": 0},
    ])

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 5))

    assert result.ekstrem is True
    assert "39.5" in result.desc
    assert "Bandung" in result.daerah


@patch("src.data.weather_data.bq_query")
def test_extreme_wind(mock_bq):
    """Wind >60 km/h should trigger extreme weather."""
    mock_bq.return_value = _make_weather_rows([
        {"wind_speed_max": 75.0, "precipitation_sum": 0, "temperature_max": 28.0},
    ])

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 5))

    assert result.ekstrem is True
    assert "75" in result.desc
    assert "angin" in result.desc.lower() or "Angin" in result.desc


@patch("src.data.weather_data.bq_query")
def test_drought_detection(mock_bq):
    """14+ consecutive dry days should trigger drought."""
    # 15 days with <1mm precipitation (newest first)
    mock_bq.return_value = _make_weather_rows([
        {"precipitation_sum": 0.2, "tanggal": date(2026, 5, i),
         "temperature_max": 30.0, "wind_speed_max": 10.0}
        for i in range(15, 0, -1)
    ])

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 15), lookback_days=20)

    assert result.ekstrem is True
    assert "kekeringan" in result.desc.lower() or "Kekeringan" in result.desc


@patch("src.data.weather_data.bq_query")
def test_normal_weather(mock_bq):
    """Normal weather (all within bounds) should not trigger."""
    mock_bq.return_value = _make_weather_rows([
        {"precipitation_sum": 10.0, "temperature_max": 30.0, "wind_speed_max": 15.0},
        {"precipitation_sum": 5.0, "temperature_max": 28.0, "wind_speed_max": 10.0},
    ])

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 5))

    assert result.ekstrem is False
    assert "Normal" in result.desc or "normal" in result.desc.lower()


@patch("src.data.weather_data.bq_query")
def test_no_data_fallback(mock_bq):
    """No weather data should return non-extreme with appropriate message."""
    mock_bq.return_value = []

    result = get_weather_for_rca(99, tanggal=date(2026, 5, 5))

    assert result.ekstrem is False
    assert "tidak tersedia" in result.desc.lower()


@patch("src.data.weather_data.bq_query")
def test_rain_priority_over_heat(mock_bq):
    """Heavy rain should be detected before heat (check order matters)."""
    mock_bq.return_value = _make_weather_rows([
        {"precipitation_sum": 150.0, "temperature_max": 40.0},  # both extreme
    ])

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 5))

    assert result.ekstrem is True
    # Rain should be detected first (higher priority)
    assert "150" in result.desc or "hujan" in result.desc.lower()


@patch("src.data.weather_data.bq_query")
def test_drought_with_aggregated_rows(mock_bq):
    """Drought detection works correctly when SQL aggregates multi-location data.

    The SQL query now uses GROUP BY tanggal with MAX(), so each row
    represents one date even if there are multiple weather stations.
    This test verifies the drought counter works with aggregated data.
    """
    # Simulate aggregated rows: one row per date, 15 dry days
    mock_bq.return_value = _make_weather_rows([
        {"precipitation_sum": 0.5, "tanggal": date(2026, 5, i),
         "temperature_max": 32.0, "wind_speed_max": 12.0}
        for i in range(15, 0, -1)
    ])

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 15), lookback_days=20)

    assert result.ekstrem is True
    assert "kekeringan" in result.desc.lower() or "Kekeringan" in result.desc
