"""Intent definitions for Kisan AI.

Every message from a farmer resolves to exactly one Intent. The classifier
pipeline tries regex first (fast, free, deterministic); only escalates to
the LLM when regex returns UNKNOWN.

Intent taxonomy:
  PRICE_QUERY        — farmer wants today's mandi price for a commodity
  WEATHER_QUERY      — farmer wants weather forecast / conditions (Phase 2 Module 1)
  PEST_QUERY         — farmer uploads image for pest/disease diagnosis (Phase 2 Module 3)
  SUBSCRIBE          — farmer wants daily broadcast at 6:30 AM
  UNSUBSCRIBE        — farmer wants to stop receiving broadcasts
  ONBOARDING         — new farmer, or asking "how does this work"
  HELP               — asking for list of commands
  GREETING           — namaste / hello (no clear intent — send menu)
  FEEDBACK           — farmer giving feedback / complaint
  UNKNOWN            — couldn't classify; LLM will retry or send fallback

Marathi is a first-class language here: every pattern list has Marathi
variants alongside English/Hinglish.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Intent(str, Enum):
    PRICE_QUERY = "price_query"
    WEATHER_QUERY = "weather_query"  # Phase 2 Module 1: weather forecast queries
    PEST_QUERY = "pest_query"  # Phase 2 Module 3: image-based pest diagnosis
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    ONBOARDING = "onboarding"
    HELP = "help"
    GREETING = "greeting"
    FEEDBACK = "feedback"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class IntentResult:
    """Output of the classifier for one message."""

    intent: Intent
    confidence: float                    # 1.0 = regex match; 0.0–1.0 = LLM score
    commodity: Optional[str] = None      # canonical slug if PRICE_QUERY
    district: Optional[str] = None       # canonical slug if extracted
    source: str = "regex"                # 'regex' | 'llm'
    raw_text: str = ""
    explanation: str = ""                # LLM explanation or regex rule name

    @property
    def is_price_query(self) -> bool:
        return self.intent == Intent.PRICE_QUERY

    @property
    def needs_commodity(self) -> bool:
        """Price query but no commodity extracted — must ask farmer."""
        return self.is_price_query and self.commodity is None
