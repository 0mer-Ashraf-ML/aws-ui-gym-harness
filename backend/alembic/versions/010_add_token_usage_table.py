"""Add token_usage table for monitoring API usage

Revision ID: 010
Revises: 009
Create Date: 2025-11-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade():
    """
    Create token_usage table for tracking API token consumption.
    
    This table tracks token usage per iteration for monitoring and cost analysis.
    """
    op.create_table(
        'token_usage',
        sa.Column('uuid', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('iteration_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('execution_id', postgresql.UUID(as_uuid=True), nullable=False),
        
        # Model information
        sa.Column('model_name', sa.String(length=100), nullable=False),
        sa.Column('model_version', sa.String(length=100), nullable=True),
        
        # Token counts
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        
        # Additional usage metrics
        sa.Column('api_calls_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('cached_tokens', sa.Integer(), nullable=True, server_default='0'),
        
        # Cost estimation
        sa.Column('estimated_cost_usd', sa.Float(), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        # Foreign keys
        sa.ForeignKeyConstraint(['iteration_id'], ['iterations.uuid'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['execution_id'], ['executions.uuid'], ondelete='CASCADE'),
    )
    
    # Create indexes for efficient queries
    op.create_index('ix_token_usage_uuid', 'token_usage', ['uuid'])
    op.create_index('ix_token_usage_iteration_id', 'token_usage', ['iteration_id'])
    op.create_index('ix_token_usage_execution_id', 'token_usage', ['execution_id'])
    op.create_index('ix_token_usage_model_name', 'token_usage', ['model_name'])
    op.create_index('ix_token_usage_created_at', 'token_usage', ['created_at'])


def downgrade():
    """
    Drop token_usage table and related indexes.
    """
    op.drop_index('ix_token_usage_created_at', table_name='token_usage')
    op.drop_index('ix_token_usage_model_name', table_name='token_usage')
    op.drop_index('ix_token_usage_execution_id', table_name='token_usage')
    op.drop_index('ix_token_usage_iteration_id', table_name='token_usage')
    op.drop_index('ix_token_usage_uuid', table_name='token_usage')
    op.drop_table('token_usage')

