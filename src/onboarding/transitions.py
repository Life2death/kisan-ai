"""State transition handlers (extracted from machine.py for clarity)."""
from __future__ import annotations

from src.ingestion.normalizer import normalize_commodity, normalize_district
from src.onboarding.states import OnboardingContext, OnboardingState


def to_awaiting_consent(ctx: OnboardingContext) -> tuple[OnboardingContext, str]:
    """NEW → AWAITING_CONSENT."""
    ctx.state = OnboardingState.AWAITING_CONSENT
    reply = (
        "नमस्कार! महाराष्ट्र किसान AI मध्ये आपले स्वागत आहे. 🌾\n"
        "आम्ही तुमचा फोन नंबर, नाव, जिल्हा, तालुका, गाव आणि पीक माहिती साठवतो — फक्त बाजारभाव कळवण्यासाठी.\n"
        '"हो" पाठवा सहमती देण्यासाठी. "नाही" पाठवा नाकारण्यासाठी.\n'
        "कधीही STOP पाठवून सेवा थांबवा.\n\n"
        "Welcome to Maharashtra Kisan AI! 🌾\n"
        "We store your phone, name, district, taluka, village, and crop info — only to send market prices.\n"
        'Send "YES" to agree or "NO" to decline.'
    )
    return ctx, reply


def from_awaiting_consent(ctx: OnboardingContext, user_input: str) -> tuple[OnboardingContext, str]:
    """AWAITING_CONSENT → AWAITING_NAME or OPTED_OUT."""
    consent = user_input.strip().upper()
    if consent in ("YES", "हो", "होय", "HO"):
        ctx.consent_given = True
        ctx.state = OnboardingState.AWAITING_NAME
        reply = "धन्यवाद! आपले नाव काय आहे? — What's your name?"
        return ctx, reply
    elif consent in ("NO", "नाही", "NAH"):
        ctx.state = OnboardingState.OPTED_OUT
        reply = "समजले. कधीही परिवर्तित करू शकतात. — Understood. Feel free to change your mind."
        return ctx, reply
    else:
        reply = 'कृपया "हो" किंवा "नाही" पाठवा. — Please send "YES" or "NO".'
        return ctx, reply


_DISTRICTS_WITH_VILLAGE = {"ahilyanagar"}

_AHILYANAGAR_TALUKAS: dict[str, str] = {
    "ahmednagar": "Ahmednagar", "ahilyanagar": "Ahmednagar", "nagar": "Ahmednagar",
    "akola": "Akola", "jamkhed": "Jamkhed", "karjat": "Karjat",
    "kopargaon": "Kopargaon", "nevasa": "Nevasa", "newasa": "Nevasa",
    "parner": "Parner", "pathardi": "Pathardi", "rahata": "Rahata",
    "rahuri": "Rahuri", "sangamner": "Sangamner", "shevgaon": "Shevgaon",
    "shrigonda": "Shrigonda", "shrirampur": "Shrirampur",
}


def from_awaiting_name(ctx: OnboardingContext, user_input: str) -> tuple[OnboardingContext, str]:
    """AWAITING_NAME → AWAITING_DISTRICT."""
    ctx.name = user_input.strip()[:100]
    ctx.state = OnboardingState.AWAITING_DISTRICT
    reply = (
        f"अरे वाह! स्वागत आहे {ctx.name}! 🌾\n"
        f"तुमचा जिल्हा कोणता आहे?\n\n"
        f"Welcome {ctx.name}! Great to have you here! 🌾\n"
        "Which district? पुणे / अहिल्यानगर / नाशिक / Pune / Ahilyanagar / Nashik / Mumbai"
    )
    return ctx, reply


