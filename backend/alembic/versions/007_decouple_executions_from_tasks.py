"""decouple executions from tasks - add snapshot fields and remove FK

Revision ID: 007
Revises: 006
Create Date: 2025-10-23 10:52:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    """
    Decouple executions from tasks by:
    1. Adding task_identifier and prompt snapshot fields to executions
    2. Backfilling these fields from the tasks table using existing task_id FK
    3. Dropping the task_id FK column entirely
    """
    
    # Step 1: Add new snapshot columns to executions table
    op.add_column('executions', sa.Column('task_identifier', sa.String(length=255), nullable=True))
    op.add_column('executions', sa.Column('prompt', sa.Text(), nullable=True))
    
    # Step 2: Create indexes on new columns for performance
    op.create_index(op.f('ix_executions_task_identifier'), 'executions', ['task_identifier'], unique=False)
    
    # Step 3: Backfill snapshot fields from tasks table using existing task_id FK
    # This uses raw SQL to perform the data migration
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE executions
        SET 
            task_identifier = tasks.task_id,
            prompt = tasks.prompt
        FROM tasks
        WHERE executions.task_id = tasks.uuid
    """))
    
    # Step 4: Drop the FK constraint on task_id
    # Note: PostgreSQL automatically names the constraint, we need to find and drop it
    # The constraint name is typically 'executions_task_id_fkey'
    op.drop_constraint('executions_task_id_fkey', 'executions', type_='foreignkey')
    
    # Step 5: Drop the task_id column entirely
    op.drop_index(op.f('ix_executions_task_id'), table_name='executions')
    op.drop_column('executions', 'task_id')


def downgrade():
    """
    Reverse the decoupling by:
    1. Re-adding task_id column
    2. Re-creating the FK constraint
    3. Dropping the snapshot fields
    
    WARNING: This downgrade will lose data if tasks have been deleted after this migration.
    """
    
    # Step 1: Re-add task_id column
    op.add_column('executions', sa.Column('task_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_executions_task_id'), 'executions', ['task_id'], unique=False)
    
    # Step 2: Try to restore task_id from task_identifier
    # This will only work if tasks still exist with matching task_ids
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE executions
        SET task_id = tasks.uuid
        FROM tasks
        WHERE executions.task_identifier = tasks.task_id
    """))
    
    # Step 3: Re-create FK constraint
    op.create_foreign_key('executions_task_id_fkey', 'executions', 'tasks', ['task_id'], ['uuid'])
    
    # Step 4: Drop the snapshot columns
    op.drop_index(op.f('ix_executions_task_identifier'), table_name='executions')
    op.drop_column('executions', 'prompt')
    op.drop_column('executions', 'task_identifier')
