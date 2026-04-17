"""Tests for Phase 2 Module 2 — Voice Message Support.

Covers:
- Speech-to-Text transcription (Google Cloud, Whisper)
- Webhook audio message handling
- Intent classification from transcribed text
- Error handling (timeouts, failed transcriptions)
- Integration with existing intent handlers
"""
from __future__ import annotations

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import json

from src.handlers.webhook import IncomingMessage, parse_webhook_message, handle_message
from src.ingestion.transcriber import VoiceTranscriber, TranscriptionError, TranscriptionResult
from src.voice.formatter import format_transcription_failed, format_transcription_empty
from src.classifier.intents import Intent, IntentResult


class TestVoiceTranscription:
    """Test speech-to-text transcription services."""

    def test_transcription_result_dataclass(self):
        """Test TranscriptionResult dataclass creation."""
        result = TranscriptionResult(
            text="कांदा पुणे दर काय?",
            language="mr-IN",
            confidence=0.98
        )
        assert result.text == "कांदा पुणे दर काय?"
        assert result.language == "mr-IN"
        assert result.confidence == 0.98

    @pytest.mark.asyncio
    async def test_transcriber_google_cloud_success(self):
        """Test successful Google Cloud transcription."""
        config = {
            "google_speech_api_key": "test-key",
            "google_speech_language_code": "mr-IN",
            "voice_transcription_timeout": 30,
        }

        transcriber = VoiceTranscriber(config)

        # Mock Google Cloud API
        mock_response = MagicMock()
        mock_response.results = [MagicMock()]
        mock_response.results[0].alternatives = [MagicMock()]
        mock_response.results[0].alternatives[0].transcript = "कांदा दर काय?"
        mock_response.results[0].alternatives[0].confidence = 0.95

        with patch.object(transcriber.google_speech_client, 'recognize', return_value=mock_response):
            result = await transcriber.transcribe("https://example.com/audio.ogg")
            assert result.text == "कांदा दर काय?"
            assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_transcriber_timeout(self):
        """Test transcription timeout handling."""
        config = {
            "google_speech_api_key": "test-key",
            "voice_transcription_timeout": 1,
        }

        transcriber = VoiceTranscriber(config)

        # Mock slow API
        async def slow_download(url):
            import asyncio
            await asyncio.sleep(2)  # Exceeds 1-second timeout
            return b"audio data"

        with patch.object(transcriber, '_download_audio', side_effect=slow_download):
            with pytest.raises(TranscriptionError, match="timeout"):
                await transcriber.transcribe("https://example.com/audio.ogg")

    @pytest.mark.asyncio
    async def test_transcriber_no_speech_detected(self):
        """Test transcription when audio contains no speech."""
        config = {
            "google_speech_api_key": "test-key",
            "google_speech_language_code": "mr-IN",
            "voice_transcription_timeout": 30,
        }

        transcriber = VoiceTranscriber(config)

        # Mock empty response (no speech detected)
        mock_response = MagicMock()
        mock_response.results = []

        with patch.object(transcriber.google_speech_client, 'recognize', return_value=mock_response):
            with pytest.raises(TranscriptionError, match="No speech"):
                await transcriber.transcribe("https://example.com/silence.ogg")

    @pytest.mark.asyncio
    async def test_transcriber_network_error(self):
        """Test transcription with network failure."""
        config = {
            "google_speech_api_key": "test-key",
            "voice_transcription_timeout": 30,
        }

        transcriber = VoiceTranscriber(config)

        import httpx
        with patch.object(transcriber, '_download_audio', side_effect=httpx.ConnectError("Connection failed")):
            with pytest.raises(TranscriptionError, match="download"):
                await transcriber.transcribe("https://invalid-url.example.com/audio.ogg")


