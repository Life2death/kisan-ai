"""Format price query results into WhatsApp replies (Marathi + English)."""
from __future__ import annotations

from src.price.models import MandiPriceRecord, PriceQueryResult


def format_price_reply(result: PriceQueryResult, lang: str = "mr") -> str:
    """
    Format PriceQueryResult into a human-readable WhatsApp message.
    lang: "mr" (Marathi) or "en" (English)
    """
    q = result.query
    commodity_display = q.commodity.replace("_", " ").title()

    if not result.found:
        if result.missing_district:
            return (
                "कृपया पहिले आपल्या जिल्हाचा नोंदणी करा. — "
                "Please register your district first."
            )
        if lang == "mr":
            return f"आज {commodity_display} भाव उपलब्ध नाही. — No {commodity_display} price available today."
        return f"No {commodity_display} price available today."

    if result.stale:
        stale_msg = " (कालचा भाव — yesterday's price)" if lang == "mr" else " (yesterday's price)"
    else:
        stale_msg = ""

    # Format top result
    top = result.records[0]
    if lang == "mr":
        reply = (
            f"🌾 {commodity_display} — {top.mandi_display}\n"
            f"दर: {top.price_str} {top.range_str}\n"
            f"स्रोत: {top.source}{stale_msg}\n"
        )
    else:
        reply = (
            f"🌾 {commodity_display} — {top.mandi_display}\n"
            f"Price: {top.price_str} {top.range_str}\n"
            f"Source: {top.source}{stale_msg}\n"
        )

    # Add other mandis if available
    if len(result.records) > 1:
        if lang == "mr":
            reply += "\n📍 इतर मंडी:"
        else:
            reply += "\n📍 Other mandis:"
        for rec in result.records[1:4]:  # top 3 more
            reply += f"\n  • {rec.mandi_display}: {rec.price_str}"

    return reply


def format_price_query_needed(commodity: str, lang: str = "mr") -> str:
    """Reply when classifier returns PRICE_QUERY but no commodity extracted."""
    if lang == "mr":
        return (
            f"कोण सा पीक? उदा: कांदा, तूर, सोयाबीन, कपास, टोमॅटो?\n"
            f"Which crop? E.g: onion, tur, soyabean, cotton, tomato?"
        )
    return "Which crop? E.g: onion, tur, soyabean, cotton, tomato?"
