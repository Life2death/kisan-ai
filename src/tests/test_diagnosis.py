"""Comprehensive tests for pest diagnosis module (Phase 2 Module 3)."""
import pytest
import asyncio
from io import BytesIO
from unittest.mock import patch, AsyncMock, MagicMock
from PIL import Image
import numpy as np

from src.diagnosis.processor import (
    ImageDiagnoser,
    DiagnosisResult,
    DiagnosisError,
)
from src.diagnosis.handler import DiagnosisHandler
from src.diagnosis.formatter import (
    format_diagnosis_reply,
    format_diagnosis_failed,
    format_diagnosis_low_confidence,
)
from src.classifier.intents import IntentResult, Intent


# ==================== Fixtures ====================


@pytest.fixture
def dummy_image_bytes():
    """Create a dummy image (small colored square) for testing."""
    img = Image.new("RGB", (100, 100), color="green")
    img_bytes = BytesIO()
    img.save(img_bytes, format="PNG")
    return img_bytes.getvalue()


@pytest.fixture
def dummy_config():
    """Minimal diagnoser config."""
    return {
        "tensorflow_model_path": "",  # Empty path to skip model loading
        "gemini_vision_enabled": True,
        "image_processing_timeout": 30,
        "diagnosis_confidence_threshold": 0.7,
    }


@pytest.fixture
def sample_diagnosis_result():
    """Sample DiagnosisResult for formatting tests."""
    return DiagnosisResult(
        pest="Powdery Mildew",
        disease_marathi="पाउडर मिल्ड्यू",
        confidence=0.92,
        severity="moderate",
        treatment="Spray neem oil daily for 5 days",
        source="tensorflow",
    )


# ==================== ImageDiagnoser Tests ====================


