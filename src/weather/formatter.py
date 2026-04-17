"""Format weather data into WhatsApp replies (Phase 2 Module 1)."""
from __future__ import annotations

from src.weather.models import WeatherQueryResult


# Marathi translation for weather metrics and conditions
_METRIC_MARATHI = {
    "temperature": "तापमान",
    "rainfall": "पाऊस",
    "humidity": "ओलावा",
    "wind_speed": "वारा वेग",
    "pressure": "दबाव",
    "cloud_cover": "ढग",
}

_CONDITION_MARATHI = {
    "Sunny": "धूप",
    "Cloudy": "ढगाळ",
    "Rainy": "पावसाळी",
    "Partly Cloudy": "अर्ध ढगाळ",
    "Clear": "स्वच्छ",
    "Overcast": "ढग",
}


def format_weather_reply(result: WeatherQueryResult, lang: str = "mr") -> str:
    """Format weather query result into a WhatsApp message.

    Supports Marathi and English. Includes metric, value, unit, and advisory.

    Args:
        result: WeatherQueryResult from repository query
        lang: "mr" (Marathi) or "en" (English)

    Returns:
        Formatted message text suitable for WhatsApp
    """
    if not result.found:
        if lang == "mr":
            return (
                "आज हवामान डेटा उपलब्ध नाही. "
                "पुन्हा कृपया प्रयत्न करा. — "
                "Weather data not available today."
            )
        return "Weather data not available today. Please try again."

    record = result.record
    metric_display = _METRIC_MARATHI.get(record.metric, record.metric.replace("_", " "))

    if lang == "mr":
        reply = (
            f"🌤️ {metric_display} — {record.apmc.title()}\n"
            f"मूल्य: {record.value_str} {record.unit}\n"
        )

        if record.range_str:
            reply += f"श्रेणी: {record.range_str}\n"

        if record.condition:
            condition_mr = _CONDITION_MARATHI.get(record.condition, record.condition)
            reply += f"स्थिति: {condition_mr}\n"

        reply += f"स्रोत: {record.source}\n"

        if result.stale:
            reply += "(⚠️ ३-४ तास पुरानो डेटा)\n"

    else:  # English
        reply = (
            f"🌤️ {metric_display.title()} — {record.apmc.title()}\n"
            f"Value: {record.value_str} {record.unit}\n"
        )

        if record.range_str:
            reply += f"Range: {record.range_str}\n"

        if record.condition:
            reply += f"Condition: {record.condition}\n"

        reply += f"Source: {record.source}\n"

        if result.stale:
            reply += "(⚠️ Data is 3-4 hours old)\n"

    # Add forecast if available
    if result.forecast:
        if lang == "mr":
            reply += "\n📅 अंदाजे 3 दिवस:\n"
            for day_rec in result.forecast[:3]:
                reply += f"  • {day_rec.date.strftime('%d %b')}: {day_rec.value_str}{day_rec.unit}\n"
        else:
            reply += "\n📅 Next 3 days:\n"
            for day_rec in result.forecast[:3]:
                reply += f"  • {day_rec.date.strftime('%d %b')}: {day_rec.value_str}{day_rec.unit}\n"

    # Add advisory if available
    if result.record and hasattr(result.record, "advisory") and result.record.advisory:
        advisory = result.record.advisory
        if lang == "mr":
            reply += f"\n⚠️ सल्ला: {advisory}\n"
        else:
            reply += f"\n⚠️ Advisory: {advisory}\n"

    return reply.strip()


def format_weather_not_extracted(lang: str = "mr") -> str:
    """Reply when WEATHER_QUERY intent detected but no metric extracted.

    Asks farmer which weather metric they want.

    Args:
        lang: "mr" (Marathi) or "en" (English)

    Returns:
        Prompt message asking for metric clarification
    """
    if lang == "mr":
        return (
            "कोण सी हवामान माहिती पाहिजे? "
            "तापमान / पाऊस / ओलावा / वारा\n"
            "— Which weather info? Temperature / Rain / Humidity / Wind"
        )
    return (
        "Which weather information do you want?\n"
        "Temperature / Rainfall / Humidity / Wind Speed"
    )
