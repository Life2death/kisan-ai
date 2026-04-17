from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import String, Integer, Date, DateTime, Numeric, Boolean, Index, UniqueConstraint, ForeignKey, UUID as SA_UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class MandiPrice(Base):
    """A single daily price observation from one source.

    A row represents: on `date`, at `apmc` (canonical code), the commodity `crop`
    of `variety` was reported by `source` with min/max/modal prices and arrival
    quantity. Multiple sources may report the same cell; the merger view picks
    one per (date, apmc, crop, variety) based on source preference rules.
    """

    __tablename__ = "mandi_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    crop: Mapped[str] = mapped_column(String(50), nullable=False)
    variety: Mapped[Optional[str]] = mapped_column(String(100))
    mandi: Mapped[str] = mapped_column(String(100), nullable=False)           # display name
    apmc: Mapped[Optional[str]] = mapped_column(String(100))                  # canonical code
    district: Mapped[str] = mapped_column(String(50), nullable=False)
    modal_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    min_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    max_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    msp: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    arrival_quantity_qtl: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    source: Mapped[str] = mapped_column(String(50), default="agmarknet", nullable=False)
    raw_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("date", "apmc", "crop", "variety", "source", name="uq_mandi_prices_dedupe"),
        Index("idx_prices_lookup", "crop", "district", "date"),
        Index("idx_prices_date", "date"),
        Index("idx_mandi_prices_commodity_date", "crop", "date"),
        Index("idx_mandi_prices_district_date", "district", "date"),
    )


# Price Alerts (Phase 2 Module 5)
class PriceAlert(Base):
    """Farmer subscription to mandi price alerts (e.g., 'notify when onion > ₹5,000')."""

    __tablename__ = "price_alerts"

    id: Mapped[str] = mapped_column(SA_UUID(as_uuid=True), primary_key=True, default=func.gen_random_uuid())
    farmer_id: Mapped[str] = mapped_column(SA_UUID(as_uuid=True), ForeignKey("farmers.id", ondelete="CASCADE"))
    commodity: Mapped[str] = mapped_column(String(100), nullable=False)  # "onion", "wheat"
    district: Mapped[Optional[str]] = mapped_column(String(100))  # optional: specific mandi
    condition: Mapped[str] = mapped_column(String(10), nullable=False, default=">")  # ">", "<", "=="
    threshold: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=2), nullable=False)  # ₹5000
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # Last time alert sent
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("farmer_id", "commodity", "district", "condition", "threshold", name="uq_price_alert"),
        Index("idx_price_alerts_farmer", "farmer_id"),
        Index("idx_price_alerts_commodity", "commodity"),
        Index("idx_price_alerts_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<PriceAlert {self.commodity}{self.condition}₹{self.threshold}>"