class TestImageDownload:
    """Test image downloading from Meta WhatsApp URLs."""

    @pytest.mark.asyncio
    async def test_download_image_success(self, dummy_config, dummy_image_bytes):
        """Test successful image download from Meta URL."""
        import httpx as _httpx
        diagnoser = ImageDiagnoser(dummy_config)

        with patch("src.diagnosis.processor.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            mock_response = MagicMock()
            mock_response.content = dummy_image_bytes
            mock_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)

            result = await diagnoser._download_image("https://example.com/image.jpg")
            assert result == dummy_image_bytes
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_download_image_timeout(self, dummy_config):
        """Test image download timeout (httpx.ReadTimeout → DiagnosisError)."""
        import httpx as _httpx
        diagnoser = ImageDiagnoser(dummy_config)

        with patch("src.diagnosis.processor.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=_httpx.ReadTimeout("Request timed out"))

            with pytest.raises(DiagnosisError):
                await diagnoser._download_image("https://example.com/image.jpg")

    @pytest.mark.asyncio
    async def test_download_image_network_error(self, dummy_config):
        """Test image download network error."""
        import httpx

        diagnoser = ImageDiagnoser(dummy_config)

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.HTTPError("Connection refused")

            with pytest.raises(DiagnosisError):
                await diagnoser._download_image("https://example.com/image.jpg")


class TestTensorFlowDiagnosis:
    """Test local TensorFlow model diagnosis."""

    def test_model_load_not_available(self, dummy_config):
        """Test graceful handling when model file doesn't exist."""
        config = dummy_config.copy()
        config["tensorflow_model_path"] = "/nonexistent/model.h5"

        diagnoser = ImageDiagnoser(config)
        assert not diagnoser._model_available
        # Should not crash, just log warning

    @pytest.mark.asyncio
    async def test_tensorflow_diagnose_with_mock_model(self, dummy_config, dummy_image_bytes):
        """Test TensorFlow diagnosis with mocked model."""
        diagnoser = ImageDiagnoser(dummy_config)

        # Mock the model
        mock_model = MagicMock()
        mock_predictions = np.array([[0.05, 0.90, 0.03, 0.01, 0.01]])  # High confidence on index 1
        mock_model.predict.return_value = mock_predictions

        diagnoser.tf_model = mock_model
        diagnoser._model_available = True

        result = await diagnoser._diagnose_tensorflow(dummy_image_bytes)

        assert isinstance(result, DiagnosisResult)
        assert result.source == "tensorflow"
        assert result.confidence == 0.90
        assert result.pest == "Leaf Blight"  # Index 1 in pest_map
        assert result.disease_marathi == "पत्तियों पर सड़न"
        assert result.severity == "moderate"  # 0.9 > 0.7

    @pytest.mark.asyncio
    async def test_tensorflow_diagnose_severe_confidence(self, dummy_config, dummy_image_bytes):
        """Test severity determination from confidence score."""
        diagnoser = ImageDiagnoser(dummy_config)

        mock_model = MagicMock()
        mock_predictions = np.array([[0.01, 0.01, 0.96, 0.01, 0.01]])  # Very high confidence
        mock_model.predict.return_value = mock_predictions

        diagnoser.tf_model = mock_model
        diagnoser._model_available = True

        result = await diagnoser._diagnose_tensorflow(dummy_image_bytes)
        assert result.severity == "severe"  # 0.96 > 0.9

    @pytest.mark.asyncio
    async def test_tensorflow_diagnose_mild_confidence(self, dummy_config, dummy_image_bytes):
        """Test mild severity at low confidence."""
        diagnoser = ImageDiagnoser(dummy_config)

        mock_model = MagicMock()
        mock_predictions = np.array([[0.40, 0.30, 0.20, 0.05, 0.05]])  # Highest is 0.4
        mock_model.predict.return_value = mock_predictions

        diagnoser.tf_model = mock_model
        diagnoser._model_available = True

        result = await diagnoser._diagnose_tensorflow(dummy_image_bytes)
        assert result.confidence == 0.40
        assert result.severity == "mild"  # 0.4 < 0.7


class TestGeminiVisionDiagnosis:
    """Test Gemini Vision API diagnosis fallback."""

    @pytest.mark.asyncio
    async def test_gemini_diagnose_success(self, dummy_config, dummy_image_bytes):
        """Test successful Gemini Vision diagnosis."""
        diagnoser = ImageDiagnoser(dummy_config)
        diagnoser.genai = MagicMock()

        # Mock Gemini response
        mock_response = MagicMock()
        mock_response.text = '{"pest": "Rust", "disease_marathi": "गेरुई/खरचा", "confidence": 0.85, "severity": "moderate", "treatment_marathi": "तांबे का घोल छिड़कें"}'

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        diagnoser.genai.GenerativeModel.return_value = mock_model

        result = await diagnoser._diagnose_gemini(dummy_image_bytes)

        assert result.pest == "Rust"
        assert result.disease_marathi == "गेरुई/खरचा"
        assert result.confidence == 0.85
        assert result.severity == "moderate"
        assert result.source == "gemini"

    @pytest.mark.asyncio
    async def test_gemini_diagnose_no_pest_detected(self, dummy_config, dummy_image_bytes):
        """Test Gemini detecting no pest in image."""
        diagnoser = ImageDiagnoser(dummy_config)
        diagnoser.genai = MagicMock()

        mock_response = MagicMock()
        mock_response.text = '{"pest": "No pest detected", "disease_marathi": "रोग नहीं देखा गया", "confidence": 0.0, "severity": "none", "treatment_marathi": ""}'

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        diagnoser.genai.GenerativeModel.return_value = mock_model

        result = await diagnoser._diagnose_gemini(dummy_image_bytes)

        assert result.pest == "No pest detected"
        assert result.confidence == 0.0
        assert result.severity == "none"

    @pytest.mark.asyncio
    async def test_gemini_diagnose_json_parse_error(self, dummy_config, dummy_image_bytes):
        """Test Gemini response with invalid JSON."""
        diagnoser = ImageDiagnoser(dummy_config)
        diagnoser.genai = MagicMock()

        mock_response = MagicMock()
        mock_response.text = "Invalid JSON response"  # Not JSON

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        diagnoser.genai.GenerativeModel.return_value = mock_model

        with pytest.raises(DiagnosisError):
            await diagnoser._diagnose_gemini(dummy_image_bytes)

    @pytest.mark.asyncio
    async def test_gemini_not_configured(self, dummy_config, dummy_image_bytes):
        """Test Gemini diagnosis when genai not initialized."""
        diagnoser = ImageDiagnoser(dummy_config)
        diagnoser.genai = None  # Not initialized

        with pytest.raises(DiagnosisError):
            await diagnoser._diagnose_gemini(dummy_image_bytes)


class TestDiagnosisFlow:
    """Test full diagnosis flow (TensorFlow → Gemini fallback)."""

    @pytest.mark.asyncio
    async def test_diagnose_tensorflow_success(self, dummy_config, dummy_image_bytes):
        """Test successful TensorFlow diagnosis in full flow."""
        diagnoser = ImageDiagnoser(dummy_config)

        # Mock TensorFlow
        mock_model = MagicMock()
        mock_predictions = np.array([[0.01, 0.88, 0.05, 0.03, 0.03]])
        mock_model.predict.return_value = mock_predictions
        diagnoser.tf_model = mock_model
        diagnoser._model_available = True

        with patch("src.diagnosis.processor.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            mock_http_response = MagicMock()
            mock_http_response.content = dummy_image_bytes
            mock_http_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_http_response)

            result = await diagnoser.diagnose("https://example.com/image.jpg")

            assert result.source == "tensorflow"
            assert result.pest == "Leaf Blight"

    @pytest.mark.asyncio
    async def test_diagnose_gemini_fallback(self, dummy_config, dummy_image_bytes):
        """Test Gemini fallback when TensorFlow unavailable."""
        diagnoser = ImageDiagnoser(dummy_config)
        diagnoser._model_available = False  # TensorFlow not available
        diagnoser.genai = MagicMock()

        mock_response = MagicMock()
        mock_response.text = '{"pest": "Mosaic Virus", "disease_marathi": "मोजेक वायरस", "confidence": 0.75, "severity": "moderate", "treatment_marathi": "वायरस प्रतिरोधी किस्म लगाएं"}'

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response
        diagnoser.genai.GenerativeModel.return_value = mock_model

        with patch("src.diagnosis.processor.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            mock_http_response = MagicMock()
            mock_http_response.content = dummy_image_bytes
            mock_http_response.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_http_response)

            result = await diagnoser.diagnose("https://example.com/image.jpg")

            assert result.source == "gemini"
            assert result.pest == "Mosaic Virus"

    @pytest.mark.asyncio
    async def test_diagnose_both_fail(self, dummy_config, dummy_image_bytes):
        """Test failure when both TensorFlow and Gemini fail."""
        diagnoser = ImageDiagnoser(dummy_config)
        diagnoser._model_available = False
        diagnoser.gemini_enabled = False  # Gemini also disabled

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.content = dummy_image_bytes
            mock_get.return_value.__aenter__.return_value = mock_response

            with pytest.raises(DiagnosisError):
                await diagnoser.diagnose("https://example.com/image.jpg")

    @pytest.mark.asyncio
    async def test_diagnose_download_fails(self, dummy_config):
        """Test diagnosis when image download fails."""
        diagnoser = ImageDiagnoser(dummy_config)

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = Exception("Network error")

            with pytest.raises(DiagnosisError):
                await diagnoser.diagnose("https://example.com/image.jpg")


# ==================== DiagnosisHandler Tests ====================


class TestDiagnosisHandler:
    """Test DiagnosisHandler orchestration."""

    @pytest.mark.asyncio
    async def test_handle_high_confidence(self, sample_diagnosis_result):
        """Test handler with high-confidence diagnosis."""
        mock_diagnoser = AsyncMock()
        mock_diagnoser.diagnose.return_value = sample_diagnosis_result

        handler = DiagnosisHandler(mock_diagnoser)
        intent = IntentResult(intent=Intent.PEST_QUERY, confidence=1.0)

        reply = await handler.handle(
            intent=intent,
            media_url="https://example.com/image.jpg",
            farmer_phone="919876543210",
            farmer_language="mr",
        )

        assert "पाउडर मिल्ड्यू" in reply  # Marathi disease name
        assert "Powdery Mildew" in reply
        assert "92%" in reply or "92" in reply  # Confidence percentage

    @pytest.mark.asyncio
    async def test_handle_low_confidence(self):
        """Test handler with low-confidence diagnosis."""
        low_conf_result = DiagnosisResult(
            pest="Unknown Pest",
            disease_marathi="अज्ञात कीट",
            confidence=0.35,
            severity="mild",
            treatment=None,
            source="gemini",
        )

        mock_diagnoser = AsyncMock()
        mock_diagnoser.diagnose.return_value = low_conf_result

        handler = DiagnosisHandler(mock_diagnoser)
        intent = IntentResult(intent=Intent.PEST_QUERY, confidence=1.0)

        reply = await handler.handle(
            intent=intent,
            media_url="https://example.com/image.jpg",
            farmer_language="mr",
        )

        assert "अस्पष्ट" in reply or "unclear" in reply  # Low confidence warning

    @pytest.mark.asyncio
    async def test_handle_diagnosis_error(self):
        """Test handler when diagnosis fails."""
        mock_diagnoser = AsyncMock()
        mock_diagnoser.diagnose.side_effect = DiagnosisError("TensorFlow timeout")

        handler = DiagnosisHandler(mock_diagnoser)
        intent = IntentResult(intent=Intent.PEST_QUERY, confidence=1.0)

        reply = await handler.handle(
            intent=intent,
            media_url="https://example.com/image.jpg",
            farmer_language="mr",
        )

        assert "खेद" in reply or "sorry" in reply  # Failure message


# ==================== Formatter Tests ====================


class TestDiagnosisFormatter:
    """Test diagnosis result formatting for farmers."""

    def test_format_diagnosis_marathi(self, sample_diagnosis_result):
        """Test Marathi formatting of high-confidence diagnosis."""
        reply = format_diagnosis_reply(sample_diagnosis_result, lang="mr")

        assert "पाउडर मिल्ड्यू" in reply
        assert "Powdery Mildew" in reply
        assert "92%" in reply or "92" in reply
        assert "🟡" in reply or "moderate" in reply or "मध्यम" in reply

    def test_format_diagnosis_english(self, sample_diagnosis_result):
        """Test English formatting of diagnosis."""
        reply = format_diagnosis_reply(sample_diagnosis_result, lang="en")

        assert "Powdery Mildew" in reply
        assert "92%" in reply or "92" in reply
        assert "Moderate" in reply or "moderate" in reply

    def test_format_low_confidence_marathi(self):
        """Test low-confidence warning in Marathi."""
        result = DiagnosisResult(
            pest="Unknown",
            disease_marathi="अज्ञात",
            confidence=0.45,
            severity="mild",
        )

        reply = format_diagnosis_low_confidence(result, lang="mr")
        assert "अस्पष्ट" in reply  # "unclear" in Marathi
        assert "45%" in reply or "45" in reply

    def test_format_diagnosis_failed_marathi(self):
        """Test failure message in Marathi."""
        reply = format_diagnosis_failed(lang="mr")

        assert "खेद" in reply  # "sorry" in Marathi
        assert "📸" in reply or "फोटो" in reply

    def test_format_diagnosis_failed_english(self):
        """Test failure message in English."""
        reply = format_diagnosis_failed(lang="en")

        assert "Sorry" in reply
        assert "photo" in reply or "image" in reply

    def test_format_severe_diagnosis(self):
        """Test formatting of severe diagnosis."""
        result = DiagnosisResult(
            pest="Severe Blight",
            disease_marathi="गंभीर सड़न",
            confidence=0.95,
            severity="severe",
        )

        reply = format_diagnosis_reply(result, lang="mr")
        assert "🔴" in reply or "severe" in reply or "गंभीर" in reply

    def test_format_no_pest_detected(self):
        """Test formatting when no pest detected."""
        result = DiagnosisResult(
            pest="No pest detected",
            disease_marathi="कोई रोग नहीं",
            confidence=0.0,
            severity="none",
        )

        reply = format_diagnosis_reply(result, lang="mr")
        assert "✅" in reply or "no pest" in reply or "none" in reply


# ==================== Integration Tests ====================


class TestWebhookIntegration:
    """Test integration with webhook handler."""

    def test_image_message_routing(self):
        """Test that image messages are routed to PEST_QUERY."""
        from src.handlers.webhook import IncomingMessage, handle_message

        msg = IncomingMessage(
            from_phone="919876543210",
            message_id="msg123",
            message_type="image",
            media_id="media456",
            media_url="https://example.com/image.jpg",
        )

        # should mark as image ready
        assert msg.is_image()
        assert not msg.is_text()
        assert not msg.is_audio()

    @pytest.mark.asyncio
    async def test_handle_image_message(self):
        """Test webhook handler processes image messages correctly."""
        from src.handlers.webhook import IncomingMessage, handle_message

        msg = IncomingMessage(
            from_phone="919876543210",
            message_id="msg123",
            message_type="image",
            media_id="media456",
            media_url="https://example.com/image.jpg",
        )

        result = await handle_message(msg)

        assert result["intent"] == "pest_query"
        assert result["status"] == "image_ready"

    @pytest.mark.asyncio
    async def test_handle_image_missing_media_url(self):
        """Test webhook handler when image lacks media URL."""
        from src.handlers.webhook import IncomingMessage, handle_message
        from src.classifier.intents import Intent

        msg = IncomingMessage(
            from_phone="919876543210",
            message_id="msg123",
            message_type="image",
            media_id="media456",
            media_url=None,  # Missing!
        )

        result = await handle_message(msg)

        assert result["intent"] == Intent.PEST_QUERY.value
        assert result["status"] == "image_error"


# ==================== Edge Cases & Error Handling ====================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_translate_to_marathi_unknown_pest(self, dummy_config):
        """Test translation of unknown pest name."""
        diagnoser = ImageDiagnoser(dummy_config)

        translated = diagnoser._translate_to_marathi("Unknown Pest XYZ")
        assert translated == "Unknown Pest XYZ"  # Falls back to original

    @pytest.mark.asyncio
    async def test_diagnose_with_timeout(self, dummy_config):
        """Test diagnosis timeout handling."""
        diagnoser = ImageDiagnoser(dummy_config)

        async def slow_download(*args, **kwargs):
            await asyncio.sleep(100)  # Simulate very slow download

        with patch.object(diagnoser, "_download_image", side_effect=asyncio.TimeoutError):
            with pytest.raises(DiagnosisError):
                await diagnoser.diagnose("https://example.com/image.jpg")

    def test_diagnosis_result_dataclass(self):
        """Test DiagnosisResult dataclass creation."""
        result = DiagnosisResult(
            pest="Test Pest",
            disease_marathi="परीक्षण कीट",
            confidence=0.80,
            severity="moderate",
            treatment="Test treatment",
            source="tensorflow",
        )

        assert result.pest == "Test Pest"
        assert result.confidence == 0.80
        assert result.source == "tensorflow"

    def test_confidence_boundaries(self):
        """Test confidence score boundary conditions."""
        # Confidence exactly at threshold
        result = DiagnosisResult(
            pest="Test",
            disease_marathi="परीक्षण",
            confidence=0.7,  # Exactly at 0.7
            severity="moderate",
        )
        assert result.confidence == 0.7

        # Min confidence
        result_min = DiagnosisResult(
            pest="Test",
            disease_marathi="परीक्षण",
            confidence=0.0,
            severity="none",
        )
        assert result_min.confidence == 0.0

        # Max confidence
        result_max = DiagnosisResult(
            pest="Test",
            disease_marathi="परीक्षण",
            confidence=1.0,
            severity="severe",
        )
        assert result_max.confidence == 1.0
