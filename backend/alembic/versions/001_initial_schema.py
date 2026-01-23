"""Initial schema with all models

Revision ID: 001
Revises: 
Create Date: 2025-09-22 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create users table
    op.create_table('users',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('google_id', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('picture', sa.String(length=500), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=False),
        sa.Column('is_whitelisted', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('uuid')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_google_id'), 'users', ['google_id'], unique=True)
    op.create_index(op.f('ix_users_uuid'), 'users', ['uuid'], unique=False)
    
    # Create refresh_tokens table
    op.create_table('refresh_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_revoked', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.uuid'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash')
    )
    
    # Create gyms table
    op.create_table('gyms',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('base_url', sa.Text(), nullable=False),
        sa.Column('verification_url', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('uuid')
    )
    op.create_index(op.f('ix_gyms_name'), 'gyms', ['name'], unique=False)
    op.create_index(op.f('ix_gyms_uuid'), 'gyms', ['uuid'], unique=False)
    
    # Create tasks table
    op.create_table('tasks',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('task_id', sa.String(length=255), nullable=False),
        sa.Column('gym_id', sa.UUID(), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['gym_id'], ['gyms.uuid'], ),
        sa.PrimaryKeyConstraint('uuid'),
        sa.UniqueConstraint('task_id', 'gym_id', name='unique_task_id_per_gym')
    )
    op.create_index(op.f('ix_tasks_gym_id'), 'tasks', ['gym_id'], unique=False)
    op.create_index(op.f('ix_tasks_task_id'), 'tasks', ['task_id'], unique=False)
    op.create_index(op.f('ix_tasks_uuid'), 'tasks', ['uuid'], unique=False)
    
    # Create executions table (without status column)
    op.create_table('executions',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('execution_folder_name', sa.String(length=255), nullable=True),
        sa.Column('task_id', sa.UUID(), nullable=True),
        sa.Column('gym_id', sa.UUID(), nullable=False),
        sa.Column('number_of_iterations', sa.Integer(), nullable=False),
        sa.Column('model', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['gym_id'], ['gyms.uuid'], ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.uuid'], ),
        sa.PrimaryKeyConstraint('uuid')
    )
    op.create_index(op.f('ix_executions_execution_folder_name'), 'executions', ['execution_folder_name'], unique=False)
    op.create_index(op.f('ix_executions_gym_id'), 'executions', ['gym_id'], unique=False)
    op.create_index(op.f('ix_executions_model'), 'executions', ['model'], unique=False)
    op.create_index(op.f('ix_executions_task_id'), 'executions', ['task_id'], unique=False)
    op.create_index(op.f('ix_executions_uuid'), 'executions', ['uuid'], unique=False)
    
    # Create iterations table
    op.create_table('iterations',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('execution_id', sa.UUID(), nullable=False),
        sa.Column('task_id', sa.UUID(), nullable=False),
        sa.Column('iteration_number', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('celery_task_id', sa.String(length=255), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('execution_time_seconds', sa.Integer(), nullable=True),
        sa.Column('result_data', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('logs', sa.Text(), nullable=True),
        sa.Column('verification_details', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['execution_id'], ['executions.uuid'], ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.uuid'], ),
        sa.PrimaryKeyConstraint('uuid')
    )
    op.create_index(op.f('ix_iterations_celery_task_id'), 'iterations', ['celery_task_id'], unique=False)
    op.create_index(op.f('ix_iterations_execution_id'), 'iterations', ['execution_id'], unique=False)
    op.create_index(op.f('ix_iterations_iteration_number'), 'iterations', ['iteration_number'], unique=False)
    op.create_index(op.f('ix_iterations_status'), 'iterations', ['status'], unique=False)
    op.create_index(op.f('ix_iterations_task_id'), 'iterations', ['task_id'], unique=False)
    op.create_index(op.f('ix_iterations_uuid'), 'iterations', ['uuid'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop iterations table
    op.drop_index(op.f('ix_iterations_uuid'), table_name='iterations')
    op.drop_index(op.f('ix_iterations_task_id'), table_name='iterations')
    op.drop_index(op.f('ix_iterations_status'), table_name='iterations')
    op.drop_index(op.f('ix_iterations_iteration_number'), table_name='iterations')
    op.drop_index(op.f('ix_iterations_execution_id'), table_name='iterations')
    op.drop_index(op.f('ix_iterations_celery_task_id'), table_name='iterations')
    op.drop_table('iterations')
    
    # Drop executions table
    op.drop_index(op.f('ix_executions_uuid'), table_name='executions')
    op.drop_index(op.f('ix_executions_task_id'), table_name='executions')
    op.drop_index(op.f('ix_executions_model'), table_name='executions')
    op.drop_index(op.f('ix_executions_gym_id'), table_name='executions')
    op.drop_index(op.f('ix_executions_execution_folder_name'), table_name='executions')
    op.drop_table('executions')
    
    # Drop tasks table
    op.drop_index(op.f('ix_tasks_uuid'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_task_id'), table_name='tasks')
    op.drop_index(op.f('ix_tasks_gym_id'), table_name='tasks')
    op.drop_table('tasks')
    
    # Drop gyms table
    op.drop_index(op.f('ix_gyms_uuid'), table_name='gyms')
    op.drop_index(op.f('ix_gyms_name'), table_name='gyms')
    op.drop_table('gyms')
    
    # Drop refresh_tokens table
    op.drop_table('refresh_tokens')
    
    # Drop users table
    op.drop_index(op.f('ix_users_uuid'), table_name='users')
    op.drop_index(op.f('ix_users_google_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
