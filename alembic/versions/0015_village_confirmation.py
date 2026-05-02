"""Add village confirmation tracking fields.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-01 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add village confirmation fields
    op.add_column('farmers', sa.Column('village_confirmation_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('farmers', sa.Column('village_locked', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('farmers', sa.Column('village_confirmed_at', sa.DateTime(timezone=True), nullable=True))

    # Drop the server defaults after adding columns (so they're just for initial population)
    op.alter_column('farmers', 'village_confirmation_count', server_default=None)
    op.alter_column('farmers', 'village_locked', server_default=None, existing_type=sa.Boolean())


def downgrade() -> None:
    op.drop_column('farmers', 'village_confirmed_at')
    op.drop_column('farmers', 'village_locked')
    op.drop_column('farmers', 'village_confirmation_count')
