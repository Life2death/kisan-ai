from datetime import datetime
from typing import Optional, Any

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.models.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("farmers.id"))
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # 'inbound' | 'outbound'
    message_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'text' | 'template' | 'interactive' | 'audio'
    raw_message: Mapped[Optional[str]] = mapped_column(Text)
    detected_intent: Mapped[Optional[str]] = mapped_column(String(50))
    detected_entities: Mapped[Optional[Any]] = mapped_column(JSONB)
    response_sent: Mapped[Optional[str]] = mapped_column(Text)
    media_url: Mapped[Optional[str]] = mapped_column(String(500))  # Meta WhatsApp media URL (24-hour expiry)
    voice_transcription: Mapped[Optional[str]] = mapped_column(Text)  # Transcribed text from STT (Google Cloud / Whisper)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_conv_farmer", "farmer_id"),
        Index("idx_conv_created", "created_at"),
    )
