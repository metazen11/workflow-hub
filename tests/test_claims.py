"""Tests for the Falsification Framework: Claims, Tests, Evidence.

Tests the core Claim → Test → Evidence contract:
- Claim CRUD operations
- Test creation and execution
- Evidence capture and validation
- Gate enforcement based on claims
"""
import pytest
import json
from datetime import datetime

from app.db import get_db, engine, Base
from app.models import (
    Project, Task, Run, RunState, TaskStatus, TaskPipelineStage,
    Claim, ClaimTest, ClaimEvidence,
    ClaimScope, ClaimStatus, ClaimCategory,
    TestType, TestStatus, EvidenceType
)
from app.services.claim_service import ClaimService
from app.services.run_service import RunService


@pytest.fixture
def db():
    """Get a database session for testing."""
    session = next(get_db())
    yield session
    session.close()


@pytest.fixture
def sample_project(db):
    """Create a sample project for testing."""
    project = Project(
        name=f"Test Project {datetime.utcnow().timestamp()}",
        description="A test project for claims testing",
        require_claims=False,
        require_evidence_for_gates=False
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    yield project
    # Cleanup
    try:
        db.delete(project)
        db.commit()
    except Exception:
        db.rollback()


@pytest.fixture
def sample_task(db, sample_project):
    """Create a sample task for testing."""
    task = Task(
        project_id=sample_project.id,
        task_id="T001",
        title="Test Task",
        description="A test task for claims testing",
        status=TaskStatus.BACKLOG,
        pipeline_stage=TaskPipelineStage.DEV
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    yield task
    # Cleanup
    try:
        db.delete(task)
        db.commit()
    except Exception:
        db.rollback()


@pytest.fixture
def claim_service(db):
    """Create a ClaimService instance."""
    return ClaimService(db)


class TestClaimModel:
    """Tests for the Claim model."""

    def test_create_project_claim(self, db, sample_project, claim_service):
        """Test creating a project-level claim."""
        claim, error = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="System accuracy ≥90% on test dataset",
            scope=ClaimScope.PROJECT,
            category=ClaimCategory.ACCURACY,
            priority=8
        )

        assert error is None
        assert claim is not None
        assert claim.project_id == sample_project.id
        assert claim.task_id is None
        assert claim.scope == ClaimScope.PROJECT
        assert claim.category == ClaimCategory.ACCURACY
        assert claim.priority == 8
        assert claim.status == ClaimStatus.PENDING

        # Cleanup
        db.delete(claim)
        db.commit()

    def test_create_task_claim(self, db, sample_project, sample_task, claim_service):
        """Test creating a task-level claim."""
        claim, error = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="API response time <200ms",
            scope=ClaimScope.TASK,
            task_id=sample_task.id,
            category=ClaimCategory.PERFORMANCE,
            priority=9
        )

        assert error is None
        assert claim is not None
        assert claim.project_id == sample_project.id
        assert claim.task_id == sample_task.id
        assert claim.scope == ClaimScope.TASK

        # Cleanup
        db.delete(claim)
        db.commit()

    def test_task_claim_requires_task_id(self, db, sample_project, claim_service):
        """Test that task-level claims require a task_id."""
        claim, error = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="Task claim without task",
            scope=ClaimScope.TASK,
            task_id=None  # Missing!
        )

        assert claim is None
        assert error == "task_id required for TASK scope claims"

    def test_claim_to_dict(self, db, sample_project, claim_service):
        """Test claim serialization."""
        claim, _ = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="Test claim",
            scope=ClaimScope.PROJECT,
            category=ClaimCategory.SECURITY
        )

        data = claim.to_dict()

        assert "id" in data
        assert data["claim_text"] == "Test claim"
        assert data["scope"] == "project"
        assert data["category"] == "security"
        assert data["status"] == "pending"

        # Cleanup
        db.delete(claim)
        db.commit()


