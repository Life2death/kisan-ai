"""Normalize weather metric names to canonical forms (Phase 2 Module 1)."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Map raw metric names from APIs → canonical metric slugs
_METRIC_ALIASES = {
    # Temperature variants
    "temperature": "temperature",
    "temp": "temperature",
    "temperature_max": "temperature",
    "temperature_min": "temperature",
    "temp_max": "temperature",
    "temp_min": "temperature",
    "max_temp": "temperature",
    "min_temp": "temperature",
    "तापमान": "temperature",
    "तापमान_उच्च": "temperature",
    "तापमान_न्यून": "temperature",
    # Rainfall variants
    "rainfall": "rainfall",
    "rain": "rainfall",
    "precipitation": "rainfall",
    "1h": "rainfall",
    "rain_1h": "rainfall",
    "पाऊस": "rainfall",
    # Humidity variants
    "humidity": "humidity",
    "relative_humidity": "humidity",
    "humidity_max": "humidity",
    "humidity_min": "humidity",
    "ओलावा": "humidity",
    # Wind speed variants
    "wind_speed": "wind_speed",
    "wind": "wind_speed",
    "speed": "wind_speed",
    "wind_spd": "wind_speed",
    "वारा_वेग": "wind_speed",
    "वारा": "wind_speed",
    # Wind direction
    "wind_direction": "wind_direction",
    "wind_deg": "wind_direction",
    "wind_dir": "wind_direction",
    # Pressure variants
    "pressure": "pressure",
    "press": "pressure",
    "barometric_pressure": "pressure",
    # Cloud cover
    "clouds": "cloud_cover",
    "cloud_coverage": "cloud_cover",
    "cloudiness": "cloud_cover",
}

# Canonical metric list (target)
CANONICAL_METRICS = {
    "temperature",      # °C
    "rainfall",         # mm
    "humidity",         # %
    "wind_speed",       # km/h
    "wind_direction",   # degrees
    "pressure",         # hPa
    "cloud_cover",      # %
}

# APMC aliases (raw → canonical)
_APMC_ALIASES = {
    "pune": "pune",
    "पुणे": "pune",
    "Pune": "pune",
    "nashik": "nashik",
    "नाशिक": "nashik",
    "Nashik": "nashik",
    "ahilyanagar": "ahilyanagar",
    "अहमदनगर": "ahilyanagar",
    "Ahmednagar": "ahilyanagar",
    "navi_mumbai": "navi_mumbai",
    "navimumbai": "navi_mumbai",
    "नवी_मुंबई": "navi_mumbai",
    "Navi Mumbai": "navi_mumbai",
    "mumbai": "mumbai",
    "मुंबई": "mumbai",
    "Mumbai": "mumbai",
}


def normalize_metric(raw: str) -> Optional[str]:
    """Normalize raw metric name to canonical slug.

    Args:
        raw: Raw metric name from API (case-insensitive)

    Returns:
        Canonical metric slug or None if unrecognized
    """
    if not raw:
        return None

    # Case-insensitive lookup
    lower = raw.lower().strip()
    return _METRIC_ALIASES.get(lower)


def normalize_apmc(raw: str) -> Optional[str]:
    """Normalize raw APMC name to canonical slug.

    Args:
        raw: Raw APMC/district name from API

    Returns:
        Canonical APMC slug or None if unrecognized
    """
    if not raw:
        return None

    # Direct lookup (case-sensitive for Unicode support)
    if raw in _APMC_ALIASES:
        return _APMC_ALIASES[raw]

    # Case-insensitive fallback
    lower = raw.lower().strip()
    return _APMC_ALIASES.get(lower)


def normalize_unit(metric: str) -> str:
    """Return canonical unit for a metric.

    Args:
        metric: Canonical metric slug (e.g., "temperature")

    Returns:
        Unit string (e.g., "°C")
    """
    units = {
        "temperature": "°C",
        "rainfall": "mm",
        "humidity": "%",
        "wind_speed": "km/h",
        "wind_direction": "degrees",
        "pressure": "hPa",
        "cloud_cover": "%",
    }
    return units.get(metric, "unknown")
