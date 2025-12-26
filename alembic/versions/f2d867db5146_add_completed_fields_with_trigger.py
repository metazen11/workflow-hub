"""Add completed fields with trigger

Revision ID: f2d867db5146
Revises: 5481f073f90f
Create Date: 2025-12-24 13:11:37.394321

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2d867db5146'
down_revision: Union[str, Sequence[str], None] = '5481f073f90f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add completed and completed_at columns with auto-timestamp trigger."""
    # Add columns
    op.add_column('tasks', sa.Column('completed', sa.Boolean(), nullable=True, default=False))
    op.add_column('tasks', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))

    # Set default for existing rows
    op.execute("UPDATE tasks SET completed = false WHERE completed IS NULL")

    # Make completed not nullable after setting defaults
    op.alter_column('tasks', 'completed', nullable=False, server_default='false')

    # Create trigger function to auto-set completed_at when completed becomes true
    op.execute("""
        CREATE OR REPLACE FUNCTION set_completed_at()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.completed = true AND (OLD.completed = false OR OLD.completed IS NULL) THEN
                NEW.completed_at = NOW();
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger on tasks table
    op.execute("""
        DROP TRIGGER IF EXISTS trigger_set_completed_at ON tasks;
        CREATE TRIGGER trigger_set_completed_at
            BEFORE UPDATE ON tasks
            FOR EACH ROW
            EXECUTE FUNCTION set_completed_at();
    """)


def downgrade() -> None:
    """Remove completed columns and trigger."""
    # Drop trigger and function
    op.execute("DROP TRIGGER IF EXISTS trigger_set_completed_at ON tasks")
    op.execute("DROP FUNCTION IF EXISTS set_completed_at()")

    # Drop columns
    op.drop_column('tasks', 'completed_at')
    op.drop_column('tasks', 'completed')
