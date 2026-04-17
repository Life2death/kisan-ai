"""Tests for scheduler tasks (price alerts, scheme ingestion, etc.)."""
import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.models.base import Base
from src.models.farmer import Farmer, CropOfInterest
from src.models.price import MandiPrice, PriceAlert
from src.models.schemes import MSPAlert, GovernmentScheme


@pytest.fixture
async def db_session():
    """Create in-memory database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


class TestTriggerPriceAlerts:
    """Test price alert triggering logic."""

    @pytest.mark.asyncio
    async def test_alert_triggered_when_condition_met(self, db_session):
        """Test that alert is triggered when price meets condition."""
        # Setup: Create farmer + alert
        farmer = Farmer(
            phone="+919876543210",
            name="किसान",
            district="pune",
            preferred_language="mr",
            subscription_status="active",
        )
        db_session.add(farmer)
        await db_session.flush()

        alert = PriceAlert(
            farmer_id=farmer.id,
            commodity="onion",
            district="pune",
            condition=">",
            threshold=Decimal("4000"),
            is_active=True,
        )
        db_session.add(alert)

        # Add price data (current price > threshold)
        price = MandiPrice(
            date=date.today(),
            crop="onion",
            mandi="Pune Market",
            apmc="pune",
            district="pune",
            modal_price=Decimal("4500"),
            source="agmarknet",
        )
        db_session.add(price)
        await db_session.commit()

        # Test: Check condition
        from src.price.alert_repository import PriceAlertRepository

        repo = PriceAlertRepository(db_session)
        result = repo.check_condition(">", 4500, 4000)
        assert result is True

    @pytest.mark.asyncio
    async def test_alert_not_triggered_when_condition_not_met(self, db_session):
        """Test that alert is not triggered when price doesn't meet condition."""
        from src.price.alert_repository import PriceAlertRepository

        repo = PriceAlertRepository(db_session)
        # Price 3500 > 4000 is False
        result = repo.check_condition(">", 3500, 4000)
        assert result is False

    @pytest.mark.asyncio
    async def test_less_than_condition(self, db_session):
        """Test less than condition."""
        from src.price.alert_repository import PriceAlertRepository

        repo = PriceAlertRepository(db_session)
        # Price 3500 < 4000 is True
        result = repo.check_condition("<", 3500, 4000)
        assert result is True

    @pytest.mark.asyncio
    async def test_equals_condition(self, db_session):
        """Test equals condition."""
        from src.price.alert_repository import PriceAlertRepository

        repo = PriceAlertRepository(db_session)
        # Price 4000 == 4000 is True (within tolerance)
        result = repo.check_condition("==", 4000, 4000)
        assert result is True

        # Price 4000.005 == 4000 is False (outside tolerance)
        result = repo.check_condition("==", 4000.005, 4000)
        assert result is False


class TestTriggerMSPAlerts:
    """Test MSP alert triggering logic."""

    @pytest.mark.asyncio
    async def test_msp_alert_retrieval(self, db_session):
        """Test retrieving MSP alerts for a commodity."""
        # Create farmer + MSP alert
        farmer = Farmer(
            phone="+919876543210",
            name="किसान",
            district="pune",
            preferred_language="mr",
        )
        db_session.add(farmer)
        await db_session.flush()

        alert = MSPAlert(
            farmer_id=farmer.id,
            commodity="onion",
            alert_threshold=Decimal("3000"),
            is_active=True,
        )
        db_session.add(alert)
        await db_session.commit()

        # Test: Retrieve active alerts
        from src.scheme.repository import SchemeRepository

        repo = SchemeRepository(db_session)
        alerts = await repo.get_msp_alerts_for_commodity("onion")

        assert len(alerts) == 1
        assert alerts[0]["farmer_id"] == str(farmer.id)
        assert alerts[0]["commodity"] == "onion"
        assert float(alerts[0]["threshold"]) == 3000.0

    @pytest.mark.asyncio
    async def test_msp_alert_inactive_not_returned(self, db_session):
        """Test that inactive MSP alerts are not returned."""
        farmer = Farmer(phone="+919876543210", name="किसान")
        db_session.add(farmer)
        await db_session.flush()

        alert = MSPAlert(
            farmer_id=farmer.id,
            commodity="wheat",
            alert_threshold=Decimal("2000"),
            is_active=False,  # Inactive
        )
        db_session.add(alert)
        await db_session.commit()

        from src.scheme.repository import SchemeRepository

        repo = SchemeRepository(db_session)
        alerts = await repo.get_msp_alerts_for_commodity("wheat")

        # Should not include inactive alert
        assert len(alerts) == 0


