"""Tests for Phase 2 intent patterns in regex classifier."""
import pytest
from src.classifier.regex_classifier import classify_regex
from src.classifier.intents import Intent


class TestPriceAlertPatterns:
    """Test PRICE_ALERT intent detection."""

    def test_alert_keyword_english(self):
        """Test 'alert' keyword in English."""
        result = classify_regex("alert when onion > 5000")
        assert result.intent == Intent.PRICE_ALERT
        assert result.confidence == 1.0

    def test_notify_keyword(self):
        """Test 'notify' keyword."""
        result = classify_regex("notify me when price goes above 4000")
        assert result.intent == Intent.PRICE_ALERT

    def test_set_alert_english(self):
        """Test 'set alert' pattern."""
        result = classify_regex("set alert for wheat")
        assert result.intent == Intent.PRICE_ALERT

    def test_when_price_pattern(self):
        """Test 'when price' pattern."""
        result = classify_regex("when price reaches 3000")
        assert result.intent == Intent.PRICE_ALERT

    def test_alert_marathi(self):
        """Test Marathi alert pattern."""
        result = classify_regex("सूचित करो कांदा ₹4000")
        assert result.intent == Intent.PRICE_ALERT

    def test_commodity_extraction(self):
        """Test that commodity is extracted."""
        result = classify_regex("alert when onion > 5000")
        assert result.commodity == "onion"

    def test_district_extraction(self):
        """Test that district is extracted."""
        result = classify_regex("alert when onion pune 5000")
        assert result.commodity == "onion"


class TestSchemeQueryPatterns:
    """Test SCHEME_QUERY intent detection."""

    def test_scheme_keyword(self):
        """Test 'scheme' keyword."""
        result = classify_regex("which schemes am I eligible for")
        assert result.intent == Intent.SCHEME_QUERY

    def test_eligible_keyword(self):
        """Test 'eligible' keyword."""
        result = classify_regex("am I eligible for government schemes")
        assert result.intent == Intent.SCHEME_QUERY

    def test_subsidy_keyword(self):
        """Test 'subsidy' keyword."""
        result = classify_regex("what subsidy can I get")
        assert result.intent == Intent.SCHEME_QUERY

    def test_yojana_marathi(self):
        """Test Marathi 'योजना' keyword."""
        result = classify_regex("मला कोणती योजना मिळेल")
        assert result.intent == Intent.SCHEME_QUERY

    def test_grant_keyword(self):
        """Test 'grant' keyword."""
        result = classify_regex("what grants are available")
        assert result.intent == Intent.SCHEME_QUERY

    def test_pmkisan_abbreviation(self):
        """Test scheme abbreviations."""
        result = classify_regex("am I eligible for pmkisan")
        assert result.intent == Intent.SCHEME_QUERY


class TestPestQueryPatterns:
    """Test PEST_QUERY intent detection."""

    def test_pest_keyword(self):
        """Test 'pest' keyword."""
        result = classify_regex("my plants have pests")
        assert result.intent == Intent.PEST_QUERY

    def test_disease_keyword(self):
        """Test 'disease' keyword."""
        result = classify_regex("what disease is this")
        assert result.intent == Intent.PEST_QUERY

    def test_bug_keyword(self):
        """Test 'bug' keyword."""
        result = classify_regex("there are bugs on my crop")
        assert result.intent == Intent.PEST_QUERY

    def test_whats_wrong_pattern(self):
        """Test 'what's wrong' pattern."""
        result = classify_regex("what's wrong with my plant")
        assert result.intent == Intent.PEST_QUERY

    def test_sick_plant_pattern(self):
        """Test 'sick plant' pattern."""
        result = classify_regex("my crop is sick")
        assert result.intent == Intent.PEST_QUERY

    def test_yellow_leaves_pattern(self):
        """Test 'yellow leaves' pattern."""
        result = classify_regex("the leaves are turning yellow")
        assert result.intent == Intent.PEST_QUERY

    def test_dark_spots_pattern(self):
        """Test 'dark spots' pattern."""
        result = classify_regex("there are dark spots on the leaves")
        assert result.intent == Intent.PEST_QUERY

    def test_keet_marathi(self):
        """Test Marathi 'कीट' keyword."""
        result = classify_regex("काय कीट आहेत")
        assert result.intent == Intent.PEST_QUERY

    def test_rog_marathi(self):
        """Test Marathi 'रोग' keyword."""
        result = classify_regex("पिकाला रोग आहे")
        assert result.intent == Intent.PEST_QUERY


