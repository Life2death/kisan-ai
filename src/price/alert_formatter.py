"""Format price alert subscriptions and notifications."""
from typing import Optional


def format_price_alert_subscription(
    commodity: str,
    condition: str,
    threshold: float,
    district: Optional[str],
    lang: str = "mr",
) -> str:
    """Format price alert subscription confirmation."""
    if lang == "mr":
        district_text = f" ({district})" if district else " (सर्व)"
        condition_display = {">": "से अधिक", "<": "से कम", "==": "बराबर"}.get(condition, condition)
        return (
            f"✅ किंमत अलर्ट सेट केला\n\n"
            f"🌾 पीक: {commodity.capitalize()}\n"
            f"📊 स्थिती: {condition_display}\n"
            f"💹 लक्ष्य किंमत: ₹{threshold:,.0f}/क्विंटल{district_text}\n\n"
            f"जेव्हा {commodity} की किंमत {condition_display} ₹{threshold:,.0f} होईल, तर आपल्याला सूचित केले जाईल।"
        )
    else:
        district_text = f" ({district})" if district else " (all)"
        condition_display = {">": "above", "<": "below", "==": "equals"}.get(condition, condition)
        return (
            f"✅ Price Alert Set\n\n"
            f"🌾 Commodity: {commodity.capitalize()}\n"
            f"📊 Condition: {condition_display}\n"
            f"💹 Target Price: ₹{threshold:,.0f}/quintal{district_text}\n\n"
            f"You'll be notified when {commodity} price goes {condition_display} ₹{threshold:,.0f}."
        )


def format_price_alert_triggered(
    commodity: str,
    condition: str,
    current_price: float,
    threshold: float,
    district: str,
    lang: str = "mr",
) -> str:
    """Format price alert notification when triggered."""
    if lang == "mr":
        condition_display = {">": "से अधिक", "<": "से कम", "==": "बराबर"}.get(condition, condition)
        return (
            f"🚨 किंमत अलर्ट — {commodity.upper()}\n\n"
            f"📈 आपका लक्ष्य किंमत पार हुई!\n"
            f"🌾 पीक: {commodity.capitalize()}\n"
            f"💹 वर्तमान किंमत: ₹{current_price:,.0f}/क्विंटल\n"
            f"📊 आपका लक्ष्य: {condition_display} ₹{threshold:,.0f}\n"
            f"📍 मंडी: {district}\n\n"
            f"💡 अब बेचने का समय! तहसील मंडी से संपर्क करें।"
        )
    else:
        condition_display = {">": "above", "<": "below", "==": "equals"}.get(condition, condition)
        return (
            f"🚨 Price Alert — {commodity.upper()}\n\n"
            f"📈 Your target price has been reached!\n"
            f"🌾 Commodity: {commodity.capitalize()}\n"
            f"💹 Current Price: ₹{current_price:,.0f}/quintal\n"
            f"📊 Your Target: {condition_display} ₹{threshold:,.0f}\n"
            f"📍 Market: {district}\n\n"
            f"💡 Consider selling now! Contact your local mandi."
        )
