"""Add gym snapshot and batch_is_deleted to token_usage

Revision ID: 015
Revises: 014
Create Date: 2025-11-11 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    # Add gym snapshot fields (no FKs to preserve history) - idempotent
    op.execute("ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS gym_id UUID")
    op.execute("ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS gym_name VARCHAR(255)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_token_usage_gym_id ON token_usage (gym_id)")

    # Add batch deletion snapshot flag - idempotent
    op.execute("ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS batch_is_deleted BOOLEAN NOT NULL DEFAULT false")

    # Backfill missing batch_id from executions
    op.execute("""
        UPDATE token_usage tu
        SET batch_id = e.batch_id
        FROM executions e
        WHERE tu.execution_id = e.uuid AND tu.batch_id IS NULL
    """)
    # Backfill gym_id from executions
    op.execute("""
        UPDATE token_usage tu
        SET gym_id = e.gym_id
        FROM executions e
        WHERE tu.execution_id = e.uuid AND tu.gym_id IS NULL
    """)
    # Backfill gym_name from gyms via executions
    op.execute("""
        UPDATE token_usage tu
        SET gym_name = g.name
        FROM executions e
        JOIN gyms g ON g.uuid = e.gym_id
        WHERE tu.execution_id = e.uuid AND (tu.gym_name IS NULL OR tu.gym_name = '')
    """)
    # Backfill batch_name from batches
    op.execute("""
        UPDATE token_usage tu
        SET batch_name = b.name
        FROM batches b
        WHERE tu.batch_id = b.uuid AND (tu.batch_name IS NULL OR tu.batch_name = '')
    """)


def downgrade():
    op.drop_column('token_usage', 'batch_is_deleted')
    op.drop_index('ix_token_usage_gym_id', table_name='token_usage')
    op.drop_column('token_usage', 'gym_name')
    op.drop_column('token_usage', 'gym_id')


