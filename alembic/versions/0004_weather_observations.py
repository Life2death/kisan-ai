"""Create weather_observations table for Phase 2 weather integration

Adds new table to store daily weather observations and forecasts:
- weather_observations: stores temperature, rainfall, humidity, wind, pressure
- Supports multi-source ingestion (IMD, OpenWeather)
- Includes forecast data (next 7 days)
- Soft-delete and staleness tracking

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create weather_observations table with indexes and constraints."""

    # Create weather_observations table
    op.create_table(
        "weather_observations",
        sa.Column("id", sa.Integer(), nullable=False, comment="Primary key"),
        sa.Column("date", sa.Date(), nullable=False, comment="Date of observation (YYYY-MM-DD)"),
        sa.Column("apmc", sa.String(100), nullable=False, comment="APMC code (canonical: pune, nashik, etc.)"),
        sa.Column("district", sa.String(50), nullable=False, comment="District name"),
        sa.Column("metric", sa.String(50), nullable=False, comment="Weather metric: temperature, rainfall, humidity, wind_speed, pressure"),
        sa.Column("value", sa.Numeric(10, 2), nullable=False, comment="Metric value (e.g., 28.5 for temperature)"),
        sa.Column("unit", sa.String(20), nullable=False, comment="Unit of measurement: °C, mm, %, km/h, hPa"),
        sa.Column("min_value", sa.Numeric(10, 2), nullable=True, comment="Minimum value (e.g., low temperature)"),
        sa.Column("max_value", sa.Numeric(10, 2), nullable=True, comment="Maximum value (e.g., high temperature)"),
        sa.Column("forecast_days_ahead", sa.Integer(), nullable=False, default=0, comment="0=today, 1-7=forecast days"),
        sa.Column("condition", sa.String(50), nullable=True, comment="Overall condition: Sunny, Cloudy, Rainy, etc."),
        sa.Column("advisory", sa.String(500), nullable=True, comment="Crop-specific advisory (e.g., pest risk warning)"),
        sa.Column("source", sa.String(50), nullable=False, comment="Data source: imd (India Met Dept), openweather"),
        sa.Column(
            "raw_payload",
            sa.dialects.postgresql.JSONB(none_as_null=True),
            nullable=True,
            comment="Original API response (for auditability)",
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="Timestamp when data was fetched",
        ),
        sa.Column("is_stale", sa.Boolean(), nullable=False, default=False, comment="True if >6 hours old"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "date",
            "apmc",
            "metric",
            "forecast_days_ahead",
            "source",
            name="uq_weather_obs_dedupe",
            comment="Prevent duplicate observations from same source",
        ),
        comment="Daily weather observations from multiple sources (IMD, OpenWeather)",
    )

    # Create indexes for efficient queries
    op.create_index(
        "idx_weather_lookup",
        "weather_observations",
        ["date", "apmc", "forecast_days_ahead"],
        comment="Fast lookup by date + location + forecast",
    )

    op.create_index(
        "idx_weather_metric",
        "weather_observations",
        ["metric", "date"],
        comment="Fast lookup by metric type + date",
    )

    op.create_index(
        "idx_weather_district",
        "weather_observations",
        ["district", "date"],
        comment="Fast lookup by district + date",
    )

    op.create_index(
        "idx_weather_source",
        "weather_observations",
        ["source", "fetched_at"],
        comment="Track data freshness per source",
    )


def downgrade() -> None:
    """Drop weather_observations table and indexes."""

    op.drop_index("idx_weather_source", table_name="weather_observations")
    op.drop_index("idx_weather_district", table_name="weather_observations")
    op.drop_index("idx_weather_metric", table_name="weather_observations")
    op.drop_index("idx_weather_lookup", table_name="weather_observations")

    op.drop_table("weather_observations")
