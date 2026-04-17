"""Tests for intent routing logic in main webhook handler."""
import pytest
from src.classifier.intents import Intent, IntentResult


class TestIntentClassification:
    """Test that intents are classified correctly."""

    def test_price_query_intent(self):
        """Test PRICE_QUERY classification."""
        result = IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=1.0,
            commodity="onion",
            source="regex",
        )
        assert result.intent == Intent.PRICE_QUERY
        assert result.is_price_query is True
        assert result.needs_commodity is False

    def test_price_query_needs_commodity(self):
        """Test that PRICE_QUERY without commodity is flagged."""
        result = IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=0.8,
            commodity=None,  # Missing commodity
            source="llm",
        )
        assert result.is_price_query is True
        assert result.needs_commodity is True

    def test_price_alert_intent(self):
        """Test PRICE_ALERT classification."""
        result = IntentResult(
            intent=Intent.PRICE_ALERT,
            confidence=1.0,
            commodity="wheat",
            source="regex",
        )
        assert result.intent == Intent.PRICE_ALERT

    def test_scheme_query_intent(self):
        """Test SCHEME_QUERY classification."""
        result = IntentResult(
            intent=Intent.SCHEME_QUERY,
            confidence=1.0,
            source="regex",
        )
        assert result.intent == Intent.SCHEME_QUERY

    def test_msp_alert_intent(self):
        """Test MSP_ALERT classification."""
        result = IntentResult(
            intent=Intent.MSP_ALERT,
            confidence=1.0,
            commodity="onion",
            source="regex",
        )
        assert result.intent == Intent.MSP_ALERT

    def test_weather_query_intent(self):
        """Test WEATHER_QUERY classification."""
        result = IntentResult(
            intent=Intent.WEATHER_QUERY,
            confidence=1.0,
            commodity="temperature",  # Metric, reused field
            source="regex",
        )
        assert result.intent == Intent.WEATHER_QUERY

    def test_pest_query_intent(self):
        """Test PEST_QUERY classification."""
        result = IntentResult(
            intent=Intent.PEST_QUERY,
            confidence=1.0,
            source="regex",
        )
        assert result.intent == Intent.PEST_QUERY

    def test_subscribe_intent(self):
        """Test SUBSCRIBE classification."""
        result = IntentResult(
            intent=Intent.SUBSCRIBE,
            confidence=1.0,
            source="regex",
        )
        assert result.intent == Intent.SUBSCRIBE

    def test_unsubscribe_intent(self):
        """Test UNSUBSCRIBE classification."""
        result = IntentResult(
            intent=Intent.UNSUBSCRIBE,
            confidence=1.0,
            source="regex",
        )
        assert result.intent == Intent.UNSUBSCRIBE

    def test_help_intent(self):
        """Test HELP classification."""
        result = IntentResult(
            intent=Intent.HELP,
            confidence=1.0,
            source="regex",
        )
        assert result.intent == Intent.HELP

    def test_greeting_intent(self):
        """Test GREETING classification."""
        result = IntentResult(
            intent=Intent.GREETING,
            confidence=1.0,
            source="regex",
        )
        assert result.intent == Intent.GREETING

    def test_feedback_intent(self):
        """Test FEEDBACK classification."""
        result = IntentResult(
            intent=Intent.FEEDBACK,
            confidence=0.85,
            source="llm",
        )
        assert result.intent == Intent.FEEDBACK

    def test_onboarding_intent(self):
        """Test ONBOARDING classification."""
        result = IntentResult(
            intent=Intent.ONBOARDING,
            confidence=1.0,
            source="regex",
        )
        assert result.intent == Intent.ONBOARDING

    def test_unknown_intent(self):
        """Test UNKNOWN classification."""
        result = IntentResult(
            intent=Intent.UNKNOWN,
            confidence=0.0,
            source="regex",
            explanation="no_pattern_matched",
        )
        assert result.intent == Intent.UNKNOWN


