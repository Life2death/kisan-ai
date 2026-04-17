"""Add voice message support for Phase 2 Module 2

Adds fields to conversations table to support audio message transcription:
- media_url: Stores Meta's 24-hour media download URL for audio files
- voice_transcription: Stores the transcribed text from Speech-to-Text service

Design:
- media_url: VARCHAR(500) NULL — Meta WhatsApp Cloud API audio URL (24-hour expiry)
- voice_transcription: TEXT NULL — Transcribed Marathi text from Google Cloud STT or Whisper

These fields enable:
- Full audit trail of voice messages (media_url proves audio was processed)
- Transparency (farmers can verify transcription accuracy)
- Privacy (no permanent storage of audio, only transcription)
- Retry capability (can re-download from media_url within 24 hours if transcription fails)

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add voice message support columns to conversations table."""

    # Add media_url column for audio file download URL
    op.add_column(
        "conversations",
        sa.Column(
            "media_url",
            sa.String(500),
            nullable=True,
            comment="Meta WhatsApp Cloud API media download URL (24-hour expiry) for audio/image/document files"
        ),
    )

    # Add voice_transcription column for STT output
    op.add_column(
        "conversations",
        sa.Column(
            "voice_transcription",
            sa.Text(),
            nullable=True,
            comment="Transcribed text from Speech-to-Text service (Google Cloud STT or Whisper). Empty if transcription failed."
        ),
    )

    # Create index on media_url for audit trail queries
    op.create_index(
        "idx_conversations_media_url",
        "conversations",
        ["media_url"],
        comment="Fast lookup for media messages with URLs",
    )

    # Create index on voice_transcription for filtering transcribed messages
    op.create_index(
        "idx_conversations_transcribed",
        "conversations",
        ["voice_transcription"],
        comment="Fast filtering of transcribed voice messages",
    )


def downgrade() -> None:
    """Rollback voice message support fields."""

    op.drop_index("idx_conversations_transcribed", table_name="conversations")
    op.drop_index("idx_conversations_media_url", table_name="conversations")

    op.drop_column("conversations", "voice_transcription")
    op.drop_column("conversations", "media_url")
