"""WhatsApp Webhook Message Handler.

Processes incoming WhatsApp messages from Meta and routes them through
the intent classifier. Supports text, audio (with transcription), and other message types.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.classifier.classify import classify
from src.classifier.intents import Intent, IntentResult
from src.ingestion.transcriber import VoiceTranscriber, TranscriptionError
from src.voice.formatter import format_transcription_failed
from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class IncomingMessage:
    """Parsed incoming WhatsApp message."""
    from_phone: str
    message_id: str
    message_type: str   # text, image, document, audio, location, etc.
    text: Optional[str] = None
    timestamp: Optional[str] = None
    # Phase 2 Module 2: Audio message fields
    media_id: Optional[str] = None  # Meta's 139-char media ID
    media_url: Optional[str] = None  # Download URL (24-hour expiry)
    mime_type: Optional[str] = None  # e.g., "audio/ogg"

    def is_text(self) -> bool:
        return self.message_type == "text"

    def is_audio(self) -> bool:
        """Check if this is an audio message."""
        return self.message_type == "audio"

    def is_marathi(self) -> bool:
        """Check if message contains Marathi/Devanagari script (U+0900–U+097F)."""
        if not self.text:
            return False
        return any(0x0900 <= ord(c) <= 0x097F for c in self.text)


def parse_webhook_message(webhook_data: Dict[str, Any]) -> list[IncomingMessage]:
    """Parse Meta's nested webhook JSON into IncomingMessage objects.

    Meta sends:
      {"entry": [{"changes": [{"value": {"messages": [...]}}]}]}

    Handles text, audio, image, and other message types.
    """
    messages: list[IncomingMessage] = []
    try:
        for entry in webhook_data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg_data in value.get("messages", []):
                    msg_type = msg_data.get("type", "text")
                    text_content: Optional[str] = None
                    media_id: Optional[str] = None
                    media_url: Optional[str] = None
                    mime_type: Optional[str] = None

                    # Extract text from text messages
                    if msg_type == "text":
                        text_content = msg_data.get("text", {}).get("body")

                    # Extract media metadata from audio/image/document messages
                    if msg_type == "audio":
                        audio_obj = msg_data.get("audio", {})
                        media_id = audio_obj.get("id")
                        mime_type = audio_obj.get("mime_type")  # e.g., "audio/ogg"
                        # Note: media_url will be populated by WhatsApp adapter's get_media_url()

                    elif msg_type in ("image", "document"):
                        media_obj = msg_data.get(msg_type, {})
                        media_id = media_obj.get("id")
                        mime_type = media_obj.get("mime_type")

                    messages.append(IncomingMessage(
                        from_phone=msg_data.get("from", ""),
                        message_id=msg_data.get("id", ""),
                        message_type=msg_type,
                        text=text_content,
                        timestamp=msg_data.get("timestamp"),
                        media_id=media_id,
                        media_url=media_url,
                        mime_type=mime_type,
                    ))
    except Exception as exc:
        logger.error("parse_webhook_message: error: %s", exc)
    return messages


async def handle_message(message: IncomingMessage) -> Dict[str, Any]:
    """Route an incoming message through intent classification and dispatch.

    Flow:
    1. If audio: transcribe to text (Google Cloud STT or Whisper)
    2. If text (or transcribed): classify intent
    3. Return result dict for webhook logging/ack

    Returns a result dict consumed by the webhook endpoint for logging/ack.
    """
    logger.info("handle_message: from=%s type=%s marathi=%s",
                message.from_phone, message.message_type, message.is_marathi())

    # Phase 2 Module 2: Handle audio messages
    if message.is_audio():
        if not message.media_url:
            logger.error("handle_message: audio message missing media_url")
            return {
                "status": "audio_error",
                "message_id": message.message_id,
                "intent": Intent.UNKNOWN.value,
                "error": "Missing media URL for audio transcription",
            }

        try:
            # Initialize transcriber with config
            transcriber_config = {
                "google_speech_api_key": settings.google_speech_api_key,
                "google_speech_language_code": settings.google_speech_language_code,
                "voice_transcription_timeout": settings.voice_transcription_timeout,
                "openai_api_key": settings.openai_api_key,
            }
            transcriber = VoiceTranscriber(transcriber_config)

            # Transcribe audio to text
            result = await transcriber.transcribe(message.media_url)
            message.text = result.text
            message.voice_transcription = result.text  # Store for audit trail

            logger.info(f"✅ Transcribed audio to text: {result.text[:50]}...")

        except TranscriptionError as e:
            logger.error(f"❌ Audio transcription failed: {e}")
            # Don't block message processing - return error status
            return {
                "status": "transcription_failed",
                "message_id": message.message_id,
                "intent": Intent.UNKNOWN.value,
                "error": str(e),
            }

    # Regular text messages or transcribed audio
    if not message.is_text() or not message.text:
        # Non-audio, non-text messages (images, documents, etc.)
        logger.info(f"⚠️  Non-text, non-audio message type: {message.message_type}")
        return {
            "status": "non_text",
            "message_id": message.message_id,
            "intent": Intent.UNKNOWN.value,
        }

    result: IntentResult = await classify(message.text)

    logger.info(
        "handle_message: intent=%s confidence=%.2f commodity=%s district=%s source=%s",
        result.intent.value, result.confidence,
        result.commodity, result.district, result.source,
    )

    return {
        "status": "classified",
        "message_id": message.message_id,
        "intent": result.intent.value,
        "confidence": result.confidence,
        "commodity": result.commodity,
        "district": result.district,
        "source": result.source,
        "needs_commodity": result.needs_commodity,
        "voice_transcription": getattr(message, 'voice_transcription', None),  # Include if present
    }