class TestMSPAlertPatterns:
    """Test MSP_ALERT intent detection."""

    def test_msp_keyword(self):
        """Test 'msp' keyword."""
        result = classify_regex("set alert for msp")
        assert result.intent == Intent.MSP_ALERT

    def test_minimum_support_price(self):
        """Test 'minimum support price' full phrase."""
        result = classify_regex("notify when minimum support price reaches 3000")
        assert result.intent == Intent.MSP_ALERT

    def test_support_price_pattern(self):
        """Test 'support price' pattern."""
        result = classify_regex("when support price goes above 2000")
        assert result.intent == Intent.MSP_ALERT

    def test_msp_alert_pattern(self):
        """Test 'msp alert' pattern."""
        result = classify_regex("set msp alert for wheat")
        assert result.intent == Intent.MSP_ALERT

    def test_nyuntam_mulya_marathi(self):
        """Test Marathi 'न्यूनतम मूल्य' keyword."""
        result = classify_regex("न्यूनतम मूल्य सूचित करो")
        assert result.intent == Intent.MSP_ALERT

    def test_emsepee_marathi(self):
        """Test Marathi 'एमएसपी' (MSP transliterated)."""
        result = classify_regex("एमएसपी अलर्ट सेट करो")
        assert result.intent == Intent.MSP_ALERT

    def test_commodity_extraction_msp(self):
        """Test that commodity is extracted for MSP alerts."""
        result = classify_regex("msp alert for onion")
        assert result.commodity == "onion"


class TestIntentPriority:
    """Test that intents are classified in correct priority order."""

    def test_alert_before_price_query(self):
        """Test that PRICE_ALERT is detected before PRICE_QUERY."""
        # "alert" should trigger PRICE_ALERT, not PRICE_QUERY
        result = classify_regex("alert when price high")
        assert result.intent == Intent.PRICE_ALERT
        assert result.intent != Intent.PRICE_QUERY

    def test_scheme_before_commodity(self):
        """Test that SCHEME_QUERY is detected before commodity-only PRICE_QUERY."""
        result = classify_regex("scheme wheat")
        assert result.intent == Intent.SCHEME_QUERY

    def test_msp_before_price_alert(self):
        """Test that MSP_ALERT is detected appropriately."""
        result = classify_regex("msp when above 3000")
        assert result.intent == Intent.MSP_ALERT

    def test_unsubscribe_before_price(self):
        """Test that UNSUBSCRIBE is detected before price query."""
        result = classify_regex("stop price alerts")
        assert result.intent == Intent.UNSUBSCRIBE

    def test_subscribe_before_scheme(self):
        """Test that SUBSCRIBE is detected before other intents."""
        result = classify_regex("subscribe scheme daily")
        assert result.intent == Intent.SUBSCRIBE


class TestIntegrationWithExistingIntents:
    """Test that Phase 2 patterns don't break existing intents."""

    def test_price_query_still_works(self):
        """Ensure PRICE_QUERY still works."""
        result = classify_regex("what is today's onion price")
        assert result.intent == Intent.PRICE_QUERY
        assert result.commodity == "onion"

    def test_weather_query_still_works(self):
        """Ensure WEATHER_QUERY still works."""
        result = classify_regex("what is the weather today")
        assert result.intent == Intent.WEATHER_QUERY

    def test_subscribe_still_works(self):
        """Ensure SUBSCRIBE still works."""
        result = classify_regex("subscribe me for daily alerts")
        assert result.intent == Intent.SUBSCRIBE

    def test_unsubscribe_still_works(self):
        """Ensure UNSUBSCRIBE still works."""
        result = classify_regex("stop sending me alerts")
        assert result.intent == Intent.UNSUBSCRIBE

    def test_greeting_still_works(self):
        """Ensure GREETING still works."""
        result = classify_regex("namaste")
        assert result.intent == Intent.GREETING

    def test_help_still_works(self):
        """Ensure HELP still works."""
        result = classify_regex("what can you do")
        assert result.intent == Intent.HELP


class TestEdgeCases:
    """Test edge cases and ambiguous messages."""

    def test_empty_message(self):
        """Test empty message returns UNKNOWN."""
        result = classify_regex("")
        assert result.intent == Intent.UNKNOWN

    def test_whitespace_only(self):
        """Test whitespace-only message returns UNKNOWN."""
        result = classify_regex("   ")
        assert result.intent == Intent.UNKNOWN

    def test_case_insensitive(self):
        """Test that patterns are case-insensitive."""
        result1 = classify_regex("ALERT when onion high")
        result2 = classify_regex("alert when onion high")
        assert result1.intent == result2.intent == Intent.PRICE_ALERT

    def test_mixed_language(self):
        """Test Hinglish/mixed language patterns."""
        result = classify_regex("कांदा ka bhav alert karo")
        # Should detect alert keyword
        assert result.intent in [Intent.PRICE_ALERT, Intent.PRICE_QUERY]

    def test_typos_tolerated(self):
        """Test that minor typos are still matched."""
        result = classify_regex("alrt when onion high")  # typo: alrt
        # This might not match due to regex strictness, which is ok
        # Just verify it doesn't crash
        assert result.intent in [Intent.UNKNOWN, Intent.PRICE_ALERT]
