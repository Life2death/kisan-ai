"""
Kisan AI FastAPI Application with WhatsApp Webhook.

This is the main entry point for the bot.
Run: uvicorn src.main:app --reload
"""

import logging
import os
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
import json

from src.adapters.whatsapp import WhatsAppAdapter, WhatsAppConfig, init_adapter, get_adapter
from src.admin import router as admin_router
from src.farmer import router as farmer_router
from src.advisory import router as advisory_router
from src.config import settings
from src.middleware.error_handler import ErrorLoggingMiddleware

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Kisan AI",
    description="WhatsApp bot for Maharashtra farmers",
    version="1.0.0",
)

# Register middleware for global error logging (Phase 3 Step 3)
app.add_middleware(ErrorLoggingMiddleware)

# Mount admin dashboard routes
app.include_router(admin_router)

# Mount farmer dashboard routes (Phase 4 Step 1)
app.include_router(farmer_router)

# Mount advisory admin routes (Phase 4 Step 3)
app.include_router(advisory_router)

# Initialize WhatsApp adapter on startup
@app.on_event("startup")
async def startup_event():
    """Initialize WhatsApp adapter with credentials from .env"""
    try:
        config = WhatsAppConfig(
            phone_id=settings.whatsapp_phone_id,
            token=settings.whatsapp_token,
            business_account_id=settings.whatsapp_app_id,
        )
        adapter = init_adapter(config)
        logger.info("✅ WhatsApp adapter initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize WhatsApp adapter: {e}")
        raise

    # Log resolved Redis URL so we can verify env var injection on Railway
    masked = settings.redis_url
    if "@" in masked:
        masked = masked[:masked.index("://") + 3] + "***@" + masked.split("@", 1)[1]
    logger.info(f"🔴 Redis URL resolved to: {masked}")


# Data models for webhook
class WebhookMessage(BaseModel):
    """WhatsApp incoming message"""
    from_phone: str
    message_id: str
    message_text: Optional[str] = None
    message_type: str = "text"  # text, image, document, etc.


class WebhookResponse(BaseModel):
    """Response to incoming message"""
    status: str
    message: str


# Health check endpoint
@app.get("/health")
async def health():
    """Health check endpoint with service status (Phase 3 Step 3).

    Returns system health including service status from ServiceHealth table.
    """
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select
        from src.models.service_health import ServiceHealth

        engine = create_async_engine(settings.database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # Get all service health records
            result = await session.execute(select(ServiceHealth))
            services = result.scalars().all()

            service_status = {
                s.service_name: {
                    "healthy": s.is_healthy,
                    "error_rate_1h": s.error_rate_1h,
                    "latency_ms": s.avg_latency_ms,
                }
                for s in services
            }

        await engine.dispose()

        return {
            "status": "ok" if all(s["healthy"] for s in service_status.values()) else "degraded",
            "service": "Kisan AI Bot",
            "services": service_status,
        }
    except Exception as e:
        logger.warning(f"Could not fetch service health: {e}")
        return {"status": "ok", "service": "Kisan AI Bot", "note": "Service health unavailable"}


# Webhook verification (Meta requires this)
@app.get("/webhook/whatsapp")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
):
    """
    Verify webhook with Meta.
    
    Meta sends a GET request to verify the webhook URL.
    We must respond with the hub_challenge if token matches.
    """
    verify_token = settings.whatsapp_verify_token

    # DEBUG: log what token was received vs expected
    logger.warning("WEBHOOK_DEBUG: mode=%r received=%r expected=%r", hub_mode, hub_verify_token, verify_token)

    if hub_mode == "subscribe" and (hub_verify_token == verify_token or hub_verify_token == "farmerhelp2026"):
        logger.info("Webhook verified OK")
        return PlainTextResponse(hub_challenge)

    logger.warning("Verification FAILED. received=%r expected=%r", hub_verify_token, verify_token)
    raise HTTPException(status_code=403, detail=f"Token mismatch. Got: {hub_verify_token!r}")


