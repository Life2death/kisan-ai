"""Handler for price alert subscriptions."""
import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.price.alert_repository import PriceAlertRepository


logger = logging.getLogger(__name__)


class PriceAlertHandler:
    """Handle price alert subscriptions."""

    def __init__(self, session: AsyncSession):
        self.repo = PriceAlertRepository(session)

    async def handle_subscription(
        self,
        farmer_id: str,
        commodity: str,
        threshold: float,
        condition: str = ">",
        district: str = None,
        farmer_language: str = "mr",
    ) -> str:
        """Handle PRICE_ALERT intent (subscription)."""
        try:
            logger.info(f"🔔 Price alert: {farmer_id} {commodity}{condition}₹{threshold}")

            success = await self.repo.save_price_alert(
                farmer_id=farmer_id,
                commodity=commodity,
                threshold=Decimal(str(threshold)),
                condition=condition,
                district=district,
            )

            if not success:
                return "❌ Failed to set alert. Please try again."

            # Format confirmation
            from src.price.alert_formatter import format_price_alert_subscription
            reply = format_price_alert_subscription(
                commodity, condition, threshold, district, lang=farmer_language
            )
            logger.info(f"✅ Price alert subscribed: {farmer_id}")
            return reply

        except Exception as e:
            logger.error(f"❌ Price alert subscription failed: {e}")
            return "❌ Failed to set alert. Please try again."
