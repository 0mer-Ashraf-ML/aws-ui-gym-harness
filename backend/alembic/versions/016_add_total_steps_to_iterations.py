"""Add total_steps to iterations

Revision ID: 016
Revises: 015
Create Date: 2025-11-12 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('iterations', sa.Column('total_steps', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('iterations', 'total_steps')