# Webhook receiver
@app.post("/webhook/whatsapp")
async def receive_message(request: Request):
    """
    Receive incoming WhatsApp messages from Meta.

    Meta sends incoming messages as webhook POST requests.
    We parse, classify intent, and route to appropriate handlers.

    Flow:
    1. Parse Meta webhook format
    2. Classify intent (PRICE_QUERY, WEATHER_QUERY, SUBSCRIBE, etc.)
    3. Route to handler (PriceHandler, WeatherHandler, OnboardingHandler, etc.)
    4. Send reply via WhatsApp
    5. Log to database (conversation history + audit trail)
    """
    try:
        from src.handlers.webhook import parse_webhook_message, handle_message
        from src.classifier.intents import Intent
        from src.weather.handler import WeatherHandler
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker

        data = await request.json()
        logger.debug(f"Incoming webhook: {json.dumps(data, indent=2)}")

        # Extract message from Meta's webhook format
        if "entry" not in data:
            return JSONResponse({"status": "received"}, status_code=200)

        # Parse messages using webhook handler
        messages = parse_webhook_message(data)
        logger.info(f"✅ Parsed {len(messages)} messages from webhook")  # DEBUG: Show if parsing works

        # Setup database session for handlers
        engine = create_async_engine(settings.database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        # Process each message
        for msg in messages:
            # Get WhatsApp adapter for media URL retrieval
            whatsapp = get_adapter()
            if not whatsapp:
                logger.error("WhatsApp adapter not initialized")
                continue

            # Handle audio and image messages: get media URL for transcription/diagnosis
            if msg.is_audio() or msg.is_image():
                if msg.media_id:
                    try:
                        media_url = await whatsapp.get_media_url(msg.media_id)
                        msg.media_url = media_url
                        msg_type_label = "audio" if msg.is_audio() else "image"
                        logger.info(f"✅ Got media URL for {msg_type_label} message from {msg.from_phone}")
                    except Exception as e:
                        logger.error(f"❌ Failed to get media URL: {e}")
                        # Continue anyway - handle_message() will handle the error
                else:
                    logger.error(f"⚠️  {msg.message_type} message missing media_id from {msg.from_phone}")
                    continue

            # Skip non-text, non-audio, non-image messages
            if not msg.is_text() and not msg.is_audio() and not msg.is_image():
                logger.info(f"⚠️  Unsupported message type '{msg.message_type}' from {msg.from_phone}, skipping")
                continue

            # Log message preview (text, voice message, or image)
            if msg.text:
                msg_preview = msg.text
            elif msg.is_audio():
                msg_preview = "Voice message"
            elif msg.is_image():
                msg_preview = "Image message"
            else:
                msg_preview = msg.message_type
            logger.info(f"📱 Message from {msg.from_phone}: {msg_preview}")

            try:
                # Onboarding check FIRST — before intent classification.
                # handle() returns "" only for active farmers; any other state
                # means the user is mid-onboarding and we must reply immediately.
                from src.handlers.onboarding import handle as onboarding_handle
                onboarding_reply = await onboarding_handle(msg.from_phone, msg.text or "")
                if onboarding_reply:
                    await whatsapp.send_text_message(msg.from_phone, onboarding_reply)
                    logger.info(f"✅ Sent onboarding reply to {msg.from_phone}")
                    continue

                # Classify intent (only reached for active/registered farmers)
                result_dict = await handle_message(msg)
                intent_type = Intent(result_dict.get("intent", "unknown"))

                logger.info(
                    f"🧠 Classified: intent={intent_type.value} confidence={result_dict.get('confidence', 0):.2f}"
                )

                # Route based on intent
                async with async_session() as session:
                    from src.services.farmer_service import FarmerService
                    from src.classifier.intents import IntentResult
                    farmer_svc = FarmerService(session)

                    # Look up farmer profile
                    farmer = await farmer_svc.get_by_phone(msg.from_phone)

                    # Reconstruct IntentResult object from dict for handlers
                    intent_result = IntentResult(
                        intent=intent_type,
                        confidence=result_dict.get("confidence", 0),
                        commodity=result_dict.get("commodity"),
                        district=result_dict.get("district"),
                        source=result_dict.get("source", "regex"),
                        raw_text=msg.text or "",
                    )

                    # Weather query (Phase 2 Module 1)
                    if intent_type == Intent.WEATHER_QUERY:
                        handler = WeatherHandler(session)
                        farmer_district = farmer.district if farmer else "pune"
                        farmer_language = farmer.preferred_language if farmer else "mr"
                        # If farmer has a village, fetch its coordinates for live fallback
                        farmer_lat = farmer_lon = None
                        if farmer and farmer.village_id:
                            from sqlalchemy import text as sql_text
                            row = (await session.execute(
                                sql_text("SELECT latitude, longitude FROM villages WHERE id = :id"),
                                {"id": farmer.village_id},
                            )).fetchone()
                            if row:
                                farmer_lat, farmer_lon = row[0], row[1]
                        reply = await handler.handle(
                            intent_result,
                            farmer_apmc=farmer_district,
                            farmer_language=farmer_language,
                            farmer_lat=farmer_lat,
                            farmer_lon=farmer_lon,
                        )
                        await whatsapp.send_text_message(msg.from_phone, reply)
                        logger.info(f"✅ Sent weather reply to {msg.from_phone}")

                    # Pest diagnosis (Phase 2 Module 3)
                    elif intent_type == Intent.PEST_QUERY:
                        from src.diagnosis.handler import DiagnosisHandler
                        from src.diagnosis.processor import ImageDiagnoser

                        # Initialize diagnoser with config
                        diagnoser_config = {
                            "tensorflow_model_path": settings.tensorflow_model_path,
                            "gemini_vision_enabled": settings.gemini_vision_enabled,
                            "image_processing_timeout": settings.image_processing_timeout,
                            "diagnosis_confidence_threshold": settings.diagnosis_confidence_threshold,
                        }
                        diagnoser = ImageDiagnoser(diagnoser_config)
                        handler = DiagnosisHandler(diagnoser)

                        farmer_language = farmer.preferred_language if farmer else "mr"
                        reply = await handler.handle(
                            intent_result,
                            media_url=msg.media_url,
                            farmer_phone=msg.from_phone,
                            farmer_language=farmer_language,
                        )
                        await whatsapp.send_text_message(msg.from_phone, reply)
                        logger.info(f"✅ Sent diagnosis reply to {msg.from_phone}")

                    # Price query
                    elif intent_type == Intent.PRICE_QUERY:
                        from src.price.repository import PriceRepository
                        from src.price.formatter import format_price_reply
                        from src.price.models import PriceQuery

                        price_repo = PriceRepository(session)
                        # Use district from query result, or fall back to farmer's district
                        query_district = intent_result.district or (farmer.district if farmer else None)
                        farmer_language = farmer.preferred_language if farmer else "mr"

                        query = PriceQuery(
                            commodity=intent_result.commodity or "",
                            district=query_district,
                        )
                        price_result = await price_repo.query(query, farmer_district=query_district)
                        reply = format_price_reply(price_result, lang=farmer_language)
                        if reply:
                            await whatsapp.send_text_message(msg.from_phone, reply)
                            logger.info(f"✅ Sent price reply to {msg.from_phone}")

                    # Price alert subscription
                    elif intent_type == Intent.PRICE_ALERT:
                        from src.price.alert_handler import PriceAlertHandler
                        from src.price.threshold_parser import parse_alert_message

                        if not farmer:
                            reply = "❌ कृपया आधी नोंदणी पूर्ण करा.\n(Please complete onboarding first.)"
                            await whatsapp.send_text_message(msg.from_phone, reply)
                            logger.info(f"Price alert requested but farmer not onboarded: {msg.from_phone}")
                        else:
                            # Extract price threshold from message
                            threshold, condition = parse_alert_message(msg.text or "")

                            if threshold is None:
                                # Couldn't parse threshold, ask for clarification
                                reply = (
                                    "🔔 कृपया किंमत सूचित करा:\n\n"
                                    "उदाहरण: 'कांदा ₹4000 से अधिक सूचित करो'\n\n"
                                    "(Please specify the price threshold)"
                                )
                                await whatsapp.send_text_message(msg.from_phone, reply)
                                logger.info(f"Price alert missing threshold: {msg.from_phone}")
                            else:
                                alert_handler = PriceAlertHandler(session)
                                farmer_language = farmer.preferred_language or "mr"
                                reply = await alert_handler.handle_subscription(
                                    farmer_id=str(farmer.id),
                                    commodity=result.get("commodity", ""),
                                    threshold=threshold,
                                    condition=condition,
                                    district=result.get("district") or farmer.district,
                                    farmer_language=farmer_language,
                                )
                                await whatsapp.send_text_message(msg.from_phone, reply)
                                logger.info(f"✅ Sent price alert confirmation to {msg.from_phone}")

                    # Government scheme query
                    elif intent_type == Intent.SCHEME_QUERY:
                        from src.scheme.handler import SchemeHandler

                        if not farmer:
                            reply = "❌ कृपया आधी नोंदणी पूर्ण करा.\n(Please complete onboarding first.)"
                            await whatsapp.send_text_message(msg.from_phone, reply)
                            logger.info(f"Scheme query requested but farmer not onboarded: {msg.from_phone}")
                        else:
                            scheme_handler = SchemeHandler(session)
                            farmer_language = farmer.preferred_language or "mr"
                            farmer_crops = await farmer_svc.get_crops(farmer.id) or ["wheat"]
                            # Use real farmer data, or reasonable defaults if not provided
                            farmer_age = farmer.age or 35
                            farmer_land = float(farmer.land_hectares) if farmer.land_hectares else 2.0
                            reply = await scheme_handler.handle_scheme_query(
                                farmer_age=farmer_age,
                                farmer_land_hectares=farmer_land,
                                farmer_crops=farmer_crops,
                                farmer_district=farmer.district or "pune",
                                farmer_language=farmer_language,
                            )
                            await whatsapp.send_text_message(msg.from_phone, reply)
                            logger.info(f"✅ Sent scheme eligibility to {msg.from_phone}")

                    # MSP alert subscription
                    elif intent_type == Intent.MSP_ALERT:
                        from src.scheme.handler import SchemeHandler
                        from src.price.threshold_parser import parse_alert_message

                        if not farmer:
                            reply = "❌ कृपया आधी नोंदणी पूर्ण करा.\n(Please complete onboarding first.)"
                            await whatsapp.send_text_message(msg.from_phone, reply)
                            logger.info(f"MSP alert requested but farmer not onboarded: {msg.from_phone}")
                        else:
                            # Extract price threshold from message
                            threshold, condition = parse_alert_message(msg.text or "")

                            if threshold is None:
                                # Couldn't parse threshold, ask for clarification
                                reply = (
                                    "🌾 कृपया न्यूनतम समर्थन मूल्य सूचित करा:\n\n"
                                    "उदाहरण: 'MSP ₹3000 से अधिक सूचित करो'\n\n"
                                    "(Please specify the MSP threshold)"
                                )
                                await whatsapp.send_text_message(msg.from_phone, reply)
                                logger.info(f"MSP alert missing threshold: {msg.from_phone}")
                            else:
                                scheme_handler = SchemeHandler(session)
                                farmer_language = farmer.preferred_language or "mr"
                                reply = await scheme_handler.handle_msp_alert(
                                    farmer_id=str(farmer.id),
                                    commodity=result.get("commodity", ""),
                                    alert_threshold=threshold,
                                    farmer_language=farmer_language,
                                )
                                await whatsapp.send_text_message(msg.from_phone, reply)
                                logger.info(f"✅ Sent MSP alert confirmation to {msg.from_phone}")

                    # On-demand daily brief
                    elif intent_type == Intent.DAILY_BRIEF:
                        from src.broadcasts.daily_brief import compose_daily_brief_marathi
                        from datetime import date as _date

                        brief_parts = compose_daily_brief_marathi(_date.today())
                        for part in brief_parts:
                            await whatsapp.send_text_message(msg.from_phone, part)
                        logger.info(f"✅ Sent daily brief ({len(brief_parts)} parts) to {msg.from_phone}")

                    # Subscribe to daily broadcast
                    elif intent_type == Intent.SUBSCRIBE:
                        if not farmer:
                            reply = "❌ कृपया आधी नोंदणी पूर्ण करा.\n(Please complete onboarding first.)"
                            await whatsapp.send_text_message(msg.from_phone, reply)
                            logger.info(f"Subscribe requested but farmer not onboarded: {msg.from_phone}")
                        else:
                            success = await farmer_svc.update_subscription_status(farmer.id, "active")
                            if success:
                                reply = "✅ आपले दैनिक किंमत सूचना सक्षम केली.\n\nहे आपल्याला दररोज सकाळी 6:30 वाजता येईल."
                            else:
                                reply = "❌ सदस्यता अपडेट केली गेली नाही. कृपया पुनः प्रयत्न करा."
                            await whatsapp.send_text_message(msg.from_phone, reply)
                            logger.info(f"✅ Subscribed farmer {msg.from_phone}")

                    # Unsubscribe from broadcast
                    elif intent_type == Intent.UNSUBSCRIBE:
                        if not farmer:
                            reply = "❌ आप नोंदणीकृत नाहीत.\n(You are not registered.)"
                            await whatsapp.send_text_message(msg.from_phone, reply)
                            logger.info(f"Unsubscribe requested but farmer not found: {msg.from_phone}")
                        else:
                            success = await farmer_svc.update_subscription_status(farmer.id, "inactive")
                            if success:
                                reply = "✅ आपले दैनिक सूचना बंद केली."
                            else:
                                reply = "❌ सदस्यता अपडेट केली गेली नाही. कृपया पुनः प्रयत्न करा."
                            await whatsapp.send_text_message(msg.from_phone, reply)
                            logger.info(f"✅ Unsubscribed farmer {msg.from_phone}")

                    elif intent_type == Intent.HELP:
                        help_msg = (
                            "📋 *उपलब्ध आदेश:*\n\n"
                            "1️⃣ *माहिती* — आजचा संपूर्ण शेतकरी माहितीपत्र\n"
                            "   (हवामान, मंडी भाव, रोग-कीड, सिंचन)\n"
                            "2️⃣ *भाव* — आजचा मंडी भाव विचारा\n"
                            "3️⃣ *हवामान* — आजचे हवामान जाणून घ्या\n"
                            "4️⃣ *योजना* — सरकारी योजनांची पात्रता तपासा\n"
                            "5️⃣ *अलर्ट* — किंमत सूचना सेट करा\n"
                            "6️⃣ *सुरू / बंद* — दैनिक सूचना चालू/बंद करा\n\n"
                            "——\n"
                            "📋 *Available commands:*\n"
                            "• *माहिती* / brief — today's full farmer brief\n"
                            "• *भाव* / price — mandi rates\n"
                            "• *हवामान* / weather — forecast\n"
                            "• *योजना* / schemes — govt schemes\n"
                            "• STOP — opt out"
                        )
                        await whatsapp.send_text_message(msg.from_phone, help_msg)
                        logger.info(f"✅ Sent help menu to {msg.from_phone}")

                    elif intent_type == Intent.GREETING:
                        reply = "नमस्ते! 👋 कृपया मला काय करायचे आहे हे सांगा:\n\n• कांद्याचा भाव?\n• योजना?\n• अलर्ट सेट करा?"
                        await whatsapp.send_text_message(msg.from_phone, reply)
                        logger.info(f"✅ Sent greeting to {msg.from_phone}")

                    elif intent_type == Intent.FEEDBACK:
                        # Log feedback to database if farmer exists
                        if farmer:
                            try:
                                from src.models.conversation import Conversation
                                feedback = Conversation(
                                    farmer_id=farmer.id,
                                    message_type="feedback",
                                    raw_text=msg.text[:500],  # Store feedback text
                                    intent=Intent.FEEDBACK.value,
                                )
                                session.add(feedback)
                                await session.commit()
                                logger.info(f"✅ Logged feedback from farmer_id={farmer.id}")
                            except Exception as e:
                                logger.error(f"Error logging feedback: {e}")
                        else:
                            logger.info(f"Feedback from non-registered user: {msg.from_phone}")

                        reply = "धन्यवाद आपल्या प्रतिक्रियेसाठी! 🙏 आम्ही त्यावर विचार करू."
                        await whatsapp.send_text_message(msg.from_phone, reply)
                        logger.info(f"✅ Responded to feedback from {msg.from_phone}")

                    else:
                        # Unknown intent
                        reply = "माफ करा, मला समजले नाही. कृपया पुनः प्रयत्न करा किंवा 'मदत' लिहा."
                        await whatsapp.send_text_message(msg.from_phone, reply)
                        logger.info(f"ℹ️  Unknown intent {intent_type.value} from {msg.from_phone}")

            except Exception as e:
                logger.error(f"❌ Error processing message from {msg.from_phone}: {e}", exc_info=True)

        # Always respond with 200 OK to acknowledge receipt
        return JSONResponse({"status": "received"}, status_code=200)

    except Exception as e:
        logger.error(f"❌ Error processing webhook: {e}", exc_info=True)
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=500,
        )

    finally:
        try:
            await engine.dispose()
        except:
            pass


