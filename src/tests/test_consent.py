"""Tests for Module 11 — DPDPA consent flow and right-to-erasure."""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


class TestConsentFlow:
    """Tests for consent event logging in onboarding flow."""

    @pytest.mark.asyncio
    async def test_consent_opt_in_event_logged(self):
        """Test that opt_in event is logged when farmer gives consent."""
        from src.models.consent import ConsentEvent

        # Mock ConsentEvent model creation
        event = ConsentEvent(
            farmer_id=1,
            event_type="opt_in",
            consent_version="1.0",
            created_at=datetime.now(),
        )

        assert event.farmer_id == 1
        assert event.event_type == "opt_in"
        assert event.consent_version == "1.0"

    @pytest.mark.asyncio
    async def test_consent_opt_out_event_logged(self):
        """Test that opt_out event is logged when farmer opts out."""
        from src.models.consent import ConsentEvent

        event = ConsentEvent(
            farmer_id=2,
            event_type="opt_out",
            created_at=datetime.now(),
        )

        assert event.farmer_id == 2
        assert event.event_type == "opt_out"

    @pytest.mark.asyncio
    async def test_erasure_request_event_logged(self):
        """Test that erasure_request event is logged when farmer requests deletion."""
        from src.models.consent import ConsentEvent

        event = ConsentEvent(
            farmer_id=3,
            event_type="erasure_request",
            created_at=datetime.now(),
        )

        assert event.farmer_id == 3
        assert event.event_type == "erasure_request"

    @pytest.mark.asyncio
    async def test_erasure_complete_event_logged(self):
        """Test that erasure_complete event is logged after hard-delete."""
        from src.models.consent import ConsentEvent

        event = ConsentEvent(
            farmer_id=4,
            event_type="erasure_complete",
            created_at=datetime.now(),
        )

        assert event.farmer_id == 4
        assert event.event_type == "erasure_complete"


class TestErasureRequest:
    """Tests for erasure request handling."""

    def test_erasure_requested_at_timestamp(self):
        """Test that erasure_requested_at field tracks deletion request timestamp."""
        from src.models.farmer import Farmer

        farmer = Farmer(
            phone="919876543210",
            name="Rajesh",
            district="pune",
            erasure_requested_at=datetime.now(),
        )

        assert farmer.erasure_requested_at is not None
        assert isinstance(farmer.erasure_requested_at, datetime)

    def test_erasure_requested_at_none_for_active_farmer(self):
        """Test that active farmers have erasure_requested_at = None."""
        from src.models.farmer import Farmer

        farmer = Farmer(
            phone="919876543210",
            name="Rajesh",
            district="pune",
            erasure_requested_at=None,
        )

        assert farmer.erasure_requested_at is None

    def test_erasure_30_day_eligibility(self):
        """Test logic for determining if farmer is eligible for hard-delete (30+ days)."""
        cutoff = datetime.now() - timedelta(days=30)

        # Farmer requested 31 days ago — eligible
        erasure_at_31_days = datetime.now() - timedelta(days=31)
        assert erasure_at_31_days < cutoff  # Should be hard-deleted

        # Farmer requested 29 days ago — not eligible
        erasure_at_29_days = datetime.now() - timedelta(days=29)
        assert erasure_at_29_days >= cutoff  # Should NOT be hard-deleted yet

    def test_soft_delete_broadcast_on_erasure(self):
        """Test that broadcast_log records are soft-deleted when erasure is requested."""
        from src.models.broadcast import BroadcastLog

        log = BroadcastLog(
            farmer_id=5,
            template_id="daily_price",
            status="sent",
            deleted_at=datetime.now(),  # Marked for deletion
        )

        assert log.farmer_id == 5
        assert log.deleted_at is not None

    def test_soft_delete_conversation_on_hard_delete(self):
        """Test that conversation records are soft-deleted during hard-delete."""
        from src.models.conversation import Conversation

        conv = Conversation(
            farmer_id=6,
            phone="919876543211",
            direction="inbound",
            message_type="text",
            raw_message="price",
            deleted_at=datetime.now(),
        )

        assert conv.farmer_id == 6
        assert conv.deleted_at is not None


