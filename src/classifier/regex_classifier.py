"""Regex-based intent classifier — handles ~85% of farmer queries for free.

Design:
- Patterns are compiled once at module import (fast).
- Each pattern list covers English, Hinglish transliteration, and Marathi Devanagari.
- Commodity extraction is a separate pass so "soyabean bhav" and "bhav soyabean" both work.
- District extraction feeds the price handler (optional — many farmers say "today's price"
  meaning their own registered district).
- Matching is case-insensitive and strips leading/trailing whitespace.

Commodity aliases mirror normalizer.py but live here too so the classifier is
self-contained (no DB dependency).
"""
from __future__ import annotations

import re
from typing import Optional

from src.classifier.intents import Intent, IntentResult
from src.ingestion.normalizer import normalize_commodity, normalize_district


# ──────────────────────────── COMPILED PATTERNS ────────────────────────────

def _p(*patterns: str) -> re.Pattern:
    """Compile a set of patterns into one OR regex (case-insensitive)."""
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE | re.UNICODE)


# ── Price query triggers ─────────────────────────────────────────────────
_PRICE_RE = _p(
    # English
    r"\bprice\b", r"\brate\b", r"\brates\b", r"\bbhav\b", r"\bmarket\b",
    r"\bmandi\b", r"\btoday.?s?\s+price", r"\baaj\s+ka\s+bhav\b",
    r"\bkitna\s+(hai|h)\b", r"\bkya\s+(rate|bhav)\b",
    # Marathi Devanagari
    r"भाव", r"दर", r"किंमत", r"बाजार\s*भाव", r"मंडी", r"आजचा\s*भाव",
    r"आजचा\s*दर", r"किती\s*(आहे|आहे\?)?",
    # Hinglish phonetic
    r"\bkanda\s*(ka\s*)?bhav\b", r"\bpyaz\s*(ka\s*)?rate\b",
    r"\bsoya\w*\s*(ka\s*)?bhav\b", r"\btur\s*(dal\s*)?(ka\s*)?bhav\b",
)

# ── Subscribe triggers ───────────────────────────────────────────────────
_SUBSCRIBE_RE = _p(
    r"\bsubscribe\b", r"\bstart\b", r"\bsuru\b",
    r"\bjoin\b", r"\bhaan\b", r"\byes\b",
    r"\bdaily\s+(alert|update|price)", r"\bsandesh\b",
    # Marathi — "पाठवा" (send/deliver) is the clearest subscribe signal;
    # also catches "दैनिक भाव पाठवा" (daily price send = subscribe).
    r"पाठवा", r"सुरू\s*कर", r"सदस्य\s*व्हा",
    r"होय",
    # "हो" = yes in Marathi — only standalone to avoid matching mid-word
    r"^\s*हो\s*[!.]*\s*$",
)

# ── Unsubscribe triggers ─────────────────────────────────────────────────
_UNSUBSCRIBE_RE = _p(
    r"\bunsubscribe\b", r"\bstop\b", r"\bband\b", r"\boff\b",
    r"\bcancel\b", r"\bquit\b", r"\bbye\b",
    r"\bno\s+more\b", r"\bnahi\s+chahiye\b",
    # Marathi
    r"थांबव", r"बंद\s*कर", r"रद्द\s*कर", r"नको",
)

# ── Onboarding triggers ──────────────────────────────────────────────────
_ONBOARDING_RE = _p(
    r"\bregister\b", r"\bregistration\b", r"\bnew\s+user\b",
    r"\bsign\s*up\b", r"\bkisan\s+ai\b",
    r"\bshuru\s+karo\b", r"\bkaise\s+(use|kare)\b",
    r"\bnaya\s+(user|kisan)\b",
    # Marathi
    r"नोंदणी", r"नवीन\s*शेतकरी", r"कसे\s*वापरावे",
)

# ── Help triggers ─────────────────────────────────────────────────────────
_HELP_RE = _p(
    r"\bhelp\b", r"\b(madad|help\s*karo)\b", r"\bwhat\s+can\s+you\s+do\b",
    r"\bcommands\b", r"\bmenu\b",
    # Marathi
    r"मदत", r"काय\s*करता\s*येते", r"सूचना",
)

# ── Greeting triggers ─────────────────────────────────────────────────────
_GREETING_RE = _p(
    r"^\s*(hi|hello|hey|namaste|namaskar|ram\s*ram|jai\s*hind)\s*[!.]*\s*$",
    r"^\s*(नमस्ते|नमस्कार|राम\s*राम|जय\s*हिंद)\s*[!.]*\s*$",
    r"^\s*hy\s*$",
)