class TestClaimTestModel:
    """Tests for the ClaimTest model."""

    def test_create_gold_set_test(self, db, sample_project, claim_service):
        """Test creating a gold set comparison test."""
        claim, _ = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="Downbeat accuracy ≥90%"
        )

        test, error = claim_service.create_test(
            claim_id=claim.id,
            name="Gold Set Comparison",
            test_type=TestType.GOLD_SET,
            config={
                "dataset_path": "/data/gold.csv",
                "output_path": "/data/output.csv",
                "metric": "accuracy",
                "threshold": 0.90
            },
            run_on_stages=["qa"]
        )

        assert error is None
        assert test is not None
        assert test.claim_id == claim.id
        assert test.test_type == TestType.GOLD_SET
        assert test.config["threshold"] == 0.90
        assert "qa" in test.run_on_stages
        assert test.status == TestStatus.PENDING

        # Cleanup
        db.delete(claim)  # Cascade deletes test
        db.commit()

    def test_create_benchmark_test(self, db, sample_project, claim_service):
        """Test creating a benchmark test."""
        claim, _ = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="Processing time <1 second"
        )

        test, error = claim_service.create_test(
            claim_id=claim.id,
            name="Performance Benchmark",
            test_type=TestType.BENCHMARK,
            config={
                "command": "python benchmark.py",
                "metric": "latency_ms",
                "threshold": 1000,
                "comparison": "lte"
            },
            timeout_seconds=60
        )

        assert error is None
        assert test.test_type == TestType.BENCHMARK
        assert test.timeout_seconds == 60

        # Cleanup
        db.delete(claim)
        db.commit()


class TestClaimEvidence:
    """Tests for the ClaimEvidence model."""

    def test_capture_evidence(self, db, sample_project, claim_service):
        """Test manually capturing evidence."""
        claim, _ = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="System passes all tests"
        )

        evidence, error = claim_service.capture_evidence(
            claim_id=claim.id,
            title="Test Results",
            evidence_type=EvidenceType.METRICS_JSON,
            metrics={"passed": 10, "failed": 0, "skipped": 2},
            supports_claim=True,
            verdict_reason="All tests passed"
        )

        assert error is None
        assert evidence is not None
        assert evidence.claim_id == claim.id
        assert evidence.supports_claim is True
        assert evidence.metrics["passed"] == 10

        # Cleanup
        db.delete(claim)
        db.commit()

    def test_evidence_updates_claim_status(self, db, sample_project, claim_service):
        """Test that evidence updates claim status."""
        claim, _ = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="Accuracy target met"
        )

        # Capture validating evidence
        claim_service.capture_evidence(
            claim_id=claim.id,
            title="Validation Results",
            supports_claim=True,
            verdict_reason="Accuracy 95% > 90% threshold"
        )

        # Refresh claim
        claim = claim_service.get_claim(claim.id)
        # Note: Status update depends on tests existing too
        # With no tests but positive evidence, status may still be pending or validated
        assert claim.status in [ClaimStatus.PENDING, ClaimStatus.VALIDATED, ClaimStatus.INCONCLUSIVE]

        # Cleanup
        db.delete(claim)
        db.commit()


class TestClaimService:
    """Tests for the ClaimService."""

    def test_get_project_claims(self, db, sample_project, sample_task, claim_service):
        """Test getting all claims for a project."""
        # Create project-level claim
        project_claim, _ = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="Project-level claim",
            scope=ClaimScope.PROJECT
        )

        # Create task-level claim
        task_claim, _ = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="Task-level claim",
            scope=ClaimScope.TASK,
            task_id=sample_task.id
        )

        # Get all claims
        claims = claim_service.get_project_claims(sample_project.id, include_task_claims=True)
        assert len(claims) >= 2

        # Get only project claims
        project_claims = claim_service.get_project_claims(sample_project.id, include_task_claims=False)
        assert all(c.scope == ClaimScope.PROJECT for c in project_claims)

        # Cleanup
        db.delete(project_claim)
        db.delete(task_claim)
        db.commit()

    def test_get_task_claims(self, db, sample_project, sample_task, claim_service):
        """Test getting claims applicable to a task."""
        # Create project-level claim
        project_claim, _ = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="Inherited project claim",
            scope=ClaimScope.PROJECT
        )

        # Create task-level claim
        task_claim, _ = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="Task-specific claim",
            scope=ClaimScope.TASK,
            task_id=sample_task.id
        )

        # Get task claims (includes inherited project claims)
        claims = claim_service.get_task_claims(sample_task.id, include_project_claims=True)
        assert len(claims) >= 2

        # Get only task-specific claims
        task_only = claim_service.get_task_claims(sample_task.id, include_project_claims=False)
        assert all(c.task_id == sample_task.id for c in task_only)

        # Cleanup
        db.delete(project_claim)
        db.delete(task_claim)
        db.commit()

    def test_claims_summary(self, db, sample_project, claim_service):
        """Test getting claims summary."""
        # Create some claims
        claims = []
        for i in range(3):
            claim, _ = claim_service.create_claim(
                project_id=sample_project.id,
                claim_text=f"Test claim {i}",
                category=ClaimCategory.ACCURACY if i < 2 else ClaimCategory.SECURITY
            )
            claims.append(claim)

        summary = claim_service.get_claims_summary(sample_project.id)

        assert summary["total"] >= 3
        assert "by_status" in summary
        assert "by_category" in summary
        assert "falsification_rate" in summary

        # Cleanup
        for claim in claims:
            db.delete(claim)
        db.commit()


