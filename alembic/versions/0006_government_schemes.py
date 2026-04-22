"""Add government schemes and MSP alerts tables.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-18 10:00:00.000000

Government Schemes (Phase 2 Module 4):
- government_schemes: Ingested scheme data (PM-KISAN, PM-FASAL, etc.)
- msp_alerts: Farmer subscriptions to price alerts
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create government_schemes and msp_alerts tables."""

    # Create government_schemes table
    op.create_table(
        'government_schemes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('scheme_name', sa.String(200), nullable=False),  # e.g., "PM Kisan Yojana"
        sa.Column('scheme_slug', sa.String(100), nullable=False),  # e.g., "pm_kisan"
        sa.Column('ministry', sa.String(100), nullable=True),  # "Agriculture", "Finance"
        sa.Column('description', sa.Text, nullable=True),  # Marathi + English
        sa.Column('eligibility_criteria', postgresql.JSONB(astext_type=sa.Text()), nullable=True),  # {"min_age": 18, "max_land": 5, ...}
        sa.Column('commodities', postgresql.ARRAY(sa.String()), nullable=True),  # ["wheat", "rice", ...]
        sa.Column('min_land_hectares', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('max_land_hectares', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('annual_benefit', sa.String(100), nullable=True),  # "₹6,000/year" or "70% subsidy"
        sa.Column('benefit_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('application_deadline', sa.Date(), nullable=True),
        sa.Column('district', sa.String(100), nullable=True),  # NULL = all-India (nationwide)
        sa.Column('state', sa.String(100), nullable=True),  # "Maharashtra"
        sa.Column('source', sa.String(50), nullable=False),  # "pmksy_api", "pmfby_api", "govt_website"
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),  # Full API response for audit
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scheme_slug', 'district', 'source', name='uq_scheme_district_source'),
    )

    # Create indexes for government_schemes
    op.create_index('idx_schemes_commodity', 'government_schemes', [sa.text('commodities')], postgresql_using='gin')
    op.create_index('idx_schemes_district', 'government_schemes', ['district'])
    op.create_index('idx_schemes_state', 'government_schemes', ['state'])
    op.create_index('idx_schemes_source', 'government_schemes', ['source'])
    op.create_index('idx_schemes_slug', 'government_schemes', ['scheme_slug'])
    op.create_index('idx_schemes_deadline', 'government_schemes', ['application_deadline'])

    # Create msp_alerts table
    op.create_table(
        'msp_alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('farmer_id', sa.Integer(), nullable=False),
        sa.Column('commodity', sa.String(100), nullable=False),  # "onion", "wheat", etc.
        sa.Column('alert_threshold', sa.Numeric(precision=10, scale=2), nullable=False),  # Alert when MSP >= this value
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=True),  # Last time alert sent
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('farmer_id', 'commodity', name='uq_farmer_commodity_alert'),
        sa.ForeignKeyConstraint(['farmer_id'], ['farmers.id'], ondelete='CASCADE'),
    )

    # Create indexes for msp_alerts
    op.create_index('idx_msp_alerts_farmer', 'msp_alerts', ['farmer_id'])
    op.create_index('idx_msp_alerts_commodity', 'msp_alerts', ['commodity'])
    op.create_index('idx_msp_alerts_active', 'msp_alerts', ['is_active'])
    op.create_index('idx_msp_alerts_threshold', 'msp_alerts', ['alert_threshold'])


def downgrade() -> None:
    """Drop government_schemes and msp_alerts tables."""

    # Drop msp_alerts table and indexes
    op.drop_index('idx_msp_alerts_threshold', table_name='msp_alerts')
    op.drop_index('idx_msp_alerts_active', table_name='msp_alerts')
    op.drop_index('idx_msp_alerts_commodity', table_name='msp_alerts')
    op.drop_index('idx_msp_alerts_farmer', table_name='msp_alerts')
    op.drop_table('msp_alerts')

    # Drop government_schemes table and indexes
    op.drop_index('idx_schemes_deadline', table_name='government_schemes')
    op.drop_index('idx_schemes_slug', table_name='government_schemes')
    op.drop_index('idx_schemes_source', table_name='government_schemes')
    op.drop_index('idx_schemes_state', table_name='government_schemes')
    op.drop_index('idx_schemes_district', table_name='government_schemes')
    op.drop_index('idx_schemes_commodity', table_name='government_schemes')
    op.drop_table('government_schemes')
