"""Celery tasks."""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.adapters.whatsapp import WhatsAppAdapter
from src.config import settings
from src.models.farmer import Farmer
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
            # Fetch all farmers with active subscriptions
            stmt = select(Farmer).where(
                Farmer.subscription_status == "active",
                Farmer.onboarding_state == "active",
                Farmer.deleted_at == None,
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
