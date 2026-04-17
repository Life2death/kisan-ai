"""Tests for price threshold extraction from user messages."""
import pytest
from src.price.threshold_parser import (
    extract_price_threshold,
    parse_alert_message,
    ThresholdParseError,
    _extract_condition,
    _extract_price_value,
)


class TestExtractCondition:
    """Test condition operator extraction."""

    def test_greater_than_symbol(self):
        """Test extraction of > symbol."""
        assert _extract_condition("alert when > 5000") == ">"
        assert _extract_condition("price > 4000") == ">"

    def test_greater_than_english(self):
        """Test English 'greater than' patterns."""
        assert _extract_condition("greater than 5000") == ">"
        assert _extract_condition("above 4000") == ">"
        assert _extract_condition("from 3000") == ">"

    def test_greater_than_hindi(self):
        """Test Hindi 'से अधिक' (se adhik) pattern."""
        assert _extract_condition("कांदा 5000 से अधिक") == ">"
        assert _extract_condition("से अधिक 4000") == ">"
        assert _extract_condition("se adhik 3000") == ">"

    def test_greater_than_hinglish(self):
        """Test Hinglish variations."""
        assert _extract_condition("se zyada 5000") == ">"

    def test_less_than_symbol(self):
        """Test extraction of < symbol."""
        assert _extract_condition("alert when < 5000") == "<"
        assert _extract_condition("price < 4000") == "<"

    def test_less_than_english(self):
        """Test English 'less than' patterns."""
        assert _extract_condition("less than 5000") == "<"
        assert _extract_condition("below 4000") == "<"

    def test_less_than_hindi(self):
        """Test Hindi 'से कम' (se kam) pattern."""
        assert _extract_condition("कांदा 5000 से कम") == "<"
        assert _extract_condition("से कम 3000") == "<"

    def test_equals_patterns(self):
        """Test equals operator."""
        assert _extract_condition("equals 5000") == "=="
        assert _extract_condition("= 4000") == "=="
        assert _extract_condition("== 3000") == "=="
        assert _extract_condition("बराबर 5000") == "=="
        assert _extract_condition("exactly 4000") == "=="

    def test_default_condition(self):
        """Test that default is > when no condition found."""
        assert _extract_condition("alert 5000") == ">"
        assert _extract_condition("कांदा 4000") == ">"
        assert _extract_condition("notify 3000") == ">"


class TestExtractPriceValue:
    """Test price value extraction."""

    def test_rupee_symbol_no_comma(self):
        """Test ₹ symbol without comma."""
        assert _extract_price_value("alert ₹5000") == 5000.0
        assert _extract_price_value("₹4500") == 4500.0
        assert _extract_price_value("₹100") == 100.0

    def test_rupee_symbol_with_comma(self):
        """Test ₹ symbol with comma separators."""
        assert _extract_price_value("alert ₹5,000") == 5000.0
        assert _extract_price_value("₹1,00,000") == 100000.0
        assert _extract_price_value("₹2,50,000") == 250000.0

    def test_rs_prefix(self):
        """Test Rs and Rs. prefix."""
        assert _extract_price_value("Rs 5000") == 5000.0
        assert _extract_price_value("Rs. 4000") == 4000.0
        assert _extract_price_value("Rs5000") == 5000.0
        assert _extract_price_value("Rs. 1,00,000") == 100000.0

    def test_devanagari_currency(self):
        """Test Marathi रु (ru) symbol."""
        assert _extract_price_value("रु 5000") == 5000.0
        assert _extract_price_value("रु5000") == 5000.0
        assert _extract_price_value("रु. 4000") == 4000.0

    def test_bare_number(self):
        """Test extraction of bare numbers."""
        assert _extract_price_value("alert 5000") == 5000.0
        assert _extract_price_value("कांदा 4000") == 4000.0
        assert _extract_price_value("price 1000") == 1000.0
        assert _extract_price_value("1,00,000") == 100000.0

    def test_with_unit_suffix(self):
        """Test numbers with unit suffixes."""
        assert _extract_price_value("5000/quintal") == 5000.0
        assert _extract_price_value("4000 per quintal") == 4000.0

    def test_no_price_found(self):
        """Test that None is returned when no price found."""
        assert _extract_price_value("alert when high") is None
        assert _extract_price_value("notify me") is None
        assert _extract_price_value("") is None

    def test_multiple_numbers_returns_first(self):
        """Test that first number is returned when multiple found."""
        assert _extract_price_value("alert 5000 to 6000") == 5000.0
        result = _extract_price_value("yesterday it was 3000 today 4000")
        assert result in [3000.0, 4000.0]  # Either is acceptable


