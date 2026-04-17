"""Data models for weather queries and results (Phase 2 Module 1)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass(slots=True)
class WeatherQuery:
    """Query parameters for weather data."""

    metric: str                    # temperature, rainfall, humidity, wind_speed, pressure
    apmc: Optional[str] = None     # APMC code (if None, use farmer's registered APMC)
    days_ahead: int = 0            # 0=today, 1-7=forecast


@dataclass(slots=True)
class WeatherRecord:
    """A single weather observation record."""

    date: date
    apmc: str
    metric: str
    value: Decimal
    unit: str
    min_value: Optional[Decimal] = None
    max_value: Optional[Decimal] = None
    condition: Optional[str] = None
    source: str = "unknown"
    raw_payload: Optional[dict] = None

    @property
    def value_str(self) -> str:
        """Format value for display."""
        return f"{float(self.value):.1f}"

    @property
    def range_str(self) -> str:
        """Format min/max range for display (if available)."""
        if self.min_value and self.max_value:
            return f"({float(self.min_value):.0f}–{float(self.max_value):.0f})"
        return ""


@dataclass(slots=True)
class WeatherQueryResult:
    """Result of a weather query."""

    found: bool
    query: WeatherQuery
    record: Optional[WeatherRecord] = None
    forecast: Optional[list[WeatherRecord]] = None
    stale: bool = False
    source: str = "unknown"
    error: Optional[str] = None
