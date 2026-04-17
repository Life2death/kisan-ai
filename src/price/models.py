"""Price query models."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass(slots=True)
class PriceQuery:
    """Extracted by intent classifier."""
    commodity: str          # canonical: onion, tur, soyabean, ...
    district: Optional[str] = None  # canonical: pune, nashik, ...
    variety: Optional[str] = None
    query_date: date = None  # defaults to today


@dataclass(slots=True, frozen=True)
class MandiPriceRecord:
    """One row from mandi_prices table."""
    date: date
    apmc: str
    mandi_display: str
    commodity: str
    variety: Optional[str]
    modal_price: Optional[Decimal]
    min_price: Optional[Decimal]
    max_price: Optional[Decimal]
    source: str
    is_stale: bool = False

    @property
    def price_str(self) -> str:
        """Format price for display."""
        if not self.modal_price:
            return "उपलब्ध नाही"
        return f"₹{int(self.modal_price)}/क्विंटल"

    @property
    def range_str(self) -> str:
        """Min-max range."""
        if not self.min_price or not self.max_price:
            return ""
        return f"(₹{int(self.min_price)} - ₹{int(self.max_price)})"


@dataclass(slots=True)
class PriceQueryResult:
    """Result of a price query."""
    query: PriceQuery
    records: list[MandiPriceRecord]
    found: bool
    missing_district: bool = False  # farmer hasn't registered district
    stale: bool = False             # all records are >36h old