def from_awaiting_district(ctx: OnboardingContext, user_input: str) -> tuple[OnboardingContext, str]:
    """AWAITING_DISTRICT → AWAITING_TALUKA (Ahilyanagar) or AWAITING_CROPS (others)."""
    district = normalize_district(user_input)
    if not district:
        reply = (
            "हा जिल्हा सपोर्ट केला जात नाही अभी. "
            "पुणे, अहिल्यानगर, नवी मुंबई, मुंबई, नाशिक पाठवा. — "
            "District not supported yet. Send one of the five."
        )
        return ctx, reply
    ctx.district = district
    name = ctx.name or "आपण"
    if district in _DISTRICTS_WITH_VILLAGE:
        ctx.state = OnboardingState.AWAITING_TALUKA
        taluka_list = " / ".join(sorted(set(_AHILYANAGAR_TALUKAS.values())))
        reply = (
            f"छान {name}! अहिल्यानगर जिल्ह्यातील तुमचा तालुका कोणता?\n\n"
            f"Great {name}! Which taluka in Ahilyanagar district?\n{taluka_list}"
        )
    else:
        ctx.state = OnboardingState.AWAITING_CROPS
        reply = (
            f"छान! आप कोणत्या पीक विषयी भाव पाहू इच्छिता?\n"
            f"उदा: कांदा, तूर, सोयाबीन, कपास, टोमॅटो, गहू.\n"
            f"एक किंवा अधिक पाठवा (हिंगलिश: onion tur soyabean)."
        )
    return ctx, reply


def from_awaiting_taluka(ctx: OnboardingContext, user_input: str) -> tuple[OnboardingContext, str]:
    """AWAITING_TALUKA → AWAITING_VILLAGE or stay."""
    canonical = _AHILYANAGAR_TALUKAS.get(user_input.strip().lower())
    if not canonical:
        taluka_list = " / ".join(sorted(set(_AHILYANAGAR_TALUKAS.values())))
        return ctx, (
            "तालुका ओळखता आला नाही.\n"
            f"Taluka not recognised. Please send one of:\n{taluka_list}"
        )
    ctx.taluka = canonical
    ctx.state = OnboardingState.AWAITING_VILLAGE
    reply = (
        f"तुमचे गाव नाव पाठवा ({canonical} तालुका).\n"
        f"Please send your village name ({canonical} taluka)."
    )
    return ctx, reply


def from_awaiting_village(ctx: OnboardingContext, user_input: str) -> tuple[OnboardingContext, str]:
    """AWAITING_VILLAGE → AWAITING_CROPS."""
    ctx.village_name = user_input.strip()[:100]
    ctx.state = OnboardingState.AWAITING_CROPS
    reply = (
        f"छान! {ctx.village_name} गाव नोंदवले.\n"
        f"कोणती पिके? उदा: कांदा, तूर, सोयाबीन.\n\n"
        f"Village {ctx.village_name} saved!\n"
        "Which crops? E.g.: onion tur soyabean"
    )
    return ctx, reply


def from_awaiting_crops(ctx: OnboardingContext, user_input: str) -> tuple[OnboardingContext, str]:
    """AWAITING_CROPS → AWAITING_LANGUAGE or stay in AWAITING_CROPS."""
    crops_raw = user_input.split()
    crops = [normalize_commodity(c) for c in crops_raw]
    crops = [c for c in crops if c]
    if not crops:
        reply = "कृपया किमान एक पीक नाव पाठवा. — Send at least one crop name."
        return ctx, reply
    ctx.crops = crops
    ctx.state = OnboardingState.AWAITING_LANGUAGE
    reply = (
        f"छान! आपणास मराठी किंवा इंग्रजी प्राधान्य आहे?\n"
        f"पाठवा: मराठी (MR) किंवा इंग्रजी (EN)."
    )
    return ctx, reply


def from_awaiting_language(ctx: OnboardingContext, user_input: str) -> tuple[OnboardingContext, str]:
    """AWAITING_LANGUAGE → ACTIVE or stay in AWAITING_LANGUAGE."""
    lang = user_input.strip().upper()
    if lang in ("MR", "मराठी", "MARATHI"):
        ctx.preferred_language = "mr"
    elif lang in ("EN", "इंग्रजी", "ENGLISH"):
        ctx.preferred_language = "en"
    else:
        reply = 'कृपया MR किंवा EN पाठवा. — Send "MR" or "EN".'
        return ctx, reply

    ctx.state = OnboardingState.ACTIVE
    crops_str = ", ".join(ctx.crops)
    reply = (
        f"✅ तयार! आपण सक्रिय आहात, {ctx.name}!\n"
        f"जिल्हा: {ctx.district}, पीक: {crops_str}\n"
        f"प्रत्येक दिवस सकाळी 6:30 ला भाव मिळणार.\n"
        f"---\n"
        f"✅ All set, {ctx.name}!\n"
        f"District: {ctx.district}, Crops: {crops_str}\n"
        f"You'll get daily prices at 6:30 AM."
    )
    return ctx, reply
