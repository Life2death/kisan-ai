"""Tests for farmer profile service."""
import pytest
import pytest_asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.models.base import Base
from src.models.farmer import Farmer, CropOfInterest
from src.services.farmer_service import FarmerService


@pytest_asyncio.fixture
async def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        # Only create Farmer and CropOfInterest tables (JSONB not supported by SQLite)
        await conn.run_sync(Farmer.__table__.create, checkfirst=True)
        await conn.run_sync(CropOfInterest.__table__.create, checkfirst=True)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


class TestFarmerServiceGetByPhone:
    """Test farmer lookup by phone."""

    @pytest.mark.asyncio
    async def test_get_existing_farmer(self, db_session):
        """Test retrieving an existing farmer."""
        # Create test farmer
        farmer = Farmer(
            phone="+919876543210",
            name="राज कुलकर्णी",
            district="pune",
            preferred_language="mr",
            subscription_status="active",
            onboarding_state="active",
            age=35,
        )
        db_session.add(farmer)
        await db_session.commit()

        # Test lookup
        service = FarmerService(db_session)
        result = await service.get_by_phone("+919876543210")

        assert result is not None
        assert result.name == "राज कुलकर्णी"
        assert result.district == "pune"
        assert result.age == 35

    @pytest.mark.asyncio
    async def test_get_nonexistent_farmer(self, db_session):
        """Test retrieving a farmer that doesn't exist."""
        service = FarmerService(db_session)
        result = await service.get_by_phone("+919999999999")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_farmer_with_all_fields(self, db_session):
        """Test retrieving farmer with all fields populated."""
        from decimal import Decimal

        farmer = Farmer(
            phone="+919876543210",
            name="भाऊ शेठ",
            age=45,
            district="nashik",
            land_hectares=Decimal("2.5"),
            preferred_language="mr",
            subscription_status="active",
            onboarding_state="active",
        )
        db_session.add(farmer)
        await db_session.commit()

        service = FarmerService(db_session)
        result = await service.get_by_phone("+919876543210")

        assert result.age == 45
        assert result.land_hectares == Decimal("2.5")


class TestFarmerServiceGetCrops:
    """Test crop retrieval."""

    @pytest.mark.asyncio
    async def test_get_crops_for_farmer(self, db_session):
        """Test retrieving crops for a farmer."""
        farmer = Farmer(
            phone="+919876543210",
            name="किसान",
            subscription_status="active",
            onboarding_state="active",
        )
        db_session.add(farmer)
        await db_session.flush()

        # Add crops
        crop1 = CropOfInterest(farmer_id=farmer.id, crop="onion")
        crop2 = CropOfInterest(farmer_id=farmer.id, crop="wheat")
        db_session.add_all([crop1, crop2])
        await db_session.commit()

        # Test retrieval
        service = FarmerService(db_session)
        crops = await service.get_crops(farmer.id)

        assert len(crops) == 2
        assert "onion" in crops
        assert "wheat" in crops

    @pytest.mark.asyncio
    async def test_get_crops_empty(self, db_session):
        """Test retrieving crops when farmer has none."""
        farmer = Farmer(
            phone="+919876543210",
            name="नया किसान",
            subscription_status="active",
            onboarding_state="active",
        )
        db_session.add(farmer)
        await db_session.commit()

        service = FarmerService(db_session)
        crops = await service.get_crops(farmer.id)

        assert crops == []

    @pytest.mark.asyncio
    async def test_get_crops_nonexistent_farmer(self, db_session):
        """Test retrieving crops for non-existent farmer."""
        service = FarmerService(db_session)
        crops = await service.get_crops(999)

        assert crops == []