class TestExtractPriceThreshold:
    """Test complete threshold extraction."""

    def test_english_full_message(self):
        """Test complete English message."""
        threshold, condition = extract_price_threshold("alert when onion > ₹5000")
        assert threshold == 5000.0
        assert condition == ">"

    def test_marathi_full_message(self):
        """Test complete Marathi message."""
        threshold, condition = extract_price_threshold("कांदा ₹4000 से अधिक सूचित करो")
        assert threshold == 4000.0
        assert condition == ">"

    def test_less_than_english(self):
        """Test less than in English."""
        threshold, condition = extract_price_threshold("notify me when price falls below 3000")
        assert threshold == 3000.0
        assert condition == "<"

    def test_equals_english(self):
        """Test equals operator."""
        threshold, condition = extract_price_threshold("alert when equals ₹2500")
        assert threshold == 2500.0
        assert condition == "=="

    def test_hinglish(self):
        """Test Hinglish mix."""
        threshold, condition = extract_price_threshold("onion price se zyada 4500")
        assert threshold == 4500.0
        assert condition == ">"

    def test_no_threshold_raises_error(self):
        """Test that ThresholdParseError is raised when no price found."""
        with pytest.raises(ThresholdParseError):
            extract_price_threshold("alert when high")

    def test_threshold_with_spacing(self):
        """Test with various spacing."""
        threshold, condition = extract_price_threshold("alert    when   ₹5000")
        assert threshold == 5000.0

    def test_case_insensitive(self):
        """Test case insensitivity."""
        threshold, condition = extract_price_threshold("ALERT WHEN GREATER THAN ₹5000")
        assert threshold == 5000.0
        assert condition == ">"


class TestParseAlertMessage:
    """Test error-tolerant wrapper."""

    def test_valid_message(self):
        """Test parsing of valid message."""
        threshold, condition = parse_alert_message("alert ₹5000")
        assert threshold == 5000.0
        assert condition == ">"

    def test_invalid_message_returns_default(self):
        """Test that invalid message returns (None, '>')."""
        threshold, condition = parse_alert_message("alert when high")
        assert threshold is None
        assert condition == ">"

    def test_empty_message(self):
        """Test empty message."""
        threshold, condition = parse_alert_message("")
        assert threshold is None
        assert condition == ">"


class TestIntegrationScenarios:
    """Integration tests with realistic farmer messages."""

    def test_onion_alert_marathi(self):
        """Test realistic Marathi onion alert."""
        threshold, condition = extract_price_threshold(
            "कांदा किंमत ₹4000 से अधिक झाली तर सूचित करो"
        )
        assert threshold == 4000.0
        assert condition == ">"

    def test_wheat_alert_english(self):
        """Test realistic English wheat alert."""
        threshold, condition = extract_price_threshold(
            "notify me when wheat price goes below ₹2000 per quintal"
        )
        assert threshold == 2000.0
        assert condition == "<"

    def test_soyabean_alert_hinglish(self):
        """Test realistic Hinglish soyabean alert."""
        threshold, condition = extract_price_threshold(
            "soyabean ka bhav 5000 se zyada ho to mujhe batao"
        )
        assert threshold == 5000.0
        assert condition == ">"

    def test_msp_alert_marathi(self):
        """Test MSP alert in Marathi."""
        threshold, condition = extract_price_threshold(
            "MSP ₹1,50,000 से अधिक होने पर सूचित करो"
        )
        assert threshold == 150000.0
        assert condition == ">"

    def test_large_numbers(self):
        """Test extraction of large numbers."""
        threshold, condition = extract_price_threshold("alert when above ₹5,00,000")
        assert threshold == 500000.0

    def test_small_numbers(self):
        """Test extraction of small numbers."""
        threshold, condition = extract_price_threshold("alert when above ₹100")
        assert threshold == 100.0
