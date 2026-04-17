"""Price data repository — queries mandi_prices table."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.price import MandiPrice
from src.price.models import MandiPriceRecord, PriceQuery, PriceQueryResult

logger = logging.getLogger(__name__)


class PriceRepository:
    """Query mandi_prices from Postgres."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def query(self, q: PriceQuery, farmer_district: Optional[str] = None) -> PriceQueryResult:
        """
        Query prices for a commodity, optionally by district.
        Falls back to farmer's registered district if not specified.
        Returns today's prices if query_date is None.
        """
        query_date = q.query_date or date.today()
        target_district = q.district or farmer_district

        # Query: crop + (district if specified) + today's date
        stmt = select(MandiPrice).where(
            MandiPrice.crop == q.commodity,
            MandiPrice.date == query_date,
        )
        if target_district:
            stmt = stmt.where(MandiPrice.district == target_district)

        stmt = stmt.order_by(MandiPrice.modal_price.desc().nullslast())

        result = await self.session.execute(stmt)
        rows = result.scalars().all()

        records = [
            MandiPriceRecord(
                date=row.date,
                apmc=row.apmc or row.mandi,
                mandi_display=row.mandi,
                commodity=row.crop,
                variety=row.variety,
                modal_price=row.modal_price,
                min_price=row.min_price,
                max_price=row.max_price,
                source=row.source,
                is_stale=row.is_stale,
            )
            for row in rows
        ]

        stale = all(r.is_stale for r in records) if records else False

        return PriceQueryResult(
            query=q,
            records=records,
            found=len(records) > 0,
            missing_district=(farmer_district is None and q.district is None),
            stale=stale,
        )

    async def get_historical(
        self,
        commodity: str,
        apmc: str,
        days: int = 7,
    ) -> list[MandiPriceRecord]:
        """Fetch last N days of prices for trend display."""
        since = date.today() - timedelta(days=days)
        stmt = select(MandiPrice).where(
            MandiPrice.crop == commodity,
            MandiPrice.apmc == apmc,
            MandiPrice.date >= since,
        ).order_by(MandiPrice.date.asc())

        result = await self.session.execute(stmt)
        rows = result.scalars().all()

        return [
            MandiPriceRecord(
                date=row.date,
                apmc=row.apmc or row.mandi,
                mandi_display=row.mandi,
                commodity=row.crop,
                variety=row.variety,
                modal_price=row.modal_price,
                min_price=row.min_price,
                max_price=row.max_price,
                source=row.source,
                is_stale=row.is_stale,
            )
            for row in rows
        ]
