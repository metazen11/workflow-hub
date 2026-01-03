"""add_daemon_started_at_to_director_settings

Revision ID: 157bbc9f206d
Revises: 4bbcb22d76ad
Create Date: 2026-01-02 03:47:01.311589

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '157bbc9f206d'
down_revision: Union[str, Sequence[str], None] = '4bbcb22d76ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('director_settings', sa.Column('daemon_started_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('director_settings', 'daemon_started_at')
