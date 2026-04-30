"""Marathi + English response templates with variable injection."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Template:
    """A response template with optional variable slots."""

    key: str
    marathi: str
    english: str

    def render(self, lang: str = "mr", **kwargs) -> str:
        """Render template, optionally injecting variables.

        E.g., template.render(lang="mr", name="Rajesh")
        """
        text = self.marathi if lang == "mr" else self.english
        try:
            return text.format(**kwargs)
        except KeyError:
            return text


# ─────────────────────────────────────────────────────────────────
# Template Registry
# ─────────────────────────────────────────────────────────────────

TEMPLATES = {
    "greeting": Template(
        key="greeting",
        marathi="नमस्कार! महाराष्ट्र किसान AI मध्ये आपले स्वागत आहे. 🌾",
        english="Welcome to Maharashtra Kisan AI! 🌾",
    ),
    "price_found": Template(
        key="price_found",
        marathi="🌾 {commodity} — {mandi}\nदर: {price}\nस्रोत: {source}",
        english="🌾 {commodity} — {mandi}\nPrice: {price}\nSource: {source}",
    ),
    "price_not_found": Template(
        key="price_not_found",
        marathi="आज {commodity} भाव उपलब्ध नाही. कृपया बाद में पुन्हा प्रयास करा.",
        english="No {commodity} price available today. Please try again later.",
    ),
    "ask_commodity": Template(
        key="ask_commodity",
        marathi="कोण सा पीक? उदा: कांदा, तूर, सोयाबीन, कपास, टमाटर?\nFull list: कांदा, तूर, सोयाबीन, कपास, आलू, गहू, चणा, ज्वारी, बाजरी",
        english="Which crop? E.g: onion, tur, soyabean, cotton, tomato?\nFull list: onion, tur, soyabean, cotton, potato, wheat, chana, jowar, bajra",
    ),
    "onboarding_consent": Template(
        key="onboarding_consent",
        marathi=(
            "नमस्कार! महाराष्ट्र किसान AI मध्ये आपले स्वागत आहे. 🌾\n"
            "आम्ही तुमचा फोन नंबर, नाव, जिल्हा, तालुका, गाव आणि पीक माहिती साठवतो — फक्त बाजारभाव कळवण्यासाठी.\n"
            '"हो" पाठवा सहमती देण्यासाठी. "नाही" पाठवा नाकारण्यासाठी.\n'
            "कधीही STOP पाठवून सेवा थांबवा."
        ),
        english=(
            "Welcome to Maharashtra Kisan AI! 🌾\n"
            "We store your phone, name, district, taluka, village, and crop info — only to send market prices.\n"
            'Send "YES" to agree or "NO" to decline.'
        ),
    ),
    "onboarding_name": Template(
        key="onboarding_name",
        marathi="धन्यवाद! आपले नाव काय आहे?",
        english="Thank you! What's your name?",
    ),
    "onboarding_district": Template(
        key="onboarding_district",
        marathi="आप कोणत्या जिल्ह्यातून आहात? (पुणे, अहिल्यानगर, नवी मुंबई, मुंबई, नाशिक)",
        english="Which district? (Pune, Ahilyanagar, Navi Mumbai, Mumbai, Nashik)",
    ),
    "onboarding_crops": Template(
        key="onboarding_crops",
        marathi="कोणत्या पीक विषयी भाव पाहू इच्छिता? (कांदा, तूर, सोयाबीन, कपास)",
        english="Which crops? E.g: onion, tur, soyabean, cotton",
    ),
    "onboarding_language": Template(
        key="onboarding_language",
        marathi="आपणास मराठी किंवा इंग्रजी प्राधान्य? (MR / EN)",
        english="Marathi or English? (MR / EN)",
    ),
    "onboarding_complete": Template(
        key="onboarding_complete",
        marathi="✅ तयार! आपण सक्रिय आहात, {name}!\nजिल्हा: {district}, पीक: {crops}\nप्रत्येक दिवस सकाळी 6:30 ला भाव मिळणार.",
        english="✅ All set, {name}!\nDistrict: {district}, Crops: {crops}\nYou'll get daily prices at 6:30 AM.",
    ),
    "help_menu": Template(
        key="help_menu",
        marathi=(
            "📱 महाराष्ट्र किसान AI — मदत\n\n"
            "आप पाठवा:\n"
            "• कांदा दर — आज की कीमत\n"
            "• आजचा भाव — सर्व पीक\n"
            "• मदत — हा मेनू\n"
            '• "STOP" — सेवा थांबवा'
        ),
        english=(
            "📱 Maharashtra Kisan AI — Help\n\n"
            "Send:\n"
            "• onion price — today's rate\n"
            "• prices — all crops\n"
            "• help — this menu\n"
            '• "STOP" — opt out'
        ),
    ),
    "opted_out": Template(
        key="opted_out",
        marathi="आपण सेवा थांबवली. कधीही संपर्क करू शकतात.",
        english="You've opted out. Feel free to reach out anytime.",
    ),
}


def get_template(key: str) -> Template | None:
    """Retrieve a template by key."""
    return TEMPLATES.get(key)


def render(key: str, lang: str = "mr", **kwargs) -> str:
    """Convenience: get + render in one call."""
    tpl = TEMPLATES.get(key)
    if not tpl:
        return f"[Template '{key}' not found]"
    return tpl.render(lang=lang, **kwargs)