class TestVoiceWebhookHandling:
    """Test webhook parsing and audio message handling."""

    def test_audio_message_parsed_correctly(self):
        """Test webhook parser extracts audio metadata."""
        webhook_data = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "919999999999",
                            "id": "wamid.xxx",
                            "timestamp": "1608669141",
                            "type": "audio",
                            "audio": {
                                "mime_type": "audio/ogg",
                                "id": "139-char-media-id-here"
                            }
                        }]
                    }
                }]
            }]
        }

        messages = parse_webhook_message(webhook_data)
        assert len(messages) == 1
        msg = messages[0]
        assert msg.is_audio() is True
        assert msg.media_id == "139-char-media-id-here"
        assert msg.mime_type == "audio/ogg"
        assert msg.from_phone == "919999999999"

    def test_incoming_message_is_audio_method(self):
        """Test IncomingMessage.is_audio() method."""
        msg_text = IncomingMessage(
            from_phone="919999999999",
            message_id="msg1",
            message_type="text",
            text="कांदा दर?"
        )
        assert msg_text.is_audio() is False
        assert msg_text.is_text() is True

        msg_audio = IncomingMessage(
            from_phone="919999999999",
            message_id="msg2",
            message_type="audio",
            media_id="media-id-123",
            media_url="https://example.com/audio.ogg",
            mime_type="audio/ogg"
        )
        assert msg_audio.is_audio() is True
        assert msg_audio.is_text() is False

    def test_voice_message_stored_with_metadata(self):
        """Test that voice transcription can be stored in IncomingMessage."""
        msg = IncomingMessage(
            from_phone="919999999999",
            message_id="msg1",
            message_type="audio",
            media_url="https://example.com/audio.ogg"
        )

        # Simulate transcription
        msg.text = "कांदा पुणे दर काय?"
        msg.voice_transcription = "कांदा पुणे दर काय?"

        assert msg.text == "कांदा पुणे दर काय?"
        assert msg.voice_transcription == "कांदा पुणे दर काय?"
        assert msg.is_marathi() is True

    @pytest.mark.asyncio
    async def test_handle_message_routes_transcribed_text(self):
        """Test that handle_message routes transcribed audio through classifier."""
        msg = IncomingMessage(
            from_phone="919999999999",
            message_id="msg1",
            message_type="audio",
            media_url="https://example.com/audio.ogg"
        )

        # Mock VoiceTranscriber
        with patch('src.handlers.webhook.VoiceTranscriber') as mock_transcriber_class:
            mock_transcriber = MagicMock()
            mock_transcriber.transcribe = AsyncMock(
                return_value=TranscriptionResult(
                    text="कांदा दर काय?",
                    confidence=0.95
                )
            )
            mock_transcriber_class.return_value = mock_transcriber

            # Mock classify
            with patch('src.handlers.webhook.classify') as mock_classify:
                mock_classify.return_value = IntentResult(
                    intent=Intent.PRICE_QUERY,
                    confidence=0.99,
                    commodity="onion",
                    district="pune"
                )

                result = await handle_message(msg)

                # Verify transcription was called
                mock_transcriber.transcribe.assert_called_once_with("https://example.com/audio.ogg")

                # Verify classify was called with transcribed text
                mock_classify.assert_called_once_with("कांदा दर काय?")

                # Verify result contains classified intent
                assert result["intent"] == "price_query"
                assert result["commodity"] == "onion"
                assert result["district"] == "pune"


class TestVoiceIntentClassification:
    """Test intent classification from voice transcriptions."""

    @pytest.mark.asyncio
    async def test_voice_price_query(self):
        """Test audio message classified as PRICE_QUERY."""
        msg = IncomingMessage(
            from_phone="919999999999",
            message_id="msg1",
            message_type="audio",
            text="कांदा दर?",  # Simulating transcription
        )

        with patch('src.handlers.webhook.classify') as mock_classify:
            mock_classify.return_value = IntentResult(
                intent=Intent.PRICE_QUERY,
                confidence=1.0,
                commodity="onion",
                district=None
            )

            result = await handle_message(msg)
            assert result["intent"] == "price_query"
            assert result["commodity"] == "onion"

    @pytest.mark.asyncio
    async def test_voice_weather_query(self):
        """Test audio message classified as WEATHER_QUERY."""
        msg = IncomingMessage(
            from_phone="919999999999",
            message_id="msg2",
            message_type="audio",
            text="हवामान काय?",  # Simulating transcription
        )

        with patch('src.handlers.webhook.classify') as mock_classify:
            mock_classify.return_value = IntentResult(
                intent=Intent.WEATHER_QUERY,
                confidence=1.0,
                commodity="temperature",
                district="pune"
            )

            result = await handle_message(msg)
            assert result["intent"] == "weather_query"
            assert result["commodity"] == "temperature"

    @pytest.mark.asyncio
    async def test_voice_with_district_extraction(self):
        """Test voice message with district extraction."""
        msg = IncomingMessage(
            from_phone="919999999999",
            message_id="msg3",
            message_type="audio",
            text="नाशिक मध्ये पाऊस कितना?",  # "How much rain in Nashik?"
        )

        with patch('src.handlers.webhook.classify') as mock_classify:
            mock_classify.return_value = IntentResult(
                intent=Intent.WEATHER_QUERY,
                confidence=0.98,
                commodity="rainfall",
                district="nashik"
            )

            result = await handle_message(msg)
            assert result["intent"] == "weather_query"
            assert result["commodity"] == "rainfall"
            assert result["district"] == "nashik"

    @pytest.mark.asyncio
    async def test_voice_unknown_intent(self):
        """Test voice message with unrecognized speech."""
        msg = IncomingMessage(
            from_phone="919999999999",
            message_id="msg4",
            message_type="audio",
            text="अरे मला काहीतरी सांग",  # Random Marathi phrase
        )

        with patch('src.handlers.webhook.classify') as mock_classify:
            mock_classify.return_value = IntentResult(
                intent=Intent.UNKNOWN,
                confidence=0.2,
            )

            result = await handle_message(msg)
            assert result["intent"] == "unknown"


