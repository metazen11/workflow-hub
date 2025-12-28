"""Pytest fixtures for Workflow Hub tests.

Uses the production database (wfhub) directly for simplicity.
TODO: Add separate test database isolation when needed for CI/CD.
"""
import os
import uuid
import pytest
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker

# Load environment from .env file
load_dotenv()

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

# Import app modules - uses DATABASE_URL from .env (wfhub)
from app.db import Base, engine, get_db
from app.models import Project, Requirement, Task, Run, AgentReport, ThreatIntel, AuditEvent


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Ensure database tables exist."""
    Base.metadata.create_all(bind=engine)
    yield


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
