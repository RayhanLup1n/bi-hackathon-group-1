"""
Tests for weather data layer (src/data/weather_data.py).

Uses mock db_cursor to avoid needing real Supabase connection.
Tests all extreme weather detection paths:
  - Heavy rain (>100mm)
  - Extreme heat (>38 C)
  - Damaging winds (>60 km/h)
  - Drought (>14 dry days)
  - Normal weather
  - No data fallback
"""
from datetime import date
from unittest.mock import patch, MagicMock
from contextlib import contextmanager

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


def _mock_db_cursor(rows: list[dict]):
    """Create a mock db_cursor context manager that returns given rows."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    return fake_cursor


@patch("src.data.weather_data.db_cursor")
def test_extreme_heavy_rain(mock_db):
    """Heavy rain >100mm should trigger extreme weather."""
    rows = _make_weather_rows([
        {"precipitation_sum": 120.0, "tanggal": date(2026, 5, 5)},
        {"precipitation_sum": 10.0, "tanggal": date(2026, 5, 4)},
    ])
    mock_db.side_effect = _mock_db_cursor(rows)

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 5))

    assert result.ekstrem is True
    assert "120" in result.desc  # should mention the precipitation value
    assert "Bandung" in result.daerah


@patch("src.data.weather_data.db_cursor")
def test_extreme_temperature(mock_db):
    """Temperature >38 C should trigger extreme weather."""
    rows = _make_weather_rows([
        {"temperature_max": 39.5, "precipitation_sum": 0},
    ])
    mock_db.side_effect = _mock_db_cursor(rows)

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 5))

    assert result.ekstrem is True
    assert "39.5" in result.desc
    assert "Bandung" in result.daerah


@patch("src.data.weather_data.db_cursor")
def test_extreme_wind(mock_db):
    """Wind >60 km/h should trigger extreme weather."""
    rows = _make_weather_rows([
        {"wind_speed_max": 75.0, "precipitation_sum": 0, "temperature_max": 28.0},
    ])
    mock_db.side_effect = _mock_db_cursor(rows)

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 5))

    assert result.ekstrem is True
    assert "75" in result.desc
    assert "angin" in result.desc.lower() or "Angin" in result.desc


@patch("src.data.weather_data.db_cursor")
def test_drought_detection(mock_db):
    """14+ consecutive dry days should trigger drought."""
    # 15 days with <1mm precipitation (newest first)
    rows = _make_weather_rows([
        {"precipitation_sum": 0.2, "tanggal": date(2026, 5, i),
         "temperature_max": 30.0, "wind_speed_max": 10.0}
        for i in range(15, 0, -1)
    ])
    mock_db.side_effect = _mock_db_cursor(rows)

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 15), lookback_days=20)

    assert result.ekstrem is True
    assert "kekeringan" in result.desc.lower() or "Kekeringan" in result.desc


@patch("src.data.weather_data.db_cursor")
def test_normal_weather(mock_db):
    """Normal weather (all within bounds) should not trigger."""
    rows = _make_weather_rows([
        {"precipitation_sum": 10.0, "temperature_max": 30.0, "wind_speed_max": 15.0},
        {"precipitation_sum": 5.0, "temperature_max": 28.0, "wind_speed_max": 10.0},
    ])
    mock_db.side_effect = _mock_db_cursor(rows)

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 5))

    assert result.ekstrem is False
    assert "Normal" in result.desc or "normal" in result.desc.lower()


@patch("src.data.weather_data.db_cursor")
def test_no_data_fallback(mock_db):
    """No weather data should return non-extreme with appropriate message."""
    mock_db.side_effect = _mock_db_cursor([])

    result = get_weather_for_rca(99, tanggal=date(2026, 5, 5))

    assert result.ekstrem is False
    assert "tidak tersedia" in result.desc.lower()


@patch("src.data.weather_data.db_cursor")
def test_rain_priority_over_heat(mock_db):
    """Heavy rain should be detected before heat (check order matters)."""
    rows = _make_weather_rows([
        {"precipitation_sum": 150.0, "temperature_max": 40.0},  # both extreme
    ])
    mock_db.side_effect = _mock_db_cursor(rows)

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 5))

    assert result.ekstrem is True
    # Rain should be detected first (higher priority)
    assert "150" in result.desc or "hujan" in result.desc.lower()


@patch("src.data.weather_data.db_cursor")
def test_drought_with_aggregated_rows(mock_db):
    """Drought detection works correctly with aggregated data.

    The SQL query groups by tanggal with MAX(), so each row
    represents one date even if there are multiple weather stations.
    This test verifies the drought counter works with aggregated data.
    """
    # Simulate aggregated rows: one row per date, 15 dry days
    rows = _make_weather_rows([
        {"precipitation_sum": 0.5, "tanggal": date(2026, 5, i),
         "temperature_max": 32.0, "wind_speed_max": 12.0}
        for i in range(15, 0, -1)
    ])
    mock_db.side_effect = _mock_db_cursor(rows)

    result = get_weather_for_rca(12, tanggal=date(2026, 5, 15), lookback_days=20)

    assert result.ekstrem is True
    assert "kekeringan" in result.desc.lower() or "Kekeringan" in result.desc
