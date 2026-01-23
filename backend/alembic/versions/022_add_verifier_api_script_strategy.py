"""Add VERIFIER_API_SCRIPT to verificationstrategy enum

Revision ID: 022
Revises: 021
Create Date: 2025-12-06 00:00:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade():
    """Add VERIFIER_API_SCRIPT enum value to verificationstrategy."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                WHERE t.typname = 'verificationstrategy'
                  AND e.enumlabel = 'VERIFIER_API_SCRIPT'
            ) THEN
                ALTER TYPE verificationstrategy ADD VALUE 'VERIFIER_API_SCRIPT';
            END IF;
        END$$;
        """
    )


def downgrade():
    """No-op: PostgreSQL enums do not support removing values safely."""
    pass


