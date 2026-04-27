"""Base classes for government scheme sources."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SchemeRecord:
    """Parsed government scheme record from any source."""
    scheme_name: str               # e.g., "PM Kisan Yojana"
    scheme_slug: str               # e.g., "pm_kisan" (canonical)
    ministry: str                  # e.g., "Ministry of Agriculture"
    description: str               # Scheme description (Marathi + English)
    eligibility_criteria: dict     # {"min_age": 18, "max_land": 5, "citizenship": "indian"}
    commodities: list[str]         # ["wheat", "rice", "onion", ...]
    min_land_hectares: float       # Minimum land size for eligibility
    max_land_hectares: float       # Maximum land size (None = no limit)
    annual_benefit: str            # e.g., "₹6,000/year" or "70% subsidy"
    benefit_amount: Decimal        # Numeric benefit amount (₹ or %)
    application_deadline: date     # Last date to apply
    district: Optional[str]        # District (None = all-India / nationwide)
    state: str                     # State code (e.g., "maharashtra")
    raw_payload: dict              # Full API response for audit trail
    source: str = ""               # Set by orchestrator after fetch (e.g., "pmksy_api")


class SchemeSource(ABC):
    """Abstract base for government scheme sources."""

    name: str  # e.g., "pmksy_api", "pmfby_api", "hardcoded"

    @abstractmethod
    async def fetch(self) -> list[SchemeRecord]:
        """
        Fetch government schemes from this source.

        Returns:
            List of canonicalized SchemeRecord objects

        Raises:
            Exception on network/parsing errors (caught by orchestrator)
        """
        pass
