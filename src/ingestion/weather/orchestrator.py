"""Orchestrate weather data ingestion from multiple sources (Phase 2 Module 1)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence, Optional

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.ingestion.weather.sources.base import WeatherRecord, WeatherSource
from src.ingestion.weather.sources.imd_api import IMDWeatherSource
from src.ingestion.weather.sources.openweather_api import OpenWeatherSource
from src.ingestion.weather.normalizer import normalize_metric, normalize_apmc, normalize_unit
from src.ingestion.weather.merger import pick_winners
from src.models.weather import WeatherObservation

logger = logging.getLogger(__name__)


@dataclass
class IngestionSummary:
    """Summary of one ingestion run."""

    trade_date: date
    total_fetched: int = 0                 # Total records from all sources
    total_normalized: int = 0              # After normalization
    total_merged: int = 0                  # After deduplication
    total_inserted: int = 0                # Successfully persisted to DB
    errors: dict[str, str] = field(default_factory=dict)  # source → error message
    source_counts: dict[str, int] = field(default_factory=dict)  # source → record count

    @property
    def healthy(self) -> bool:
        """Check if ingestion succeeded (at least 1 source healthy)."""
        return self.total_fetched > 0 and len(self.errors) < 2


async def run_ingestion(
    trade_date: date,
    session: AsyncSession,
    sources: Sequence[WeatherSource] | None = None,
) -> IngestionSummary:
    """Orchestrate weather data ingestion from multiple sources.

    Flow:
    1. Parallel fetch from all sources
    2. Normalize field names
    3. Deduplicate (merge)
    4. Upsert to PostgreSQL
    5. Return summary

    Args:
        trade_date: Date to ingest weather for
        session: AsyncSession for database operations
        sources: List of WeatherSource instances (default: IMD + OpenWeather)

    Returns:
        IngestionSummary with counts and errors
    """
    if sources is None:
        sources = _default_sources()

    logger.info("orchestrator: starting ingestion for %s with %d sources", trade_date, len(sources))

    summary = IngestionSummary(trade_date=trade_date)

    # Parallel fetch from all sources
    fetch_tasks = [_fetch_with_guard(source, trade_date) for source in sources]
    fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=False)

    all_records = []
    for source_name, records, error in fetch_results:
        if error:
            summary.errors[source_name] = error
            logger.warning("orchestrator: %s failed: %s", source_name, error)
        else:
            summary.source_counts[source_name] = len(records)
            summary.total_fetched += len(records)
            all_records.extend(records)

    logger.info(
        "orchestrator: fetched %d total records from %d sources",
        summary.total_fetched,
        len(summary.source_counts),
    )

    # Normalize records
    normalized_records = []
    for rec in all_records:
        norm_metric = normalize_metric(rec.metric)
        norm_apmc = normalize_apmc(rec.apmc)

        if not norm_metric or not norm_apmc:
            logger.warning(
                "orchestrator: skipping record with unrecognized metric=%s or apmc=%s",
                rec.metric,
                rec.apmc,
            )
            continue

        # Update record with normalized values
        rec.metric = norm_metric
        rec.apmc = norm_apmc
        rec.unit = normalize_unit(norm_metric)
        normalized_records.append(rec)

    summary.total_normalized = len(normalized_records)
    logger.info("orchestrator: normalized %d records", summary.total_normalized)

    # Merge (deduplicate)
    merged_records = pick_winners(normalized_records)
    summary.total_merged = len(merged_records)
    logger.info("orchestrator: merged into %d records", summary.total_merged)

    # Upsert to PostgreSQL
    inserted_count = await _upsert_records(session, merged_records)
    summary.total_inserted = inserted_count
    logger.info("orchestrator: inserted %d records to PostgreSQL", inserted_count)

    logger.info(
        "orchestrator: complete for %s — fetched=%d, normalized=%d, merged=%d, inserted=%d, errors=%d",
        trade_date,
        summary.total_fetched,
        summary.total_normalized,
        summary.total_merged,
        summary.total_inserted,
        len(summary.errors),
    )

    return summary


async def _fetch_with_guard(
    source: WeatherSource, trade_date: date
) -> tuple[str, list[WeatherRecord], Optional[str]]:
    """Fetch from a source with exception handling.

    Returns:
        Tuple of (source_name, records, error_message)
        error_message is None on success
    """
    try:
        records = await source.fetch(trade_date)
        return source.name, records, None
    except Exception as exc:
        logger.exception("orchestrator: fetch failed from %s", source.name)
        return source.name, [], f"{type(exc).__name__}: {str(exc)}"


async def _upsert_records(session: AsyncSession, records: Sequence[WeatherRecord]) -> int:
    """Upsert records to PostgreSQL.

    Uses ON CONFLICT to handle duplicate (date, apmc, metric, forecast_days_ahead, source).
    Idempotent: safe to run multiple times.

    Args:
        session: AsyncSession for database operations
        records: Normalized, merged WeatherRecord instances

    Returns:
        Number of rows inserted/updated
    """
    if not records:
        return 0

    # Convert WeatherRecord dataclasses to ORM objects
    orm_records = []
    for rec in records:
        orm_obj = WeatherObservation(
            date=rec.trade_date,
            apmc=rec.apmc,
            district=rec.district,
            metric=rec.metric,
            value=rec.value,
            unit=rec.unit,
            min_value=rec.min_value,
            max_value=rec.max_value,
            forecast_days_ahead=rec.forecast_days_ahead,
            condition=rec.condition,
            advisory=rec.advisory,
            source=rec.source,
            raw_payload=rec.raw,
        )
        orm_records.append(orm_obj)

    # PostgreSQL INSERT ... ON CONFLICT ... DO UPDATE
    # (upsert: insert new, update existing on conflict)
    stmt = pg_insert(WeatherObservation).values(
        [
            {
                "date": rec.date,
                "apmc": rec.apmc,
                "district": rec.district,
                "metric": rec.metric,
                "value": rec.value,
                "unit": rec.unit,
                "min_value": rec.min_value,
                "max_value": rec.max_value,
                "forecast_days_ahead": rec.forecast_days_ahead,
                "condition": rec.condition,
                "advisory": rec.advisory,
                "source": rec.source,
                "raw_payload": rec.raw_payload,
                "is_stale": False,
            }
            for rec in orm_records
        ]
    )

    # On conflict, update mutable fields (but keep raw_payload for auditability)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_weather_obs_dedupe",
        set_={
            "value": stmt.excluded.value,
            "min_value": stmt.excluded.min_value,
            "max_value": stmt.excluded.max_value,
            "condition": stmt.excluded.condition,
            "advisory": stmt.excluded.advisory,
            "is_stale": False,
            "fetched_at": stmt.excluded.fetched_at,
        },
    )

    result = await session.execute(stmt)
    await session.commit()

    # Note: result.rowcount may not reflect actual rows affected in PostgreSQL
    # We'll return the input count as approximation
    return len(orm_records)


def _default_sources() -> list[WeatherSource]:
    """Create default list of weather sources (IMD + OpenWeather).

    Returns:
        List of WeatherSource instances ready to use
    """
    from src.config import settings

    sources = [
        IMDWeatherSource(),
        OpenWeatherSource(api_key=settings.openweather_api_key),
    ]
    return sources
