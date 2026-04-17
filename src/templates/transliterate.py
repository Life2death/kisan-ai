"""Hinglish ↔ Marathi transliteration.

Maps common Hinglish (Latin-script Hindi/Marathi) to Devanagari.
E.g., "bhav" → "भाव", "kanda" → "कांदा", "nashik" → "नाशिक"
"""
from __future__ import annotations

# Hinglish → Marathi Devanagari
HINGLISH_TO_MARATHI = {
    # Common agricultural terms
    "bhav": "भाव",
    "bhaav": "भाव",
    "dar": "दर",
    "mandi": "मंडी",
    "kanda": "कांदा",
    "piyaz": "प्याज",
    "pyaz": "प्याज",
    "tur": "तूर",
    "toor": "तूर",
    "arhar": "अरहर",
    "soyabean": "सोयाबीन",
    "soya": "सोया",
    "kapas": "कापास",
    "cotton": "कापास",
    "tamatar": "टमाटर",
    "tomato": "टमाटर",
    "aloo": "आलू",
    "potato": "आलू",
    "gehu": "गहू",
    "wheat": "गहू",
    "jowar": "ज्वारी",
    "bajra": "बाजरी",
    "chana": "चणा",
    "gram": "चणा",
    # Places (districts)
    "pune": "पुणे",
    "ahilyanagar": "अहिल्यानगर",
    "ahmednagar": "अहमदनगर",
    "nashik": "नाशिक",
    "mumbai": "मुंबई",
    "bombay": "मुंबई",
    "latur": "लातूर",
    "nanded": "नांदेड",
    # Verbs / phrases
    "karo": "करो",
    "kar": "कर",
    "do": "दो",
    "ha": "आहे",
    "hai": "है",
    "hain": "हैं",
    "nahi": "नाही",
    "no": "नाही",
    "haan": "हां",
    "yes": "हां",
    "suroo": "सुरू",
    "start": "सुरू",
    "band": "बंद",
    "stop": "बंद",
    "madad": "मदत",
    "help": "मदत",
}


def transliterate_hinglish_to_marathi(text: str) -> str:
    """
    Convert Hinglish words to Marathi Devanagari.
    Preserves non-matched words and case (somewhat).

    E.g., "bhav please" → "भाव please"
    """
    words = text.split()
    result = []
    for word in words:
        clean = word.lower().rstrip(".,!?;:")
        suffix = word[len(clean) :]  # trailing punctuation

        marathi = HINGLISH_TO_MARATHI.get(clean, word)
        result.append(marathi + suffix)

    return " ".join(result)


def marathi_commodity(commodity: str) -> str:
    """Return Marathi name for a commodity slug.

    E.g., "onion" → "कांदा"
    """
    mapping = {
        "onion": "कांदा",
        "tur": "तूर",
        "soyabean": "सोयाबीन",
        "cotton": "कापास",
        "tomato": "टमाटर",
        "potato": "आलू",
        "wheat": "गहू",
        "chana": "चणा",
        "jowar": "ज्वारी",
        "bajra": "बाजरी",
        "grapes": "द्राक्षे",
        "pomegranate": "डाळिंब",
    }
    return mapping.get(commodity, commodity)


def marathi_district(district: str) -> str:
    """Return Marathi name for a district slug.

    E.g., "nashik" → "नाशिक"
    """
    mapping = {
        "pune": "पुणे",
        "ahilyanagar": "अहिल्यानगर",
        "nashik": "नाशिक",
        "navi_mumbai": "नवी मुंबई",
        "mumbai": "मुंबई",
    }
    return mapping.get(district, district)
