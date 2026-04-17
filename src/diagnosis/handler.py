"""Handler for pest diagnosis requests."""
import logging
from typing import Optional

from src.classifier.intents import IntentResult
from src.diagnosis.processor import ImageDiagnoser, DiagnosisResult, DiagnosisError
from src.diagnosis.formatter import (
    format_diagnosis_reply,
    format_diagnosis_failed,
    format_diagnosis_low_confidence,
)
from src.diagnosis.repository import DiagnosisRepository

logger = logging.getLogger(__name__)


class DiagnosisHandler:
    """Handle pest diagnosis requests (image → diagnosis → formatted reply).

    Orchestrates:
    1. Image download from Meta URL
    2. Local TensorFlow diagnosis (or Gemini fallback)
    3. Structured result storage
    4. Marathi/English formatting for farmer
    """

    def __init__(self, diagnoser: ImageDiagnoser, repo: Optional[DiagnosisRepository] = None):
        """Initialize handler.

        Args:
            diagnoser: ImageDiagnoser instance with TensorFlow + Gemini models
            repo: DiagnosisRepository for storing diagnosis history (optional)
        """
        self.diagnoser = diagnoser
        self.repo = repo

    async def handle(
        self,
        intent: IntentResult,
        media_url: str,
        farmer_phone: Optional[str] = None,
        farmer_language: str = "mr",
    ) -> str:
        """Handle pest diagnosis request end-to-end.

        Args:
            intent: Classification result (PEST_QUERY)
            media_url: Meta WhatsApp media URL (24-hour expiry)
            farmer_phone: Farmer's phone number for audit trail
            farmer_language: "mr" for Marathi, "en" for English

        Returns:
            Formatted diagnosis reply in farmer's language
        """
        try:
            # Step 1: Get diagnosis from processor (TensorFlow or Gemini)
            result = await self.diagnoser.diagnose(media_url)
            logger.info(f"✅ Diagnosis complete: {result.pest} (confidence: {result.confidence:.2f})")

            # Step 2: Store diagnosis in repository (optional)
            if self.repo and farmer_phone:
                try:
                    await self.repo.save_diagnosis(
                        farmer_phone=farmer_phone,
                        pest=result.pest,
                        disease_marathi=result.disease_marathi,
                        confidence=result.confidence,
                        severity=result.severity,
                        treatment=result.treatment,
                        source=result.source,
                    )
                except Exception as e:
                    logger.warning(f"⚠️  Failed to store diagnosis: {e}")
                    # Don't fail the response; storage is optional

            # Step 3: Format reply based on confidence
            if result.confidence < 0.5:
                # Low confidence — warn farmer
                formatted = format_diagnosis_low_confidence(
                    result=result,
                    lang=farmer_language,
                )
            else:
                # High confidence — full diagnosis
                formatted = format_diagnosis_reply(
                    result=result,
                    lang=farmer_language,
                )

            return formatted

        except DiagnosisError as e:
            logger.error(f"❌ Diagnosis failed: {e}")
            return format_diagnosis_failed(lang=farmer_language)
        except Exception as e:
            logger.error(f"❌ Unexpected error in diagnosis handler: {e}")
            return format_diagnosis_failed(lang=farmer_language)
