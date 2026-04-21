"""OpenRouter LLM fallback classifier.

Called only when regex returns UNKNOWN. Uses OpenRouter API (OpenAI-compatible)
so we can swap models freely. Defaults to mistralai/mistral-7b-instruct which
is cheap (~$0.0001/query) and handles Marathi/Hinglish well enough for intent
classification.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.classifier.intents import Intent, IntentResult
from src.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an intent classifier for Kisan AI, a WhatsApp bot serving farmers in Maharashtra, India.

You must classify incoming farmer messages into exactly one of these intents:
- price_query    : farmer wants today mandi price
- subscribe      : farmer wants daily price broadcasts
- unsubscribe    : farmer wants to stop broadcasts
- onboarding     : new farmer asking how to use the service
- help           : asking for list of commands or features
- greeting       : just saying hello/namaste with no clear intent
- feedback       : giving feedback, complaint, or thanks
- unknown        : cannot classify

Farmers message in Marathi (Devanagari), English, or Hinglish.
Extract commodity if mentioned: onion, tur, soyabean, cotton, tomato, potato, wheat, chana, jowar, bajra, grapes, pomegranate, maize — or null.
Extract district if mentioned: pune, ahilyanagar, navi_mumbai, mumbai, nashik — or null.

Respond ONLY with valid JSON, no markdown:
{"intent":"<slug>","confidence":<0.0-1.0>,"commodity":"<slug or null>","district":"<slug or null>","explanation":"<one line>"}
"""

_FEW_SHOT = [
    ("आजचा कांदा भाव काय आहे?",
     '{"intent":"price_query","confidence":0.99,"commodity":"onion","district":null,"explanation":"Marathi: today onion price"}'),
    ("Nashik mandi me soyabean ka bhav kya hai",
     '{"intent":"price_query","confidence":0.98,"commodity":"soyabean","district":"nashik","explanation":"Hinglish price query"}'),
    ("Mala daily bhav pathva",
     '{"intent":"subscribe","confidence":0.97,"commodity":null,"district":null,"explanation":"Marathi: send daily price"}'),
    ("Stop karo sab",
     '{"intent":"unsubscribe","confidence":0.96,"commodity":null,"district":null,"explanation":"Hinglish unsubscribe"}'),
    ("Mera registration kaise karo",
     '{"intent":"onboarding","confidence":0.95,"commodity":null,"district":null,"explanation":"Hinglish registration request"}'),
]


def _build_messages(text: str) -> list[dict]:
    few_shot_text = "
".join(
        f'User: "{msg}"
Assistant: {resp}' for msg, resp in _FEW_SHOT
    )
    user_content = f"{few_shot_text}
User: "{text}"
Assistant:"
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


_VALID_INTENTS = {i.value for i in Intent}
_JSON_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _parse(raw: str, text: str) -> IntentResult:
    match = _JSON_RE.search(raw)
    if not match:
        return _fallback(text, "no_json")
    try:
        data: dict[str, Any] = json.loads(match.group())
    except json.JSONDecodeError:
        return _fallback(text, "json_decode_error")
    intent_str = str(data.get("intent", "unknown")).lower()
    if intent_str not in _VALID_INTENTS:
        intent_str = "unknown"
    return IntentResult(
        intent=Intent(intent_str),
        confidence=float(data.get("confidence", 0.5)),
        commodity=data.get("commodity") or None,
        district=data.get("district") or None,
        source="llm",
        raw_text=text,
        explanation=str(data.get("explanation", "")),
    )


def _fallback(text: str, reason: str) -> IntentResult:
    return IntentResult(
        intent=Intent.UNKNOWN,
        confidence=0.0,
        source="llm",
        raw_text=text,
        explanation=reason,
    )


async def classify_llm(text: str) -> IntentResult:
    """Classify text using OpenRouter. Returns UNKNOWN on any error."""
    api_key = settings.openrouter_api_key if hasattr(settings, "openrouter_api_key") else ""
    if not api_key:
        # fallback to gemini key check for backwards compat
        api_key = getattr(settings, "gemini_api_key", "")
    if not api_key:
        logger.warning("llm_classifier: no API key configured")
        return _fallback(text, "no_api_key")

    try:
        import httpx
        model = getattr(settings, "openrouter_model", "mistralai/mistral-7b-instruct")
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://kisan-ai-production-6f73.up.railway.app",
                    "X-Title": "Kisan AI",
                },
                json={
                    "model": model,
                    "messages": _build_messages(text),
                    "temperature": 0.1,
                    "max_tokens": 128,
                },
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            result = _parse(raw, text)
            logger.info(
                "llm_classifier: intent=%s confidence=%.2f model=%s",
                result.intent.value, result.confidence, model,
            )
            return result
    except Exception as exc:
        logger.error("llm_classifier: error: %s", exc)
        return _fallback(text, f"api_error:{type(exc).__name__}")
