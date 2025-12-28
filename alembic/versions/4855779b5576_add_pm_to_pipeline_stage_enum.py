"""add_pm_to_pipeline_stage_enum

Revision ID: 4855779b5576
Revises: be92842b6bc3
Create Date: 2025-12-28 06:45:49.803163

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4855779b5576'
down_revision: Union[str, Sequence[str], None] = 'be92842b6bc3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'PM' value to taskpipelinestage enum."""
    # PostgreSQL requires ALTER TYPE to add enum values
    # DB uses uppercase: NONE, DEV, QA, SEC, DOCS, COMPLETE
    # Add 'PM' after 'NONE' in the enum order
    op.execute("ALTER TYPE taskpipelinestage ADD VALUE IF NOT EXISTS 'PM' AFTER 'NONE'")


def downgrade() -> None:
    """Remove 'pm' from enum - PostgreSQL doesn't support removing enum values easily.

    To properly downgrade, you would need to:
    1. Create new enum without 'pm'
    2. Update all rows using 'pm' to another value
    3. Alter column to use new enum
    4. Drop old enum

    For simplicity, we just warn - manual intervention needed.
    """
    # PostgreSQL doesn't support DROP VALUE from enum
    # Would need to recreate the entire enum type
    print("WARNING: Cannot remove 'pm' from enum. Manual intervention required if downgrading.")
