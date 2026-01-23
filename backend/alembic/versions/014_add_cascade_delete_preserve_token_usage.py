"""Add CASCADE delete to batch relations while preserving token_usage history

Revision ID: 014
Revises: 013
Create Date: 2025-11-10 10:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add CASCADE to executions.batch_id foreign key
    op.drop_constraint('executions_batch_id_fkey', 'executions', type_='foreignkey')
    op.create_foreign_key(
        'executions_batch_id_fkey',
        'executions', 'batches',
        ['batch_id'], ['uuid'],
        ondelete='CASCADE'
    )
    
    # 2. Add CASCADE to iterations.execution_id foreign key
    op.drop_constraint('iterations_execution_id_fkey', 'iterations', type_='foreignkey')
    op.create_foreign_key(
        'iterations_execution_id_fkey',
        'iterations', 'executions',
        ['execution_id'], ['uuid'],
        ondelete='CASCADE'
    )
    
    # 3. Remove foreign key constraints from token_usage to preserve historical data
    # Drop FK constraints so deletion of batches/executions/iterations doesn't cascade to token_usage
    op.drop_constraint('token_usage_iteration_id_fkey', 'token_usage', type_='foreignkey')
    op.drop_constraint('token_usage_execution_id_fkey', 'token_usage', type_='foreignkey')
    
    # Make columns nullable so they can survive parent deletion
    op.alter_column('token_usage', 'iteration_id',
                    existing_type=postgresql.UUID(),
                    nullable=True)
    op.alter_column('token_usage', 'execution_id',
                    existing_type=postgresql.UUID(),
                    nullable=True)
    
    # 4. Add batch_id and snapshot fields to preserve batch context
    # Note: batch_id has NO foreign key constraint so batch deletion doesn't fail
    # and we preserve the batch_id value for historical queries
    op.add_column('token_usage', sa.Column('batch_id', postgresql.UUID(), nullable=True))
    op.add_column('token_usage', sa.Column('batch_name', sa.String(255), nullable=True))
    op.add_column('token_usage', sa.Column('task_identifier', sa.String(255), nullable=True))
    op.add_column('token_usage', sa.Column('iteration_number', sa.Integer(), nullable=True))
    
    # Add indexes for better query performance (no foreign key constraint)
    op.create_index('ix_token_usage_batch_id', 'token_usage', ['batch_id'])
    op.create_index('ix_token_usage_task_identifier', 'token_usage', ['task_identifier'])


def downgrade():
    # Remove indexes
    op.drop_index('ix_token_usage_task_identifier', 'token_usage')
    op.drop_index('ix_token_usage_batch_id', 'token_usage')
    
    # Remove snapshot columns (no foreign key to drop)
    op.drop_column('token_usage', 'iteration_number')
    op.drop_column('token_usage', 'task_identifier')
    op.drop_column('token_usage', 'batch_name')
    op.drop_column('token_usage', 'batch_id')
    
    # Revert token_usage columns to NOT NULL (might fail if NULL values exist)
    op.alter_column('token_usage', 'execution_id',
                    existing_type=postgresql.UUID(),
                    nullable=False)
    op.alter_column('token_usage', 'iteration_id',
                    existing_type=postgresql.UUID(),
                    nullable=False)
    
    # Recreate foreign key constraints
    op.create_foreign_key(
        'token_usage_execution_id_fkey',
        'token_usage', 'executions',
        ['execution_id'], ['uuid']
    )
    op.create_foreign_key(
        'token_usage_iteration_id_fkey',
        'token_usage', 'iterations',
        ['iteration_id'], ['uuid']
    )
    
    # Remove CASCADE from iterations.execution_id
    op.drop_constraint('iterations_execution_id_fkey', 'iterations', type_='foreignkey')
    op.create_foreign_key(
        'iterations_execution_id_fkey',
        'iterations', 'executions',
        ['execution_id'], ['uuid']
    )
    
    # Remove CASCADE from executions.batch_id
    op.drop_constraint('executions_batch_id_fkey', 'executions', type_='foreignkey')
    op.create_foreign_key(
        'executions_batch_id_fkey',
        'executions', 'batches',
        ['batch_id'], ['uuid']
    )

