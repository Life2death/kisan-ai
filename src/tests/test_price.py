"""Tests for Module 7 — price handler."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock
import pytest

from src.classifier.intents import Intent, IntentResult
from src.price.formatter import format_price_reply, format_price_query_needed
from src.price.handler import PriceHandler
from src.price.models import MandiPriceRecord, PriceQuery, PriceQueryResult


class TestMandiPriceRecord:
    def test_price_str(self):
        rec = MandiPriceRecord(
            date=date(2026, 4, 17),
            apmc="lasalgaon",
            mandi_display="Lasalgaon",
            commodity="onion",
            variety=None,
            modal_price=Decimal("2500"),
            min_price=Decimal("2400"),
            max_price=Decimal("2600"),
            source="nhrdf",
        )
        assert rec.price_str == "₹2500/क्विंटल"

    def test_range_str(self):
        rec = MandiPriceRecord(
            date=date(2026, 4, 17),
            apmc="lasalgaon",
            mandi_display="Lasalgaon",
            commodity="onion",
            variety=None,
            modal_price=Decimal("2500"),
            min_price=Decimal("2400"),
            max_price=Decimal("2600"),
            source="nhrdf",
        )
        assert rec.range_str == "(₹2400 - ₹2600)"


class TestFormatter:
    def test_format_price_reply_marathi(self):
        rec = MandiPriceRecord(
            date=date(2026, 4, 17),
            apmc="lasalgaon",
            mandi_display="Lasalgaon",
            commodity="onion",
            variety=None,
            modal_price=Decimal("2500"),
            min_price=Decimal("2400"),
            max_price=Decimal("2600"),
            source="nhrdf",
        )
        result = PriceQueryResult(
            query=PriceQuery(commodity="onion"),
            records=[rec],
            found=True,
        )
        reply = format_price_reply(result, lang="mr")
        assert "🌾" in reply
        assert "Onion" in reply
        assert "₹2500" in reply
        assert "Lasalgaon" in reply

    def test_format_price_reply_no_data(self):
        result = PriceQueryResult(
            query=PriceQuery(commodity="onion"),
            records=[],
            found=False,
        )
        reply = format_price_reply(result, lang="mr")
        assert "उपलब्ध नाही" in reply

    def test_format_price_query_needed_marathi(self):
        reply = format_price_query_needed("onion", lang="mr")
        assert "कोण सा पीक" in reply

    def test_format_price_query_needed_english(self):
        reply = format_price_query_needed("", lang="en")
        assert "Which crop" in reply


class TestPriceHandler:
    @pytest.mark.asyncio
    async def test_handle_price_query_found(self):
        intent = IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=1.0,
            commodity="onion",
            district="nashik",
            source="regex",
            raw_text="nashik onion price",
        )
        rec = MandiPriceRecord(
            date=date(2026, 4, 17),
            apmc="lasalgaon",
            mandi_display="Lasalgaon",
            commodity="onion",
            variety=None,
            modal_price=Decimal("2500"),
            min_price=None,
            max_price=None,
            source="nhrdf",
        )
        mock_session = AsyncMock()
        handler = PriceHandler(mock_session)
        handler.repo.query = AsyncMock(return_value=PriceQueryResult(
            query=PriceQuery(commodity="onion", district="nashik"),
            records=[rec],
            found=True,
        ))
        reply = await handler.handle(intent)
        assert "₹2500" in reply
        assert "Lasalgaon" in reply

    @pytest.mark.asyncio
    async def test_handle_missing_commodity(self):
        intent = IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=0.85,
            commodity=None,
            source="regex",
            raw_text="price please",
        )
        mock_session = AsyncMock()
        handler = PriceHandler(mock_session)
        reply = await handler.handle(intent)
        assert "कोण सा पीक" in reply or "Which crop" in reply

    @pytest.mark.asyncio
    async def test_handle_fallback_farmer_district(self):
        intent = IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=1.0,
            commodity="tur",
            district=None,  # not specified
            source="regex",
            raw_text="tur price",
        )
        rec = MandiPriceRecord(
            date=date(2026, 4, 17),
            apmc="ahmednagar",
            mandi_display="Ahmednagar",
            commodity="tur",
            variety=None,
            modal_price=Decimal("7800"),
            min_price=None,
            max_price=None,
            source="agmarknet",
        )
        mock_session = AsyncMock()
        handler = PriceHandler(mock_session)
        handler.repo.query = AsyncMock(return_value=PriceQueryResult(
            query=PriceQuery(commodity="tur"),
            records=[rec],
            found=True,
        ))
        reply = await handler.handle(intent, farmer_district="ahilyanagar")
        handler.repo.query.assert_called_once()
        call_args = handler.repo.query.call_args
        assert call_args[1]["farmer_district"] == "ahilyanagar"
