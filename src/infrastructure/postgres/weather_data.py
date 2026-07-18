"""
Data layer: weather data from Supabase PostgreSQL app.cuaca_harian (Open-Meteo).

Provides weather context for RCA engine by querying historical
weather data from Supabase PostgreSQL and detecting extreme conditions.

Architecture:
    BigQuery -> raw.cuaca_harian (Bronze, ETL only)
    Supabase -> app.cuaca_harian (Gold, synced from BigQuery, served to UI)

Integration:
    commodity_data.py calls get_weather_for_rca() to populate
    CuacaInfo in CommodityData, which RCA engine then evaluates.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from config.settings import (
    WEATHER_DROUGHT_DAYS,
    WEATHER_LOOKBACK_DAYS,
    WEATHER_PRECIP_EXTREME_MM,
    WEATHER_TEMP_EXTREME_C,
    WEATHER_WIND_EXTREME_KMH,
)
from src.infrastructure.postgres.database import db_cursor
from src.domain.schemas.models import CuacaInfo


def get_weather_for_rca(
    provinsi_id: int,
    tanggal: Optional[date] = None,
    lookback_days: Optional[int] = None,
) -> CuacaInfo:
    """
    Check weather conditions for a province over the past N days.

    Checks (in order of severity):
    1. Heavy rain (>100mm/day) -> flood risk, crop damage
    2. Extreme heat (>38 C) -> crop stress
    3. Damaging winds (>60 km/h) -> crop/logistics damage
    4. Drought (>14 consecutive dry days) -> water stress

    Args:
        provinsi_id: PIHPS province ID (11=Banten, 12=Jabar, etc.)
        tanggal: Reference date (default: today)
        lookback_days: How many days back to check (default from config)

    Returns:
        CuacaInfo with ekstrem flag and description for RCA engine.
    """
    target = tanggal or date.today()
    days_back = lookback_days or WEATHER_LOOKBACK_DAYS
    start = target - timedelta(days=days_back)

    with db_cursor() as cur:
        cur.execute("""
            SELECT
                tanggal,
                lokasi_label,
                MAX(precipitation_sum) AS precipitation_sum,
                MAX(temperature_max) AS temperature_max,
                MAX(wind_speed_max) AS wind_speed_max
            FROM app.cuaca_harian
            WHERE provinsi_id = %s
              AND tanggal BETWEEN %s AND %s
            GROUP BY tanggal, lokasi_label
            ORDER BY tanggal DESC
        """, (provinsi_id, start, target))
        rows = cur.fetchall()

    if not rows:
        return CuacaInfo(
            ekstrem=False,
            desc="Data cuaca tidak tersedia",
            daerah="",
            detail=f"Tidak ada data cuaca untuk provinsi {provinsi_id}",
        )

    # Check 1: Heavy rain (>100mm/day)
    for row in rows:
        precip = row["precipitation_sum"] or 0
        if precip > WEATHER_PRECIP_EXTREME_MM:
            return CuacaInfo(
                ekstrem=True,
                desc=f"Hujan lebat ({precip:.0f}mm) pada {row['tanggal']}",
                daerah=row["lokasi_label"],
                detail=(
                    f"Curah hujan {precip:.0f}mm/hari di {row['lokasi_label']} "
                    f"melebihi ambang batas {WEATHER_PRECIP_EXTREME_MM:.0f}mm -- "
                    f"risiko banjir dan gangguan distribusi"
                ),
            )

    # Check 2: Extreme heat (>38 C)
    for row in rows:
        temp = row["temperature_max"] or 0
        if temp > WEATHER_TEMP_EXTREME_C:
            return CuacaInfo(
                ekstrem=True,
                desc=f"Suhu ekstrem ({temp:.1f}C) pada {row['tanggal']}",
                daerah=row["lokasi_label"],
                detail=(
                    f"Suhu maksimum {temp:.1f}C di {row['lokasi_label']} "
                    f"melebihi {WEATHER_TEMP_EXTREME_C:.0f}C -- "
                    f"risiko heat stress pada tanaman"
                ),
            )

    # Check 3: Damaging winds (>60 km/h)
    for row in rows:
        wind = row["wind_speed_max"] or 0
        if wind > WEATHER_WIND_EXTREME_KMH:
            return CuacaInfo(
                ekstrem=True,
                desc=f"Angin kencang ({wind:.0f} km/h) pada {row['tanggal']}",
                daerah=row["lokasi_label"],
                detail=(
                    f"Kecepatan angin {wind:.0f} km/h di {row['lokasi_label']} "
                    f"melebihi {WEATHER_WIND_EXTREME_KMH:.0f} km/h -- "
                    f"risiko kerusakan tanaman dan gangguan logistik"
                ),
            )

    # Check 4: Drought (consecutive dry days)
    dry_count = 0
    for row in rows:
        precip = row["precipitation_sum"] or 0
        if precip < 1.0:
            dry_count += 1
        else:
            break  # streak broken (rows are DESC by date)

    if dry_count >= WEATHER_DROUGHT_DAYS:
        return CuacaInfo(
            ekstrem=True,
            desc=f"Kekeringan ({dry_count} hari tanpa hujan signifikan)",
            daerah=rows[0]["lokasi_label"],
            detail=(
                f"Lebih dari {WEATHER_DROUGHT_DAYS} hari berturut-turut "
                f"curah hujan <1mm di {rows[0]['lokasi_label']} -- "
                f"risiko kekurangan air untuk irigasi"
            ),
        )

    # No extreme weather detected
    latest = rows[0]
    precip = latest["precipitation_sum"] or 0
    temp = latest["temperature_max"] or 0
    return CuacaInfo(
        ekstrem=False,
        desc=f"Normal (hujan {precip:.0f}mm, suhu {temp:.0f}C)",
        daerah=latest["lokasi_label"],
        detail=(
            f"Tidak ada cuaca ekstrem terdeteksi dalam {days_back} hari terakhir "
            f"di wilayah {latest['lokasi_label']}"
        ),
    )


def get_weather_summary(
    provinsi_id: int,
    tanggal: Optional[date] = None,
    n_days: int = 7,
) -> list[dict]:
    """
    Get daily weather summary for dashboard display.

    Returns list of dicts with daily weather data for the past N days.
    """
    target = tanggal or date.today()
    start = target - timedelta(days=n_days)

    with db_cursor() as cur:
        cur.execute("""
            SELECT
                tanggal,
                lokasi_label,
                precipitation_sum,
                rain_sum,
                temperature_max,
                temperature_min,
                wind_speed_max
            FROM app.cuaca_harian
            WHERE provinsi_id = %s
              AND tanggal BETWEEN %s AND %s
            ORDER BY tanggal DESC
        """, (provinsi_id, start, target))
        rows = cur.fetchall()

    return [dict(row) for row in rows]
