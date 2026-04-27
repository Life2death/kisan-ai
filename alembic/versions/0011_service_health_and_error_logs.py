"""Create service_health and error_logs tables.

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-27 00:00:00.000000

Phase 3 Step 3 - Monitoring & Alerting:
- service_health: per-service heartbeat, error rate, latency metrics
- error_logs: persistent error tracking for all system failures
"""
from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'service_health',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('service_name', sa.String(50), nullable=False),
        sa.Column('last_heartbeat', sa.DateTime(), nullable=False),
        sa.Column('is_healthy', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('error_rate_1h', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('error_rate_24h', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('avg_latency_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('last_error_message', sa.String(500), nullable=True),
        sa.UniqueConstraint('service_name', name='uq_service_health_name'),
    )
    op.create_index('ix_service_health_name', 'service_health', ['service_name'])
    op.create_index('ix_service_health_status', 'service_health', ['service_name', 'is_healthy'])
    op.create_index('ix_service_health_updated', 'service_health', ['updated_at'])

    op.create_table(
        'error_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('service', sa.String(50), nullable=False),
        sa.Column('error_type', sa.String(50), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('stacktrace', sa.Text(), nullable=True),
        sa.Column('context_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_error_service', 'error_logs', ['service'])
    op.create_index('ix_error_type', 'error_logs', ['error_type'])
    op.create_index('ix_error_service_type', 'error_logs', ['service', 'error_type'])
    op.create_index('ix_error_created_service', 'error_logs', ['created_at', 'service'])
    op.create_index('ix_error_resolved', 'error_logs', ['resolved_at'])


def downgrade() -> None:
    op.drop_index('ix_error_resolved', table_name='error_logs')
    op.drop_index('ix_error_created_service', table_name='error_logs')
    op.drop_index('ix_error_service_type', table_name='error_logs')
    op.drop_index('ix_error_type', table_name='error_logs')
    op.drop_index('ix_error_service', table_name='error_logs')
    op.drop_table('error_logs')

    op.drop_index('ix_service_health_updated', table_name='service_health')
    op.drop_index('ix_service_health_status', table_name='service_health')
    op.drop_index('ix_service_health_name', table_name='service_health')
    op.drop_table('service_health')
