"""Parse price thresholds and conditions from user messages."""
import re
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class ThresholdParseError(Exception):
    """Raised when threshold extraction fails."""
    pass


def extract_price_threshold(text: str) -> Tuple[Optional[float], str]:
    """
    Extract price threshold and condition from user message.

    Examples:
    - "alert when onion > 5000" → (5000.0, ">")
    - "सूचित करो कांदा ₹4000 से अधिक होने पर" → (4000.0, ">")
    - "notify when price < 3000" → (3000.0, "<")
    - "alert if equals 2500" → (2500.0, "==")

    Args:
        text: User message containing price threshold

    Returns:
        Tuple of (threshold: float, condition: str)
        condition is one of: ">", "<", "=="
        Raises ThresholdParseError if threshold not found

    """
    t = text.strip()

    # Try to extract condition first (highest priority)
    condition = _extract_condition(t)

    # Extract price value (currency symbol + digits)
    # Handles: 5000, ₹5000, 5,000, ₹5,000
    price = _extract_price_value(t)

    if price is None:
        logger.debug(f"Could not extract price threshold from: {t}")
        raise ThresholdParseError("No price value found in message")

    logger.info(f"Extracted threshold: price={price} condition={condition}")
    return float(price), condition


def _extract_condition(text: str) -> str:
    """
    Extract price condition operator from text.

    Returns: ">", "<", or "==" (default: ">")
    """
    t = text.lower()

    # Greater than patterns
    greater_patterns = [
        r"[>≥]",  # Literal symbols
        r"\bse\s+adhik",  # Hindi: "से अधिक"
        r"\bse\s+zyada",  # Hinglish
        r"\bसे\s+अधिक",  # Marathi
        r"\bसे\s+ज्यादा",  # Marathi variant
        r"\bgreater\s+than\b",  # English
        r"\babove\b",
        r"\bfrom\b",  # "from ₹5000"
    ]

    # Less than patterns
    less_patterns = [
        r"[<≤]",  # Literal symbols
        r"\bse\s+kam",  # Hindi: "से कम"
        r"\bसे\s+कम",  # Marathi
        r"\bless\s+than\b",  # English
        r"\bbelow\b",
    ]

    # Equals patterns
    equals_patterns = [
        r"[=]",  # "="
        r"==",  # "=="
        r"\bequals?\b",  # "equal", "equals"
        r"\bbarabar\b",  # Hindi/Marathi: "बराबर"
        r"\bबराबर\b",  # Marathi Devanagari
        r"\bexactly\b",
    ]

    for pattern in greater_patterns:
        if re.search(pattern, t):
            return ">"

    for pattern in less_patterns:
        if re.search(pattern, t):
            return "<"

    for pattern in equals_patterns:
        if re.search(pattern, t):
            return "=="

    # Default to ">" if no condition found
    return ">"


def _extract_price_value(text: str) -> Optional[float]:
    """
    Extract numeric price value from text.

    Handles: 5000, ₹5000, 5,000, ₹5,000, Rs 5000, रु 5000
    """
    t = text.strip()

    # Pattern: optional currency symbol + optional whitespace + digits (with optional commas)
    # Matches: ₹5000, ₹5,000, Rs 5000, Rs5000, रु5000, just 5000, etc.
    patterns = [
        r"₹\s*([0-9]{1,3}(?:,?[0-9]{3})*)",  # ₹ symbol
        r"Rs\.?\s*([0-9]{1,3}(?:,?[0-9]{3})*)",  # Rs or Rs.
        r"रु\.?\s*([0-9]{1,3}(?:,?[0-9]{3})*)",  # Marathi रु
        r"(?:^|\s)([0-9]{1,3}(?:,?[0-9]{3})*)\s*(?:rupees?|रु|rs|inr)?(?:\s|$|/qt)",  # Bare number
    ]

    for pattern in patterns:
        match = re.search(pattern, t, re.IGNORECASE | re.UNICODE)
        if match:
            price_str = match.group(1)
            # Remove commas for parsing
            price_str = price_str.replace(",", "")
            try:
                return float(price_str)
            except ValueError:
                continue

    return None


def parse_alert_message(text: str) -> Tuple[Optional[float], str]:
    """
    Convenience wrapper for extract_price_threshold with error handling.

    Args:
        text: User message

    Returns:
        (threshold, condition) or (None, ">") if parsing fails
    """
    try:
        return extract_price_threshold(text)
    except ThresholdParseError as e:
        logger.warning(f"Threshold parse error: {e}")
        return None, ">"
