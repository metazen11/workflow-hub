"""Add FAILED to taskstatus enum

Revision ID: 712ce3dc7546
Revises: f2d867db5146
Create Date: 2025-12-24 13:13:30.343328

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '712ce3dc7546'
down_revision: Union[str, Sequence[str], None] = 'f2d867db5146'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add FAILED value to taskstatus enum."""
    # PostgreSQL requires ALTER TYPE to add enum values
    op.execute("ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'FAILED'")


def downgrade() -> None:
    """Remove FAILED from taskstatus enum.

    Note: PostgreSQL doesn't support removing enum values directly.
    Would need to recreate the type and update all columns.
    """
    pass  # Cannot easily remove enum values in PostgreSQL
