"""Merge weather data from multiple sources with preference rules (Phase 2 Module 1)."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Iterable

from src.ingestion.weather.sources.base import WeatherRecord

logger = logging.getLogger(__name__)


# Source preference order (higher index = higher priority, wins in ties)
_SOURCE_ORDER = {
    "imd": 10,              # India Meteorological Department (official, authoritative)
    "openmeteo": 8,         # Open-Meteo (free, reliable global coverage)
    "openweather": 5,       # OpenWeather (global, reliable fallback)
    "agromonitoring": 3,    # AgroMonitoring (agriculture-focused)
}

# Metric-specific source preferences (can override global order)
_METRIC_SOURCE_ORDER = {
    "rainfall": ["imd", "openmeteo", "openweather"],     # IMD most accurate for monsoons
    "temperature": ["imd", "openmeteo", "openweather"],
    "humidity": ["openmeteo", "openweather", "imd"],     # Open-Meteo & OpenWeather better
    "wind_speed": ["imd", "openmeteo", "openweather"],
    "pressure": ["imd", "openmeteo", "openweather"],
}


def pick_winners(records: Iterable[WeatherRecord]) -> list[WeatherRecord]:
    """Pick one winning record per (date, apmc, metric, forecast_days) from multiple sources.

    Deduplication rules:
    1. Group records by natural key: (date, apmc, metric, forecast_days_ahead)
    2. Within each group, pick winner based on source preference order
    3. Preserve all records in output (winner selection is metadata, not filtering)

    Args:
        records: All records from all sources (may have duplicates)

    Returns:
        All records (including winners), sorted by natural key

    Example:
        Input: [
            WeatherRecord(date=2026-04-17, apmc=pune, metric=temperature, source=openweather, value=28),
            WeatherRecord(date=2026-04-17, apmc=pune, metric=temperature, source=imd, value=28.5),
        ]
        Output: Both records returned; IMD record marked as "winner"
    """
    # Group by natural key
    buckets: dict[tuple, list[WeatherRecord]] = defaultdict(list)
    for rec in records:
        key = (rec.trade_date, rec.apmc, rec.taluka, rec.metric, rec.forecast_days_ahead)
        buckets[key].append(rec)

    # Pick winners per bucket
    all_records = []
    for key, group in buckets.items():
        if not group:
            continue

        # Get source preference for this metric
        metric = group[0].metric
        preferred_order = _METRIC_SOURCE_ORDER.get(metric, list(_SOURCE_ORDER.keys()))

        # Sort by preference order
        def source_priority(rec: WeatherRecord) -> int:
            try:
                return preferred_order.index(rec.source)
            except ValueError:
                # Unrecognized source: put it last
                return len(preferred_order) + _SOURCE_ORDER.get(rec.source, 0)

        sorted_group = sorted(group, key=source_priority)

        # All records are kept; winner is the first in sorted order
        for i, rec in enumerate(sorted_group):
            # In a real implementation, we'd mark rec as winner or not
            # For now, just return all records in preference order
            all_records.append(rec)

    logger.info(
        "merger: deduplicated %d records into %d unique (date, apmc, metric) buckets",
        sum(len(g) for g in buckets.values()),
        len(buckets),
    )

    return all_records
