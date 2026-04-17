from datetime import datetime
from typing import Optional, List

from sqlalchemy import String, Integer, DateTime, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.models.base import Base


class Farmer(Base):
    __tablename__ = "farmers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(100))
    district: Mapped[Optional[str]] = mapped_column(String(50))
    preferred_language: Mapped[str] = mapped_column(String(10), default="mr")
    plan_tier: Mapped[str] = mapped_column(String(20), default="free")
    subscription_status: Mapped[str] = mapped_column(String(20), default="none")
    onboarding_state: Mapped[str] = mapped_column(String(30), default="new")
    queries_today: Mapped[int] = mapped_column(Integer, default=0)
    queries_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    consent_given_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[Optional[str]] = mapped_column(String(10))
    erasure_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    crops: Mapped[List["CropOfInterest"]] = relationship(
        "CropOfInterest", back_populates="farmer", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_farmers_phone", "phone"),
        Index("idx_farmers_district", "district"),
    )


class CropOfInterest(Base):
    __tablename__ = "crops_of_interest"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int] = mapped_column(Integer, ForeignKey("farmers.id", ondelete="CASCADE"))
    crop: Mapped[str] = mapped_column(String(50), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    farmer: Mapped["Farmer"] = relationship("Farmer", back_populates="crops")

    __table_args__ = (Index("idx_crops_farmer", "farmer_id"),)
