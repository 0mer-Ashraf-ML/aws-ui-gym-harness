"""Add verifier_path column to tasks table

Revision ID: 021
Revises: 020
Create Date: 2025-12-05 00:00:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade():
    """Add verifier_path column to tasks if it does not already exist."""
    # Use a DO block so migration is idempotent and safe on existing databases
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'tasks'
                  AND column_name = 'verifier_path'
            ) THEN
                ALTER TABLE tasks ADD COLUMN verifier_path TEXT;
            END IF;
        END $$;
        """
    )


def downgrade():
    """Drop verifier_path column from tasks."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'tasks'
                  AND column_name = 'verifier_path'
            ) THEN
                ALTER TABLE tasks DROP COLUMN verifier_path;
            END IF;
        END $$;
        """
    )


