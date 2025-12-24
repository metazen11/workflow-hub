"""Tests for SQLAlchemy models."""
import pytest
from app.models import (
    Project, Requirement, Task, TaskStatus,
    Run, RunState, AgentReport, ThreatIntel, AuditEvent
)
from app.models.report import AgentRole, ReportStatus
from app.models.threat_intel import ThreatStatus
from datetime import date


class TestProject:
    """Tests for Project model."""

    def test_create_project(self, db_session):
        """Test creating a project."""
        project = Project(
            name="My Project",
            description="Test description",
            repo_path="/home/user/project",
            stack_tags=["python", "fastapi"]
        )
        db_session.add(project)
        db_session.commit()

        assert project.id is not None
        assert project.name == "My Project"
        assert project.stack_tags == ["python", "fastapi"]

    def test_project_to_dict(self, sample_project):
        """Test project serialization."""
        data = sample_project.to_dict()
        assert data["name"] == "Test Project"
        assert data["stack_tags"] == ["python", "django"]
        assert "created_at" in data


class TestRequirement:
    """Tests for Requirement model."""

    def test_create_requirement(self, db_session, sample_project):
        """Test creating a requirement."""
        req = Requirement(
            project_id=sample_project.id,
            req_id="R1",
            title="User Login",
            acceptance_criteria="User can log in with email/password"
        )
        db_session.add(req)
        db_session.commit()

        assert req.id is not None
        assert req.req_id == "R1"

    def test_requirement_to_dict(self, sample_requirement):
        """Test requirement serialization."""
        data = sample_requirement.to_dict()
        assert data["req_id"] == "R1"
        assert data["title"] == "Test Requirement"


class TestTask:
    """Tests for Task model."""

    def test_create_task(self, db_session, sample_project):
        """Test creating a task."""
        task = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Implement login",
            status=TaskStatus.BACKLOG
        )
        db_session.add(task)
        db_session.commit()

        assert task.id is not None
        assert task.status == TaskStatus.BACKLOG

    def test_task_status_transition(self, db_session, sample_project):
        """Test task status can be changed."""
        task = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Test task",
            status=TaskStatus.BACKLOG
        )
        db_session.add(task)
        db_session.commit()

        task.status = TaskStatus.IN_PROGRESS
        db_session.commit()

        assert task.status == TaskStatus.IN_PROGRESS

    def test_task_link_to_requirements(self, db_session, sample_project, sample_requirement):
        """Test linking task to requirements."""
        task = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Implement R1"
        )
        task.requirements.append(sample_requirement)
        db_session.add(task)
        db_session.commit()

        assert len(task.requirements) == 1
        assert task.requirements[0].req_id == "R1"


class TestRun:
    """Tests for Run model."""

    def test_create_run(self, db_session, sample_project):
        """Test creating a run."""
        run = Run(
            project_id=sample_project.id,
            name="Run 2025-01-01"
        )
        db_session.add(run)
        db_session.commit()

        assert run.id is not None
        assert run.state == RunState.PM  # Default state

    def test_run_initial_state(self, sample_run):
        """Test run starts in PM state."""
        assert sample_run.state == RunState.PM

    def test_run_to_dict(self, sample_run):
        """Test run serialization."""
        data = sample_run.to_dict()
        assert data["state"] == "pm"
        assert data["name"] == "Run 2025-01-01_01"


class TestRunStateTransitions:
    """Tests for Run state machine (R5: Gate enforcement)."""

    def test_valid_transition_pm_to_dev(self, sample_run):
        """Test PM → DEV is valid."""
        assert sample_run.can_transition_to(RunState.DEV) is True

    def test_invalid_transition_pm_to_qa(self, sample_run):
        """Test PM → QA is invalid (must go through DEV)."""
        assert sample_run.can_transition_to(RunState.QA) is False

    def test_transition_method(self, sample_run):
        """Test transition_to method."""
        result = sample_run.transition_to(RunState.DEV)
        assert result is True
        assert sample_run.state == RunState.DEV

    def test_transition_to_invalid_state(self, sample_run):
        """Test transition to invalid state fails."""
        result = sample_run.transition_to(RunState.DEPLOYED)
        assert result is False
        assert sample_run.state == RunState.PM  # Unchanged


class TestAgentReport:
    """Tests for AgentReport model."""

    def test_create_report(self, db_session, sample_run):
        """Test creating an agent report."""
        report = AgentReport(
            run_id=sample_run.id,
            role=AgentRole.QA,
            status=ReportStatus.PASS,
            summary="All tests pass",
            details={"tests_run": 10, "tests_passed": 10}
        )
        db_session.add(report)
        db_session.commit()

        assert report.id is not None
        assert report.role == AgentRole.QA
        assert report.status == ReportStatus.PASS

    def test_report_to_dict(self, db_session, sample_run):
        """Test report serialization."""
        report = AgentReport(
            run_id=sample_run.id,
            role=AgentRole.DEV,
            status=ReportStatus.PASS,
            summary="Code complete"
        )
        db_session.add(report)
        db_session.commit()

        data = report.to_dict()
        assert data["role"] == "dev"
        assert data["status"] == "pass"


class TestThreatIntel:
    """Tests for ThreatIntel model (R7)."""

    def test_create_threat_intel(self, db_session):
        """Test creating threat intel entry."""
        intel = ThreatIntel(
            date_reported=date.today(),
            source="CVE-2025-0001",
            summary="SQL injection vulnerability",
            affected_tech="Django < 4.2",
            action="Upgrade Django",
            status=ThreatStatus.NEW
        )
        db_session.add(intel)
        db_session.commit()

        assert intel.id is not None
        assert intel.status == ThreatStatus.NEW

    def test_threat_intel_to_dict(self, db_session):
        """Test threat intel serialization."""
        intel = ThreatIntel(
            date_reported=date.today(),
            source="Internal Audit",
            summary="Weak password policy"
        )
        db_session.add(intel)
        db_session.commit()

        data = intel.to_dict()
        assert data["source"] == "Internal Audit"
        assert data["status"] == "new"


class TestAuditEvent:
    """Tests for AuditEvent model (R9)."""

    def test_create_audit_event(self, db_session):
        """Test creating an audit event."""
        event = AuditEvent(
            actor="human",
            action="create",
            entity_type="project",
            entity_id=1,
            details={"name": "Test Project"}
        )
        db_session.add(event)
        db_session.commit()

        assert event.id is not None
        assert event.timestamp is not None

    def test_audit_event_to_dict(self, db_session):
        """Test audit event serialization."""
        event = AuditEvent(
            actor="qa",
            action="submit_report",
            entity_type="run",
            entity_id=5
        )
        db_session.add(event)
        db_session.commit()

        data = event.to_dict()
        assert data["actor"] == "qa"
        assert data["action"] == "submit_report"
        assert "timestamp" in data
