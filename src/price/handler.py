"""Price query handler — main entrypoint."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.classifier.intents import IntentResult
from src.price.formatter import format_price_query_needed, format_price_reply
from src.price.models import PriceQuery
from src.price.repository import PriceRepository

logger = logging.getLogger(__name__)


class PriceHandler:
    """Handle PRICE_QUERY intents."""

    def __init__(self, session: AsyncSession):
        self.repo = PriceRepository(session)

    async def handle(
        self,
        intent: IntentResult,
        farmer_district: Optional[str] = None,
        farmer_language: str = "mr",
    ) -> str:
        """
        Process a PRICE_QUERY intent, return reply message.

        Args:
            intent: IntentResult with commodity + district (from classifier)
            farmer_district: farmer's registered district (fallback if not in intent)
            farmer_language: mr or en
        """
        # Sanity check
        if not intent.is_price_query:
            return "Error: wrong intent type"

        # If classifier found no commodity, ask which one
        if intent.needs_commodity:
            return format_price_query_needed("", lang=farmer_language)

        # Build query
        query = PriceQuery(
            commodity=intent.commodity,
            district=intent.district,  # may be None
        )

        # Query Postgres
        result = await self.repo.query(query, farmer_district=farmer_district)

        # Format reply
        reply = format_price_reply(result, lang=farmer_language)
        logger.info(
            "price_handler: commodity=%s district=%s farmer_district=%s found=%s",
            intent.commodity, intent.district, farmer_district, result.found,
        )
        return reply
