"""expand title/name columns to 500 chars

Revision ID: 8cbd6c502304
Revises: 4c6b0046890e
Create Date: 2025-12-31 09:47:51.364133

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8cbd6c502304'
down_revision: Union[str, Sequence[str], None] = '4c6b0046890e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Expand title/name columns to 500 chars for longer task descriptions."""
    op.alter_column('runs', 'name',
                    existing_type=sa.String(100),
                    type_=sa.String(500),
                    existing_nullable=False)
    op.alter_column('tasks', 'title',
                    existing_type=sa.String(255),
                    type_=sa.String(500),
                    existing_nullable=False)
    op.alter_column('requirements', 'title',
                    existing_type=sa.String(255),
                    type_=sa.String(500),
                    existing_nullable=False)
    op.alter_column('bug_reports', 'title',
                    existing_type=sa.String(255),
                    type_=sa.String(500),
                    existing_nullable=False)


def downgrade() -> None:
    """Revert to original column sizes."""
    op.alter_column('runs', 'name',
                    existing_type=sa.String(500),
                    type_=sa.String(100),
                    existing_nullable=False)
    op.alter_column('tasks', 'title',
                    existing_type=sa.String(500),
                    type_=sa.String(255),
                    existing_nullable=False)
    op.alter_column('requirements', 'title',
                    existing_type=sa.String(500),
                    type_=sa.String(255),
                    existing_nullable=False)
    op.alter_column('bug_reports', 'title',
                    existing_type=sa.String(500),
                    type_=sa.String(255),
                    existing_nullable=False)
