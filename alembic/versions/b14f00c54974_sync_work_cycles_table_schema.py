"""sync work_cycles table schema

Revision ID: b14f00c54974
Revises: a87c1e3226a4
Create Date: 2026-01-01 11:57:46.143869

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b14f00c54974'
down_revision: Union[str, Sequence[str], None] = 'a87c1e3226a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new columns
    op.add_column('work_cycles', sa.Column('agent_role', sa.String(length=50), nullable=True))
    op.add_column('work_cycles', sa.Column('artifacts', sa.JSON(), nullable=True))
    op.add_column('work_cycles', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('work_cycles', sa.Column('claim_results', sa.JSON(), nullable=True))
    op.add_column('work_cycles', sa.Column('claims_passed', sa.Integer(), nullable=True))
    op.add_column('work_cycles', sa.Column('claims_failed', sa.Integer(), nullable=True))
    op.add_column('work_cycles', sa.Column('started_at', sa.DateTime(), nullable=True))

    # Handle enum type conversion with raw SQL
    # Create new enum type
    op.execute("CREATE TYPE workcyclestatus AS ENUM ('PENDING', 'IN_PROGRESS', 'VALIDATING', 'COMPLETED', 'FAILED', 'SKIPPED')")

    # Convert status column using text casting
    op.execute("""
        ALTER TABLE work_cycles
        ALTER COLUMN status TYPE workcyclestatus
        USING status::text::workcyclestatus
    """)

    # Drop old index and columns
    op.execute("DROP INDEX IF EXISTS ix_work_cycles_stage")
    op.drop_column('work_cycles', 'report_summary')
    op.drop_column('work_cycles', 'accepted_at')
    op.drop_column('work_cycles', 'report_status')
    op.drop_column('work_cycles', 'context_file')
    op.drop_column('work_cycles', 'stage')
    op.drop_column('work_cycles', 'to_role')
    op.drop_column('work_cycles', 'report')
    op.drop_column('work_cycles', 'from_role')

    # Drop old enum type if exists
    op.execute("DROP TYPE IF EXISTS handoffstatus")


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate old enum
    op.execute("CREATE TYPE handoffstatus AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'SKIPPED')")

    # Add back old columns
    op.add_column('work_cycles', sa.Column('from_role', sa.VARCHAR(length=50), autoincrement=False, nullable=True))
    op.add_column('work_cycles', sa.Column('report', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True))
    op.add_column('work_cycles', sa.Column('to_role', sa.VARCHAR(length=50), autoincrement=False, nullable=True))
    op.add_column('work_cycles', sa.Column('stage', sa.VARCHAR(length=50), autoincrement=False, nullable=True))
    op.add_column('work_cycles', sa.Column('context_file', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('work_cycles', sa.Column('report_status', sa.VARCHAR(length=20), autoincrement=False, nullable=True))
    op.add_column('work_cycles', sa.Column('accepted_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
    op.add_column('work_cycles', sa.Column('report_summary', sa.TEXT(), autoincrement=False, nullable=True))
    op.create_index(op.f('ix_work_cycles_stage'), 'work_cycles', ['stage'], unique=False)

    # Convert status column back (skip VALIDATING)
    op.execute("""
        UPDATE work_cycles SET status = 'PENDING' WHERE status::text = 'VALIDATING'
    """)
    op.execute("""
        ALTER TABLE work_cycles
        ALTER COLUMN status TYPE handoffstatus
        USING status::text::handoffstatus
    """)

    # Drop new columns
    op.drop_column('work_cycles', 'started_at')
    op.drop_column('work_cycles', 'claims_failed')
    op.drop_column('work_cycles', 'claims_passed')
    op.drop_column('work_cycles', 'claim_results')
    op.drop_column('work_cycles', 'summary')
    op.drop_column('work_cycles', 'artifacts')
    op.drop_column('work_cycles', 'agent_role')

    # Drop new enum type
    op.execute("DROP TYPE IF EXISTS workcyclestatus")
