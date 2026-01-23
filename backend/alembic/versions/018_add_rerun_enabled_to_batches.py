"""Add rerun_enabled flag to batches

Revision ID: 018
Revises: 017
Create Date: 2025-11-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade():
    """Add rerun_enabled column to batches table"""
    op.add_column(
        'batches',
        sa.Column('rerun_enabled', sa.Boolean(), nullable=False, server_default=sa.text('TRUE'))
    )


def downgrade():
    """Remove rerun_enabled column from batches table"""
    op.drop_column('batches', 'rerun_enabled')

