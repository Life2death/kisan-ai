"""Format voice message responses for farmers.

Handles:
- Transcription success feedback (optional transparency)
- Transcription failure fallback (user-friendly error messages)
- Support for Marathi and English responses
"""
from __future__ import annotations


def format_transcription_failed(lang: str = "mr") -> str:
    """Return fallback message when audio transcription fails.

    Used when:
    - STT service times out (>30 seconds)
    - Audio file is corrupted or invalid
    - No speech detected in audio
    - API error or rate limit

    Args:
        lang: Language code ("mr" for Marathi, "en" for English)

    Returns:
        Farmer-friendly error message in requested language
    """
    messages = {
        "mr": "दिसून आले नाही। कृपया पुन्हा प्रयत्न करा किंवा संदेश पाठवा।",
        "en": "Sorry, I couldn't understand that. Please try again or send a text message.",
    }
    return messages.get(lang, messages["en"])


def format_transcription_feedback(
    transcribed_text: str,
    confidence: float = 0.95,
    lang: str = "mr"
) -> str:
    """Return acknowledgment of successful transcription (optional transparency).

    Shows farmer what we understood from their voice message.
    Helps verify transcription accuracy + build trust.

    This is OPTIONAL - can be omitted to reduce message count.

    Args:
        transcribed_text: Marathi text transcribed from audio
        confidence: Transcription confidence (0.0-1.0), if available
        lang: Language code ("mr" for Marathi, "en" for English)

    Returns:
        Acknowledgment message in requested language

    Example:
        "समजली: 'कांदा पुणे दर काय?'
         (हे योग्य आहे काय?)"
    """
    if lang == "mr":
        preview = transcribed_text[:50] if len(transcribed_text) > 50 else transcribed_text
        return f"समजली: '{preview}'\n(हे योग्य आहे काय?)"
    else:
        preview = transcribed_text[:50] if len(transcribed_text) > 50 else transcribed_text
        return f"Understood: '{preview}'\n(Is this correct?)"


def format_transcription_empty(lang: str = "mr") -> str:
    """Return message when audio file has no speech detected.

    Used when audio is silent or contains only background noise.

    Args:
        lang: Language code ("mr" for Marathi, "en" for English)

    Returns:
        User-friendly message asking for clearer audio
    """
    messages = {
        "mr": "मी कोणतीही बोली ऐकू शकलो नाही। कृपया जोरात बोला किंवा पुन्हा प्रयत्न करा।",
        "en": "I didn't hear any speech. Please speak clearly and try again.",
    }
    return messages.get(lang, messages["en"])


def format_transcription_too_long(lang: str = "mr") -> str:
    """Return message when audio exceeds maximum length (e.g., >2 minutes).

    Used to manage API costs and timeouts for very long voice messages.

    Args:
        lang: Language code ("mr" for Marathi, "en" for English)

    Returns:
        User-friendly message about message length
    """
    messages = {
        "mr": "संदेश खूप लांब आहे (कमाल 2 मिनिटे). कृपया सोईस्कर संक्षिप्त संदेश पाठवा।",
        "en": "Your message is too long (max 2 minutes). Please keep it brief.",
    }
    return messages.get(lang, messages["en"])
