"""Tests for Run state machine and gate enforcement (R4, R5, R8)."""
import pytest
from app.models import Run, RunState, AgentReport, AuditEvent
from app.models.report import AgentRole, ReportStatus
from app.services.run_service import RunService


class TestRunService:
    """Tests for RunService."""

    def test_create_run(self, db_session, sample_project):
        """Test creating a run via service."""
        service = RunService(db_session)
        run = service.create_run(sample_project.id, "Test Run")

        assert run.id is not None
        assert run.state == RunState.PM
        assert run.name == "Test Run"

        # Should create audit event
        events = db_session.query(AuditEvent).filter(
            AuditEvent.entity_type == "run",
            AuditEvent.action == "create"
        ).all()
        assert len(events) == 1


class TestSubmitReport:
    """Tests for submitting agent reports."""

    def test_submit_pm_report(self, db_session, sample_run):
        """Test PM can submit report."""
        service = RunService(db_session)
        report, error = service.submit_report(
            run_id=sample_run.id,
            role=AgentRole.PM,
            status=ReportStatus.PASS,
            summary="Requirements defined",
            details={"requirements_count": 5}
        )

        assert error is None
        assert report.role == AgentRole.PM
        assert sample_run.pm_result is not None

    def test_submit_qa_report_pass(self, db_session, sample_run):
        """Test QA pass report."""
        service = RunService(db_session)
        report, error = service.submit_report(
            run_id=sample_run.id,
            role=AgentRole.QA,
            status=ReportStatus.PASS,
            summary="All tests pass",
            details={
                "tests_added": ["test_login", "test_logout"],
                "commands_run": ["pytest"],
                "failing_tests": [],
                "requirements_covered": ["R1", "R2"]
            }
        )

        assert error is None
        assert report.status == ReportStatus.PASS
        assert sample_run.qa_result["status"] == "pass"

    def test_submit_qa_report_fail(self, db_session, sample_run):
        """Test QA fail report."""
        service = RunService(db_session)
        report, error = service.submit_report(
            run_id=sample_run.id,
            role=AgentRole.QA,
            status=ReportStatus.FAIL,
            summary="Tests failing",
            details={"failing_tests": ["test_login"]}
        )

        assert error is None
        assert report.status == ReportStatus.FAIL

    def test_submit_security_report(self, db_session, sample_run):
        """Test Security report."""
        service = RunService(db_session)
        report, error = service.submit_report(
            run_id=sample_run.id,
            role=AgentRole.SECURITY,
            status=ReportStatus.PASS,
            summary="No vulnerabilities found",
            details={"intel_refs": [1, 2], "controls_verified": ["no_hardcoded_secrets"]}
        )

        assert error is None
        assert report.role == AgentRole.SECURITY
        assert sample_run.sec_result is not None


class TestGateEnforcement:
    """Tests for R5: Gate enforcement."""

    def test_qa_gate_blocks_on_fail(self, db_session, sample_run):
        """Test QA gate blocks advancement when QA fails."""
        service = RunService(db_session)

        # Advance to QA state
        sample_run.state = RunState.QA
        db_session.commit()

        # Submit failing QA report
        service.submit_report(
            run_id=sample_run.id,
            role=AgentRole.QA,
            status=ReportStatus.FAIL,
            summary="Tests failing"
        )

        # Try to advance
        new_state, error = service.advance_state(sample_run.id)

        assert new_state == RunState.QA_FAILED
        assert "QA gate failed" in error

    def test_qa_gate_passes_on_pass(self, db_session, sample_run):
        """Test QA gate allows advancement when QA passes."""
        service = RunService(db_session)

        # Advance to QA state
        sample_run.state = RunState.QA
        db_session.commit()

        # Submit passing QA report
        service.submit_report(
            run_id=sample_run.id,
            role=AgentRole.QA,
            status=ReportStatus.PASS,
            summary="All tests pass"
        )

        # Try to advance
        new_state, error = service.advance_state(sample_run.id)

        assert error is None
        assert new_state == RunState.SEC

    def test_security_gate_blocks_on_fail(self, db_session, sample_run):
        """Test Security gate blocks advancement when security fails."""
        service = RunService(db_session)

        # Advance to SEC state
        sample_run.state = RunState.SEC
        db_session.commit()

        # Submit failing security report
        service.submit_report(
            run_id=sample_run.id,
            role=AgentRole.SECURITY,
            status=ReportStatus.FAIL,
            summary="Vulnerabilities found"
        )

        # Try to advance
        new_state, error = service.advance_state(sample_run.id)

        assert new_state == RunState.SEC_FAILED
        assert "Security gate failed" in error

    def test_security_gate_passes_on_pass(self, db_session, sample_run):
        """Test Security gate allows advancement when security passes."""
        service = RunService(db_session)

        # Advance to SEC state
        sample_run.state = RunState.SEC
        db_session.commit()

        # Submit passing security report
        service.submit_report(
            run_id=sample_run.id,
            role=AgentRole.SECURITY,
            status=ReportStatus.PASS,
            summary="No issues"
        )

        # Try to advance
        new_state, error = service.advance_state(sample_run.id)

        assert error is None
        assert new_state == RunState.READY_FOR_COMMIT


