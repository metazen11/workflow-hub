"""Pytest fixtures for Workflow Hub tests.

Uses the production database (wfhub) directly for simplicity.
TODO: Add separate test database isolation when needed for CI/CD.
"""
import os
import glob
import uuid
import pytest
import yaml
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# Load environment from .env file
load_dotenv()

# Project root for filesystem cleanup
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

# Import app modules - uses DATABASE_URL from .env (wfhub)
from app.db import Base, engine, get_db
from app.models import Project, Requirement, Task, Run, AgentReport, ThreatIntel, AuditEvent


def cleanup_test_projects():
    """Delete all test projects and related data after test session.

    Matches projects by:
    - Names containing 'test' (case-insensitive)
    - Names ending with 8-character hex suffix (uuid pattern from unique_name())
    - Known test fixture base names
    """
    with engine.connect() as conn:
        # Get test project IDs - comprehensive pattern matching
        result = conn.execute(text("""
            SELECT id FROM projects WHERE
                name ILIKE '%test%'
                OR name ~ '[0-9a-f]{8}$'
                OR name LIKE 'Complete Project %'
                OR name LIKE 'Repo Info Project %'
                OR name LIKE 'Dev Settings Project %'
                OR name LIKE 'Commands Project %'
                OR name LIKE 'Key Files Project %'
                OR name LIKE 'Full Stack App %'
                OR name LIKE 'Other Project %'
        """))
        project_ids = [row[0] for row in result]

        if not project_ids:
            return

        ids_str = ','.join(str(id) for id in project_ids)

        # Delete in dependency order
        tables = [
            ("claim_evidence", f"test_id IN (SELECT id FROM claim_tests WHERE claim_id IN (SELECT id FROM claims WHERE project_id IN ({ids_str}) OR task_id IN (SELECT id FROM tasks WHERE project_id IN ({ids_str}))))"),
            ("claim_tests", f"claim_id IN (SELECT id FROM claims WHERE project_id IN ({ids_str}) OR task_id IN (SELECT id FROM tasks WHERE project_id IN ({ids_str})))"),
            ("claims", f"project_id IN ({ids_str}) OR task_id IN (SELECT id FROM tasks WHERE project_id IN ({ids_str}))"),
            ("task_requirements", f"task_id IN (SELECT id FROM tasks WHERE project_id IN ({ids_str}))"),
            ("task_attachments", f"task_id IN (SELECT id FROM tasks WHERE project_id IN ({ids_str}))"),
            ("work_cycles", f"project_id IN ({ids_str})"),
            ("llm_jobs", f"project_id IN ({ids_str}) OR task_id IN (SELECT id FROM tasks WHERE project_id IN ({ids_str}))"),
            ("llm_sessions", f"project_id IN ({ids_str})"),
            ("agent_reports", f"run_id IN (SELECT id FROM runs WHERE project_id IN ({ids_str}))"),
            ("deployment_history", f"run_id IN (SELECT id FROM runs WHERE project_id IN ({ids_str}))"),
            ("runs", f"project_id IN ({ids_str})"),
            ("tasks", f"project_id IN ({ids_str})"),
            ("requirements", f"project_id IN ({ids_str})"),
            ("bug_reports", f"project_id IN ({ids_str})"),
            ("credentials", f"project_id IN ({ids_str})"),
            ("environments", f"project_id IN ({ids_str})"),
            ("projects", f"id IN ({ids_str})"),
        ]

        for table, where_clause in tables:
            try:
                conn.execute(text(f"DELETE FROM {table} WHERE {where_clause}"))
            except Exception:
                pass  # Table may not exist

        conn.commit()
        print(f"\n[conftest] Cleaned up {len(project_ids)} test projects")


def cleanup_test_ledger_entries():
    """Remove test entries from the failed claims ledger."""
    ledger_dir = os.path.join(PROJECT_ROOT, 'ledger')
    index_path = os.path.join(ledger_dir, 'failed_claims.yaml')
    claims_dir = os.path.join(ledger_dir, 'failed_claims')

    if not os.path.exists(index_path):
        return

    with open(index_path, 'r') as f:
        index_data = yaml.safe_load(f) or {'entries': []}

    original_count = len(index_data.get('entries', []))

    # Filter out test entries
    real_entries = [
        e for e in index_data.get('entries', [])
        if not (e.get('project', '').startswith('test_project') or
                'test' in e.get('project', '').lower())
    ]

    removed_count = original_count - len(real_entries)

    if removed_count > 0:
        index_data['entries'] = real_entries
        with open(index_path, 'w') as f:
            yaml.dump(index_data, f, default_flow_style=False)

        # Remove individual claim files
        for claim_file in glob.glob(os.path.join(claims_dir, 'FC-*.yaml')):
            try:
                with open(claim_file, 'r') as f:
                    claim_data = yaml.safe_load(f) or {}
                project = claim_data.get('project', '')
                if project.startswith('test_project') or 'test' in project.lower():
                    os.remove(claim_file)
            except Exception:
                pass

        print(f"[conftest] Cleaned up {removed_count} test ledger entries")


def cleanup_test_workspaces():
    """Remove test workspace directories."""
    import shutil
    workspaces_dir = os.path.join(PROJECT_ROOT, 'workspaces')
    if not os.path.exists(workspaces_dir):
        return

    removed_count = 0
    for item in os.listdir(workspaces_dir):
        # Match test_project_* and other test patterns
        if item.startswith('test_project_') or item.startswith('test-'):
            item_path = os.path.join(workspaces_dir, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    removed_count += 1
            except Exception:
                pass

    if removed_count > 0:
        print(f"[conftest] Cleaned up {removed_count} test workspace directories")


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Ensure database tables exist and clean up after tests."""
    Base.metadata.create_all(bind=engine)
    yield
    # Cleanup test data after all tests complete
    cleanup_test_projects()
    cleanup_test_ledger_entries()
    cleanup_test_workspaces()


@pytest.fixture(scope="function")
def db_session():
    """Create a database session for tests.

    Uses production database. Tests should clean up their own data
    or use unique identifiers to avoid conflicts.
    """
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    # Rollback uncommitted changes only - don't truncate
    session.rollback()
    session.close()


@pytest.fixture
def sample_project(db_session):
    """Create a sample project for testing with unique name."""
    unique_name = f"Test Project {uuid.uuid4().hex[:8]}"
    project = Project(
        name=unique_name,
        description="A test project",
        repo_path="/tmp/test-repo",
        stack_tags=["python", "django"]
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    yield project

    # Cleanup: delete project and related data
    try:
        db_session.delete(project)
        db_session.commit()
    except Exception:
        db_session.rollback()


@pytest.fixture
def sample_requirement(db_session, sample_project):
    """Create a sample requirement for testing."""
    req = Requirement(
        project_id=sample_project.id,
        req_id="R1",
        title="Test Requirement",
        description="A test requirement",
        acceptance_criteria="Must pass tests"
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)
    return req


@pytest.fixture
def sample_run(db_session, sample_project):
    """Create a sample run for testing with unique name."""
    unique_name = f"Run {uuid.uuid4().hex[:8]}"
    run = Run(
        project_id=sample_project.id,
        name=unique_name
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    yield run

    # Cleanup handled by cascade delete when project is deleted
