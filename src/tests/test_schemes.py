"""Tests for government schemes and MSP alerts (Phase 2 Module 4)."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.ingestion.schemes.normalizer import (
    normalize_commodity,
    normalize_district,
    normalize_scheme_name,
    normalize_commodities_list,
)
from src.ingestion.schemes.merger import pick_winners
from src.ingestion.schemes.sources.base import SchemeRecord
from src.scheme.formatter import (
    format_msp_alert_subscription,
    format_msp_alert_triggered,
    format_no_schemes_reply,
    format_schemes_reply,
)
from datetime import date


# ==================== Normalizer Tests ====================


class TestSchemeNormalizer:
    """Test scheme name normalization."""

    def test_normalize_commodity_onion(self):
        """Test onion commodity normalization across languages."""
        assert normalize_commodity("onion") == "onion"
        assert normalize_commodity("कांदा") == "onion"
        assert normalize_commodity("kanda") == "onion"
        assert normalize_commodity("प्याज") == "onion"

    def test_normalize_commodity_wheat(self):
        """Test wheat commodity normalization."""
        assert normalize_commodity("wheat") == "wheat"
        assert normalize_commodity("गहू") == "wheat"
        assert normalize_commodity("gehun") == "wheat"

    def test_normalize_commodity_fallback(self):
        """Test commodity normalization fallback."""
        result = normalize_commodity("unknown_crop")
        assert result == "unknown_crop"  # Falls back to original

    def test_normalize_district_pune(self):
        """Test Pune district normalization."""
        assert normalize_district("pune") == "pune"
        assert normalize_district("पुणे") == "pune"

    def test_normalize_district_ahilyanagar(self):
        """Test Ahilyanagar district normalization."""
        assert normalize_district("ahmednagar") == "ahilyanagar"
        assert normalize_district("अहिल्यानगर") == "ahilyanagar"

    def test_normalize_scheme_name_pmkisan(self):
        """Test PM-KISAN scheme normalization."""
        assert normalize_scheme_name("pm kisan") == "pm_kisan"
        assert normalize_scheme_name("PM Kisan Yojana") == "pm_kisan"
        assert normalize_scheme_name("किसान सम्मान") == "pm_kisan"

    def test_normalize_commodities_list(self):
        """Test normalizing list of commodities."""
        result = normalize_commodities_list(["कांदा", "गहू", "wheat"])
        assert "onion" in result
        assert "wheat" in result
        assert len(result) == 2  # No duplicates

    def test_normalize_commodities_list_empty(self):
        """Test normalizing empty commodity list."""
        result = normalize_commodities_list([])
        assert result == []

    def test_normalize_commodities_list_with_all(self):
        """Test normalizing list with 'all' keyword."""
        result = normalize_commodities_list(["all", "onion"])
        assert "onion" in result
        assert "all" not in result  # 'all' is filtered out


# ==================== Merger Tests ====================


class TestSchemeMerger:
    """Test scheme deduplication and merging."""

    def test_merge_pick_winner_by_source_preference(self):
        """Test picking winners by source preference."""
        records = [
            SchemeRecord(
                scheme_name="PM Kisan (Hardcoded)",
                scheme_slug="pm_kisan",
                ministry="Agriculture",
                description="Test",
                eligibility_criteria={},
                commodities=["wheat"],
                min_land_hectares=0,
                max_land_hectares=2,
                annual_benefit="₹6,000",
                benefit_amount=Decimal("6000"),
                application_deadline=date(2026, 12, 31),
                district=None,
                state="maharashtra",
                raw_payload={"source": "hardcoded"},
                source="hardcoded",
            ),
            SchemeRecord(
                scheme_name="PM Kisan (API)",
                scheme_slug="pm_kisan",
                ministry="Agriculture",
                description="Test",
                eligibility_criteria={},
                commodities=["wheat"],
                min_land_hectares=0,
                max_land_hectares=2,
                annual_benefit="₹6,000",
                benefit_amount=Decimal("6000"),
                application_deadline=date(2026, 12, 31),
                district=None,
                state="maharashtra",
                raw_payload={"source": "pmksy_api"},
                source="pmksy_api",
            ),
        ]

        winners = pick_winners(records)
        assert len(winners) == 1
        assert winners[0].source == "pmksy_api"  # Higher priority than hardcoded

    def test_merge_multiple_districts(self):
        """Test merging schemes from different districts."""
        records = [
            SchemeRecord(
                scheme_name="PM Kisan - Pune",
                scheme_slug="pm_kisan",
                ministry="Agriculture",
                description="Test",
                eligibility_criteria={},
                commodities=["wheat"],
                min_land_hectares=0,
                max_land_hectares=2,
                annual_benefit="₹6,000",
                benefit_amount=Decimal("6000"),
                application_deadline=date(2026, 12, 31),
                district="pune",
                state="maharashtra",
                raw_payload={},
                source="pmksy_api",
            ),
            SchemeRecord(
                scheme_name="PM Kisan - Nashik",
                scheme_slug="pm_kisan",
                ministry="Agriculture",
                description="Test",
                eligibility_criteria={},
                commodities=["wheat"],
                min_land_hectares=0,
                max_land_hectares=2,
                annual_benefit="₹6,000",
                benefit_amount=Decimal("6000"),
                application_deadline=date(2026, 12, 31),
                district="nashik",
                state="maharashtra",
                raw_payload={},
                source="pmksy_api",
            ),
        ]

        winners = pick_winners(records)
        assert len(winners) == 2  # Two different districts = two winners


# ==================== Formatter Tests ====================


class TestSchemeFormatter:
    """Test scheme and MSP alert formatting."""

    def test_format_no_schemes_marathi(self):
        """Test no schemes message in Marathi."""
        msg = format_no_schemes_reply(lang="mr")
        assert "खेद" in msg  # Contains "sorry" in Marathi
        assert "योजना" in msg or "नहीं" in msg

    def test_format_no_schemes_english(self):
        """Test no schemes message in English."""
        msg = format_no_schemes_reply(lang="en")
        assert "Sorry" in msg or "no schemes" in msg.lower()

    def test_format_msp_alert_subscription_marathi(self):
        """Test MSP alert subscription confirmation in Marathi."""
        msg = format_msp_alert_subscription("onion", 3000, lang="mr")
        assert "MSP" in msg or "अलर्ट" in msg
        assert "₹3" in msg or "3000" in msg
        assert "Onion" in msg or "onion" in msg.lower()

    def test_format_msp_alert_subscription_english(self):
        """Test MSP alert subscription confirmation in English."""
        msg = format_msp_alert_subscription("wheat", 2500, lang="en")
        assert "MSP" in msg
        assert "Alert" in msg
        assert "₹" in msg or "2500" in msg

    def test_format_msp_alert_triggered_marathi(self):
        """Test MSP alert triggered message in Marathi."""
        msg = format_msp_alert_triggered("onion", 3500, 3000, lang="mr")
        assert "MSP" in msg or "अलर्ट" in msg
        assert "3500" in msg or "3,500" in msg or "₹3" in msg
        assert "3,000" in msg

    def test_format_msp_alert_triggered_english(self):
        """Test MSP alert triggered message in English."""
        msg = format_msp_alert_triggered("wheat", 2800, 2500, lang="en")
        assert "Alert" in msg or "alert" in msg.lower()
        assert "2,800" in msg
        assert "2,500" in msg

    def test_format_schemes_with_data_marathi(self):
        """Test formatting schemes with data in Marathi."""
        schemes = [
            {
                "scheme_name": "PM Kisan Yojana",
                "scheme_slug": "pm_kisan",
                "annual_benefit": "₹6,000/year",
                "application_deadline": date(2026, 12, 31),
                "description": "Direct income support to farmers",
            }
        ]
        msg = format_schemes_reply(schemes, lang="mr")
        assert "PM Kisan" in msg
        assert "6000" in msg or "₹" in msg
        assert "योजना" in msg or "Scheme" in msg.lower()

    def test_format_schemes_with_data_english(self):
        """Test formatting schemes with data in English."""
        schemes = [
            {
                "scheme_name": "PM Fasal Bima Yojana",
                "scheme_slug": "pm_fasal",
                "annual_benefit": "70% subsidy",
                "application_deadline": date(2026, 6, 30),
                "description": "Crop insurance with government subsidy",
            }
        ]
        msg = format_schemes_reply(schemes, lang="en")
        assert "Fasal" in msg
        assert "70%" in msg
        assert "Scheme" in msg


# ==================== Handler Tests ====================


class TestSchemeHandler:
    """Test scheme handler logic."""

    @pytest.mark.asyncio
    async def test_handle_scheme_query_eligible(self):
        """Test scheme query with eligible schemes."""
        from src.scheme.handler import SchemeHandler

        # Mock repository
        mock_session = AsyncMock()
        handler = SchemeHandler(mock_session)
        handler.repo = AsyncMock()
        handler.repo.get_eligible_schemes = AsyncMock(
            return_value=[
                {
                    "scheme_name": "PM Kisan",
                    "annual_benefit": "₹6,000/year",
                    "application_deadline": date(2026, 12, 31),
                    "description": "Direct support",
                }
            ]
        )

        reply = await handler.handle_scheme_query(
            farmer_age=35,
            farmer_land_hectares=1.5,
            farmer_crops=["wheat", "onion"],
            farmer_district="pune",
            farmer_language="mr",
        )

        assert "PM Kisan" in reply
        assert "₹" in reply or "6000" in reply

    @pytest.mark.asyncio
    async def test_handle_msp_alert(self):
        """Test MSP alert subscription."""
        from src.scheme.handler import SchemeHandler

        mock_session = AsyncMock()
        handler = SchemeHandler(mock_session)
        handler.repo = AsyncMock()
        handler.repo.save_msp_alert = AsyncMock(return_value=True)

        reply = await handler.handle_msp_alert(
            farmer_id="919876543210",
            commodity="onion",
            alert_threshold=3000,
            farmer_language="mr",
        )

        assert "MSP" in reply or "अलर्ट" in reply
        assert "3,000" in reply


# ==================== Integration Tests ====================


class TestSchemeSourceBases:
    """Test scheme source implementations."""

    def test_pm_kisan_source_returns_records(self):
        """Test PM-KISAN source returns valid records."""
        from src.ingestion.schemes.sources.pmksy_api import PMKISANSource

        source = PMKISANSource()
        assert source.name == "pmksy_api"

    def test_pm_fasal_source_returns_records(self):
        """Test PM-FASAL source returns valid records."""
        from src.ingestion.schemes.sources.pmfby_api import PMFBYSource

        source = PMFBYSource()
        assert source.name == "pmfby_api"

    def test_hardcoded_source_returns_records(self):
        """Test hardcoded source returns valid records."""
        from src.ingestion.schemes.sources.hardcoded_schemes import HardcodedSchemesSource

        source = HardcodedSchemesSource()
        assert source.name == "hardcoded"
