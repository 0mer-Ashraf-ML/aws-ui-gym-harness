"""add verification_comments to iterations

Revision ID: 005
Revises: 004
Create Date: 2023-10-16 17:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    """Add verification_comments column to iterations table"""
    # Add verification_comments column to iterations table
    op.add_column('iterations', sa.Column('verification_comments', sa.Text(), nullable=True))


def downgrade():
    """Remove verification_comments column from iterations table"""
    # Remove verification_comments column from iterations table
    op.drop_column('iterations', 'verification_comments')
