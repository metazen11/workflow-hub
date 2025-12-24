"""Pytest fixtures for Workflow Hub tests."""
import os
import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load environment from .env file
load_dotenv()

# Verify DATABASE_URL is set
if not os.getenv("DATABASE_URL"):
    raise ValueError("DATABASE_URL must be set in .env file to run tests")

from app.db import Base, engine
from app.models import Project, Requirement, Task, Run, AgentReport, ThreatIntel, AuditEvent


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    # Create all tables
    Base.metadata.create_all(bind=engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    # Cleanup after test
    session.rollback()
    session.close()

    # Clear all data (in reverse order of dependencies)
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM agent_reports"))
        conn.execute(text("DELETE FROM task_requirements"))
        conn.execute(text("DELETE FROM runs"))
        conn.execute(text("DELETE FROM tasks"))
        conn.execute(text("DELETE FROM requirements"))
        conn.execute(text("DELETE FROM projects"))
        conn.execute(text("DELETE FROM threat_intel"))
        conn.execute(text("DELETE FROM audit_events"))
        conn.commit()


@pytest.fixture
def sample_project(db_session):
    """Create a sample project."""
    project = Project(
        name="Test Project",
        description="A test project",
        repo_path="/tmp/test-repo",
        stack_tags=["python", "django"]
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture
def sample_requirement(db_session, sample_project):
    """Create a sample requirement."""
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
    """Create a sample run."""
    run = Run(
        project_id=sample_project.id,
        name="Run 2025-01-01_01"
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run
