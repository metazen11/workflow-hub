"""add_director_docs_cicd_to_agent_role_enum

Revision ID: a7cf3d36ca19
Revises: 8ff917fb21f0
Create Date: 2025-12-26 16:54:46.042439

Adds DIRECTOR, DOCS, and CICD values to the agentrole PostgreSQL enum type.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7cf3d36ca19'
down_revision: Union[str, Sequence[str], None] = '8ff917fb21f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add new values to agentrole enum.

    PostgreSQL enums require ALTER TYPE to add new values.
    Existing values are uppercase: PM, DEV, QA, SECURITY
    Adding lowercase to match Python enum values: director, docs, cicd
    """
    conn = op.get_bind()

    # Add new enum values (lowercase to match Python enum values)
    # Using IF NOT EXISTS to be idempotent
    conn.execute(sa.text("ALTER TYPE agentrole ADD VALUE IF NOT EXISTS 'director'"))
    conn.execute(sa.text("ALTER TYPE agentrole ADD VALUE IF NOT EXISTS 'docs'"))
    conn.execute(sa.text("ALTER TYPE agentrole ADD VALUE IF NOT EXISTS 'cicd'"))


def downgrade() -> None:
    """Downgrade - PostgreSQL doesn't support removing enum values easily.

    To truly remove enum values, you would need to:
    1. Create a new enum type without those values
    2. Update the column to use the new type
    3. Drop the old enum type
    4. Rename the new type

    For simplicity, we just note that the values will remain but be unused.
    """
    # PostgreSQL doesn't support ALTER TYPE ... DROP VALUE
    # Values will remain in enum but be unused
    pass
