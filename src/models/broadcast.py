from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class BroadcastLog(Base):
    __tablename__ = "broadcast_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("farmers.id"))
    template_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|sent|delivered|failed
    cost_paise: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_broadcast_farmer", "farmer_id"),
        Index("idx_broadcast_status", "status"),
    )
