"""Add domains table for domain whitelisting

Revision ID: 002
Revises: 001
Create Date: 2025-01-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, Sequence[str], None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create domains table
    op.create_table('domains',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('domain', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('uuid')
    )
    op.create_index(op.f('ix_domains_domain'), 'domains', ['domain'], unique=True)
    op.create_index(op.f('ix_domains_uuid'), 'domains', ['uuid'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop domains table
    op.drop_index(op.f('ix_domains_uuid'), table_name='domains')
    op.drop_index(op.f('ix_domains_domain'), table_name='domains')
    op.drop_table('domains')