class TestHumanApproval:
    """Tests for R8: Human approval for deployment."""

    def test_deploy_requires_human_approval(self, db_session, sample_run):
        """Test READY_FOR_DEPLOY → DEPLOYED requires human actor."""
        service = RunService(db_session)

        # Set to ready for deploy
        sample_run.state = RunState.READY_FOR_DEPLOY
        db_session.commit()

        # Try to advance as non-human
        new_state, error = service.advance_state(sample_run.id, actor="dev")

        assert error == "Human approval required for deployment"
        assert sample_run.state == RunState.READY_FOR_DEPLOY

    def test_deploy_succeeds_with_human_approval(self, db_session, sample_run):
        """Test human can approve deployment."""
        service = RunService(db_session)

        # Set to ready for deploy
        sample_run.state = RunState.READY_FOR_DEPLOY
        db_session.commit()

        # Advance as human
        new_state, error = service.advance_state(sample_run.id, actor="human")

        assert error is None
        assert new_state == RunState.DEPLOYED


class TestRetryFromFailed:
    """Tests for retrying failed stages."""

    def test_retry_qa_failed(self, db_session, sample_run):
        """Test retrying from QA_FAILED state."""
        service = RunService(db_session)

        sample_run.state = RunState.QA_FAILED
        db_session.commit()

        new_state, error = service.retry_from_failed(sample_run.id)

        assert error is None
        assert new_state == RunState.QA

    def test_retry_sec_failed(self, db_session, sample_run):
        """Test retrying from SEC_FAILED state."""
        service = RunService(db_session)

        sample_run.state = RunState.SEC_FAILED
        db_session.commit()

        new_state, error = service.retry_from_failed(sample_run.id)

        assert error is None
        assert new_state == RunState.SEC

    def test_retry_non_failed_state_errors(self, db_session, sample_run):
        """Test retry from non-failed state returns error."""
        service = RunService(db_session)

        # Run is in PM state
        new_state, error = service.retry_from_failed(sample_run.id)

        assert error == "Run is not in a failed state"


class TestFullPipeline:
    """Integration test for full pipeline flow."""

    def test_full_pipeline_success(self, db_session, sample_project):
        """Test complete run through pipeline."""
        service = RunService(db_session)

        # Create run
        run = service.create_run(sample_project.id, "Full Pipeline Test")
        assert run.state == RunState.PM

        # PM → DEV
        service.submit_report(run.id, AgentRole.PM, ReportStatus.PASS, "Done")
        state, _ = service.advance_state(run.id)
        assert state == RunState.DEV

        # DEV → QA
        service.submit_report(run.id, AgentRole.DEV, ReportStatus.PASS, "Code complete")
        state, _ = service.advance_state(run.id)
        assert state == RunState.QA

        # QA → SEC
        service.submit_report(run.id, AgentRole.QA, ReportStatus.PASS, "Tests pass")
        state, _ = service.advance_state(run.id)
        assert state == RunState.SEC

        # SEC → READY_FOR_COMMIT
        service.submit_report(run.id, AgentRole.SECURITY, ReportStatus.PASS, "Secure")
        state, _ = service.advance_state(run.id)
        assert state == RunState.READY_FOR_COMMIT

        # READY_FOR_COMMIT → MERGED
        state, _ = service.advance_state(run.id)
        assert state == RunState.MERGED

        # MERGED → READY_FOR_DEPLOY
        state, _ = service.advance_state(run.id)
        assert state == RunState.READY_FOR_DEPLOY

        # READY_FOR_DEPLOY → DEPLOYED (human approval)
        state, _ = service.advance_state(run.id, actor="human")
        assert state == RunState.DEPLOYED

        # Verify audit trail
        events = db_session.query(AuditEvent).filter(
            AuditEvent.entity_type == "run",
            AuditEvent.entity_id == run.id
        ).all()
        assert len(events) >= 8  # create + 7 state changes
