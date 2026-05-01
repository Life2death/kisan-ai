"""Daily farmer brief composer — queries live DB for weather + mandi prices.

Sends 4 WhatsApp messages in sequence:
  Part 1 — Header + 7-day weather forecast (from weather_observations)
  Part 2 — APMC mandi prices (from mandi_prices)
  Part 3 — Disease & pest watch (weather-based advisory)
  Part 4 — Irrigation plan + action checklist
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.weather import WeatherObservation
from src.models.price import MandiPrice

logger = logging.getLogger(__name__)

_MARATHI_DAYS = ["सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]
_MARATHI_MONTHS = [
    "जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून",
    "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर",
]

_SIGNATURE = "— अन्नदाता 🌾"

# Target talukas/villages for weather (slug must match weather_observations.apmc)
_WEATHER_APMCS = ["goregaon_parner", "wadegaon_parner", "parner"]

# Known APMC display names → Marathi short name
_MANDI_MARATHI: dict[str, str] = {
    "Pune(Pimpri) APMC": "पिंपरी APMC",
    "Pune APMC": "पुणे APMC",
    "Pune(Market Yard) APMC": "मार्केट यार्ड APMC",
    "Pune(Moshi) APMC": "मोशी APMC",
    "Varud(Rajura Bazar) APMC": "वरूड APMC",
    "Sangola APMC": "सांगोला APMC",
    "Lasalgaon APMC": "लासलगाव APMC",
    "Nashik APMC": "नाशिक APMC",
    "Ahmednagar APMC": "अहमदनगर APMC",
    "Sangamner APMC": "संगमनेर APMC",
    "Rahuri APMC": "राहुरी APMC",
    "Pimpalgaon APMC": "पिंपळगाव APMC",
    "Manmad APMC": "मनमाड APMC",
    "Yeola APMC": "येवला APMC",
    "Kopargaon APMC": "कोपरगाव APMC",
    "Baramati APMC": "बारामती APMC",
    "Indapur APMC": "इंदापूर APMC",
    "Vashi APMC": "वाशी APMC",
}


def _mandi_mr(mandi_name: str) -> str:
    """Return Marathi name for a mandi; strips English suffix if unknown."""
    if mandi_name in _MANDI_MARATHI:
        return _MANDI_MARATHI[mandi_name]
    # Strip trailing " APMC" so at least English location shows cleanly
    return mandi_name.replace(" APMC", "").strip()


# District slug → Marathi display name
_DISTRICT_MARATHI: dict[str, str] = {
    "pune": "पुणे",
    "ahilyanagar": "अहिल्यानगर",
    "nashik": "नाशिक",
    "amravati": "अमरावती",
    "solapur": "सोलापूर",
    "navi_mumbai": "नवी मुंबई",
    "mumbai": "मुंबई",
    "latur": "लातूर",
    "jalgaon": "जळगाव",
    "kolhapur": "कोल्हापूर",
    "sangli": "सांगली",
    "satara": "सातारा",
    "aurangabad": "औरंगाबाद",
    "osmanabad": "उस्मानाबाद",
    "nanded": "नांदेड",
    "wardha": "वर्धा",
    "nagpur": "नागपूर",
    "buldana": "बुलढाणा",
    "akola": "अकोला",
    "yavatmal": "यवतमाळ",
}

# Crops to show in brief (Marathi label → DB crop slug)
_PRICE_CROPS = {
    "कांदा": "onion",
    "टोमॅटो": "tomato",
    "बटाटा": "potato",
    "सोयाबीन": "soyabean",
    "तूर": "tur",
    "हरभरा": "gram",
    "ज्वारी": "jowar",
    "बाजरी": "bajra",
    "गहू": "wheat",
    "मका": "maize",
    "कापूस": "cotton",
    "डाळिंब": "pomegranate",
    "द्राक्षे": "grapes",
    "लसूण": "garlic",
    "हळद": "turmeric",
    "शेंगदाणा": "groundnut",
}


async def compose_daily_brief_marathi(
    brief_date: date | None = None,
    session: AsyncSession | None = None,
) -> list[str]:
    """Return 4-part Marathi brief, querying live DB for weather + prices.

    Falls back to a minimal message if DB has no data yet.
    """
    if brief_date is None:
        brief_date = date.today()

    day_name = _MARATHI_DAYS[brief_date.weekday()]
    month_name = _MARATHI_MONTHS[brief_date.month - 1]
    date_str = f"{brief_date.day} {month_name} {brief_date.year}"

    weather_rows = []
    price_rows = []

    if session:
        weather_rows = await _fetch_weather(session, brief_date)
        price_rows = await _fetch_prices(session, brief_date)

    part1 = _build_weather_part(brief_date, day_name, date_str, weather_rows)
    part2 = _build_price_part(brief_date, price_rows)
    part3 = _build_pest_part(weather_rows)
    part4 = _build_irrigation_part(weather_rows)

    return [part1, part2, part3, part4]


# ── DB fetchers ───────────────────────────────────────────────────────────────

async def _fetch_weather(session: AsyncSession, brief_date: date) -> list[WeatherObservation]:
    """Fetch weather observations for target villages, today + 7 days."""
    end_date = brief_date + timedelta(days=7)
    result = await session.execute(
        select(WeatherObservation)
        .where(
            and_(
                WeatherObservation.apmc.in_(_WEATHER_APMCS),
                WeatherObservation.date >= brief_date,
                WeatherObservation.date <= end_date,
            )
        )
        .order_by(WeatherObservation.date, WeatherObservation.apmc, WeatherObservation.metric)
    )
    return list(result.scalars().all())


async def _fetch_prices(session: AsyncSession, brief_date: date) -> list[MandiPrice]:
    """Fetch latest mandi prices — most recent available within last 14 days."""
    for days_back in range(14):
        check_date = brief_date - timedelta(days=days_back)
        result = await session.execute(
            select(MandiPrice)
            .where(MandiPrice.date == check_date)
            .order_by(MandiPrice.crop, MandiPrice.modal_price.desc())
        )
        rows = list(result.scalars().all())
        if rows:
            logger.info("daily_brief: using mandi prices from %s (%d rows)", check_date, len(rows))
            return rows
    logger.warning("daily_brief: no mandi prices found in last 14 days")
    return []


# ── Part builders ─────────────────────────────────────────────────────────────

def _build_weather_part(
    brief_date: date, day_name: str, date_str: str,
    rows: list[WeatherObservation],
) -> str:
    header = (
        f"🌾 *शेतकरी दैनंदिन माहिती — गोरेगाव व वडेगाव, पारनेर तालुका*\n"
        f"आज: {day_name}, {date_str}\n\n"
        "☀️ *हवामान अंदाज — पुढील ७ दिवस (पारनेर तालुका)*\n"
    )

    if not rows:
        return header + f"⚠️ हवामान डेटा उपलब्ध नाही. कृपया नंतर तपासा.\n\n{_SIGNATURE}"

    # Build daily summary from weather_observations
    # Group by date → {date: {metric: value}}
    daily: dict[date, dict[str, Decimal]] = {}
    conditions: dict[date, str] = {}
    for row in rows:
        d = row.date
        if d not in daily:
            daily[d] = {}
        if row.metric == "temperature":
            if row.max_value:
                daily[d]["temp_max"] = row.max_value
            if row.min_value:
                daily[d]["temp_min"] = row.min_value
            if not row.max_value and not row.min_value:
                daily[d]["temp_max"] = row.value
        elif row.metric == "rainfall":
            daily[d]["rain"] = row.value
        elif row.metric == "humidity":
            daily[d]["humidity"] = row.value
        if row.condition and d not in conditions:
            conditions[d] = row.condition

    table = "दिवस | तारीख | कमाल°C | किमान°C | पाऊस (मि.मी.) | हवामान\n"
    for i in range(8):
        d = brief_date + timedelta(days=i)
        if d not in daily:
            continue
        m = daily[d]
        mr_day = _MARATHI_DAYS[d.weekday()][:3]
        date_label = f"{d.day} {_MARATHI_MONTHS[d.month - 1][:3]}"
        t_max = f"~{int(m['temp_max'])}" if "temp_max" in m else "—"
        t_min = f"~{int(m['temp_min'])}" if "temp_min" in m else "—"
        rain = f"{m['rain']:.1f}" if "rain" in m else "०"
        cond = conditions.get(d, "")
        table += f"{mr_day} | {date_label} | {t_max} | {t_min} | {rain} | {cond}\n"

    return header + table + f"\n{_SIGNATURE}"


def _build_price_part(brief_date: date, rows: list[MandiPrice]) -> str:
    header = "💰 *आजचे APMC मंडी भाव — महाराष्ट्र* (₹/क्विंटल)\n"

    if not rows:
        return header + "⚠️ आजचे मंडी भाव उपलब्ध नाहीत. संध्याकाळी ८ नंतर पुन्हा तपासा.\n\n— अन्नदाता 🌾"

    # Best price per crop (highest modal across all markets)
    best: dict[str, MandiPrice] = {}
    for row in rows:
        crop = row.crop
        if crop not in best or (row.modal_price and (best[crop].modal_price or 0) < row.modal_price):
            best[crop] = row

    lines = [header]
    for marathi_label, slug in _PRICE_CROPS.items():
        if slug in best:
            p = best[slug]
            low   = f"₹{int(p.min_price)}"   if p.min_price   else "—"
            modal = f"₹{int(p.modal_price)}"  if p.modal_price else "—"
            high  = f"₹{int(p.max_price)}"    if p.max_price   else "—"
            alert = " ⚠️" if slug == "onion" and p.modal_price and p.modal_price < 1000 else ""
            lines.append(f"{marathi_label:10s}: {low} | {modal} | {high}{alert}")
        else:
            lines.append(f"{marathi_label:10s}: — | — | —")

    # Group crops by their source district + mandi for attribution
    # district_slug → (Marathi district name, mandi display name, [Marathi crop labels])
    source_map: dict[str, tuple[str, str, list[str]]] = {}
    for marathi_label, slug in _PRICE_CROPS.items():
        if slug not in best:
            continue
        p = best[slug]
        dist_slug = p.district or "unknown"
        if dist_slug not in source_map:
            dist_mr = _DISTRICT_MARATHI.get(dist_slug, dist_slug)
            source_map[dist_slug] = (dist_mr, p.mandi, [])
        source_map[dist_slug][2].append(marathi_label)

    if source_map:
        lines.append("\n📍 *भाव कोठून आले:*")
        for dist_slug, (dist_mr, mandi_name, crop_labels) in source_map.items():
            crops_str = ", ".join(crop_labels)
            lines.append(f"  {crops_str} — {dist_mr} ({_mandi_mr(mandi_name)})")

    price_date = rows[0].date if rows else brief_date
    lines.append(f"\nस्रोत: Agmarknet | तारीख: {price_date.day} {_MARATHI_MONTHS[price_date.month - 1]}")
    lines.append(f"\n{_SIGNATURE}")
    return "\n".join(lines)


def _build_pest_part(rows: list[WeatherObservation]) -> str:
    """Weather-based pest advisory."""
    header = "🦠 *रोग व कीड सतर्कता — हवामानावर आधारित*\n\n"

    # Extract today's humidity and temp to give relevant advisory
    humidity = None
    temp_max = None
    for row in rows:
        if row.forecast_days_ahead == 0:
            if row.metric == "humidity" and humidity is None:
                humidity = float(row.value)
            if row.metric == "temperature" and row.max_value and temp_max is None:
                temp_max = float(row.max_value)

    advisories = []

    # High humidity → fungal disease risk
    if humidity and humidity > 70:
        advisories.append(
            "🚨 *कांदा — फुलकिडे व करपा* (जास्त आर्द्रता)\n"
            "लक्षण: पानांवर रुपेरी रेषा, पान कुरवाळणे.\n"
            "उपाय: फिप्रोनिल ५% SC @ २ मिली/लिटर फवारा."
        )
        advisories.append(
            "🚨 *डाळिंब — जिवाणू करपा (तेल्या)*\n"
            "उपाय: बोर्डो मिश्रण १% + स्ट्रेप्टोसायक्लीन ०.५ ग्रॅ/लिटर."
        )

    # High temp → thrips and heat stress
    if temp_max and temp_max > 35:
        advisories.append(
            f"🚨 *उष्णता ताण ({int(temp_max)}°C)* — टोमॅटो/वांगे\n"
            "थंड वेळात हलके पाणी द्या. दुपारी ११–४ शेतात काम टाळा."
        )

    if not advisories:
        advisories.append("✅ आज कोणताही विशेष कीड/रोग इशारा नाही. नेहमीप्रमाणे देखरेख ठेवा.")

    return header + "\n\n".join(advisories) + "\n\n— अन्नदाता 🌾"


def _build_irrigation_part(rows: list[WeatherObservation]) -> str:
    """Weather-based irrigation and action checklist."""
    header = "💧 *सिंचन योजना व कृती यादी*\n\n"

    # Check if rain expected in next 2 days
    rain_coming = False
    for row in rows:
        if row.metric == "rainfall" and row.forecast_days_ahead in (1, 2):
            if row.value and row.value > 2:
                rain_coming = True
                break

    if rain_coming:
        irrigation = (
            "🌧️ *पुढील २ दिवसात पाऊस अपेक्षित*\n"
            "• सिंचन थांबवा — नैसर्गिक पाणी मिळेल\n"
            "• काढलेले उत्पादन व चारा ताडपत्रीखाली झाका\n"
            "• रासायनिक फवारण्या पुढे ढकला"
        )
    else:
        irrigation = (
            "☀️ *कोरडे हवामान — सिंचन सुरू ठेवा*\n"
            "• कांदा कंद: दर ४–५ दिवसांनी हलके पाणी\n"
            "• टोमॅटो/वांगे: ठिबक चालू, दर २ दिवस\n"
            "• डाळिंब/मोसंबी: दर ३ दिवस, ३०–४० लिटर/झाड\n"
            "• सकाळी लवकर किंवा सायं ५ नंतरच फवारणी करा"
        )

    checklist = (
        "\n📋 *त्वरित कृती यादी — आज*\n\n"
        "१. 🌅 सकाळी: कांदा फुलकिडे, आंबा हॉपर, डाळिंब करपा तपासा\n"
        "२. ☀️ दुपार: जनावरांना सावली + दुप्पट पाणी द्या\n"
        "३. 🌇 संध्याकाळी: तणावग्रस्त पिकांना हलके सिंचन\n"
        "४. 📱 *माहिती* टाइप करा — उद्याचा ताजा अहवाल मिळवा\n\n"
        "— अन्नदाता 🌾"
    )

    return header + irrigation + checklist
