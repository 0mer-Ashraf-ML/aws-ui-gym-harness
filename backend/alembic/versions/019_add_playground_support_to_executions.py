"""Add playground support to executions

Revision ID: 019
Revises: 018
Create Date: 2025-01-XX XX:XX:XX.XXXXXX
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '019'
down_revision: Union[str, Sequence[str], None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add execution_type enum and playground_url column to executions table."""
    # Check if enum already exists, if so drop it first (handles case where it was created with wrong values)
    op.execute("""
        DO $$ 
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'executiontype') THEN
                -- Drop the column first if it exists
                IF EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'executions' AND column_name = 'execution_type') THEN
                    ALTER TABLE executions DROP COLUMN IF EXISTS execution_type;
                END IF;
                DROP TYPE executiontype CASCADE;
            END IF;
        END $$;
    """)
    
    # Create the enum type with lowercase values (matching ExecutionType enum values)
    op.execute("CREATE TYPE executiontype AS ENUM ('batch', 'playground')")
    
    # Add execution_type column with default 'batch' (only if it doesn't exist)
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'executions' AND column_name = 'execution_type') THEN
                ALTER TABLE executions ADD COLUMN execution_type executiontype NOT NULL DEFAULT 'batch';
            END IF;
        END $$;
    """)
    
    # Add playground_url column (only if it doesn't exist)
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name = 'executions' AND column_name = 'playground_url') THEN
                ALTER TABLE executions ADD COLUMN playground_url TEXT;
            END IF;
        END $$;
    """)
    
    # Make gym_id nullable (for playground executions)
    op.alter_column('executions', 'gym_id',
                    existing_type=postgresql.UUID(as_uuid=True),
                    nullable=True)
    
    # Create index on execution_type (only if it doesn't exist)
    op.execute("""
        DO $$ 
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_indexes 
                          WHERE tablename = 'executions' AND indexname = 'ix_executions_execution_type') THEN
                CREATE INDEX ix_executions_execution_type ON executions(execution_type);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Remove playground support from executions table."""
    # Drop index
    op.drop_index(op.f('ix_executions_execution_type'), table_name='executions')
    
    # Delete rows with NULL gym_id (playground executions) before making column NOT NULL
    op.execute("DELETE FROM executions WHERE gym_id IS NULL")
    
    # Make gym_id not nullable again
    op.alter_column('executions', 'gym_id',
                    existing_type=postgresql.UUID(as_uuid=True),
                    nullable=False)
    
    # Drop columns
    op.drop_column('executions', 'playground_url')
    op.drop_column('executions', 'execution_type')
    
    # Drop the enum type
    execution_type_enum = sa.Enum(name='executiontype')
    execution_type_enum.drop(op.get_bind(), checkfirst=True)

