"""Abstract base class for weather data sources (Phase 2 Module 1)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Optional


@dataclass(slots=True)
class WeatherRecord:
    """A single weather observation from a source (not an ORM object).

    Used as an intermediate representation between API and database.
    Normalized to canonical formats before persisting.
    """

    trade_date: date
    apmc: str                      # APMC code (canonical: pune, nashik, etc.)
    district: str
    metric: str                    # temperature, rainfall, humidity, wind_speed, pressure
    value: Decimal                 # measurement value
    unit: str                      # °C, mm, %, km/h, hPa
    min_value: Optional[Decimal] = None
    max_value: Optional[Decimal] = None
    forecast_days_ahead: int = 0   # 0=today, 1-7=forecast
    condition: Optional[str] = None
    advisory: Optional[str] = None
    source: str = "unknown"
    raw: Optional[dict[str, Any]] = None

    def dedupe_key(self) -> tuple:
        """Return tuple that matches database unique constraint.

        Used to identify duplicates from the same source.
        """
        return (self.trade_date, self.apmc, self.metric, self.forecast_days_ahead, self.source)


class WeatherSource(ABC):
    """Abstract base class for weather data sources.

    Each source (IMD, OpenWeather, etc.) implements fetch() to return
    a list of WeatherRecord dataclasses. The orchestrator handles:
    - Normalizing field names
    - Deduplicating records
    - Picking winners per (date, apmc, metric)
    - Persisting to PostgreSQL
    """

    name: str = "unknown"

    @abstractmethod
    async def fetch(self, trade_date: date) -> list[WeatherRecord]:
        """Fetch weather observations for a given date.

        Args:
            trade_date: Date to fetch weather for (YYYY-MM-DD)

        Returns:
            List of WeatherRecord dataclasses

        Raises:
            Exception on API failure; caller handles retry/fallback
        """
        pass