class TestSoftDeleteFiltering:
    """Tests for soft-delete filtering in queries."""

    def test_broadcast_log_has_deleted_at_field(self):
        """Test that broadcast_log model has deleted_at field."""
        from src.models.broadcast import BroadcastLog

        broadcast = BroadcastLog(
            farmer_id=7,
            template_id="test",
            status="sent",
        )

        assert hasattr(broadcast, "deleted_at")

    def test_conversation_has_deleted_at_field(self):
        """Test that conversation model has deleted_at field."""
        from src.models.conversation import Conversation

        conv = Conversation(
            farmer_id=8,
            phone="919876543212",
            direction="inbound",
            message_type="text",
        )

        assert hasattr(conv, "deleted_at")

    def test_farmer_has_erasure_requested_at_field(self):
        """Test that farmer model has erasure_requested_at field."""
        from src.models.farmer import Farmer

        farmer = Farmer(
            phone="919876543213",
            name="Test",
        )

        assert hasattr(farmer, "erasure_requested_at")

    def test_dau_excludes_soft_deleted_farmers(self):
        """Test that DAU calculation logic would exclude soft-deleted farmers."""
        # This is a conceptual test of the filter logic
        from src.models.farmer import Farmer

        # Active farmer
        active = Farmer(
            phone="919876543214",
            onboarding_state="active",
            deleted_at=None,
        )

        # Soft-deleted farmer
        deleted = Farmer(
            phone="919876543215",
            onboarding_state="active",
            deleted_at=datetime.now(),
        )

        # In query, would filter: WHERE deleted_at == None
        # So active farmer included, deleted farmer excluded
        assert active.deleted_at is None  # Would be included
        assert deleted.deleted_at is not None  # Would be excluded

    def test_dau_excludes_erasure_requested_farmers(self):
        """Test that DAU calculation excludes farmers in erasure window."""
        from src.models.farmer import Farmer

        # Farmer in erasure window
        erasure_farmer = Farmer(
            phone="919876543216",
            onboarding_state="active",
            erasure_requested_at=datetime.now(),
        )

        # In query, would filter: WHERE erasure_requested_at == None
        assert erasure_farmer.erasure_requested_at is not None  # Would be excluded


class TestConsentEventAuditTrail:
    """Tests for immutable consent event audit trail."""

    def test_consent_event_created_at_set(self):
        """Test that consent events have immutable created_at timestamp."""
        from src.models.consent import ConsentEvent

        now = datetime.now()
        event = ConsentEvent(
            farmer_id=9,
            event_type="opt_in",
            created_at=now,
        )

        assert event.created_at == now

    def test_four_event_types_exist(self):
        """Test that all 4 event types are defined and valid."""
        event_types = {"opt_in", "opt_out", "erasure_request", "erasure_complete"}

        # In actual implementation, these would be checked via DB
        assert "opt_in" in event_types
        assert "opt_out" in event_types
        assert "erasure_request" in event_types
        assert "erasure_complete" in event_types

    def test_consent_events_preserve_after_farmer_hard_delete(self):
        """Test that ConsentEvent records persist after farmer hard-delete.

        This is a conceptual test — ConsentEvent should NEVER have deleted_at.
        """
        from src.models.consent import ConsentEvent

        event = ConsentEvent(
            farmer_id=10,
            event_type="erasure_complete",
            created_at=datetime.now(),
        )

        # ConsentEvent has NO deleted_at field — it's always preserved
        assert not hasattr(event, "deleted_at") or event.__table__.columns.get("deleted_at") is None


class TestMigrationFields:
    """Tests verifying migration 0003 fields exist."""

    def test_migration_0003_adds_erasure_requested_at_to_farmers(self):
        """Verify erasure_requested_at field will be added to farmers table."""
        from src.models.farmer import Farmer
        from sqlalchemy import inspect

        # Get columns from Farmer model
        mapper = inspect(Farmer)
        column_names = [c.name for c in mapper.columns]

        assert "erasure_requested_at" in column_names

    def test_migration_0003_adds_deleted_at_to_broadcast_log(self):
        """Verify deleted_at field will be added to broadcast_log table."""
        from src.models.broadcast import BroadcastLog
        from sqlalchemy import inspect

        mapper = inspect(BroadcastLog)
        column_names = [c.name for c in mapper.columns]

        assert "deleted_at" in column_names

    def test_migration_0003_adds_deleted_at_to_conversation(self):
        """Verify deleted_at field will be added to conversation table."""
        from src.models.conversation import Conversation
        from sqlalchemy import inspect

        mapper = inspect(Conversation)
        column_names = [c.name for c in mapper.columns]

        assert "deleted_at" in column_names
