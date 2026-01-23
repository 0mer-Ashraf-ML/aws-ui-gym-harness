"""Add eval_insights fields to iterations, executions, and batches

Revision ID: 009
Revises: 008
Create Date: 2025-10-24 20:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add eval_insights fields to iterations, executions, and batches tables.
    
    - iterations.eval_insights: Text field to store insight summary
    - executions.eval_insights: Text field to store execution-level insights
    - batches.eval_insights: JSON field to store batch-level insights
    """
    # Add eval_insights to iterations table
    op.add_column('iterations', 
        sa.Column('eval_insights', sa.Text(), nullable=True)
    )
    
    # Add eval_insights to executions table
    op.add_column('executions', 
        sa.Column('eval_insights', sa.Text(), nullable=True)
    )
    
    # Add eval_insights to batches table (JSON field)
    op.add_column('batches', 
        sa.Column('eval_insights', postgresql.JSON(astext_type=sa.Text()), nullable=True)
    )


def downgrade():
    """
    Remove eval_insights fields from iterations, executions, and batches tables.
    """
    # Remove eval_insights from batches table
    op.drop_column('batches', 'eval_insights')
    
    # Remove eval_insights from executions table
    op.drop_column('executions', 'eval_insights')
    
    # Remove eval_insights from iterations table
    op.drop_column('iterations', 'eval_insights')
