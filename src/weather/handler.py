"""Handler for WEATHER_QUERY intents (Phase 2 Module 1)."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.classifier.intents import Intent, IntentResult
from src.weather.formatter import format_weather_reply, format_weather_not_extracted
from src.weather.models import WeatherQuery
from src.weather.repository import WeatherRepository

logger = logging.getLogger(__name__)


class WeatherHandler:
    """Handle WEATHER_QUERY intents and produce formatted replies."""

    def __init__(self, session: AsyncSession):
        """Initialize handler with a database session.

        Args:
            session: AsyncSession for database operations
        """
        self.repo = WeatherRepository(session)

    async def handle(
        self,
        intent: IntentResult,
        farmer_apmc: Optional[str] = None,
        farmer_language: str = "mr",
    ) -> str:
        """Process a WEATHER_QUERY intent and return formatted reply.

        Args:
            intent: IntentResult from classifier (must have intent=WEATHER_QUERY)
            farmer_apmc: Farmer's registered APMC (used if not in intent)
            farmer_language: Farmer's preferred language ("mr" or "en")

        Returns:
            Formatted WhatsApp reply message
        """
        if intent.intent != Intent.WEATHER_QUERY:
            logger.error("WeatherHandler: wrong intent type: %s", intent.intent)
            return "Error: expected WEATHER_QUERY intent"

        # If metric not extracted, ask for clarification
        if not intent.commodity:
            reply = format_weather_not_extracted(lang=farmer_language)
            logger.info("WeatherHandler: metric not extracted, asking for clarification")
            return reply

        # Build query
        query = WeatherQuery(
            metric=intent.commodity,  # e.g., "temperature", "rainfall"
            apmc=intent.district or farmer_apmc,
        )

        logger.info(
            "WeatherHandler: querying metric=%s apmc=%s",
            query.metric,
            query.apmc,
        )

        # Query weather data
        result = await self.repo.query(query)

        # Format reply
        reply = format_weather_reply(result, lang=farmer_language)

        logger.info("WeatherHandler: generated reply (%d chars)", len(reply))
        return reply
