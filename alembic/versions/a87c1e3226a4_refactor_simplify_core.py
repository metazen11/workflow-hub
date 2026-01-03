"""refactor_simplify_core

This migration implements the core refactor:
1. Renames handoffs table to work_cycles
2. Drops run_id from tasks and work_cycles (Run model being killed)
3. Drops agent_report_id from work_cycles (AgentReport being killed)
4. Adds VALIDATING to task status enum
5. Creates PostgREST roles and permissions

Revision ID: a87c1e3226a4
Revises: ce7fde9bf3e1
Create Date: 2026-01-01 10:01:49.303116

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a87c1e3226a4'
down_revision: Union[str, Sequence[str], None] = 'ce7fde9bf3e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema for simplified core."""

    # 1. Add VALIDATING to task status enum
    op.execute("ALTER TYPE taskstatus ADD VALUE IF NOT EXISTS 'validating'")

    # 2. Add claim tracking columns to tasks
    op.add_column('tasks', sa.Column('claims_total', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('tasks', sa.Column('claims_validated', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('tasks', sa.Column('claims_failed', sa.Integer(), nullable=True, server_default='0'))

    # 3. Keep pipeline_stage for backward compatibility
    # TODO: Remove when fully migrated to claim-based validation
    # op.drop_column('tasks', 'pipeline_stage')  # SKIPPED - keeping for compatibility

    # 4. Rename handoffs table to work_cycles
    op.rename_table('handoffs', 'work_cycles')

    # 3. Rename sequences and constraints for work_cycles
    op.execute("ALTER SEQUENCE IF EXISTS handoffs_id_seq RENAME TO work_cycles_id_seq")
    op.execute("ALTER INDEX IF EXISTS ix_handoffs_project_id RENAME TO ix_work_cycles_project_id")
    op.execute("ALTER INDEX IF EXISTS ix_handoffs_task_id RENAME TO ix_work_cycles_task_id")
    op.execute("ALTER INDEX IF EXISTS ix_handoffs_run_id RENAME TO ix_work_cycles_run_id")
    op.execute("ALTER INDEX IF EXISTS ix_handoffs_stage RENAME TO ix_work_cycles_stage")
    op.execute("ALTER INDEX IF EXISTS ix_handoffs_status RENAME TO ix_work_cycles_status")

    # 4. Drop run_id from tasks (nullable, so safe)
    op.drop_constraint('tasks_run_id_fkey', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'run_id')

    # 5. Drop run_id from work_cycles
    op.drop_constraint('handoffs_run_id_fkey', 'work_cycles', type_='foreignkey')
    op.drop_index('ix_work_cycles_run_id', 'work_cycles')
    op.drop_column('work_cycles', 'run_id')

    # 6. Drop agent_report_id from work_cycles (AgentReport being killed)
    op.drop_constraint('handoffs_agent_report_id_fkey', 'work_cycles', type_='foreignkey')
    op.drop_column('work_cycles', 'agent_report_id')

    # 7. Drop task_requirements association table (Requirement being killed)
    op.drop_table('task_requirements')

    # 8. Create PostgREST roles and grant permissions
    op.execute("""
        -- Create roles if they don't exist
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'web_anon') THEN
                CREATE ROLE web_anon NOLOGIN;
            END IF;
            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'web_user') THEN
                CREATE ROLE web_user NOLOGIN;
            END IF;
        END
        $$;

        -- Grant schema access
        GRANT USAGE ON SCHEMA public TO web_anon, web_user;

        -- Grant read access to web_anon (anonymous users)
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO web_anon;

        -- Grant full CRUD to web_user (authenticated users)
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO web_user;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO web_user;

        -- Set default privileges for future tables
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO web_anon;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO web_user;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO web_user;
    """)


def downgrade() -> None:
    """Downgrade - restore original schema."""

    # Restore task_requirements table
    op.create_table('task_requirements',
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('requirement_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['requirement_id'], ['requirements.id'], ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
        sa.PrimaryKeyConstraint('task_id', 'requirement_id')
    )

    # Restore agent_report_id to work_cycles
    op.add_column('work_cycles', sa.Column('agent_report_id', sa.Integer(), nullable=True))
    op.create_foreign_key('handoffs_agent_report_id_fkey', 'work_cycles', 'agent_reports', ['agent_report_id'], ['id'])

    # Restore run_id to work_cycles
    op.add_column('work_cycles', sa.Column('run_id', sa.Integer(), nullable=True))
    op.create_index('ix_work_cycles_run_id', 'work_cycles', ['run_id'])
    op.create_foreign_key('handoffs_run_id_fkey', 'work_cycles', 'runs', ['run_id'], ['id'])

    # Restore run_id to tasks
    op.add_column('tasks', sa.Column('run_id', sa.Integer(), nullable=True))
    op.create_foreign_key('tasks_run_id_fkey', 'tasks', 'runs', ['run_id'], ['id'])

    # pipeline_stage was not dropped, so no need to restore
    # op.add_column('tasks', sa.Column('pipeline_stage', ...))

    # Drop claim tracking columns from tasks
    op.drop_column('tasks', 'claims_failed')
    op.drop_column('tasks', 'claims_validated')
    op.drop_column('tasks', 'claims_total')

    # Rename indexes back
    op.execute("ALTER INDEX IF EXISTS ix_work_cycles_project_id RENAME TO ix_handoffs_project_id")
    op.execute("ALTER INDEX IF EXISTS ix_work_cycles_task_id RENAME TO ix_handoffs_task_id")
    op.execute("ALTER INDEX IF EXISTS ix_work_cycles_stage RENAME TO ix_handoffs_stage")
    op.execute("ALTER INDEX IF EXISTS ix_work_cycles_status RENAME TO ix_handoffs_status")

    # Rename sequence back
    op.execute("ALTER SEQUENCE IF EXISTS work_cycles_id_seq RENAME TO handoffs_id_seq")

    # Rename table back
    op.rename_table('work_cycles', 'handoffs')

    # Revoke PostgREST permissions
    op.execute("""
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM web_anon, web_user;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM web_user;
        REVOKE USAGE ON SCHEMA public FROM web_anon, web_user;
    """)
