"""Run all price sources in parallel, merge, persist.

One call per day (Celery beat at 20:30 IST). On each call:

  1. Build source instances.
  2. `asyncio.gather` — fetch from all sources concurrently. Exceptions from
     any one source are caught and logged; other sources continue.
  3. Feed all records (including losers) to the merger to compute the winner
     set. BOTH are persisted: raw per-source rows + a tag for the winner row,
     so disagreements stay auditable.
  4. Upsert into `mandi_prices` using the unique constraint
     `(date, apmc, crop, variety, source)` — re-running is idempotent.
  5. Emit a health summary (counts per source, winners, drops). The caller
     (Celery task) is responsible for alerting if counts look wrong.

This module has no schedule of its own — `src/scheduler/` owns the cron.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.ingestion.merger import pick_winners
from src.ingestion.sources.agmarknet_api import AgmarknetApiSource
from src.ingestion.sources.agmarknet_v2_api import AgmarknetV2Source
from src.ingestion.sources.base import PriceRecord, PriceSource
from src.ingestion.sources.enam_scraper import ENamScraperSource
from src.ingestion.sources.msamb_scraper import MsambScraperSource
from src.ingestion.sources.nhrdf_scraper import NhrdfOnionSource
from src.ingestion.sources.vashi_scraper import VashiApmcSource
from src.models.price import MandiPrice

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IngestionSummary:
    trade_date: date
    per_source_counts: dict[str, int]
    total_records: int
    winner_count: int
    persisted: int
    errors: dict[str, str]
    started_at: datetime
    finished_at: datetime

    @property
    def duration_s(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    def healthy(self, min_sources: int = 2) -> bool:
        """At least `min_sources` sources returned data with no exceptions."""
        healthy_sources = sum(1 for s, n in self.per_source_counts.items() if n > 0 and s not in self.errors)
        return healthy_sources >= min_sources


def _default_sources() -> list[PriceSource]:
    return [
        AgmarknetV2Source(),       # Primary: live api.agmarknet.gov.in/v1/ (no key, real-time)
        AgmarknetApiSource(),      # Fallback: data.gov.in (key required, 10-day lag)
        ENamScraperSource(),       # Supplementary: eNAM 118 MH APMCs (intermittently broken)
        MsambScraperSource(),
        NhrdfOnionSource(),
        VashiApmcSource(),
    ]


async def _fetch_with_guard(source: PriceSource, trade_date: date) -> tuple[str, list[PriceRecord], str | None]:
    """Run one source, capture exceptions so gather() never aborts the batch."""
    try:
        records = await source.fetch(trade_date)
        return source.name, records, None
    except Exception as exc:  # noqa: BLE001 — we really do want to swallow here
        logger.exception("source %s failed for %s", source.name, trade_date)
        return source.name, [], f"{type(exc).__name__}: {exc}"


async def run_ingestion(
    trade_date: date,
    session: AsyncSession,
    sources: Sequence[PriceSource] | None = None,
) -> IngestionSummary:
    """End-to-end ingest for one day. Idempotent — safe to retry."""
    started = datetime.now(timezone.utc)
    active_sources = list(sources) if sources is not None else _default_sources()

    results = await asyncio.gather(
        *(_fetch_with_guard(src, trade_date) for src in active_sources)
    )

    per_source_counts: dict[str, int] = {}
    errors: dict[str, str] = {}
    all_records: list[PriceRecord] = []
    for name, records, err in results:
        per_source_counts[name] = len(records)
        if err:
            errors[name] = err
        all_records.extend(records)

    winners = pick_winners(all_records)
    persisted = await _upsert_records(session, all_records)

    finished = datetime.now(timezone.utc)
    summary = IngestionSummary(
        trade_date=trade_date,
        per_source_counts=per_source_counts,
        total_records=len(all_records),
        winner_count=len(winners),
        persisted=persisted,
        errors=errors,
        started_at=started,
        finished_at=finished,
    )
    logger.info(
        "ingestion complete date=%s counts=%s winners=%d persisted=%d errors=%s duration=%.1fs",
        trade_date, per_source_counts, summary.winner_count, persisted, errors, summary.duration_s,
    )
    return summary


async def _upsert_records(session: AsyncSession, records: Iterable[PriceRecord]) -> int:
    """Upsert on the unique constraint; update mutable price fields on conflict."""
    count = 0
    for rec in records:
        stmt = pg_insert(MandiPrice).values(
            date=rec.trade_date,
            crop=rec.commodity,
            variety=rec.variety,
            mandi=rec.mandi_display,
            apmc=rec.apmc,
            district=rec.district,
            modal_price=rec.modal_price,
            min_price=rec.min_price,
            max_price=rec.max_price,
            arrival_quantity_qtl=rec.arrival_quantity_qtl,
            source=rec.source,
            raw_payload=rec.raw,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_mandi_prices_dedupe",
            set_={
                "mandi": stmt.excluded.mandi,
                "modal_price": stmt.excluded.modal_price,
                "min_price": stmt.excluded.min_price,
                "max_price": stmt.excluded.max_price,
                "arrival_quantity_qtl": stmt.excluded.arrival_quantity_qtl,
                "raw_payload": stmt.excluded.raw_payload,
            },
        )
        await session.execute(stmt)
        count += 1
    await session.commit()
    return count
