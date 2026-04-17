"""Tests for Module 8 — Celery broadcast scheduler."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.price.formatter import format_price_reply
from src.price.models import MandiPriceRecord, PriceQuery, PriceQueryResult
from src.models.farmer import Farmer


class TestBroadcastPriceFormatting:
    """Test that broadcast messages are properly formatted."""

    def test_broadcast_message_marathi(self):
        """Verify Marathi message format for broadcast."""
        rec = MandiPriceRecord(
            date="2026-04-17",
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
        msg = format_price_reply(result, lang="mr")
        assert "🌾" in msg
        assert "Onion" in msg
        assert "₹2500" in msg
        assert "nhrdf" in msg

    def test_broadcast_message_english(self):
        """Verify English message format."""
        rec = MandiPriceRecord(
            date="2026-04-17",
            apmc="ahmednagar",
            mandi_display="Ahmednagar",
            commodity="tur",
            variety=None,
            modal_price=Decimal("7800"),
            min_price=None,
            max_price=None,
            source="agmarknet",
        )
        result = PriceQueryResult(
            query=PriceQuery(commodity="tur"),
            records=[rec],
            found=True,
        )
        msg = format_price_reply(result, lang="en")
        assert "🌾" in msg
        assert "Tur" in msg
        assert "₹7800" in msg


class TestFarmerModel:
    """Test Farmer model attributes for broadcast."""

    def test_farmer_has_subscription_status(self):
        """Farmer should have subscription_status field."""
        farmer = Farmer(
            phone="919876543210",
            name="Rajesh",
            district="pune",
            subscription_status="active",
            onboarding_state="active",
            preferred_language="mr",
        )
        assert farmer.subscription_status == "active"
        assert farmer.preferred_language == "mr"
        assert farmer.district == "pune"


class TestBroadcastTaskMocking:
    """Mock tests for broadcast task flow."""

    @pytest.mark.asyncio
    async def test_broadcast_task_would_send_to_multiple_crops(self):
        """Simulate: farmer has 3 crops, gets 3 broadcast messages."""
        crops = ["onion", "tur", "tomato"]
        farmer_lang = "mr"

        messages = []
        for crop in crops:
            rec = MandiPriceRecord(
                date="2026-04-17",
                apmc="test_apmc",
                mandi_display="Test Mandi",
                commodity=crop,
                variety=None,
                modal_price=Decimal("5000"),
                min_price=None,
                max_price=None,
                source="test",
            )
            result = PriceQueryResult(
                query=PriceQuery(commodity=crop),
                records=[rec],
                found=True,
            )
            msg = format_price_reply(result, lang=farmer_lang)
            messages.append(msg)

        assert len(messages) == 3
        for msg in messages:
            assert "🌾" in msg


class TestCeleryConfig:
    """Test Celery app configuration."""

    def test_celery_beat_schedule_exists(self):
        """Verify beat schedule is configured."""
        from src.scheduler.celery_app import app
        assert "broadcast-prices-daily" in app.conf.beat_schedule
        schedule = app.conf.beat_schedule["broadcast-prices-daily"]
        assert schedule["task"] == "src.scheduler.tasks.broadcast_prices"
        # crontab hour/minute are sets
        assert 6 in schedule["schedule"].hour
        assert 30 in schedule["schedule"].minute