class TestFarmerServiceUpdateSubscription:
    """Test subscription status updates."""

    @pytest.mark.asyncio
    async def test_update_subscription_active(self, db_session):
        """Test enabling subscription."""
        farmer = Farmer(
            phone="+919876543210",
            name="किसान",
            subscription_status="none",
            onboarding_state="active",
        )
        db_session.add(farmer)
        await db_session.commit()

        service = FarmerService(db_session)
        success = await service.update_subscription_status(farmer.id, "active")

        assert success is True
        await db_session.refresh(farmer)
        assert farmer.subscription_status == "active"

    @pytest.mark.asyncio
    async def test_update_subscription_inactive(self, db_session):
        """Test disabling subscription."""
        farmer = Farmer(
            phone="+919876543210",
            name="किसान",
            subscription_status="active",
            onboarding_state="active",
        )
        db_session.add(farmer)
        await db_session.commit()

        service = FarmerService(db_session)
        success = await service.update_subscription_status(farmer.id, "inactive")

        assert success is True
        await db_session.refresh(farmer)
        assert farmer.subscription_status == "inactive"

    @pytest.mark.asyncio
    async def test_update_nonexistent_farmer(self, db_session):
        """Test updating subscription for non-existent farmer."""
        service = FarmerService(db_session)
        success = await service.update_subscription_status(999, "active")

        assert success is False


class TestFarmerServiceGetProfile:
    """Test complete profile retrieval."""

    @pytest.mark.asyncio
    async def test_get_complete_profile(self, db_session):
        """Test retrieving complete farmer profile."""
        from decimal import Decimal

        farmer = Farmer(
            phone="+919876543210",
            name="राज कुलकर्णी",
            age=35,
            district="pune",
            land_hectares=Decimal("2.5"),
            preferred_language="mr",
            subscription_status="active",
            onboarding_state="active",
        )
        db_session.add(farmer)
        await db_session.flush()

        crop1 = CropOfInterest(farmer_id=farmer.id, crop="onion")
        crop2 = CropOfInterest(farmer_id=farmer.id, crop="wheat")
        db_session.add_all([crop1, crop2])
        await db_session.commit()

        service = FarmerService(db_session)
        profile = await service.get_farmer_profile(farmer.id)

        assert profile is not None
        assert profile["name"] == "राज कुलकर्णी"
        assert profile["age"] == 35
        assert profile["land_hectares"] == 2.5
        assert profile["language"] == "mr"
        assert len(profile["crops"]) == 2
        assert "onion" in profile["crops"]

    @pytest.mark.asyncio
    async def test_get_profile_partial_fields(self, db_session):
        """Test profile with missing optional fields."""
        farmer = Farmer(
            phone="+919876543210",
            name="किसान",
            subscription_status="active",
            onboarding_state="active",
            # age, land_hectares are None
        )
        db_session.add(farmer)
        await db_session.commit()

        service = FarmerService(db_session)
        profile = await service.get_farmer_profile(farmer.id)

        assert profile is not None
        assert profile["age"] is None
        assert profile["land_hectares"] is None
        assert profile["crops"] == []

    @pytest.mark.asyncio
    async def test_get_profile_nonexistent(self, db_session):
        """Test retrieving profile for non-existent farmer."""
        service = FarmerService(db_session)
        profile = await service.get_farmer_profile(999)

        assert profile is None


class TestFarmerServiceIntegration:
    """Integration tests combining multiple operations."""

    @pytest.mark.asyncio
    async def test_farmer_lifecycle(self, db_session):
        """Test complete farmer lifecycle."""
        # 1. Create farmer during onboarding
        farmer = Farmer(
            phone="+919876543210",
            name="नया किसान",
            district="latur",
            preferred_language="mr",
            subscription_status="active",
            onboarding_state="active",
        )
        db_session.add(farmer)
        await db_session.flush()

        # 2. Add crops of interest
        crop1 = CropOfInterest(farmer_id=farmer.id, crop="soyabean")
        crop2 = CropOfInterest(farmer_id=farmer.id, crop="tur")
        db_session.add_all([crop1, crop2])
        await db_session.commit()

        service = FarmerService(db_session)

        # 3. Lookup farmer
        found = await service.get_by_phone("+919876543210")
        assert found is not None

        # 4. Get crops
        crops = await service.get_crops(farmer.id)
        assert len(crops) == 2

        # 5. Get full profile
        profile = await service.get_farmer_profile(farmer.id)
        assert profile["name"] == "नया किसान"
        assert len(profile["crops"]) == 2

        # 6. Disable subscription
        success = await service.update_subscription_status(farmer.id, "inactive")
        assert success is True

        # 7. Verify subscription updated
        updated = await service.get_by_phone("+919876543210")
        assert updated.subscription_status == "inactive"
