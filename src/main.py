"""
Kisan AI FastAPI Application with WhatsApp Webhook.

This is the main entry point for the bot.
Run: uvicorn src.main:app --reload
"""

import logging
import os
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import json

from src.adapters.whatsapp import WhatsAppAdapter, WhatsAppConfig, init_adapter, get_adapter

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Kisan AI",
    description="WhatsApp bot for Maharashtra farmers",
    version="1.0.0",
)

# Initialize WhatsApp adapter on startup
@app.on_event("startup")
async def startup_event():
    """Initialize WhatsApp adapter with credentials from .env"""
    try:
        config = WhatsAppConfig(
            phone_id=os.getenv("WHATSAPP_PHONE_ID", ""),
            token=os.getenv("WHATSAPP_TOKEN", ""),
            business_account_id=os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID"),
        )
        adapter = init_adapter(config)
        logger.info("✅ WhatsApp adapter initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize WhatsApp adapter: {e}")
        raise


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
    """Health check endpoint"""
    return {"status": "ok", "service": "Kisan AI Bot"}


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
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "kisan_webhook_token")
    
    if hub_mode == "subscribe" and hub_verify_token == verify_token:
        logger.info("✅ Webhook verified by Meta")
        return hub_challenge
    
    logger.warning(f"❌ Invalid webhook verification attempt")
    raise HTTPException(status_code=403, detail="Invalid verification token")


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

            # Handle audio messages: get media URL for transcription
            if msg.is_audio():
                if msg.media_id:
                    try:
                        media_url = await whatsapp.get_media_url(msg.media_id)
                        msg.media_url = media_url
                        logger.info(f"✅ Got media URL for audio message from {msg.from_phone}")
                    except Exception as e:
                        logger.error(f"❌ Failed to get media URL: {e}")
                        # Continue anyway - handle_message() will handle the error
                else:
                    logger.error(f"⚠️  Audio message missing media_id from {msg.from_phone}")
                    continue

            # Skip non-text, non-audio messages
            if not msg.is_text() and not msg.is_audio():
                logger.info(f"⚠️  Unsupported message type '{msg.message_type}' from {msg.from_phone}, skipping")
                continue

            # Log message preview (text or "Voice message" for audio)
            msg_preview = msg.text if msg.text else "Voice message"
            logger.info(f"📱 Message from {msg.from_phone}: {msg_preview}")

            try:
                # Classify intent
                result = await handle_message(msg)
                intent_type = Intent(result.get("intent", "unknown"))

                logger.info(
                    f"🧠 Classified: intent={intent_type.value} confidence={result.get('confidence', 0):.2f}"
                )

                # Route based on intent
                async with async_session() as session:

                    # Weather query (Phase 2)
                    if intent_type == Intent.WEATHER_QUERY:
                        handler = WeatherHandler(session)
                        # For now, assume farmer's default district
                        # In production, look up farmer profile from database
                        reply = await handler.handle(
                            result,
                            farmer_apmc="pune",  # TODO: lookup from farmer profile
                            farmer_language="mr",  # TODO: lookup from farmer profile
                        )
                        await whatsapp.send_text_message(msg.from_phone, reply)
                        logger.info(f"✅ Sent weather reply to {msg.from_phone}")

                    # Other intents (PRICE_QUERY, SUBSCRIBE, ONBOARDING, etc.)
                    # TODO: Add handlers for these intents
                    else:
                        logger.info(f"ℹ️  Intent {intent_type.value} not yet routed (stub)")

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
