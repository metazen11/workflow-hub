"""add_docs_testing_states_to_runstate_enum

Revision ID: 018315fe66d3
Revises: e40804b5ea76
Create Date: 2025-12-26 02:59:05.787687

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '018315fe66d3'
down_revision: Union[str, Sequence[str], None] = 'e40804b5ea76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add DOCS, DOCS_FAILED, TESTING, TESTING_FAILED to runstate enum."""
    # PostgreSQL requires ALTER TYPE for adding values to enum
    # Note: ADD VALUE IF NOT EXISTS handles idempotency

    # Add DOCS after SEC_FAILED
    op.execute("ALTER TYPE runstate ADD VALUE IF NOT EXISTS 'DOCS' AFTER 'SEC_FAILED'")
    op.execute("ALTER TYPE runstate ADD VALUE IF NOT EXISTS 'DOCS_FAILED' AFTER 'DOCS'")

    # Add TESTING after READY_FOR_DEPLOY
    op.execute("ALTER TYPE runstate ADD VALUE IF NOT EXISTS 'TESTING' AFTER 'READY_FOR_DEPLOY'")
    op.execute("ALTER TYPE runstate ADD VALUE IF NOT EXISTS 'TESTING_FAILED' AFTER 'TESTING'")

    # docs_result and testing_result columns may already exist in runs table
    # Adding them conditionally using raw SQL
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='runs' AND column_name='docs_result'"
    ))
    if result.fetchone() is None:
        op.add_column('runs', sa.Column('docs_result', sa.JSON(), nullable=True))

    result = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='runs' AND column_name='testing_result'"
    ))
    if result.fetchone() is None:
        op.add_column('runs', sa.Column('testing_result', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove added columns (cannot remove enum values in PostgreSQL)."""
    # Note: PostgreSQL does not support removing enum values
    # To fully downgrade, you would need to recreate the enum type
    pass
