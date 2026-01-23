"""Add notification_read_by field to batches for per-user notification tracking

Revision ID: 013
Revises: 012
Create Date: 2025-11-07 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add notification_read_by field to batches table.
    
    This field stores an array of user UUIDs who have marked the notification as read,
    enabling per-user notification tracking without a separate table.
    """
    
    # Add notification_read_by column (JSON array of user UUIDs)
    op.add_column(
        'batches',
        sa.Column('notification_read_by', postgresql.JSON(astext_type=sa.String()), nullable=True)
    )


def downgrade():
    """
    Remove notification_read_by field from batches table.
    """
    
    op.drop_column('batches', 'notification_read_by')