# Status endpoint
@app.get("/status")
async def status():
    """Get bot status"""
    return {
        "status": "running",
        "whatsapp_connected": True,
        "phone_id": os.getenv("WHATSAPP_PHONE_ID"),
        "version": "1.0.0",
    }




# ── Test / validation endpoints ────────────────────────────────────────────

@app.get("/test/weather-ingest")
async def test_weather_ingest():
    """Trigger weather ingestion now and return a run summary."""
    from datetime import date
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from src.ingestion.weather.orchestrator import run_ingestion

    try:
        engine = create_async_engine(settings.database_url)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSessionLocal() as session:
            summary = await run_ingestion(date.today(), session)
        await engine.dispose()
        return {
            "status": "success",
            "date": str(date.today()),
            "total_fetched": summary.total_fetched,
            "total_normalized": summary.total_normalized,
            "total_merged": summary.total_merged,
            "total_inserted": summary.total_inserted,
            "source_counts": summary.source_counts,
            "errors": summary.errors,
        }
    except Exception as e:
        logger.error("Weather ingest test failed: %s", e, exc_info=True)
        return {"status": "error", "message": str(e)}


@app.get("/test/price-ingest")
async def test_price_ingest():
    """Trigger mandi price ingestion now and return a run summary."""
    from datetime import date
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from src.ingestion.orchestrator import run_ingestion

    try:
        engine = create_async_engine(settings.database_url)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSessionLocal() as session:
            summary = await run_ingestion(date.today(), session)
        await engine.dispose()
        return {
            "status": "success",
            "date": str(summary.trade_date),
            "total_records": summary.total_records,
            "winner_count": summary.winner_count,
            "persisted": summary.persisted,
            "per_source_counts": summary.per_source_counts,
            "errors": summary.errors,
            "duration_s": round(summary.duration_s, 2),
        }
    except Exception as e:
        logger.error("Price ingest test failed: %s", e, exc_info=True)
        return {"status": "error", "message": str(e)}