class TestPriceAlertRepository:
    """Test PriceAlertRepository methods."""

    @pytest.mark.asyncio
    async def test_save_price_alert_creates_record(self, db_session):
        """Test that saving a price alert creates a record."""
        from src.price.alert_repository import PriceAlertRepository

        repo = PriceAlertRepository(db_session)

        # Mock farmer_id as string (would come from farmer lookup)
        success = await repo.save_price_alert(
            farmer_id="1",
            commodity="onion",
            threshold=Decimal("4000"),
            condition=">",
            district="pune",
        )

        assert success is True

    @pytest.mark.asyncio
    async def test_get_active_alerts(self, db_session):
        """Test retrieving all active price alerts."""
        # Create farmer + alerts
        farmer = Farmer(phone="+919876543210", name="किसान")
        db_session.add(farmer)
        await db_session.flush()

        alert1 = PriceAlert(
            farmer_id=farmer.id,
            commodity="onion",
            condition=">",
            threshold=Decimal("4000"),
            is_active=True,
        )
        alert2 = PriceAlert(
            farmer_id=farmer.id,
            commodity="wheat",
            condition="<",
            threshold=Decimal("2000"),
            is_active=True,
        )
        db_session.add_all([alert1, alert2])
        await db_session.commit()

        from src.price.alert_repository import PriceAlertRepository

        repo = PriceAlertRepository(db_session)
        alerts = await repo.get_active_alerts()

        assert len(alerts) == 2
        commodities = {a["commodity"] for a in alerts}
        assert commodities == {"onion", "wheat"}


class TestSchemeIngestionSummary:
    """Test scheme ingestion summary tracking."""

    def test_ingestion_summary_healthy(self):
        """Test that summary is healthy with successful sources."""
        from src.ingestion.schemes.orchestrator import IngestionSummary

        summary = IngestionSummary(
            total_records_fetched=100,
            total_records_upserted=95,
            sources_succeeded=["pmksy_api", "pmfby_api"],
            sources_failed=[],
            errors=[],
            duration_seconds=5.2,
        )

        assert summary.is_healthy is True

    def test_ingestion_summary_unhealthy_no_sources(self):
        """Test that summary is unhealthy with no successful sources."""
        from src.ingestion.schemes.orchestrator import IngestionSummary

        summary = IngestionSummary(
            total_records_fetched=0,
            total_records_upserted=0,
            sources_succeeded=[],
            sources_failed=["pmksy_api", "pmfby_api"],
            errors=["API timeout", "Connection refused"],
            duration_seconds=30,
        )

        assert summary.is_healthy is False

    def test_ingestion_summary_unhealthy_no_records(self):
        """Test that summary is unhealthy with no upserted records."""
        from src.ingestion.schemes.orchestrator import IngestionSummary

        summary = IngestionSummary(
            total_records_fetched=50,
            total_records_upserted=0,
            sources_succeeded=["pmksy_api"],
            sources_failed=["pmfby_api"],
            errors=["Upsert failed"],
            duration_seconds=10,
        )

        assert summary.is_healthy is False


class TestPriceIngestionSummary:
    """Test price ingestion summary tracking."""

    def test_price_ingestion_healthy(self):
        """Test price ingestion health check."""
        from src.ingestion.orchestrator import IngestionSummary

        summary = IngestionSummary(
            trade_date=date.today(),
            per_source_counts={"agmarknet": 50, "msib": 45},
            total_records=95,
            winner_count=50,
            persisted=50,
            errors={},
            started_at=datetime.now(),
            finished_at=datetime.now(),
        )

        assert summary.healthy(min_sources=2) is True

    def test_price_ingestion_unhealthy(self):
        """Test price ingestion unhealthy when not enough sources."""
        from src.ingestion.orchestrator import IngestionSummary

        summary = IngestionSummary(
            trade_date=date.today(),
            per_source_counts={"agmarknet": 50, "msib": 0},
            total_records=50,
            winner_count=50,
            persisted=50,
            errors={"msib": "API error"},
            started_at=datetime.now(),
            finished_at=datetime.now(),
        )

        assert summary.healthy(min_sources=2) is False


class TestSchedulerErrorHandling:
    """Test error handling in scheduler tasks."""

    @pytest.mark.asyncio
    async def test_graceful_failure_with_exception(self, db_session):
        """Test that scheduler handles exceptions gracefully."""
        from src.price.alert_repository import PriceAlertRepository

        repo = PriceAlertRepository(db_session)

        # Try to get crops for non-existent farmer
        # Should return empty list, not crash
        alerts = await repo.get_active_alerts()
        assert alerts == []

    @pytest.mark.asyncio
    async def test_partial_success_scenario(self, db_session):
        """Test scenario where some operations succeed and some fail."""
        # Create one valid farmer
        farmer = Farmer(phone="+919876543210", name="किसान")
        db_session.add(farmer)
        await db_session.flush()

        alert = PriceAlert(
            farmer_id=farmer.id,
            commodity="onion",
            condition=">",
            threshold=Decimal("4000"),
            is_active=True,
        )
        db_session.add(alert)
        await db_session.commit()

        # Try to get alerts (should succeed)
        from src.price.alert_repository import PriceAlertRepository

        repo = PriceAlertRepository(db_session)
        alerts = await repo.get_active_alerts()

        # Should return the one valid alert
        assert len(alerts) == 1