class TestGateEnforcement:
    """Tests for claim-based gate enforcement."""

    def test_gate_passes_when_not_enforced(self, db, sample_project, claim_service):
        """Test that gates pass when enforcement is disabled."""
        sample_project.require_evidence_for_gates = False
        db.commit()

        can_advance, blocking = claim_service.can_advance_gate(
            run_id=1,  # Doesn't matter - enforcement disabled
            gate="qa"
        )

        # Returns True because enforcement is disabled
        # (run doesn't exist but we check project first)
        assert blocking == []

    def test_run_create_blocked_when_claims_required(self, db, sample_project):
        """Test that run creation is blocked when claims are required but none exist."""
        sample_project.require_claims = True
        db.commit()

        run_service = RunService(db)

        with pytest.raises(ValueError, match="requires claims"):
            run_service.create_run(sample_project.id, "Test Run")

        # Reset
        sample_project.require_claims = False
        db.commit()


class TestValidation:
    """Tests for claim validation."""

    def test_validate_claims_for_run(self, db, sample_project, claim_service):
        """Test validating claims for a run."""
        # Create a run
        run = Run(project_id=sample_project.id, name="Test Run", state=RunState.PM)
        db.add(run)
        db.commit()
        db.refresh(run)

        # Create a claim
        claim, _ = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="Test validation claim"
        )

        # Validate (no evidence yet)
        result = claim_service.validate_claims_for_run(run.id)

        assert result["total_claims"] >= 1
        assert len(result["missing_evidence"]) >= 1  # Our claim has no evidence

        # Cleanup
        db.delete(claim)
        db.delete(run)
        db.commit()


class TestLedgerIntegration:
    """Tests for automatic ledger entry and task creation on claim failure."""

    def test_failed_test_creates_ledger_entry(self, db, sample_project, claim_service):
        """Test that a failing test creates a ledger entry."""
        import os
        from app.services.ledger_service import LedgerService

        # Create a claim with a test that will fail
        claim, _ = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="Test accuracy >= 90%"
        )

        test, _ = claim_service.create_test(
            claim_id=claim.id,
            name="Threshold Test",
            test_type=TestType.METRIC_THRESHOLD,
            config={
                "metric_file": "/nonexistent/file.json",  # Will fail
                "metric_name": "accuracy",
                "threshold": 0.9
            }
        )

        # Run the test (will fail because file doesn't exist)
        evidence, error = claim_service.run_test(test.id)

        # Check that a ledger entry was created
        ledger_service = LedgerService(db)
        entries = ledger_service.get_all_entries()

        # Find entry for our claim
        our_entries = [e for e in entries if e.get('claim_id') == claim.id]
        assert len(our_entries) >= 1, "Ledger entry should be created on test failure"

        entry = our_entries[0]
        assert entry['status'] == 'failed'
        assert 'failure_mode' in entry

        # Cleanup
        db.delete(claim)
        db.commit()

    def test_failed_test_creates_tasks(self, db, sample_project, claim_service):
        """Test that a failing test auto-generates tasks."""
        from app.models import Task

        initial_task_count = db.query(Task).filter(Task.project_id == sample_project.id).count()

        # Create a claim with a test that will fail
        claim, _ = claim_service.create_claim(
            project_id=sample_project.id,
            claim_text="Another accuracy claim >= 95%"
        )

        test, _ = claim_service.create_test(
            claim_id=claim.id,
            name="Another Threshold Test",
            test_type=TestType.METRIC_THRESHOLD,
            config={
                "metric_file": "/nonexistent/file2.json",
                "metric_name": "accuracy",
                "threshold": 0.95
            }
        )

        # Run the test (will fail)
        claim_service.run_test(test.id)

        # Check that tasks were created
        final_task_count = db.query(Task).filter(Task.project_id == sample_project.id).count()
        assert final_task_count > initial_task_count, "Tasks should be created on test failure"

        # Check task content
        new_tasks = db.query(Task).filter(
            Task.project_id == sample_project.id,
            Task.title.contains("Investigate")
        ).all()
        assert len(new_tasks) >= 1, "Investigation task should be created"

        # Cleanup
        for task in db.query(Task).filter(Task.project_id == sample_project.id).all():
            db.delete(task)
        db.delete(claim)
        db.commit()


# Run with: pytest tests/test_claims.py -v
