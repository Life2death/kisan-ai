"""Add price alerts table for mandi price notifications.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-18 12:00:00.000000

Price Alerts (Phase 2 Module 5):
- Farmers can subscribe to alerts: "Notify me when onion > ₹5,000"
- Triggered by daily price ingestion
- Support condition operators: >, <, ==
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create price_alerts table."""

    op.create_table(
        'price_alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('farmer_id', sa.Integer(), nullable=False),
        sa.Column('commodity', sa.String(100), nullable=False),  # "onion", "wheat"
        sa.Column('district', sa.String(100), nullable=True),  # optional: specific mandi
        sa.Column('condition', sa.String(10), nullable=False, server_default='>'),  # ">", "<", "=="
        sa.Column('threshold', sa.Numeric(precision=10, scale=2), nullable=False),  # ₹5000
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('farmer_id', 'commodity', 'district', 'condition', 'threshold', name='uq_price_alert'),
        sa.ForeignKeyConstraint(['farmer_id'], ['farmers.id'], ondelete='CASCADE'),
    )

    # Create indexes
    op.create_index('idx_price_alerts_farmer', 'price_alerts', ['farmer_id'])
    op.create_index('idx_price_alerts_commodity', 'price_alerts', ['commodity'])
    op.create_index('idx_price_alerts_active', 'price_alerts', ['is_active'])
    op.create_index('idx_price_alerts_condition', 'price_alerts', ['condition'])


def downgrade() -> None:
    """Drop price_alerts table."""

    op.drop_index('idx_price_alerts_condition', table_name='price_alerts')
    op.drop_index('idx_price_alerts_active', table_name='price_alerts')
    op.drop_index('idx_price_alerts_commodity', table_name='price_alerts')
    op.drop_index('idx_price_alerts_farmer', table_name='price_alerts')
    op.drop_table('price_alerts')
