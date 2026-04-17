"""Add DPDPA compliance fields for consent flow and right-to-erasure

Adds:
- farmers.erasure_requested_at (TIMESTAMPTZ) — tracks when farmer requested deletion
- broadcast_log.deleted_at (TIMESTAMPTZ) — soft-delete for audit trail compliance
- conversation.deleted_at (TIMESTAMPTZ) — soft-delete for privacy

These fields enable:
- 30-day countdown before hard-delete (erasure_requested_at)
- Soft-delete pattern for audit trail preservation
- DPDPA v2023 "right to be forgotten" with audit logging

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add DPDPA fields to farmers, broadcast_log, conversation tables."""

    # Add erasure_requested_at to farmers (nullable, for 30-day countdown)
    op.add_column(
        "farmers",
        sa.Column(
            "erasure_requested_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when farmer requested data deletion (triggers 30-day countdown)"
        ),
    )

    # Add deleted_at to broadcast_log (soft-delete for audit compliance)
    op.add_column(
        "broadcast_log",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Soft-delete timestamp for audit trail preservation"
        ),
    )

    # Add deleted_at to conversation (soft-delete for privacy)
    op.add_column(
        "conversation",
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Soft-delete timestamp for farmer privacy"
        ),
    )

    # Create index on erasure_requested_at for efficient 30-day cleanup queries
    op.create_index(
        "idx_farmers_erasure_requested",
        "farmers",
        ["erasure_requested_at"],
    )

    # Create index on broadcast_log deleted_at for filtering soft-deleted records
    op.create_index(
        "idx_broadcast_log_deleted",
        "broadcast_log",
        ["deleted_at"],
    )

    # Create index on conversation deleted_at for filtering soft-deleted records
    op.create_index(
        "idx_conversation_deleted",
        "conversation",
        ["deleted_at"],
    )


def downgrade() -> None:
    """Rollback DPDPA fields."""

    op.drop_index("idx_conversation_deleted", table_name="conversation")
    op.drop_index("idx_broadcast_log_deleted", table_name="broadcast_log")
    op.drop_index("idx_farmers_erasure_requested", table_name="farmers")

    op.drop_column("conversation", "deleted_at")
    op.drop_column("broadcast_log", "deleted_at")
    op.drop_column("farmers", "erasure_requested_at")
