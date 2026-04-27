"""Celery tasks."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.adapters.whatsapp import WhatsAppAdapter, WhatsAppConfig
from src.config import settings
from src.models.farmer import Farmer
from src.models.schemes import MSPAlert, GovernmentScheme
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
def trigger_farm_advisories(self):
    """Daily: generate advisories for all farmers and WhatsApp-push high-risk ones.

    Runs at 6:45 AM IST (after weather ingest at 6:00). Idempotent via UNIQUE
    (farmer_id, rule_id, advisory_date) — safe to re-run manually.
    """
    import asyncio
    return asyncio.run(_trigger_farm_advisories_async())


async def _trigger_farm_advisories_async():
    """Generate advisories for every farmer, then WhatsApp-push high-risk ones."""
    from src.advisory.engine import generate_for_all_farmers
    from src.advisory.repository import AdvisoryRepository
    from src.models.advisory import Advisory

    logger.info("trigger_farm_advisories: starting")
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    MAX_PUSH_PER_FARMER = 2

    try:
        async with async_session() as session:
            counts = await generate_for_all_farmers(session)
            total_created = sum(counts.values())
            logger.info(
                "trigger_farm_advisories: generated %d advisories across %d farmers",
                total_created, len(counts),
            )

            # WhatsApp push — high-risk only, capped per farmer, only today's
            whatsapp = WhatsAppAdapter()
            repo = AdvisoryRepository(session)
            today = date.today()
            pushed = skipped = errors = 0

            for farmer_id, created in counts.items():
                if not created:
                    continue
                farmer = (
                    await session.execute(select(Farmer).where(Farmer.id == farmer_id))
                ).scalar_one_or_none()
                if not farmer or not farmer.phone:
                    continue
                if farmer.deleted_at or farmer.erasure_requested_at:
                    continue

                # Fetch today's high-risk undelivered advisories for this farmer
                stmt = (
                    select(Advisory)
                    .where(
                        Advisory.farmer_id == farmer_id,
                        Advisory.advisory_date == today,
                        Advisory.risk_level == "high",
                    )
                    .order_by(Advisory.created_at.desc())
                    .limit(MAX_PUSH_PER_FARMER)
                )
                to_push = list((await session.execute(stmt)).scalars().all())
                for adv in to_push:
                    already = (adv.delivered_via or {}).get("whatsapp")
                    if already:
                        skipped += 1
                        continue
                    try:
                        src_line = f"\nSource: {adv.source_citation}" if adv.source_citation else ""
                        msg = (
                            f"🌾 Kisan AI advisory\n"
                            f"{adv.title}\n"
                            f"{adv.message}\n"
                            f"👉 {adv.action_hint}"
                            f"{src_line}"
                        )
                        msg_id = await whatsapp.send_text_message(to=farmer.phone, text=msg)
                        if msg_id:
                            await repo.mark_whatsapp_delivered(adv.id, msg_id)
                            pushed += 1
                        else:
                            errors += 1
                    except Exception as exc:
                        logger.error(
                            "trigger_farm_advisories: WhatsApp push failed farmer=%s adv=%s: %s",
                            farmer.phone, adv.id, exc,
                        )
                        errors += 1

            logger.info(
                "trigger_farm_advisories: complete generated=%d pushed=%d skipped=%d errors=%d",
                total_created, pushed, skipped, errors,
            )
            return {
                "generated": total_created,
                "pushed": pushed,
                "skipped": skipped,
                "errors": errors,
            }
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


@app.task(bind=True, max_retries=3)
def ingest_prices(self):
    """
    Daily price ingestion: fetch from 4 sources (Agmarknet, MSIB, NHRDF, Vashi).
    Runs at 8:00 PM IST (before evening alert trigger at 8:30 PM).

    Phase 2 Module 5: Price Alerts
    """
    import asyncio
    return asyncio.run(_ingest_prices_async())


async def _ingest_prices_async():
    """Actual price ingestion logic (async)."""
    logger.info("ingest_prices: starting")

    try:
        from src.ingestion.orchestrator import run_ingestion

        # Setup DB connection
        engine = create_async_engine(settings.database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            trade_date = date.today()

            # Run multi-source price ingestion
            summary = await run_ingestion(trade_date, session)

            logger.info(
                "ingest_prices: complete for %s — total=%d, winners=%d, persisted=%d, healthy=%s",
                trade_date,
                summary.total_records,
                summary.winner_count,
                summary.persisted,
                summary.healthy(),
            )

            return {
                "date": trade_date.isoformat(),
                "total": summary.total_records,
                "persisted": summary.persisted,
                "healthy": summary.healthy(),
                "per_source": summary.per_source_counts,
                "errors": summary.errors,
            }

    except Exception as exc:
        logger.exception("ingest_prices: failed")
        raise
    finally:
        await engine.dispose()


@app.task(bind=True, max_retries=3)
def trigger_price_alerts(self):
    """
    Check active price alert subscriptions against just-ingested mandi prices.
    Send WhatsApp notifications for triggered alerts.

    Runs at 8:30 PM IST (after ingest_prices completes at 8:00 PM).

    Phase 2 Module 5: Price Alerts
    """
    import asyncio
    return asyncio.run(_trigger_price_alerts_async())


async def _trigger_price_alerts_async():
    """Check and trigger price alerts."""
    logger.info("trigger_price_alerts: starting")

    # Setup DB connection
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            from src.price.alert_repository import PriceAlertRepository
            from src.price.alert_formatter import format_price_alert_triggered
            from src.price.repository import PriceRepository

            alert_repo = PriceAlertRepository(session)
            price_repo = PriceRepository(session)
            whatsapp = WhatsAppAdapter()

            # Get all active price alerts
            active_alerts = await alert_repo.get_active_alerts()
            logger.info("trigger_price_alerts: found %d active alerts", len(active_alerts))

            triggered_count = 0
            error_count = 0

            for alert in active_alerts:
                try:
                    farmer_id = alert["farmer_id"]
                    commodity = alert["commodity"]
                    condition = alert["condition"]
                    threshold = alert["threshold"]
                    district = alert["district"]

                    # Get latest price for this commodity/district
                    from src.price.models import PriceQuery
                    query = PriceQuery(commodity=commodity, district=district)
                    price_result = await price_repo.query(query)

                    if not price_result.found:
                        logger.debug(
                            "trigger_price_alerts: no price data for %s/%s",
                            commodity, district or "all",
                        )
                        continue

                    current_price = price_result.modal_price
                    if current_price is None:
                        continue

                    # Check if condition is met
                    if alert_repo.check_condition(condition, float(current_price), threshold):
                        # Get farmer language preference
                        farmer_stmt = select(Farmer).where(Farmer.id == farmer_id)
                        farmer_result = await session.execute(farmer_stmt)
                        farmer = farmer_result.scalar_one_or_none()

                        if not farmer:
                            logger.warning("trigger_price_alerts: farmer %s not found", farmer_id)
                            continue

                        # Format and send notification
                        lang = farmer.preferred_language or "mr"
                        msg_text = format_price_alert_triggered(
                            commodity=commodity,
                            condition=condition,
                            current_price=float(current_price),
                            threshold=threshold,
                            district=district or "all",
                            lang=lang,
                        )

                        success = await whatsapp.send_text_message(
                            phone=farmer.phone,
                            text=msg_text,
                        )

                        if success:
                            triggered_count += 1
                            logger.info(
                                "trigger_price_alerts: sent to farmer=%s commodity=%s",
                                farmer.phone, commodity,
                            )
                        else:
                            error_count += 1

                except Exception as exc:
                    logger.error(
                        "trigger_price_alerts: error processing alert: %s",
                        exc,
                    )
                    error_count += 1

            logger.info(
                "trigger_price_alerts: complete triggered=%d errors=%d",
                triggered_count, error_count,
            )
            return {"triggered": triggered_count, "errors": error_count}

    finally:
        await engine.dispose()


@app.task(bind=True, max_retries=3)
def ingest_government_schemes(self):
    """
    Daily government schemes ingestion: fetch from PMKSY, PM-FASAL, Rashtriya Kranti.
    Runs at 6:15 AM IST (after weather at 6:00 AM, before price broadcast at 6:30 AM).

    Phase 2 Module 4: Government Schemes & MSP Alerts
    """
    import asyncio
    return asyncio.run(_ingest_government_schemes_async())


async def _ingest_government_schemes_async():
    """Actual government schemes ingestion logic (async)."""
    logger.info("ingest_government_schemes: starting")

    try:
        from src.ingestion.schemes.orchestrator import SchemeOrchestrator

        # Setup DB connection
        engine = create_async_engine(settings.database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # Create orchestrator with config
            config = {
                "pmksy_api_enabled": settings.pmksy_api_enabled,
                "pmfby_api_enabled": settings.pmfby_api_enabled,
            }
            orchestrator = SchemeOrchestrator(session, config)

            # Run ingestion
            summary = await orchestrator.ingest()

            logger.info(
                "ingest_government_schemes: complete — fetched=%d, upserted=%d, healthy=%s, errors=%d",
                summary.total_records_fetched,
                summary.total_records_upserted,
                summary.is_healthy,
                len(summary.errors),
            )

            return {
                "fetched": summary.total_records_fetched,
                "upserted": summary.total_records_upserted,
                "healthy": summary.is_healthy,
                "sources_succeeded": summary.sources_succeeded,
                "sources_failed": summary.sources_failed,
                "errors": summary.errors,
            }

    except Exception as exc:
        logger.exception("ingest_government_schemes: failed")
        raise
    finally:
        await engine.dispose()


@app.task(bind=True, max_retries=3)
def trigger_msp_alerts(self):
    """
    Check active MSP alert subscriptions against just-ingested scheme MSP data.
    Send WhatsApp notifications for triggered alerts.

    Runs at 6:20 AM IST (after ingest_government_schemes completes at 6:15 AM).

    Phase 2 Module 4: Government Schemes & MSP Alerts
    """
    import asyncio
    return asyncio.run(_trigger_msp_alerts_async())


async def _trigger_msp_alerts_async():
    """Check and trigger MSP alerts."""
    logger.info("trigger_msp_alerts: starting")

    # Setup DB connection
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            from src.scheme.formatter import format_msp_alert_triggered

            whatsapp = WhatsAppAdapter(WhatsAppConfig(
                phone_id=settings.whatsapp_phone_id,
                token=settings.whatsapp_token,
                business_account_id=settings.whatsapp_app_id,
            ))

            # Get all active MSP alerts
            stmt = select(MSPAlert).where(MSPAlert.is_active == True)
            result = await session.execute(stmt)
            msp_alerts = result.scalars().all()

            logger.info("trigger_msp_alerts: found %d active MSP alerts", len(msp_alerts))

            triggered_count = 0
            error_count = 0

            # Group alerts by commodity for efficient lookup
            alerts_by_commodity = {}
            for alert in msp_alerts:
                commodity = alert.commodity
                if commodity not in alerts_by_commodity:
                    alerts_by_commodity[commodity] = []
                alerts_by_commodity[commodity].append(alert)

            # For each commodity with alerts, get latest MSP from schemes
            for commodity, commodity_alerts in alerts_by_commodity.items():
                try:
                    # Query latest scheme that includes this commodity
                    stmt = (
                        select(GovernmentScheme)
                        .where(GovernmentScheme.commodities.contains([commodity]))
                        .order_by(GovernmentScheme.created_at.desc())
                        .limit(1)
                    )
                    result = await session.execute(stmt)
                    scheme = result.scalar_one_or_none()

                    if not scheme:
                        logger.debug("trigger_msp_alerts: no scheme data for %s", commodity)
                        continue

                    # Extract MSP from benefit_amount or eligibility_criteria
                    msp_value = None
                    if scheme.benefit_amount:
                        msp_value = float(scheme.benefit_amount)
                    elif scheme.eligibility_criteria and isinstance(scheme.eligibility_criteria, dict):
                        msp_value = scheme.eligibility_criteria.get("msp_value")

                    if msp_value is None:
                        logger.debug("trigger_msp_alerts: no MSP value in scheme for %s", commodity)
                        continue

                    # Check each alert for this commodity
                    for alert in commodity_alerts:
                        try:
                            # For MSP alerts, trigger when MSP >= threshold (condition always ">")
                            if msp_value >= float(alert.alert_threshold):
                                # Get farmer for language preference
                                farmer_stmt = select(Farmer).where(Farmer.id == alert.farmer_id)
                                farmer_result = await session.execute(farmer_stmt)
                                farmer = farmer_result.scalar_one_or_none()

                                if not farmer:
                                    logger.warning("trigger_msp_alerts: farmer %s not found", alert.farmer_id)
                                    continue

                                # Format and send notification
                                lang = farmer.preferred_language or "mr"
                                msg_text = format_msp_alert_triggered(
                                    commodity=commodity,
                                    msp_price=msp_value,
                                    threshold=float(alert.alert_threshold),
                                    lang=lang,
                                )

                                success = await whatsapp.send_text_message(
                                    phone=farmer.phone,
                                    text=msg_text,
                                )

                                if success:
                                    # Update triggered_at to avoid duplicate sends
                                    alert.triggered_at = datetime.now(timezone.utc)
                                    await session.commit()

                                    triggered_count += 1
                                    logger.info(
                                        "trigger_msp_alerts: sent to farmer=%s commodity=%s msp=%.0f",
                                        farmer.phone, commodity, msp_value,
                                    )
                                else:
                                    error_count += 1

                        except Exception as exc:
                            logger.error(
                                "trigger_msp_alerts: error processing alert for farmer %s: %s",
                                alert.farmer_id, exc,
                            )
                            error_count += 1

                except Exception as exc:
                    logger.error(
                        "trigger_msp_alerts: error processing commodity=%s: %s",
                        commodity, exc,
                    )

            logger.info(
                "trigger_msp_alerts: complete triggered=%d errors=%d",
                triggered_count, error_count,
            )
            return {"triggered": triggered_count, "errors": error_count}

    finally:
        await engine.dispose()