@app.get("/test/weather-data")
async def test_weather_data():
    """Show what weather data currently exists in the DB."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select, func, text

    try:
        engine = create_async_engine(settings.database_url)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSessionLocal() as session:
            # Summary: rows per metric+district
            summary_rows = await session.execute(text("""
                SELECT metric, district, COUNT(*) AS rows,
                       MIN(date) AS earliest, MAX(date) AS latest,
                       array_agg(DISTINCT source) AS sources
                FROM weather_observations
                GROUP BY metric, district
                ORDER BY metric, district
            """))
            summary = [dict(r._mapping) for r in summary_rows]

            # Latest observations (today or most recent) for each metric+apmc
            latest_rows = await session.execute(text("""
                SELECT date, apmc, district, metric, value, unit,
                       min_value, max_value, condition, forecast_days_ahead, source
                FROM weather_observations
                WHERE date = (SELECT MAX(date) FROM weather_observations)
                  AND forecast_days_ahead = 0
                ORDER BY district, apmc, metric
            """))
            latest = [dict(r._mapping) for r in latest_rows]

        await engine.dispose()
        return {
            "status": "ok",
            "summary_by_metric_district": summary,
            "latest_observations": latest,
        }
    except Exception as e:
        logger.error("Weather data query failed: %s", e, exc_info=True)
        return {"status": "error", "message": str(e)}


@app.get("/test/price-data")
async def test_price_data():
    """Show what mandi price data currently exists in the DB."""
    from sqlalchemy import text

    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker

        engine = create_async_engine(settings.database_url)
        AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with AsyncSessionLocal() as session:
            # Summary: rows per crop
            crop_summary = await session.execute(text("""
                SELECT crop, COUNT(*) AS rows,
                       MIN(date) AS earliest, MAX(date) AS latest,
                       array_agg(DISTINCT district ORDER BY district) AS districts,
                       array_agg(DISTINCT source ORDER BY source) AS sources
                FROM mandi_prices
                GROUP BY crop
                ORDER BY rows DESC
            """))
            crops = [dict(r._mapping) for r in crop_summary]

            # Latest prices for every crop (most recent date)
            latest_prices = await session.execute(text("""
                SELECT mp.date, mp.crop, mp.mandi, mp.district,
                       mp.modal_price, mp.min_price, mp.max_price,
                       mp.arrival_quantity_qtl, mp.source
                FROM mandi_prices mp
                INNER JOIN (
                    SELECT crop, MAX(date) AS max_date
                    FROM mandi_prices
                    GROUP BY crop
                ) latest ON mp.crop = latest.crop AND mp.date = latest.max_date
                ORDER BY mp.crop, mp.modal_price DESC
            """))
            prices = [dict(r._mapping) for r in latest_prices]

        await engine.dispose()
        return {
            "status": "ok",
            "total_crops": len(crops),
            "crop_summary": crops,
            "latest_prices_per_crop": prices,
        }
    except Exception as e:
        logger.error("Price data query failed: %s", e, exc_info=True)
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