# ── Feedback triggers ─────────────────────────────────────────────────────
_FEEDBACK_RE = _p(
    r"\bfeedback\b", r"\bsuggestion\b", r"\bcomplaint\b",
    r"\bpraise\b", r"\bthank\b", r"\bshukriya\b",
    # Marathi
    r"अभिप्राय", r"सूचना\s*द्या", r"तक्रार", r"धन्यवाद",
)

# ── Weather query triggers (Phase 2) ──────────────────────────────────────
_WEATHER_RE = _p(
    # English
    r"\bweather\b", r"\bforecast\b", r"\brain(fall)?\b",
    r"\btemperature\b", r"\btemp\b", r"\bhumidity\b", r"\bwind\b",
    r"\bkaisa\s+mausam\b", r"\bhow.?s?\s+the\s+weather\b",
    # Marathi Devanagari
    r"हवामान", r"पाऊस", r"पावसाचा\s*अंदाज", r"तापमान", r"ओलावा",
    r"आजचे\s*हवामान", r"मौसम",
    # Hinglish
    r"\baaj\s+ka\s+mausam\b", r"\bgarmi\b", r"\bthandi\b",
)

# ── Price alert triggers (Phase 2 Module 5) ──────────────────────────────────
_PRICE_ALERT_RE = _p(
    # English
    r"\balert\b", r"\bnotif(ication)?\b", r"\bwhen\s+(price|rate)\b",
    r"\bnotify\s+me\b", r"\btell\s+me\s+(if|when)\b",
    r"\bset\s+(alert|alarm|notification)\b", r"\bset\s+price\b",
    # Marathi Devanagari
    r"सूचित\s*कर", r"सूचना", r"जेव्हा", r"अलर्ट",
    r"किंमत\s*बदल", r"अलर्ट\s*लाग",
    # Hinglish
    r"\balert\s*do\b", r"\bnotify\s+karo\b", r"\bjab\s+(price|bhav)\b",
)

# ── Government scheme query triggers (Phase 2 Module 4) ────────────────────
_SCHEME_QUERY_RE = _p(
    # English
    r"\bschemes?\b", r"\beligible\b", r"\beligibility\b", r"\bsubsid(?:y|ies)\b",
    r"\bgrants?\b", r"\baids?\b", r"\bpmkisan\b", r"\bfasal\b",
    r"\bgovernment\s+(?:scheme|support|aid)s?\b", r"\bwhat\s+schemes?\b",
    r"\bwhat\s+(?:can\s+)?i\s+(?:get|avail)\b",
    # Marathi Devanagari
    r"योजना", r"अर्ह", r"अर्हता", r"सहायता", r"अनुदान",
    r"पीएम\s*किसान", r"केंद्र\s*सरकार", r"राज्य\s*सरकार",
    r"सरकारी\s*योजना", r"कोणती\s*योजना",
    # Hinglish
    r"\byojana\b", r"\bkaunsi\s+yojana\b", r"\bkisaan\s+yojana\b",
)

# ── Pest/Disease diagnosis triggers (Phase 2 Module 3) ──────────────────────
_PEST_QUERY_RE = _p(
    # English
    r"\bpests?\b", r"\bdiseases?\b", r"\bbugs?\b", r"\binfestations?\b",
    r"\bwhat.?s\s+(?:wrong|wrong)\b", r"\bmy\s+(?:plant|crop)s?\s+(?:is\s+)?sick\b",
    r"\bdiagnose\b", r"\bwhat.?s\s+this\b", r"\bidentify\b",
    r"\b(?:white|yellow|dark)\s+(?:spots?|leaves?)\b", r"\byellow\b",
    # Marathi Devanagari
    r"कीट", r"रोग", r"संक्रमण", r"बोंड", r"झाल\w*\s+आहे",
    r"काय\s+समस्या", r"पाहून\s*द्या", r"दिसून\s*द्या",
    # Hinglish
    r"\bpests?\b", r"\bkeeta\b", r"\brog\b", r"\binfections?\b",
)

# ── MSP alert triggers (Phase 2 Module 4 — minimum support price alerts) ────
_MSP_ALERT_RE = _p(
    # English
    r"\bmsp\b", r"\bminimum\s+support\s+price\b", r"\bsupport\s+price\b",
    r"\bwhen\s+msp\b", r"\bset\s+msp\b", r"\bmsp\s+alert\b",
    # Marathi Devanagari
    r"न्यूनतम\s*समर्थन\s*मूल्य", r"न्यूनतम\s*मूल्य", r"समर्थन\s*मूल्य",
    r"एमएसपी", r"एमएसपी\s*अलर्ट",
    # Hinglish
    r"\bmsp\b", r"\bminimum\s+price\b",
)

