"""Tests for BugReport model."""
import pytest
from app.models.bug_report import BugReport, BugReportStatus


class TestBugReport:
    """Test BugReport model."""

    def test_create_bug_report(self, db_session):
        """Test creating a basic bug report."""
        report = BugReport(
            title="Button not working",
            description="The submit button does nothing when clicked"
        )
        db_session.add(report)
        db_session.commit()

        assert report.id is not None
        assert report.title == "Button not working"
        assert report.status == BugReportStatus.OPEN
        assert report.created_at is not None

    def test_bug_report_with_screenshot(self, db_session):
        """Test bug report with base64 screenshot."""
        screenshot_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        report = BugReport(
            title="Visual bug",
            screenshot=screenshot_data
        )
        db_session.add(report)
        db_session.commit()

        assert report.screenshot.startswith("data:image/png;base64,")

    def test_bug_report_with_metadata(self, db_session):
        """Test bug report with URL and user agent."""
        report = BugReport(
            title="Page crash",
            url="http://localhost:5050/kanban",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            app_name="Todo App"
        )
        db_session.add(report)
        db_session.commit()

        assert report.url == "http://localhost:5050/kanban"
        assert "Mozilla" in report.user_agent
        assert report.app_name == "Todo App"

    def test_bug_report_status_enum(self, db_session):
        """Test all status enum values."""
        assert BugReportStatus.OPEN.value == "open"
        assert BugReportStatus.IN_PROGRESS.value == "in_progress"
        assert BugReportStatus.RESOLVED.value == "resolved"
        assert BugReportStatus.CLOSED.value == "closed"

    def test_bug_report_status_transitions(self, db_session):
        """Test changing bug report status."""
        report = BugReport(title="Test bug")
        db_session.add(report)
        db_session.commit()

        assert report.status == BugReportStatus.OPEN

        report.status = BugReportStatus.IN_PROGRESS
        db_session.commit()
        assert report.status == BugReportStatus.IN_PROGRESS

        report.status = BugReportStatus.RESOLVED
        db_session.commit()
        assert report.status == BugReportStatus.RESOLVED

    def test_bug_report_to_dict(self, db_session):
        """Test serialization to dictionary."""
        report = BugReport(
            title="Test bug",
            description="Description here",
            app_name="Test App"
        )
        db_session.add(report)
        db_session.commit()

        data = report.to_dict()

        assert data["id"] == report.id
        assert data["title"] == "Test bug"
        assert data["description"] == "Description here"
        assert data["app_name"] == "Test App"
        assert data["status"] == "open"
        assert "created_at" in data

    def test_bug_report_resolved_at_null_by_default(self, db_session):
        """Test resolved_at is null for new reports."""
        report = BugReport(title="New bug")
        db_session.add(report)
        db_session.commit()

        assert report.resolved_at is None
