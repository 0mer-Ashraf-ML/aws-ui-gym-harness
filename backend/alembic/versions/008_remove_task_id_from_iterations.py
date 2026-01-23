"""Remove task_id from iterations

Revision ID: 008
Revises: 007
Create Date: 2025-10-23 13:31:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    """
    Remove task_id FK from iterations table.
    
    Iterations will now get task information from their parent execution's
    snapshot fields (task_identifier and prompt).
    """
    # Drop the foreign key constraint
    op.drop_constraint('iterations_task_id_fkey', 'iterations', type_='foreignkey')
    
    # Drop the task_id column
    op.drop_column('iterations', 'task_id')


def downgrade():
    """
    Restore task_id FK to iterations table.
    
    WARNING: This downgrade will fail if there are iterations whose
    executions reference tasks that no longer exist.
    """
    # Add back the task_id column (nullable initially)
    op.add_column('iterations', 
        sa.Column('task_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    
    # Try to backfill task_id from execution's task_identifier
    # This is best-effort and may fail for orphaned data
    op.execute("""
        UPDATE iterations i
        SET task_id = t.uuid
        FROM executions e
        JOIN tasks t ON t.task_id = e.task_identifier
        WHERE i.execution_id = e.uuid
    """)
    
    # Make task_id NOT NULL
    op.alter_column('iterations', 'task_id', nullable=False)
    
    # Recreate the foreign key constraint
    op.create_foreign_key(
        'iterations_task_id_fkey',
        'iterations', 'tasks',
        ['task_id'], ['uuid']
    )
    
    # Recreate the index
    op.create_index('ix_iterations_task_id', 'iterations', ['task_id'])