# ── Weather metric extraction (Phase 2) ────────────────────────────────────
_WEATHER_METRIC_PATTERNS: list[tuple[re.Pattern, str]] = [
    (_p(r"\btemp\b", r"\btemperature\b", r"\bgarmi\b", r"तापमान"), "temperature"),
    (_p(r"\brain\b", r"\brainfall\b", r"\bprecip\b", r"पाऊस"), "rainfall"),
    (_p(r"\bhumidity\b", r"\bhumid\b", r"ओलावा"), "humidity"),
    (_p(r"\bwind\b", r"\bwind\s*speed\b", r"वारा"), "wind_speed"),
    (_p(r"\bpressure\b", r"\bbarometer\b"), "pressure"),
]

# ── Commodity extraction ─────────────────────────────────────────────────
# Each tuple: (regex, canonical_slug)
_COMMODITY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (_p(r"\bonion\b", r"\bkanda\b", r"\bkande\b", r"\bpyaz\b", r"\bpyaaz\b",
        r"कांदा", r"कांदे"), "onion"),
    (_p(r"\btur\b", r"\btoor\b", r"\barhar\b", r"\bred\s*gram\b",
        r"\bpigeon\s*pea", r"तूर"), "tur"),
    (_p(r"\bsoya\w*\b", r"\bsoyabean\b", r"\bsoybean\b",
        r"सोयाबीन"), "soyabean"),
    (_p(r"\bcotton\b", r"\bkapas\b", r"कापूस"), "cotton"),
    (_p(r"\btomato\b", r"\btamatar\b", r"टोमॅटो"), "tomato"),
    (_p(r"\bpotato\b", r"\baloo\b", r"\baloo\b", r"बटाटा"), "potato"),
    (_p(r"\bwheat\b", r"\bgehu\b", r"\bgahu\b", r"गहू"), "wheat"),
    (_p(r"\bchana\b", r"\bgram\b", r"\bbengal\s*gram\b",
        r"\bharbhara\b", r"चणा"), "chana"),
    (_p(r"\bjowar\b", r"\bsorghum\b", r"ज्वारी"), "jowar"),
    (_p(r"\bbajra\b", r"\bmillet\b", r"बाजरी"), "bajra"),
    (_p(r"\bgrapes\b", r"\bdraksh\b", r"द्राक्षे"), "grapes"),
    (_p(r"\bpomegranate\b", r"\bdaaliimb\b", r"डाळिंब"), "pomegranate"),
    (_p(r"\bmaize\b", r"\bcorn\b", r"\bmaka\b", r"मका"), "maize"),
]

# ── District extraction ──────────────────────────────────────────────────
_DISTRICT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (_p(r"\bpune\b", r"पुणे"), "pune"),
    (_p(r"\bahilyanagar\b", r"\bahmednagar\b", r"\ba\.?\s*nagar\b",
        r"अहिल्यानगर", r"अहमदनगर"), "ahilyanagar"),
    (_p(r"\bnavi\s*mumbai\b", r"\bvashi\b", r"नवी\s*मुंबई"), "navi_mumbai"),
    (_p(r"\bmumbai\b", r"\bbombay\b", r"मुंबई"), "mumbai"),
    (_p(r"\bnashik\b", r"\bnasik\b", r"\blasalgaon\b",
        r"नाशिक"), "nashik"),
]


# ──────────────────────────── PUBLIC API ────────────────────────────────

