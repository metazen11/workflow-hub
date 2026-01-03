"""add_director_settings_table

Revision ID: ac0bc5805600
Revises: 8b92d4730395
Create Date: 2026-01-02 03:25:34.698120

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac0bc5805600'
down_revision: Union[str, Sequence[str], None] = '8b92d4730395'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('director_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('poll_interval', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('enforce_tdd', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('enforce_dry', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('enforce_security', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('include_images', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('vision_model', sa.String(length=100), nullable=False, server_default='ai/qwen3-vl'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    # Insert default settings row (singleton pattern)
    op.execute("INSERT INTO director_settings (id) VALUES (1)")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('director_settings')
