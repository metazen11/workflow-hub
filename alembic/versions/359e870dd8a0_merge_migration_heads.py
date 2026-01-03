"""merge_migration_heads

Revision ID: 359e870dd8a0
Revises: 3a1b2c4d5e6f, d71bab89c85d
Create Date: 2026-01-02 18:14:09.364119

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '359e870dd8a0'
down_revision: Union[str, Sequence[str], None] = ('3a1b2c4d5e6f', 'd71bab89c85d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
