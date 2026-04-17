"""Speech-to-Text (STT) transcriber for voice messages.

Supports:
- Google Cloud Speech-to-Text API (primary: ~95% Marathi accuracy)
- OpenAI Whisper (fallback: ~90% Marathi accuracy)

Design:
- Download audio from Meta WhatsApp Cloud API URL (24-hour expiry)
- Convert to Marathi text with language code mr-IN
- Graceful fallback: if STT fails, raise TranscriptionError
- Timeout: 30 seconds max per transcription request
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional
from dataclasses import dataclass

import httpx
from google.cloud import speech_v1
import openai

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when audio transcription fails."""
    pass


@dataclass
class TranscriptionResult:
    """Result of speech-to-text transcription."""
    text: str
    """Transcribed text (Marathi or English)."""
    language: Optional[str] = None
    """Detected language code (e.g., 'mr-IN' for Marathi)."""
    confidence: Optional[float] = None
    """Transcription confidence (0.0-1.0), if provided by service."""


class VoiceTranscriber:
    """Transcribe audio messages to text using Google Cloud STT or Whisper.

    Usage:
        transcriber = VoiceTranscriber(config)
        result = await transcriber.transcribe(media_url="https://...")
        print(result.text)  # "कांदा दर काय?"
    """

    def __init__(self, config: dict):
        """Initialize transcriber with STT service config.

        Args:
            config: Dictionary with keys:
                - google_speech_api_key: Google Cloud API key (for Google Cloud STT)
                - google_speech_language_code: Language code, default "mr-IN" (Marathi)
                - voice_transcription_timeout: Max seconds per request, default 30
                - openai_api_key: OpenAI API key (for Whisper fallback)
        """
        self.config = config
        self.timeout = config.get("voice_transcription_timeout", 30)
        self.language_code = config.get("google_speech_language_code", "mr-IN")
        self.google_api_key = config.get("google_speech_api_key", "")
        self.openai_api_key = config.get("openai_api_key", "")

        # Initialize clients
        self.google_speech_client: Optional[speech_v1.SpeechClient] = None
        if self.google_api_key:
            try:
                self.google_speech_client = speech_v1.SpeechClient()
                logger.info("✅ Google Cloud Speech-to-Text initialized")
            except Exception as e:
                logger.error(f"❌ Google Cloud STT init failed: {e}")

        if self.openai_api_key:
            openai.api_key = self.openai_api_key
            logger.info("✅ OpenAI Whisper initialized")

    async def transcribe(self, media_url: str) -> TranscriptionResult:
        """Download audio from Media URL and transcribe to text.

        Flow:
        1. Download audio from Meta's media_url (24-hour expiry)
        2. Transcribe using Google Cloud STT or Whisper
        3. Return transcribed text or raise TranscriptionError

        Args:
            media_url: Meta WhatsApp Cloud API audio URL (expires in 24 hours)

        Returns:
            TranscriptionResult with transcribed text

        Raises:
            TranscriptionError: On download failure or API error
        """
        try:
            # Step 1: Download audio from Meta URL
            audio_bytes = await self._download_audio(media_url)
            logger.info(f"✅ Downloaded audio from {media_url[:50]}... ({len(audio_bytes)} bytes)")

            # Step 2: Try Google Cloud STT first (if configured)
            if self.google_speech_client:
                try:
                    result = await self._transcribe_google_cloud(audio_bytes)
                    logger.info(f"✅ Google Cloud transcription: {result.text[:50]}...")
                    return result
                except Exception as e:
                    logger.warning(f"⚠️  Google Cloud STT failed: {e}. Trying Whisper fallback...")

            # Step 3: Fallback to Whisper if Google Cloud unavailable/failed
            if self.openai_api_key:
                try:
                    result = await self._transcribe_whisper(audio_bytes)
                    logger.info(f"✅ Whisper transcription: {result.text[:50]}...")
                    return result
                except Exception as e:
                    logger.error(f"❌ Whisper STT failed: {e}")
                    raise TranscriptionError(f"All STT services failed: {e}")

            # No STT service available
            raise TranscriptionError("No STT service configured (Google Cloud or Whisper)")

        except asyncio.TimeoutError:
            logger.error("❌ Transcription timeout (>30 seconds)")
            raise TranscriptionError("Transcription timeout")
        except Exception as e:
            logger.error(f"❌ Transcription failed: {e}")
            raise TranscriptionError(str(e))

    async def _download_audio(self, media_url: str) -> bytes:
        """Download audio file from Meta's media URL.

        Args:
            media_url: Meta WhatsApp Cloud API media URL

        Returns:
            Audio file bytes (OGG Opus format)

        Raises:
            TranscriptionError: On download failure
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(media_url, follow_redirects=True)
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as e:
            raise TranscriptionError(f"Failed to download audio: {e}")

    async def _transcribe_google_cloud(self, audio_bytes: bytes) -> TranscriptionResult:
        """Transcribe audio using Google Cloud Speech-to-Text API.

        Language: Marathi (mr-IN)
        Encoding: OGG_OPUS (from Meta WhatsApp)

        Args:
            audio_bytes: Audio file bytes

        Returns:
            TranscriptionResult with transcribed Marathi text

        Raises:
            TranscriptionError: On API error or timeout
        """
        try:
            # Prepare Google Cloud Speech config
            config = speech_v1.RecognitionConfig(
                encoding=speech_v1.RecognitionConfig.AudioEncoding.OGG_OPUS,
                language_code=self.language_code,  # "mr-IN"
                enable_automatic_punctuation=True,
            )

            audio = speech_v1.RecognitionAudio(content=audio_bytes)

            # Call Google Cloud API (runs in thread to avoid blocking)
            def _call_api():
                response = self.google_speech_client.recognize(config=config, audio=audio)
                if response.results:
                    result = response.results[0]
                    if result.alternatives:
                        alt = result.alternatives[0]
                        return TranscriptionResult(
                            text=alt.transcript,
                            language=self.language_code,
                            confidence=alt.confidence,
                        )
                return None

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _call_api),
                timeout=self.timeout
            )

            if not result or not result.text:
                raise TranscriptionError("No speech detected in audio")

            return result

        except asyncio.TimeoutError:
            raise TranscriptionError("Google Cloud STT timeout")
        except Exception as e:
            raise TranscriptionError(f"Google Cloud STT error: {e}")

    async def _transcribe_whisper(self, audio_bytes: bytes) -> TranscriptionResult:
        """Transcribe audio using OpenAI Whisper API.

        Language: Auto-detected (Whisper supports 99 languages including Marathi)

        Args:
            audio_bytes: Audio file bytes

        Returns:
            TranscriptionResult with transcribed text

        Raises:
            TranscriptionError: On API error or timeout
        """
        try:
            import tempfile
            import os

            # Save audio to temporary file (Whisper API requires file object)
            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                temp_path = f.name
                f.write(audio_bytes)

            try:
                # Call Whisper API in executor to avoid blocking
                def _call_api():
                    with open(temp_path, "rb") as audio_file:
                        transcript = openai.Audio.transcribe(
                            model="whisper-1",
                            file=audio_file,
                        )
                    return TranscriptionResult(
                        text=transcript.text,
                        language=None,  # Whisper auto-detects
                        confidence=None,
                    )

                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, _call_api),
                    timeout=self.timeout
                )

                if not result or not result.text:
                    raise TranscriptionError("No speech detected in audio")

                return result

            finally:
                # Clean up temporary file
                os.unlink(temp_path)

        except asyncio.TimeoutError:
            raise TranscriptionError("Whisper timeout")
        except Exception as e:
            raise TranscriptionError(f"Whisper error: {e}")
