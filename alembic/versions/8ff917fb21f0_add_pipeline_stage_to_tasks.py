"""add pipeline_stage to tasks

Revision ID: 8ff917fb21f0
Revises: 9eb5bd5ef076
Create Date: 2025-12-26 15:32:54.979732

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8ff917fb21f0'
down_revision: Union[str, Sequence[str], None] = '9eb5bd5ef076'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the enum type first
    taskpipelinestage = postgresql.ENUM(
        'NONE', 'DEV', 'QA', 'SEC', 'DOCS', 'COMPLETE',
        name='taskpipelinestage',
        create_type=True
    )
    taskpipelinestage.create(op.get_bind(), checkfirst=True)

    # Then add the column
    op.add_column('tasks', sa.Column('pipeline_stage', taskpipelinestage, nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tasks', 'pipeline_stage')
    # Drop the enum type
    postgresql.ENUM(name='taskpipelinestage').drop(op.get_bind(), checkfirst=True)
