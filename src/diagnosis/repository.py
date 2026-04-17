"""Repository for storing and retrieving diagnosis results."""
import logging
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DiagnosisRepository:
    """Store and query pest diagnosis results for analytics."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy AsyncSession for database operations
        """
        self.session = session

    async def save_diagnosis(
        self,
        farmer_phone: str,
        pest: str,
        disease_marathi: str,
        confidence: float,
        severity: str,
        treatment: Optional[str] = None,
        source: str = "tensorflow",
    ) -> None:
        """Save diagnosis result to database.

        Args:
            farmer_phone: Farmer's phone number
            pest: English pest/disease name
            disease_marathi: Marathi disease name
            confidence: Confidence score (0.0-1.0)
            severity: "mild", "moderate", "severe", "none"
            treatment: Treatment recommendations (optional)
            source: "tensorflow" or "gemini"
        """
        try:
            # Import here to avoid circular imports
            from src.models.diagnosis import DiagnosisRecord

            record = DiagnosisRecord(
                farmer_phone=farmer_phone,
                pest=pest,
                disease_marathi=disease_marathi,
                confidence=confidence,
                severity=severity,
                treatment=treatment,
                source=source,
                diagnosed_at=datetime.utcnow(),
            )

            self.session.add(record)
            await self.session.flush()  # Flush to get ID without committing
            logger.info(f"✅ Diagnosis saved for {farmer_phone}: {pest}")

        except Exception as e:
            logger.error(f"❌ Failed to save diagnosis: {e}")
            raise

    async def get_farmer_diagnosis_history(
        self,
        farmer_phone: str,
        limit: int = 10,
    ) -> List[dict]:
        """Get recent diagnosis history for a farmer.

        Args:
            farmer_phone: Farmer's phone number
            limit: Max results to return

        Returns:
            List of diagnosis records (most recent first)
        """
        try:
            from src.models.diagnosis import DiagnosisRecord

            query = (
                select(DiagnosisRecord)
                .where(DiagnosisRecord.farmer_phone == farmer_phone)
                .order_by(DiagnosisRecord.diagnosed_at.desc())
                .limit(limit)
            )

            result = await self.session.execute(query)
            records = result.scalars().all()

            return [
                {
                    "pest": r.pest,
                    "disease_marathi": r.disease_marathi,
                    "confidence": r.confidence,
                    "severity": r.severity,
                    "source": r.source,
                    "diagnosed_at": r.diagnosed_at,
                }
                for r in records
            ]

        except Exception as e:
            logger.error(f"❌ Failed to retrieve diagnosis history: {e}")
            return []

    async def get_district_pest_stats(self, district: str, limit: int = 5) -> List[dict]:
        """Get most common pests diagnosed in a district.

        Args:
            district: District name
            limit: Top N pests to return

        Returns:
            List of pests with diagnosis counts
        """
        try:
            from sqlalchemy import func
            from src.models.diagnosis import DiagnosisRecord
            from src.models.farmer import Farmer

            query = (
                select(
                    DiagnosisRecord.pest,
                    DiagnosisRecord.disease_marathi,
                    func.count(DiagnosisRecord.id).label("count"),
                )
                .join(Farmer, Farmer.phone == DiagnosisRecord.farmer_phone)
                .where(Farmer.district == district)
                .group_by(DiagnosisRecord.pest, DiagnosisRecord.disease_marathi)
                .order_by(func.count(DiagnosisRecord.id).desc())
                .limit(limit)
            )

            result = await self.session.execute(query)
            rows = result.all()

            return [
                {
                    "pest": r[0],
                    "disease_marathi": r[1],
                    "count": r[2],
                }
                for r in rows
            ]

        except Exception as e:
            logger.error(f"❌ Failed to retrieve district pest stats: {e}")
            return []
