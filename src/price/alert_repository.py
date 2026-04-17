"""Repository for price alert subscriptions and queries."""
import logging
from decimal import Decimal
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PriceAlertRepository:
    """Manage price alert subscriptions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_price_alert(
        self,
        farmer_id: str,
        commodity: str,
        threshold: Decimal,
        condition: str = ">",
        district: str = None,
    ) -> bool:
        """Save/update price alert subscription."""
        try:
            from src.models.price import PriceAlert
            from datetime import datetime

            stmt = (
                PriceAlert.__table__.insert()
                .values(
                    farmer_id=farmer_id,
                    commodity=commodity,
                    threshold=threshold,
                    condition=condition,
                    district=district,
                    is_active=True,
                    created_at=datetime.utcnow(),
                )
                .on_conflict_do_update(
                    index_elements=["farmer_id", "commodity", "district", "condition", "threshold"],
                    set_={"is_active": True},
                )
            )

            await self.session.execute(stmt)
            await self.session.commit()
            logger.info(f"✅ Price alert saved: {farmer_id} {commodity}{condition}₹{threshold}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to save price alert: {e}")
            await self.session.rollback()
            return False

    async def get_active_alerts(self) -> list[dict]:
        """Get all active price alerts for triggering."""
        try:
            from src.models.price import PriceAlert

            query = select(PriceAlert).where(PriceAlert.is_active == True)
            result = await self.session.execute(query)
            alerts = result.scalars().all()

            return [
                {
                    "farmer_id": str(a.farmer_id),
                    "commodity": a.commodity,
                    "district": a.district,
                    "condition": a.condition,
                    "threshold": float(a.threshold),
                }
                for a in alerts
            ]

        except Exception as e:
            logger.error(f"❌ Failed to get active alerts: {e}")
            return []

    def check_condition(self, condition: str, actual: float, threshold: float) -> bool:
        """Check if price meets alert condition."""
        if condition == ">":
            return actual > threshold
        elif condition == "<":
            return actual < threshold
        elif condition == "==":
            return abs(actual - threshold) < 0.01  # Float equality
        return False
