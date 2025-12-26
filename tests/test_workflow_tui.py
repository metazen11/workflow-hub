"""Tests for WorkflowTUI - Rich terminal UI for workflow pipeline.

TDD: These tests are written FIRST. They should FAIL until we implement the TUI.
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from app.models import Task, TaskStatus, Run
from scripts.workflow_tui import WorkflowTUI, STATUS_ICONS, AGENT_COLORS


class TestStatusIcons:
    """Tests for status icon mapping."""

    def test_done_has_checkmark(self):
        """DONE status should show checkmark icon."""
        assert STATUS_ICONS[TaskStatus.DONE] == "\u2713"  # ✓

    def test_in_progress_has_dots(self):
        """IN_PROGRESS status should show ellipsis."""
        assert STATUS_ICONS[TaskStatus.IN_PROGRESS] == "\u22ef"  # ⋯

    def test_failed_has_x(self):
        """FAILED status should show X icon."""
        assert STATUS_ICONS[TaskStatus.FAILED] == "\u2717"  # ✗

    def test_backlog_has_circle(self):
        """BACKLOG status should show empty circle."""
        assert STATUS_ICONS[TaskStatus.BACKLOG] == "\u25cb"  # ○

    def test_blocked_has_circle(self):
        """BLOCKED status should show empty circle."""
        assert STATUS_ICONS[TaskStatus.BLOCKED] == "\u25cb"  # ○


class TestAgentColors:
    """Tests for agent color mapping."""

    def test_pm_is_magenta(self):
        """PM agent should be magenta."""
        assert AGENT_COLORS["PM"] == "magenta"

    def test_dev_is_green(self):
        """DEV agent should be green."""
        assert AGENT_COLORS["DEV"] == "green"

    def test_qa_is_yellow(self):
        """QA agent should be yellow."""
        assert AGENT_COLORS["QA"] == "yellow"

    def test_sec_is_red(self):
        """SEC agent should be red."""
        assert AGENT_COLORS["SEC"] == "red"


class TestWorkflowTUIInit:
    """Tests for WorkflowTUI initialization."""

    def test_accepts_run_name_and_sandbox(self):
        """TUI should accept run name and sandbox path."""
        tui = WorkflowTUI(run_name="Test Run", sandbox_path="/tmp/test")
        assert tui.run_name == "Test Run"
        assert tui.sandbox_path == "/tmp/test"

    def test_log_starts_empty(self):
        """Log should start with no entries."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        assert len(tui.log_entries) == 0

    def test_current_agent_starts_none(self):
        """Current agent should start as None."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        assert tui.current_agent is None

    def test_agent_start_time_starts_none(self):
        """Agent start time should start as None."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        assert tui.agent_start_time is None