def classify_regex(text: str) -> IntentResult:
    """Classify `text` using compiled regex patterns.

    Returns an IntentResult with confidence=1.0 on regex match,
    or intent=UNKNOWN with confidence=0.0 when no pattern fires.
    """
    t = text.strip()
    if not t:
        return IntentResult(
            intent=Intent.UNKNOWN,
            confidence=0.0,
            source="regex",
            raw_text=text,
            explanation="empty_message",
        )

    # Unsubscribe/subscribe before price — a message like "दैनिक भाव पाठवा"
    # contains "भाव" (price word) but the intent is subscribe (पाठवा = send me).
    if _UNSUBSCRIBE_RE.search(t):
        return IntentResult(
            intent=Intent.UNSUBSCRIBE,
            confidence=1.0,
            source="regex",
            raw_text=text,
            explanation="unsubscribe_pattern",
        )

    if _SUBSCRIBE_RE.search(t):
        return IntentResult(
            intent=Intent.SUBSCRIBE,
            confidence=1.0,
            source="regex",
            raw_text=text,
            explanation="subscribe_pattern",
        )

    # MSP alert (minimum support price alert) — check before PRICE_ALERT
    # so "set alert for msp" matches MSP_ALERT, not PRICE_ALERT
    if _MSP_ALERT_RE.search(t):
        commodity = _extract_commodity(t)
        return IntentResult(
            intent=Intent.MSP_ALERT,
            confidence=1.0,
            commodity=commodity,
            source="regex",
            raw_text=text,
            explanation="msp_alert_pattern",
        )

    # Price alert (set alert for price condition)
    if _PRICE_ALERT_RE.search(t):
        commodity = _extract_commodity(t)
        district = _extract_district(t)
        return IntentResult(
            intent=Intent.PRICE_ALERT,
            confidence=1.0,
            commodity=commodity,
            district=district,
            source="regex",
            raw_text=text,
            explanation="price_alert_pattern",
        )

    # Government scheme query
    if _SCHEME_QUERY_RE.search(t):
        return IntentResult(
            intent=Intent.SCHEME_QUERY,
            confidence=1.0,
            source="regex",
            raw_text=text,
            explanation="scheme_query_pattern",
        )

    # Price query
    if _PRICE_RE.search(t):
        commodity = _extract_commodity(t)
        district = _extract_district(t)
        return IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=1.0,
            commodity=commodity,
            district=district,
            source="regex",
            raw_text=text,
            explanation="price_pattern",
        )

    # Pest/disease diagnosis
    if _PEST_QUERY_RE.search(t):
        return IntentResult(
            intent=Intent.PEST_QUERY,
            confidence=1.0,
            source="regex",
            raw_text=text,
            explanation="pest_query_pattern",
        )

    if _ONBOARDING_RE.search(t):
        return IntentResult(
            intent=Intent.ONBOARDING,
            confidence=1.0,
            source="regex",
            raw_text=text,
            explanation="onboarding_pattern",
        )

    if _HELP_RE.search(t):
        return IntentResult(
            intent=Intent.HELP,
            confidence=1.0,
            source="regex",
            raw_text=text,
            explanation="help_pattern",
        )

    if _GREETING_RE.search(t):
        return IntentResult(
            intent=Intent.GREETING,
            confidence=1.0,
            source="regex",
            raw_text=text,
            explanation="greeting_pattern",
        )

    if _FEEDBACK_RE.search(t):
        return IntentResult(
            intent=Intent.FEEDBACK,
            confidence=1.0,
            source="regex",
            raw_text=text,
            explanation="feedback_pattern",
        )

    # Weather query (Phase 2)
    if _WEATHER_RE.search(t):
        metric = _extract_weather_metric(t)
        district = _extract_district(t)
        return IntentResult(
            intent=Intent.WEATHER_QUERY,
            confidence=1.0,
            commodity=metric,  # Reuse commodity field for metric
            district=district,
            source="regex",
            raw_text=text,
            explanation="weather_pattern",
        )

    # Only commodity mentioned — implicit price query
    commodity = _extract_commodity(t)
    if commodity:
        district = _extract_district(t)
        return IntentResult(
            intent=Intent.PRICE_QUERY,
            confidence=0.85,
            commodity=commodity,
            district=district,
            source="regex",
            raw_text=text,
            explanation="commodity_only_implicit_price",
        )

    return IntentResult(
        intent=Intent.UNKNOWN,
        confidence=0.0,
        source="regex",
        raw_text=text,
        explanation="no_pattern_matched",
    )


def _extract_commodity(text: str) -> Optional[str]:
    for pattern, slug in _COMMODITY_PATTERNS:
        if pattern.search(text):
            return slug
    return None


def _extract_district(text: str) -> Optional[str]:
    for pattern, slug in _DISTRICT_PATTERNS:
        if pattern.search(text):
            return slug
    return None


def _extract_weather_metric(text: str) -> Optional[str]:
    """Extract weather metric (temperature, rainfall, etc.) from text.

    Args:
        text: User message

    Returns:
        Canonical metric slug (e.g., "temperature") or None if not found
    """
    for pattern, slug in _WEATHER_METRIC_PATTERNS:
        if pattern.search(text):
            return slug
    return None
