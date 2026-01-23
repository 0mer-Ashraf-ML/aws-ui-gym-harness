"""Add grader_config and simulator_config columns to tasks and GRADER_CONFIG enum value

Revision ID: 011
Revises: 010
Create Date: 2025-10-31 10:45:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade():
    """Add JSONB configuration columns and supporting indexes to tasks, and add GRADER_CONFIG enum value."""
    # Add grader_config and simulator_config columns to tasks table
    op.add_column(
        'tasks',
        sa.Column('grader_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'tasks',
        sa.Column('simulator_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Create GIN indexes for JSONB columns
    op.create_index(
        'ix_tasks_grader_config',
        'tasks',
        ['grader_config'],
        unique=False,
        postgresql_using='gin',
    )
    op.create_index(
        'ix_tasks_simulator_config',
        'tasks',
        ['simulator_config'],
        unique=False,
        postgresql_using='gin',
    )

    # Add 'GRADER_CONFIG' enum value to verificationstrategy enum type
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type t
                JOIN pg_enum e ON t.oid = e.enumtypid
                WHERE t.typname = 'verificationstrategy'
                AND e.enumlabel = 'GRADER_CONFIG'
            ) THEN
                ALTER TYPE verificationstrategy ADD VALUE 'GRADER_CONFIG';
            END IF;
        END$$;
        """
    )


def downgrade():
    """Remove configuration columns and indexes from tasks.
    
    Note: The 'GRADER_CONFIG' enum value is not removed from verificationstrategy
    as PostgreSQL enums do not support removing values easily.
    """
    op.drop_index('ix_tasks_simulator_config', table_name='tasks')
    op.drop_index('ix_tasks_grader_config', table_name='tasks')

    op.drop_column('tasks', 'simulator_config')
    op.drop_column('tasks', 'grader_config')
