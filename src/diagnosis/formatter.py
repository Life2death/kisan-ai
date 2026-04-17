"""Format pest diagnosis results for farmer display."""
from typing import Optional

from src.diagnosis.processor import DiagnosisResult


def format_diagnosis_reply(result: DiagnosisResult, lang: str = "mr") -> str:
    """Format high-confidence diagnosis with treatment recommendations.

    Args:
        result: DiagnosisResult from diagnosis processor
        lang: "mr" for Marathi, "en" for English

    Returns:
        Formatted diagnosis text for WhatsApp
    """
    if lang == "mr":
        return _format_diagnosis_marathi(result)
    else:
        return _format_diagnosis_english(result)


def format_diagnosis_low_confidence(result: DiagnosisResult, lang: str = "mr") -> str:
    """Format low-confidence diagnosis (warn farmer to consult expert).

    Args:
        result: DiagnosisResult with confidence < 0.5
        lang: "mr" for Marathi, "en" for English

    Returns:
        Low-confidence warning in farmer's language
    """
    if lang == "mr":
        return (
            f"⚠️  कीट निदान अस्पष्ट आहे ({result.pest})\n\n"
            f"संभाव्य कीट: {result.pest}\n"
            f"निश्चितता: {int(result.confidence * 100)}%\n\n"
            f"💡 सल्ला: कृपया आपल्या तहसील कृषि अधिकाऱ्यांशी संपर्क साधा किंवा "
            f"स्थानिक शेतकरी समूहाला सांगा।\n\n"
            f"📸 अधिक स्पष्ट फोटो पाठवा (रोगग्रस्त भाग जवळून)।"
        )
    else:
        return (
            f"⚠️  Diagnosis unclear ({result.pest})\n\n"
            f"Possible pest: {result.pest}\n"
            f"Confidence: {int(result.confidence * 100)}%\n\n"
            f"💡 Recommendation: Please contact your agricultural officer or local farming group.\n\n"
            f"📸 Try sending a clearer photo (close-up of affected area)."
        )


def format_diagnosis_failed(lang: str = "mr") -> str:
    """Format diagnosis failure message.

    Args:
        lang: "mr" for Marathi, "en" for English

    Returns:
        Failure message encouraging farmer to retry or contact expert
    """
    if lang == "mr":
        return (
            "😔 खेद आहे, कीट निदान करू शकलो नाही।\n\n"
            "कृपया:\n"
            "📸 स्पष्ट फोटो पाठवा (रोगी पत्तियां/भाग)\n"
            "🌞 दिवसाच्या प्रकाशात काढलेला फोटो\n"
            "☎️ तहसील कृषि अधिकाऱ्यांशी संपर्क साधा\n\n"
            "पुन्हा प्रयत्न करा किंवा खेतीशी संबंधित संदेश पाठवा।"
        )
    else:
        return (
            "😔 Sorry, I couldn't diagnose the pest from the image.\n\n"
            "Please try:\n"
            "📸 Send a clear photo (of affected leaves/area)\n"
            "🌞 Taken in daylight\n"
            "☎️ Contact your agricultural officer\n\n"
            "Or send another photo or a farming-related message."
        )


# ==================== Marathi Formatting ====================


def _format_diagnosis_marathi(result: DiagnosisResult) -> str:
    """Format diagnosis in Marathi with severity, treatment, emergency contacts."""
    severity_emoji = _get_severity_emoji(result.severity)
    severity_marathi = _get_severity_marathi(result.severity)

    # Build treatment section
    treatment_text = ""
    if result.treatment:
        treatment_text = f"\n\n💊 उपचार:\n{result.treatment}"

    # Build confidence badge
    confidence_pct = int(result.confidence * 100)

    reply = (
        f"{severity_emoji} कीट निदान — {result.disease_marathi}\n\n"
        f"🌾 कीट: {result.pest}\n"
        f"📊 गंभीरता: {severity_marathi}\n"
        f"✔️ निश्चितता: {confidence_pct}%"
        f"{treatment_text}\n\n"
        f"📞 अधिक मदत:\n"
        f"तहसील कृषि अधिकारी किंवा स्थानिक KVK संस्था\n\n"
        f"⚠️ हे स्वयंचलित निदान आहे। अगर संदेह असेल तर विशेषज्ञांशी संपर्क साधा।"
    )

    return reply


def _format_diagnosis_english(result: DiagnosisResult) -> str:
    """Format diagnosis in English with severity, treatment, emergency contacts."""
    severity_emoji = _get_severity_emoji(result.severity)
    severity_english = _get_severity_english(result.severity)

    # Build treatment section
    treatment_text = ""
    if result.treatment:
        treatment_text = f"\n\n💊 Treatment:\n{result.treatment}"

    # Build confidence badge
    confidence_pct = int(result.confidence * 100)

    reply = (
        f"{severity_emoji} Pest Diagnosis — {result.disease_marathi} ({result.pest})\n\n"
        f"🌾 Pest: {result.pest}\n"
        f"📊 Severity: {severity_english}\n"
        f"✔️ Confidence: {confidence_pct}%"
        f"{treatment_text}\n\n"
        f"📞 More Help:\n"
        f"Contact your agricultural officer or local KVK center.\n\n"
        f"⚠️ This is an automated diagnosis. Consult an expert if in doubt."
    )

    return reply


# ==================== Helpers ====================


def _get_severity_emoji(severity: str) -> str:
    """Return emoji based on severity level."""
    emoji_map = {
        "mild": "🟢",
        "moderate": "🟡",
        "severe": "🔴",
        "none": "✅",
    }
    return emoji_map.get(severity, "❓")


def _get_severity_marathi(severity: str) -> str:
    """Return Marathi severity description."""
    marathi_map = {
        "mild": "हल्का (हरी रंगाची पत्तियां)",
        "moderate": "मध्यम (काहीसे हानी)",
        "severe": "गंभीर (भारी हानी)",
        "none": "कोण्याही रोग नाहीत",
    }
    return marathi_map.get(severity, "अज्ञात")


def _get_severity_english(severity: str) -> str:
    """Return English severity description."""
    english_map = {
        "mild": "Mild (light damage)",
        "moderate": "Moderate (some damage)",
        "severe": "Severe (heavy damage)",
        "none": "No pest detected",
    }
    return english_map.get(severity, "Unknown")
