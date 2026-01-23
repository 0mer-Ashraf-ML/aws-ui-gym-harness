"""Add created_by field to batches to track who created/ran each batch

Revision ID: 017
Revises: 016
Create Date: 2025-11-XX XX:XX:XX.XXXXXX
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add created_by field to batches table.
    
    This field stores the UUID of the user who created/ran the batch,
    enabling tracking of batch ownership and accountability.
    """
    
    # Add created_by column (nullable for existing batches, foreign key to users)
    op.add_column(
        'batches',
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True)
    )
    
    # Create foreign key constraint
    op.create_foreign_key(
        'batches_created_by_fkey',
        'batches', 'users',
        ['created_by'], ['uuid']
    )
    
    # Create index for better query performance
    op.create_index(
        'ix_batches_created_by',
        'batches',
        ['created_by']
    )


def downgrade():
    """
    Remove created_by field from batches table.
    """
    
    op.drop_index('ix_batches_created_by', table_name='batches')
    op.drop_constraint('batches_created_by_fkey', 'batches', type_='foreignkey')
    op.drop_column('batches', 'created_by')

