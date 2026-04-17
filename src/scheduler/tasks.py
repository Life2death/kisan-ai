"""Celery tasks."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.adapters.whatsapp import WhatsAppAdapter
from src.config import settings
from src.models.farmer import Farmer
from src.models.broadcast import BroadcastLog
from src.models.conversation import Conversation
from src.models.consent import ConsentEvent
from src.price.models import PriceQuery
from src.price.repository import PriceRepository
from src.price.formatter import format_price_reply
from src.scheduler.celery_app import app

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=3)
def broadcast_prices(self):
    """
    Daily broadcast: send price alerts to all subscribed farmers.
    Runs at 6:30 AM IST.
    """
    import asyncio
    return asyncio.run(_broadcast_prices_async())


async def _broadcast_prices_async():
    """Actual broadcast logic (async)."""
    logger.info("broadcast_prices: starting")

    # Setup DB connection
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            # Fetch all farmers with active subscriptions (exclude soft-deleted and erasure-requested)
            stmt = select(Farmer).where(
                Farmer.subscription_status == "active",
                Farmer.onboarding_state == "active",
                Farmer.deleted_at == None,
                Farmer.erasure_requested_at == None,  # Don't send to farmers in erasure window
            )
            result = await session.execute(stmt)
            farmers = result.scalars().all()
            logger.info("broadcast_prices: found %d active farmers", len(farmers))

            whatsapp = WhatsAppAdapter()
            price_repo = PriceRepository(session)
            sent_count = 0
            error_count = 0

            for farmer in farmers:
                try:
                    # Send price for each crop they're interested in
                    for crop in farmer.crops_of_interest:
                        query = PriceQuery(
                            commodity=crop.crop,
                            district=farmer.district,
                        )
                        result = await price_repo.query(query)

                        if not result.found:
                            logger.warning(
                                "broadcast_prices: no data for farmer=%s crop=%s district=%s",
                                farmer.phone, crop.crop, farmer.district,
                            )
                            continue

                        # Format message in farmer's language
                        msg_text = format_price_reply(result, lang=farmer.preferred_language)

                        # Send via WhatsApp
                        success = await whatsapp.send_text_message(
                            phone=farmer.phone,
                            text=msg_text,
                        )
                        if success:
                            sent_count += 1
                        else:
                            error_count += 1

                except Exception as exc:
                    logger.error(
                        "broadcast_prices: error for farmer=%s: %s",
                        farmer.phone, exc,
                    )
                    error_count += 1

            logger.info(
                "broadcast_prices: complete sent=%d errors=%d",
                sent_count, error_count,
            )
            return {"sent": sent_count, "errors": error_count}

    finally:
        await engine.dispose()


@app.task(bind=True, max_retries=3)
def hard_delete_erased_farmers(self):
    """
    Hard-delete farmers whose 30-day erasure countdown has expired.

    For each farmer with erasure_requested_at > 30 days old:
    1. Log erasure_complete event (before deletion)
    2. Soft-delete related broadcast_log and conversation records
    3. Hard-delete the farmer row

    Runs daily at 1:00 AM IST (00:30 UTC).
    """
    import asyncio
    return asyncio.run(_hard_delete_erased_farmers_async())


async def _hard_delete_erased_farmers_async():
    """Actual hard-delete logic (async)."""
    logger.info("hard_delete_erased_farmers: starting")

    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            # Find farmers with erasure_requested_at > 30 days ago
            cutoff = datetime.now() - timedelta(days=30)
            stmt = select(Farmer).where(
                Farmer.erasure_requested_at != None,
                Farmer.erasure_requested_at < cutoff,
                Farmer.deleted_at == None,  # Not already hard-deleted
            )
            result = await session.execute(stmt)
            farmers_to_erase = result.scalars().all()

            erased_count = 0
            error_count = 0

            logger.info("hard_delete_erased_farmers: found %d eligible farmers", len(farmers_to_erase))

            for farmer in farmers_to_erase:
                try:
                    # 1. Log erasure_complete event (BEFORE deletion for audit trail)
                    ce = ConsentEvent(
                        farmer_id=farmer.id,
                        event_type="erasure_complete",
                        created_at=datetime.now(),
                    )
                    session.add(ce)
                    await session.flush()

                    # 2. Soft-delete related broadcast_log records
                    stmt_bl = update(BroadcastLog).where(
                        BroadcastLog.farmer_id == farmer.id
                    ).values(deleted_at=datetime.now())
                    await session.execute(stmt_bl)

                    # 3. Soft-delete related conversation records
                    stmt_conv = update(Conversation).where(
                        Conversation.farmer_id == farmer.id
                    ).values(deleted_at=datetime.now())
                    await session.execute(stmt_conv)

                    # 4. Hard-delete the farmer row
                    await session.delete(farmer)

                    await session.commit()

                    erased_count += 1
                    logger.info(
                        "hard_delete_erased_farmers: erased farmer_id=%d phone=%s",
                        farmer.id, farmer.phone,
                    )

                except Exception as exc:
                    error_count += 1
                    logger.error(
                        "hard_delete_erased_farmers: error for farmer_id=%d: %s",
                        farmer.id, exc,
                    )

            logger.info(
                "hard_delete_erased_farmers: complete erased=%d errors=%d",
                erased_count, error_count,
            )
            return {"erased": erased_count, "errors": error_count}

    finally:
        await engine.dispose()


@app.task(bind=True, max_retries=3)
def ingest_weather(self):
    """
    Daily weather ingestion: fetch from IMD + OpenWeather for all 5 districts.
    Runs at 6:00 AM IST (before price broadcast at 6:30 AM).

    Phase 2 Module 1: Weather Integration
    """
    import asyncio
    return asyncio.run(_ingest_weather_async())


async def _ingest_weather_async():
    """Actual weather ingestion logic (async)."""
    logger.info("ingest_weather: starting")

    try:
        from src.ingestion.weather.orchestrator import run_ingestion

        # Setup DB connection
        engine = create_async_engine(settings.database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            trade_date = date.today()

            # Run multi-source ingestion
            summary = await run_ingestion(trade_date, session)

            logger.info(
                "ingest_weather: complete for %s — fetched=%d, normalized=%d, merged=%d, inserted=%d, errors=%d",
                trade_date,
                summary.total_fetched,
                summary.total_normalized,
                summary.total_merged,
                summary.total_inserted,
                len(summary.errors),
            )

            return {
                "date": trade_date.isoformat(),
                "fetched": summary.total_fetched,
                "inserted": summary.total_inserted,
                "errors": summary.errors,
                "healthy": summary.healthy,
            }

    except Exception as exc:
        logger.exception("ingest_weather: failed")
        raise
    finally:
        await engine.dispose()