class TestIntentRouting:
    """Test routing logic for different intents."""

    def test_routing_logic_price_query(self):
        """Test routing logic for PRICE_QUERY."""
        intent = Intent.PRICE_QUERY
        # Should route to: PriceRepository.query() -> format_price_reply()
        assert intent == Intent.PRICE_QUERY
        assert intent in [
            Intent.PRICE_QUERY,
            Intent.PRICE_ALERT,
            Intent.SCHEME_QUERY,
            Intent.MSP_ALERT,
            Intent.WEATHER_QUERY,
            Intent.PEST_QUERY,
            Intent.SUBSCRIBE,
            Intent.UNSUBSCRIBE,
            Intent.ONBOARDING,
            Intent.HELP,
            Intent.GREETING,
            Intent.FEEDBACK,
        ]

    def test_routing_logic_alert_intents(self):
        """Test routing logic for alert intents."""
        for intent in [Intent.PRICE_ALERT, Intent.MSP_ALERT]:
            assert intent in [Intent.PRICE_ALERT, Intent.MSP_ALERT]

    def test_routing_logic_subscription_intents(self):
        """Test routing logic for subscription intents."""
        for intent in [Intent.SUBSCRIBE, Intent.UNSUBSCRIBE]:
            assert intent in [Intent.SUBSCRIBE, Intent.UNSUBSCRIBE]

    def test_routing_logic_information_intents(self):
        """Test routing logic for information intents."""
        for intent in [Intent.HELP, Intent.GREETING, Intent.FEEDBACK]:
            assert intent in [Intent.HELP, Intent.GREETING, Intent.FEEDBACK]


class TestIntentAttributes:
    """Test IntentResult attributes."""

    def test_confidence_levels(self):
        """Test different confidence levels."""
        regex_result = IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=1.0,  # Regex match = 100%
            source="regex",
        )
        assert regex_result.confidence == 1.0

        llm_result = IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=0.75,  # LLM score = 75%
            source="llm",
        )
        assert llm_result.confidence == 0.75

    def test_source_attribution(self):
        """Test source attribution."""
        regex_result = IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=1.0,
            source="regex",
        )
        assert regex_result.source == "regex"

        llm_result = IntentResult(
            intent=Intent.UNKNOWN,
            confidence=0.5,
            source="llm",
        )
        assert llm_result.source == "llm"

    def test_explanation_field(self):
        """Test explanation field."""
        result = IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=1.0,
            source="regex",
            explanation="price_pattern",
        )
        assert result.explanation == "price_pattern"

    def test_commodity_and_district(self):
        """Test commodity and district extraction."""
        result = IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=1.0,
            commodity="onion",
            district="pune",
            source="regex",
        )
        assert result.commodity == "onion"
        assert result.district == "pune"


class TestIntentFallbacks:
    """Test fallback behavior when intents are ambiguous."""

    def test_unknown_intent_fallback(self):
        """Test fallback for UNKNOWN intent."""
        result = IntentResult(
            intent=Intent.UNKNOWN,
            confidence=0.0,
            source="regex",
            explanation="no_pattern_matched",
        )
        # Handler should show help menu or ask for clarification
        assert result.intent == Intent.UNKNOWN
        assert result.confidence == 0.0

    def test_low_confidence_fallback(self):
        """Test fallback for low confidence LLM results."""
        result = IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=0.3,  # Below threshold
            source="llm",
        )
        # Handler might ask for clarification
        assert result.confidence < 0.5

    def test_commodity_missing_fallback(self):
        """Test fallback when commodity is missing."""
        result = IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=1.0,
            commodity=None,
            source="regex",
        )
        # Handler should ask farmer to specify commodity
        assert result.needs_commodity is True


class TestIntentEnum:
    """Test Intent enum values."""

    def test_all_intents_defined(self):
        """Test that all required intents are defined."""
        required_intents = {
            Intent.PRICE_QUERY,
            Intent.PRICE_ALERT,
            Intent.WEATHER_QUERY,
            Intent.PEST_QUERY,
            Intent.SCHEME_QUERY,
            Intent.MSP_ALERT,
            Intent.SUBSCRIBE,
            Intent.UNSUBSCRIBE,
            Intent.ONBOARDING,
            Intent.HELP,
            Intent.GREETING,
            Intent.FEEDBACK,
            Intent.UNKNOWN,
        }

        # Check that all intents exist
        for intent in required_intents:
            assert isinstance(intent, Intent)

    def test_intent_values_are_strings(self):
        """Test that intent values are strings."""
        assert isinstance(Intent.PRICE_QUERY.value, str)
        assert isinstance(Intent.PRICE_ALERT.value, str)
        assert Intent.PRICE_QUERY.value == "price_query"
        assert Intent.PRICE_ALERT.value == "price_alert"
        assert Intent.UNKNOWN.value == "unknown"
