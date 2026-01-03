"""Tests for Task queue functionality - priority and blocked_by fields.

TDD: These tests are written FIRST. They should FAIL until we extend the Task model.
"""
import pytest
from app.models import Task, TaskStatus


class TestTaskPriority:
    """Tests for Task priority field."""

    def test_task_has_priority_field(self, db_session, sample_project):
        """Task should have a priority field (1-10, higher = more important)."""
        task = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="High priority task",
            priority=8
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.priority == 8

    def test_task_priority_default_is_5(self, db_session, sample_project):
        """Task should default to priority 5 if not specified."""
        task = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Default priority task"
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.priority == 5

    def test_task_priority_in_to_dict(self, db_session, sample_project):
        """Task.to_dict() should include priority."""
        task = Task(
            project_id=sample_project.id,
            task_id="T3",
            title="Serializable task",
            priority=10
        )
        db_session.add(task)
        db_session.commit()

        data = task.to_dict()
        assert "priority" in data
        assert data["priority"] == 10


class TestTaskBlockedBy:
    """Tests for Task blocked_by field (dependencies)."""

    def test_task_has_blocked_by_field(self, db_session, sample_project):
        """Task should have a blocked_by field (list of task IDs)."""
        task = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Dependent task",
            blocked_by=["T1"]
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.blocked_by == ["T1"]

    def test_task_blocked_by_default_is_empty(self, db_session, sample_project):
        """Task should default to empty blocked_by list."""
        task = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Independent task"
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.blocked_by == [] or task.blocked_by is None

    def test_task_blocked_by_multiple_dependencies(self, db_session, sample_project):
        """Task can be blocked by multiple other tasks."""
        task = Task(
            project_id=sample_project.id,
            task_id="T3",
            title="Multi-dependent task",
            blocked_by=["T1", "T2"]
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert "T1" in task.blocked_by
        assert "T2" in task.blocked_by

    def test_task_blocked_by_in_to_dict(self, db_session, sample_project):
        """Task.to_dict() should include blocked_by."""
        task = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Serializable dependent task",
            blocked_by=["T1"]
        )
        db_session.add(task)
        db_session.commit()

        data = task.to_dict()
        assert "blocked_by" in data
        assert data["blocked_by"] == ["T1"]


class TestTaskIsBlocked:
    """Tests for Task.is_blocked() method."""

    def test_is_blocked_when_dependency_not_done(self, db_session, sample_project):
        """Task is blocked if any dependency is not DONE."""
        t1 = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="First task",
            status=TaskStatus.BACKLOG
        )
        t2 = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Second task",
            blocked_by=["T1"]
        )
        db_session.add_all([t1, t2])
        db_session.commit()

        assert t2.is_blocked(db_session) is True

    def test_not_blocked_when_dependency_done(self, db_session, sample_project):
        """Task is not blocked if all dependencies are DONE."""
        t1 = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="First task",
            status=TaskStatus.DONE
        )
        t2 = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Second task",
            blocked_by=["T1"]
        )
        db_session.add_all([t1, t2])
        db_session.commit()

        assert t2.is_blocked(db_session) is False

    def test_not_blocked_when_no_dependencies(self, db_session, sample_project):
        """Task with no dependencies is never blocked."""
        task = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Independent task"
        )
        db_session.add(task)
        db_session.commit()

        assert task.is_blocked(db_session) is False

    def test_blocked_when_one_of_multiple_dependencies_not_done(self, db_session, sample_project):
        """Task is blocked if ANY dependency is not done."""
        t1 = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="First task",
            status=TaskStatus.DONE
        )
        t2 = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Second task",
            status=TaskStatus.IN_PROGRESS  # Not done!
        )
        t3 = Task(
            project_id=sample_project.id,
            task_id="T3",
            title="Third task",
            blocked_by=["T1", "T2"]
        )
        db_session.add_all([t1, t2, t3])
        db_session.commit()

        assert t3.is_blocked(db_session) is True


class TestTaskProjectLink:
    """Tests for Task.project_id field (link to project).

    NOTE: Task.run_id was removed in refactor. Tasks are now linked
    to projects only, not to individual runs.
    """

    def test_task_has_project_id_field(self, db_session, sample_project):
        """Task must be linked to a Project."""
        task = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Project-linked task"
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.project_id == sample_project.id

    def test_task_project_id_required(self, db_session):
        """Task.project_id is required (not nullable)."""
        # Creating task without project_id should fail
        import pytest
        task = Task(
            task_id="T1",
            title="No-project task"
        )
        db_session.add(task)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()


class TestTaskStatusFailed:
    """Tests for FAILED status in TaskStatus enum."""

    def test_task_status_has_failed(self):
        """TaskStatus enum should include FAILED."""
        assert hasattr(TaskStatus, 'FAILED')
        assert TaskStatus.FAILED.value == "failed"

    def test_task_can_be_marked_failed(self, db_session, sample_project):
        """Task can be set to FAILED status."""
        task = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Failing task",
            status=TaskStatus.FAILED
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.status == TaskStatus.FAILED


class TestTaskCompleted:
    """Tests for completed boolean and completed_at timestamp."""

    def test_task_has_completed_field(self, db_session, sample_project):
        """Task should have a completed boolean field."""
        task = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Test task",
            completed=False
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.completed is False

    def test_task_completed_default_is_false(self, db_session, sample_project):
        """Task.completed should default to False."""
        task = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Default completed task"
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.completed is False

    def test_completed_at_auto_set_when_completed_true(self, db_session, sample_project):
        """completed_at should be auto-set by DB trigger when completed=true."""
        task = Task(
            project_id=sample_project.id,
            task_id="T3",
            title="Task to complete"
        )
        db_session.add(task)
        db_session.commit()

        # Initially no completed_at
        assert task.completed_at is None

        # Set completed to true
        task.completed = True
        db_session.commit()
        db_session.refresh(task)

        # completed_at should now be set by the DB trigger
        assert task.completed_at is not None

    def test_completed_in_to_dict(self, db_session, sample_project):
        """Task.to_dict() should include completed and completed_at."""
        task = Task(
            project_id=sample_project.id,
            task_id="T4",
            title="Serializable task"
        )
        db_session.add(task)
        db_session.commit()

        data = task.to_dict()
        assert "completed" in data
        assert "completed_at" in data
        assert data["completed"] is False
