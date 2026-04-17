"""Image-based pest and disease diagnosis using TensorFlow + Gemini Vision fallback."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
from io import BytesIO
import tempfile
import os

import httpx
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)


class DiagnosisError(Exception):
    """Raised when pest diagnosis fails."""
    pass


@dataclass
class DiagnosisResult:
    """Result of pest/disease diagnosis from image."""
    pest: str
    """English pest/disease name (e.g., 'Powdery Mildew')."""
    disease_marathi: str
    """Marathi disease name."""
    confidence: float
    """Confidence score (0.0-1.0)."""
    severity: str
    """Severity level: 'mild', 'moderate', 'severe'."""
    treatment: Optional[str] = None
    """Treatment recommendations."""
    source: str = "tensorflow"
    """Source of diagnosis: 'tensorflow' or 'gemini'."""


class ImageDiagnoser:
    """Diagnose crop pests from images using TensorFlow + Gemini Vision fallback.

    Flow:
    1. Download image from Meta WhatsApp URL (24-hour expiry)
    2. Try local TensorFlow model for fast diagnosis
    3. Fallback to Gemini Vision if TensorFlow unavailable/fails
    4. Return structured DiagnosisResult
    """

    def __init__(self, config: dict):
        """Initialize diagnoser.

        Args:
            config: Dict with keys:
                - tensorflow_model_path: Path to .h5 model file
                - gemini_vision_enabled: Whether to use Gemini fallback
                - image_processing_timeout: Max seconds for diagnosis
                - diagnosis_confidence_threshold: Min confidence to report
        """
        self.config = config
        self.timeout = config.get("image_processing_timeout", 60)
        self.model_path = config.get("tensorflow_model_path", "")
        self.gemini_enabled = config.get("gemini_vision_enabled", True)
        self.confidence_threshold = config.get("diagnosis_confidence_threshold", 0.7)

        # Lazy load TensorFlow model
        self.tf_model = None
        self._model_available = False
        self._try_load_model()

        # Gemini client (same as LLM classifier)
        try:
            import google.generativeai as genai
            self.genai = genai
            logger.info("✅ Gemini Vision initialized")
        except Exception as e:
            logger.warning(f"⚠️  Gemini Vision init failed: {e}")
            self.genai = None

    def _try_load_model(self) -> None:
        """Try to load TensorFlow model. Fail gracefully if unavailable."""
        if not self.model_path:
            logger.warning("⚠️  No TensorFlow model path configured")
            return

        try:
            import tensorflow as tf
            if os.path.exists(self.model_path):
                self.tf_model = tf.keras.models.load_model(self.model_path)
                self._model_available = True
                logger.info(f"✅ TensorFlow model loaded from {self.model_path}")
            else:
                logger.warning(f"⚠️  Model file not found: {self.model_path}")
                logger.info("Will use Gemini Vision fallback")
        except Exception as e:
            logger.warning(f"⚠️  TensorFlow model load failed: {e}")
            logger.info("Will use Gemini Vision fallback")

    async def diagnose(self, media_url: str) -> DiagnosisResult:
        """Download image and diagnose pest/disease.

        Args:
            media_url: Meta WhatsApp media URL (24-hour expiry)

        Returns:
            DiagnosisResult with pest identification + treatment

        Raises:
            DiagnosisError: If both TensorFlow and Gemini fail
        """
        try:
            # Step 1: Download image
            image_bytes = await self._download_image(media_url)
            logger.info(f"✅ Downloaded image ({len(image_bytes)} bytes)")

            # Step 2: Try TensorFlow first
            if self._model_available:
                try:
                    result = await self._diagnose_tensorflow(image_bytes)
                    logger.info(f"✅ TensorFlow diagnosis: {result.pest}")
                    return result
                except Exception as e:
                    logger.warning(f"⚠️  TensorFlow failed: {e}. Using Gemini fallback...")

            # Step 3: Fallback to Gemini Vision
            if self.gemini_enabled and self.genai:
                try:
                    result = await self._diagnose_gemini(image_bytes)
                    logger.info(f"✅ Gemini diagnosis: {result.pest}")
                    return result
                except Exception as e:
                    logger.error(f"❌ Gemini Vision failed: {e}")
                    raise DiagnosisError(f"All diagnosis methods failed: {e}")

            raise DiagnosisError("No diagnosis service available (TensorFlow + Gemini disabled)")

        except asyncio.TimeoutError:
            logger.error("❌ Diagnosis timeout (>60 seconds)")
            raise DiagnosisError("Diagnosis timeout")
        except Exception as e:
            logger.error(f"❌ Diagnosis failed: {e}")
            raise DiagnosisError(str(e))

    async def _download_image(self, media_url: str) -> bytes:
        """Download image from Meta URL with timeout."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(media_url, follow_redirects=True)
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as e:
            raise DiagnosisError(f"Failed to download image: {e}")

    async def _diagnose_tensorflow(self, image_bytes: bytes) -> DiagnosisResult:
        """Diagnose using local TensorFlow model.

        Returns:
            DiagnosisResult from model prediction

        Raises:
            DiagnosisError: If inference fails
        """
        if not self._model_available or self.tf_model is None:
            raise DiagnosisError("TensorFlow model not available")

        try:
            # Load and preprocess image
            image = Image.open(BytesIO(image_bytes))
            image = image.convert("RGB")
            image = image.resize((224, 224))  # Standard input size
            image_array = np.array(image) / 255.0  # Normalize

            # Run inference in executor (non-blocking)
            def _predict():
                predictions = self.tf_model.predict(np.expand_dims(image_array, 0), verbose=0)
                top_idx = np.argmax(predictions[0])
                confidence = float(predictions[0][top_idx])
                return top_idx, confidence

            loop = asyncio.get_event_loop()
            top_idx, confidence = await asyncio.wait_for(
                loop.run_in_executor(None, _predict),
                timeout=30  # TensorFlow timeout
            )

            # Map to pest name (placeholder — actual mapping depends on model)
            pest_map = {
                0: "Powdery Mildew",
                1: "Leaf Blight",
                2: "Rust",
                3: "Mosaic Virus",
                4: "Anthracnose",
                # ... up to 20 pests
            }

            pest_name = pest_map.get(int(top_idx), f"Unknown Pest {top_idx}")
            disease_marathi = self._translate_to_marathi(pest_name)

            # Determine severity based on confidence
            if confidence > 0.9:
                severity = "severe"
            elif confidence > 0.7:
                severity = "moderate"
            else:
                severity = "mild"

            return DiagnosisResult(
                pest=pest_name,
                disease_marathi=disease_marathi,
                confidence=confidence,
                severity=severity,
                source="tensorflow",
            )

        except asyncio.TimeoutError:
            raise DiagnosisError("TensorFlow inference timeout")
        except Exception as e:
            raise DiagnosisError(f"TensorFlow error: {e}")

    async def _diagnose_gemini(self, image_bytes: bytes) -> DiagnosisResult:
        """Diagnose using Gemini Vision API."""
        if not self.genai:
            raise DiagnosisError("Gemini Vision not configured")

        try:
            # Convert bytes to PIL Image
            image = Image.open(BytesIO(image_bytes))

            # Prepare Gemini prompt
            prompt = """You are an expert plant pathologist. Analyze this crop image and identify any pest or disease.

Return a JSON response with EXACTLY these fields:
{
  "pest": "English name of pest/disease (e.g., Powdery Mildew)",
  "disease_marathi": "Marathi name of the disease",
  "confidence": 0.95,
  "severity": "moderate",
  "treatment_marathi": "Treatment recommendations in Marathi"
}

If you cannot identify a pest, return:
{"pest": "No pest detected", "disease_marathi": "रोग नहीं देखा गया", "confidence": 0.0, "severity": "none", "treatment_marathi": ""}

ONLY return the JSON, no other text."""

            # Call Gemini Vision
            def _call_gemini():
                model = self.genai.GenerativeModel("gemini-1.5-flash")
                response = model.generate_content([prompt, image])
                return response.text

            loop = asyncio.get_event_loop()
            response_text = await asyncio.wait_for(
                loop.run_in_executor(None, _call_gemini),
                timeout=self.timeout
            )

            # Parse JSON response
            import json
            response_json = json.loads(response_text)

            return DiagnosisResult(
                pest=response_json.get("pest", "Unknown"),
                disease_marathi=response_json.get("disease_marathi", "अज्ञात"),
                confidence=float(response_json.get("confidence", 0.0)),
                severity=response_json.get("severity", "unknown"),
                treatment=response_json.get("treatment_marathi"),
                source="gemini",
            )

        except asyncio.TimeoutError:
            raise DiagnosisError("Gemini Vision timeout")
        except Exception as e:
            raise DiagnosisError(f"Gemini Vision error: {e}")

    def _translate_to_marathi(self, pest_name: str) -> str:
        """Translate pest name to Marathi."""
        pest_marathi_map = {
            "Powdery Mildew": "पाउडर मिल्ड्यू",
            "Leaf Blight": "पत्तियों पर सड़न",
            "Rust": "गेरुई/खरचा",
            "Mosaic Virus": "मोजेक वायरस",
            "Anthracnose": "एन्थ्रेक्नोज",
        }
        return pest_marathi_map.get(pest_name, pest_name)
