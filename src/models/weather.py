"""ORM model for weather observations (Phase 2 Module 1)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import String, Integer, Date, DateTime, Numeric, Boolean, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class WeatherObservation(Base):
    """A single daily weather observation from one source.

    A row represents: on `date`, at `apmc` (canonical code), the weather `metric`
    (temperature, rainfall, humidity, wind, pressure) was reported by `source` with
    value and unit. Supports both observations (today) and forecasts (next 1-7 days).

    Multiple sources may report the same cell; queries pick one per (date, apmc, metric)
    based on source preference rules (IMD > OpenWeather).
    """

    __tablename__ = "weather_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    apmc: Mapped[str] = mapped_column(String(100), nullable=False)           # canonical: pune, nashik, etc.
    district: Mapped[str] = mapped_column(String(50), nullable=False)
    metric: Mapped[str] = mapped_column(String(50), nullable=False)          # temperature, rainfall, humidity, wind_speed, pressure
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)   # actual measurement (25.5, 40.0, 80, etc.)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)            # °C, mm, %, km/h, hPa
    min_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))     # e.g., low temperature
    max_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))     # e.g., high temperature
    forecast_days_ahead: Mapped[int] = mapped_column(Integer, default=0)     # 0=today, 1-7=forecast
    condition: Mapped[Optional[str]] = mapped_column(String(50))             # Sunny, Cloudy, Rainy, etc.
    advisory: Mapped[Optional[str]] = mapped_column(String(500))             # Crop-specific advisory (e.g., pest warning)
    source: Mapped[str] = mapped_column(String(50), nullable=False)          # imd | openweather
    raw_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)     # Original API response
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)           # True if >6 hours old

    __table_args__ = (
        UniqueConstraint("date", "apmc", "metric", "forecast_days_ahead", "source", name="uq_weather_obs_dedupe"),
        Index("idx_weather_lookup", "date", "apmc", "forecast_days_ahead"),
        Index("idx_weather_metric", "metric", "date"),
        Index("idx_weather_district", "district", "date"),
        Index("idx_weather_source", "source", "fetched_at"),
    )