class TestVoiceErrorHandling:
    """Test error handling for voice messages."""

    @pytest.mark.asyncio
    async def test_transcription_failure_returns_error_status(self):
        """Test that transcription failure returns proper error status."""
        msg = IncomingMessage(
            from_phone="919999999999",
            message_id="msg1",
            message_type="audio",
            media_url="https://example.com/corrupted.ogg"
        )

        with patch('src.handlers.webhook.VoiceTranscriber') as mock_transcriber_class:
            mock_transcriber = MagicMock()
            mock_transcriber.transcribe = AsyncMock(
                side_effect=TranscriptionError("Audio file corrupted")
            )
            mock_transcriber_class.return_value = mock_transcriber

            result = await handle_message(msg)

            assert result["status"] == "transcription_failed"
            assert result["intent"] == "unknown"
            assert "corrupted" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_media_url(self):
        """Test audio message without media URL."""
        msg = IncomingMessage(
            from_phone="919999999999",
            message_id="msg1",
            message_type="audio",
            # No media_url provided
        )

        result = await handle_message(msg)

        assert result["status"] == "audio_error"
        assert result["intent"] == "unknown"
        assert "media URL" in result["error"]

    @pytest.mark.asyncio
    async def test_transcription_timeout(self):
        """Test handling of transcription timeout (>30 seconds)."""
        msg = IncomingMessage(
            from_phone="919999999999",
            message_id="msg1",
            message_type="audio",
            media_url="https://example.com/slow-audio.ogg"
        )

        with patch('src.handlers.webhook.VoiceTranscriber') as mock_transcriber_class:
            mock_transcriber = MagicMock()
            mock_transcriber.transcribe = AsyncMock(
                side_effect=TranscriptionError("Transcription timeout")
            )
            mock_transcriber_class.return_value = mock_transcriber

            result = await handle_message(msg)

            assert result["status"] == "transcription_failed"
            assert "timeout" in result["error"]


class TestVoiceFormatting:
    """Test voice message formatters."""

    def test_format_transcription_failed_marathi(self):
        """Test failed transcription message in Marathi."""
        reply = format_transcription_failed(lang="mr")
        assert "दिसून आले नाही" in reply or "कृपया" in reply
        assert isinstance(reply, str)
        assert len(reply) > 0

    def test_format_transcription_failed_english(self):
        """Test failed transcription message in English."""
        reply = format_transcription_failed(lang="en")
        assert "couldn't understand" in reply.lower()
        assert "text message" in reply.lower()

    def test_format_transcription_empty_marathi(self):
        """Test no-speech-detected message in Marathi."""
        reply = format_transcription_empty(lang="mr")
        assert "बोली" in reply or "कृपया" in reply
        assert isinstance(reply, str)

    def test_format_transcription_empty_english(self):
        """Test no-speech-detected message in English."""
        reply = format_transcription_empty(lang="en")
        assert "didn't hear" in reply.lower()
        assert "speak clearly" in reply.lower()

    def test_format_fallback_default_english(self):
        """Test that unknown language defaults to English."""
        reply = format_transcription_failed(lang="unknown")
        assert "couldn't understand" in reply.lower()


class TestVoiceWebhookParsing:
    """Test comprehensive webhook parsing for audio messages."""

    def test_parse_multiple_messages_mixed_types(self):
        """Test parsing webhook with mixed text and audio messages."""
        webhook_data = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [
                            {
                                "from": "919999999999",
                                "id": "msg1",
                                "type": "text",
                                "text": {"body": "कांदा दर"}
                            },
                            {
                                "from": "919999999999",
                                "id": "msg2",
                                "type": "audio",
                                "audio": {
                                    "mime_type": "audio/ogg",
                                    "id": "media-id-audio"
                                }
                            }
                        ]
                    }
                }]
            }]
        }

        messages = parse_webhook_message(webhook_data)
        assert len(messages) == 2

        # First message is text
        assert messages[0].is_text() is True
        assert messages[0].text == "कांदा दर"

        # Second message is audio
        assert messages[1].is_audio() is True
        assert messages[1].media_id == "media-id-audio"

    def test_parse_image_message(self):
        """Test parsing of image message (for future Phase 2 Module 3)."""
        webhook_data = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "919999999999",
                            "id": "img1",
                            "type": "image",
                            "image": {
                                "mime_type": "image/jpeg",
                                "id": "media-id-image"
                            }
                        }]
                    }
                }]
            }]
        }

        messages = parse_webhook_message(webhook_data)
        assert len(messages) == 1
        assert messages[0].message_type == "image"
        assert messages[0].media_id == "media-id-image"
        assert messages[0].mime_type == "image/jpeg"
