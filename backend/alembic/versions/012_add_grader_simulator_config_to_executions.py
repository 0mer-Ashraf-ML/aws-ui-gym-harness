"""Add grader_config and simulator_config snapshot columns to executions

Revision ID: 012
Revises: 011
Create Date: 2025-11-03 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add grader_config and simulator_config as snapshot fields to executions.
    This completes the decoupling pattern from migration 007, ensuring executions
    can access verification configs even if tasks are deleted.
    """
    
    # Step 1: Add new snapshot columns to executions table
    op.add_column(
        'executions',
        sa.Column('grader_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        'executions',
        sa.Column('simulator_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    
    # Step 2: Create GIN indexes on JSONB columns for query performance
    op.create_index(
        'ix_executions_grader_config',
        'executions',
        ['grader_config'],
        unique=False,
        postgresql_using='gin',
    )
    op.create_index(
        'ix_executions_simulator_config',
        'executions',
        ['simulator_config'],
        unique=False,
        postgresql_using='gin',
    )
    
    # Step 3: Backfill snapshot fields from tasks table using task_identifier
    # This backfills only where tasks still exist (safe migration)
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE executions
        SET 
            grader_config = tasks.grader_config,
            simulator_config = tasks.simulator_config
        FROM tasks
        WHERE executions.task_identifier = tasks.task_id
          AND executions.gym_id = tasks.gym_id
    """))
    
    # Note: Executions where task no longer exists will have NULL values
    # This preserves existing behavior and allows fallback to file configs


def downgrade():
    """
    Remove grader_config and simulator_config snapshot columns from executions.
    
    WARNING: This downgrade will lose snapshot data if tasks have been deleted.
    """
    
    # Step 1: Drop indexes
    op.drop_index('ix_executions_simulator_config', table_name='executions')
    op.drop_index('ix_executions_grader_config', table_name='executions')
    
    # Step 2: Drop columns
    op.drop_column('executions', 'simulator_config')
    op.drop_column('executions', 'grader_config')

