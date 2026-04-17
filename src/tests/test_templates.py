"""Tests for Module 9 — Marathi templates & transliteration."""
from __future__ import annotations

import pytest

from src.templates.transliterate import (
    transliterate_hinglish_to_marathi,
    marathi_commodity,
    marathi_district,
)
from src.templates.templates import get_template, render


class TestTransliteration:
    def test_hinglish_bhav_to_marathi(self):
        result = transliterate_hinglish_to_marathi("bhav")
        assert result == "भाव"

    def test_hinglish_kanda_to_marathi(self):
        result = transliterate_hinglish_to_marathi("kanda")
        assert result == "कांदा"

    def test_hinglish_mandi_to_marathi(self):
        result = transliterate_hinglish_to_marathi("mandi")
        assert result == "मंडी"

    def test_hinglish_sentence(self):
        result = transliterate_hinglish_to_marathi("bhav kanda please")
        assert "भाव" in result
        assert "कांदा" in result
        assert "please" in result

    def test_hinglish_with_punctuation(self):
        result = transliterate_hinglish_to_marathi("kanda? tur!")
        assert "कांदा?" in result
        assert "तूर!" in result

    def test_marathi_commodity_onion(self):
        assert marathi_commodity("onion") == "कांदा"

    def test_marathi_commodity_tur(self):
        assert marathi_commodity("tur") == "तूर"

    def test_marathi_commodity_soyabean(self):
        assert marathi_commodity("soyabean") == "सोयाबीन"

    def test_marathi_district_pune(self):
        assert marathi_district("pune") == "पुणे"

    def test_marathi_district_nashik(self):
        assert marathi_district("nashik") == "नाशिक"

    def test_marathi_district_navi_mumbai(self):
        assert marathi_district("navi_mumbai") == "नवी मुंबई"


class TestTemplates:
    def test_get_template_greeting(self):
        tpl = get_template("greeting")
        assert tpl is not None
        assert tpl.key == "greeting"
        assert "नमस्कार" in tpl.marathi

    def test_template_render_marathi(self):
        tpl = get_template("onboarding_complete")
        msg = tpl.render(lang="mr", name="Rajesh", district="पुणे", crops="कांदा, तूर")
        assert "Rajesh" in msg
        assert "पुणे" in msg
        assert "कांदा" in msg

    def test_template_render_english(self):
        tpl = get_template("onboarding_complete")
        msg = tpl.render(lang="en", name="Rajesh", district="Pune", crops="onion, tur")
        assert "Rajesh" in msg
        assert "Pune" in msg

    def test_convenience_render(self):
        msg = render("help_menu", lang="mr")
        assert "महाराष्ट्र किसान AI" in msg
        assert "मदत" in msg

    def test_template_not_found(self):
        result = render("nonexistent", lang="mr")
        assert "not found" in result

    def test_price_found_template(self):
        tpl = get_template("price_found")
        msg = tpl.render(
            lang="mr",
            commodity="कांदा",
            mandi="Lasalgaon",
            price="₹2500/क्विंटल",
            source="nhrdf",
        )
        assert "कांदा" in msg
        assert "Lasalgaon" in msg
        assert "₹2500" in msg

    def test_all_templates_have_both_languages(self):
        from src.templates.templates import TEMPLATES
        for key, tpl in TEMPLATES.items():
            assert tpl.marathi, f"{key} missing Marathi"
            assert tpl.english, f"{key} missing English"
            assert len(tpl.marathi) > 0
            assert len(tpl.english) > 0