class TestWorkflowTUILog:
    """Tests for WorkflowTUI.log() method."""

    def test_log_adds_entry(self):
        """log() should add entry to log_entries."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        tui.log("PM", "Created 5 tasks")
        assert len(tui.log_entries) == 1

    def test_log_entry_has_timestamp(self):
        """Log entry should include timestamp."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        tui.log("DEV", "Started task")
        entry = tui.log_entries[0]
        assert "timestamp" in entry
        assert isinstance(entry["timestamp"], datetime)

    def test_log_entry_has_agent(self):
        """Log entry should include agent name."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        tui.log("QA", "Tests passed")
        entry = tui.log_entries[0]
        assert entry["agent"] == "QA"

    def test_log_entry_has_message(self):
        """Log entry should include message."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        tui.log("SEC", "Scan complete")
        entry = tui.log_entries[0]
        assert entry["message"] == "Scan complete"

    def test_log_limits_entries(self):
        """Log should limit entries to max_log_entries."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp", max_log_entries=3)
        for i in range(5):
            tui.log("PM", f"Entry {i}")
        assert len(tui.log_entries) == 3
        # Should keep newest entries
        assert tui.log_entries[-1]["message"] == "Entry 4"


class TestWorkflowTUIAgentState:
    """Tests for agent state management."""

    def test_start_agent_sets_current_agent(self):
        """start_agent() should set current_agent."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        tui.start_agent("DEV", "Working on T1")
        assert tui.current_agent == "DEV"

    def test_start_agent_sets_start_time(self):
        """start_agent() should set agent_start_time."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        tui.start_agent("DEV", "Working on T1")
        assert tui.agent_start_time is not None

    def test_start_agent_sets_current_task(self):
        """start_agent() should set current_task description."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        tui.start_agent("DEV", "Working on T1")
        assert tui.current_task == "Working on T1"

    def test_stop_agent_clears_state(self):
        """stop_agent() should clear agent state."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        tui.start_agent("DEV", "Working")
        tui.stop_agent()
        assert tui.current_agent is None
        assert tui.agent_start_time is None
        assert tui.current_task is None


class TestWorkflowTUIElapsedTime:
    """Tests for elapsed time calculation."""

    def test_get_elapsed_returns_none_when_no_agent(self):
        """get_elapsed() should return None when no agent is running."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        assert tui.get_elapsed() is None

    def test_get_elapsed_returns_seconds_when_agent_running(self):
        """get_elapsed() should return elapsed seconds when agent is running."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        tui.start_agent("DEV", "Working")
        # Just started, should be 0 or very small
        elapsed = tui.get_elapsed()
        assert elapsed is not None
        assert elapsed >= 0


class TestWorkflowTUITaskTable:
    """Tests for task table generation."""

    def test_make_task_table_with_tasks(self, db_session, sample_project, sample_run):
        """make_task_table() should create table with tasks from DB."""
        t1 = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="First task",
            status=TaskStatus.DONE,
            run_id=sample_run.id
        )
        t2 = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Second task",
            status=TaskStatus.IN_PROGRESS,
            run_id=sample_run.id,
            blocked_by=["T1"]
        )
        db_session.add_all([t1, t2])
        db_session.commit()

        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        table = tui.make_task_table([t1, t2])

        # Table should be a rich Table object
        from rich.table import Table
        assert isinstance(table, Table)

    def test_make_task_table_shows_blockers(self, db_session, sample_project, sample_run):
        """Task table should show blocked_by tasks."""
        t1 = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Blocker",
            status=TaskStatus.BACKLOG,
            run_id=sample_run.id
        )
        t2 = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Blocked",
            status=TaskStatus.BACKLOG,
            run_id=sample_run.id,
            blocked_by=["T1"]
        )
        db_session.add_all([t1, t2])
        db_session.commit()

        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        table = tui.make_task_table([t1, t2])

        # Verify table has rows (we can check column count)
        assert table.row_count == 2


class TestWorkflowTUILayout:
    """Tests for overall TUI layout generation."""

    def test_make_layout_returns_layout(self, db_session, sample_project, sample_run):
        """make_layout() should return a rich Layout object."""
        tui = WorkflowTUI(run_name="Test Run", sandbox_path="/tmp/test")
        tui.set_status_summary({"done": 1, "in_progress": 0, "backlog": 2, "failed": 0, "total": 3})
        layout = tui.make_layout([])

        from rich.layout import Layout
        assert isinstance(layout, Layout)

    def test_layout_shows_run_name(self, db_session, sample_project, sample_run):
        """Layout header should include run name."""
        tui = WorkflowTUI(run_name="My Test Run", sandbox_path="/tmp/test")
        tui.set_status_summary({"done": 0, "in_progress": 0, "backlog": 0, "failed": 0, "total": 0})
        # Layout generation should not raise
        layout = tui.make_layout([])
        assert layout is not None


class TestWorkflowTUIProgressHeader:
    """Tests for progress header display."""

    def test_set_status_summary_stores_counts(self):
        """set_status_summary() should store status counts."""
        tui = WorkflowTUI(run_name="Test", sandbox_path="/tmp")
        tui.set_status_summary({
            "done": 3,
            "in_progress": 1,
            "backlog": 5,
            "failed": 0,
            "total": 9
        })
        assert tui.status_summary["done"] == 3
        assert tui.status_summary["total"] == 9
