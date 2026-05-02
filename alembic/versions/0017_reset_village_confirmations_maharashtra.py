"""Reset village confirmation tracking for Maharashtra farmers.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-01 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None

# List of Maharashtra district slugs
MH_DISTRICTS = [
    'ahmednagar', 'pune', 'nashik', 'solapur', 'satara',
    'sangli', 'kolhapur', 'aurangabad', 'jalgaon', 'nanded',
    'wardha', 'nagpur', 'buldana', 'akola', 'yavatmal',
    'latur', 'osmanaabad', 'navi_mumbai', 'mumbai', 'ahilyanagar'
]


def upgrade() -> None:
    # Reset village confirmation fields for all Maharashtra farmers
    # This allows them to re-confirm their village preferences
    op.execute(f"""
        UPDATE farmers SET
            village_confirmation_count = 0,
            village_locked = 0,
            village_confirmed_at = NULL
        WHERE district IN ({', '.join([f"'{d}'" for d in MH_DISTRICTS])})
        AND deleted_at IS NULL
    """)


def downgrade() -> None:
    # No downgrade action needed for this data reset
    # Existing farmer confirmation states cannot be recovered
    pass
