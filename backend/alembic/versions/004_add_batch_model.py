"""add_batch_model

Revision ID: 004
Revises: 003
Create Date: 2025-10-08 07:54:21.322881

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, Sequence[str], None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create batches table
    op.create_table('batches',
        sa.Column('uuid', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('gym_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('number_of_iterations', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['gym_id'], ['gyms.uuid'], ),
        sa.PrimaryKeyConstraint('uuid')
    )
    
    # Create indexes for batches table
    op.create_index(op.f('ix_batches_gym_id'), 'batches', ['gym_id'], unique=False)
    op.create_index(op.f('ix_batches_name'), 'batches', ['name'], unique=False)
    op.create_index(op.f('ix_batches_uuid'), 'batches', ['uuid'], unique=False)
    
    # Add batch_id column to executions table
    op.add_column('executions', sa.Column('batch_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f('ix_executions_batch_id'), 'executions', ['batch_id'], unique=False)
    op.create_foreign_key('executions_batch_id_fkey', 'executions', 'batches', ['batch_id'], ['uuid'])


def downgrade() -> None:
    """Downgrade schema."""
    # Remove batch_id from executions table
    op.drop_constraint('executions_batch_id_fkey', 'executions', type_='foreignkey')
    op.drop_index(op.f('ix_executions_batch_id'), table_name='executions')
    op.drop_column('executions', 'batch_id')
    
    # Drop batches table
    op.drop_index(op.f('ix_batches_uuid'), table_name='batches')
    op.drop_index(op.f('ix_batches_name'), table_name='batches')
    op.drop_index(op.f('ix_batches_gym_id'), table_name='batches')
    op.drop_table('batches')
