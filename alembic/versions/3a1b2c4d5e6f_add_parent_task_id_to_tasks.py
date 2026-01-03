"""Add parent_task_id to tasks

Revision ID: 3a1b2c4d5e6f
Revises: dae777ad7c5d
Create Date: 2026-01-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3a1b2c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "dae777ad7c5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add parent_task_id column and FK for subtasks."""
    op.add_column("tasks", sa.Column("parent_task_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tasks_parent_task_id",
        "tasks",
        "tasks",
        ["parent_task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tasks_parent_task_id", "tasks", ["parent_task_id"])


def downgrade() -> None:
    """Remove parent_task_id column and FK."""
    op.drop_index("ix_tasks_parent_task_id", table_name="tasks")
    op.drop_constraint("fk_tasks_parent_task_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "parent_task_id")
