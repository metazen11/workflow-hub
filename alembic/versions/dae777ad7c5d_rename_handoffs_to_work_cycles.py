"""rename_handoffs_to_work_cycles

Revision ID: dae777ad7c5d
Revises: b14f00c54974
Create Date: 2026-01-01 13:02:11.293587

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'dae777ad7c5d'
down_revision: Union[str, Sequence[str], None] = 'b14f00c54974'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename handoffs table to work_cycles.

    The database has two tables:
    - handoffs: correct schema matching the WorkCycle model
    - work_cycles: incorrect schema from an older migration

    This migration:
    1. Drops the incorrect work_cycles table
    2. Renames handoffs to work_cycles
    3. Updates enum type and indexes
    """
    # Step 1: Drop the incorrect work_cycles table
    op.drop_index('ix_work_cycles_project_id', table_name='work_cycles', if_exists=True)
    op.drop_index('ix_work_cycles_status', table_name='work_cycles', if_exists=True)
    op.drop_index('ix_work_cycles_task_id', table_name='work_cycles', if_exists=True)
    op.drop_table('work_cycles')

    # Step 2: Rename handoffs table to work_cycles
    op.rename_table('handoffs', 'work_cycles')

    # Step 3: Rename indexes
    # Drop old indexes with handoffs_ prefix
    op.drop_index('ix_handoffs_project_id', table_name='work_cycles', if_exists=True)
    op.drop_index('ix_handoffs_run_id', table_name='work_cycles', if_exists=True)
    op.drop_index('ix_handoffs_stage', table_name='work_cycles', if_exists=True)
    op.drop_index('ix_handoffs_status', table_name='work_cycles', if_exists=True)
    op.drop_index('ix_handoffs_task_id', table_name='work_cycles', if_exists=True)

    # Create new indexes with work_cycles_ prefix
    op.create_index('ix_work_cycles_project_id', 'work_cycles', ['project_id'])
    op.create_index('ix_work_cycles_run_id', 'work_cycles', ['run_id'])
    op.create_index('ix_work_cycles_stage', 'work_cycles', ['stage'])
    op.create_index('ix_work_cycles_status', 'work_cycles', ['status'])
    op.create_index('ix_work_cycles_task_id', 'work_cycles', ['task_id'])

    # Step 4: Alter column to use new enum type
    # The workcyclestatus enum already exists, just need to cast the column
    op.execute("ALTER TABLE work_cycles ALTER COLUMN status TYPE workcyclestatus USING status::text::workcyclestatus")


def downgrade() -> None:
    """Restore handoffs table from work_cycles."""
    # Revert status column to handoffstatus
    op.execute("ALTER TABLE work_cycles ALTER COLUMN status TYPE handoffstatus USING status::text::handoffstatus")

    # Drop new indexes
    op.drop_index('ix_work_cycles_project_id', table_name='work_cycles', if_exists=True)
    op.drop_index('ix_work_cycles_run_id', table_name='work_cycles', if_exists=True)
    op.drop_index('ix_work_cycles_stage', table_name='work_cycles', if_exists=True)
    op.drop_index('ix_work_cycles_status', table_name='work_cycles', if_exists=True)
    op.drop_index('ix_work_cycles_task_id', table_name='work_cycles', if_exists=True)

    # Rename table back
    op.rename_table('work_cycles', 'handoffs')

    # Recreate old indexes
    op.create_index('ix_handoffs_project_id', 'handoffs', ['project_id'])
    op.create_index('ix_handoffs_run_id', 'handoffs', ['run_id'])
    op.create_index('ix_handoffs_stage', 'handoffs', ['stage'])
    op.create_index('ix_handoffs_status', 'handoffs', ['status'])
    op.create_index('ix_handoffs_task_id', 'handoffs', ['task_id'])
