"""Tests for TaskQueueService - priority-based task queue with dependencies.

TDD: These tests are written FIRST. They should FAIL until we implement the service.
"""
import pytest
from app.models import Task, TaskStatus, Run
from app.services.task_queue_service import TaskQueueService


class TestGetNextTask:
    """Tests for TaskQueueService.get_next_task()"""

    def test_returns_highest_priority_unblocked_task(self, db_session, sample_project, sample_run):
        """Should return the highest priority task that is not blocked."""
        t1 = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Low priority",
            priority=3,
            run_id=sample_run.id,
            status=TaskStatus.BACKLOG
        )
        t2 = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="High priority",
            priority=10,
            run_id=sample_run.id,
            status=TaskStatus.BACKLOG
        )
        t3 = Task(
            project_id=sample_project.id,
            task_id="T3",
            title="Medium priority",
            priority=5,
            run_id=sample_run.id,
            status=TaskStatus.BACKLOG
        )
        db_session.add_all([t1, t2, t3])
        db_session.commit()

        service = TaskQueueService(db_session, sample_run.id)
        next_task = service.get_next_task()

        assert next_task is not None
        assert next_task.task_id == "T2"  # Highest priority

    def test_skips_blocked_tasks(self, db_session, sample_project, sample_run):
        """Should skip tasks that are blocked by incomplete dependencies."""
        t1 = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Blocker task",
            priority=5,
            run_id=sample_run.id,
            status=TaskStatus.BACKLOG  # Not done, so T2 is blocked
        )
        t2 = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Blocked high priority",
            priority=10,
            run_id=sample_run.id,
            status=TaskStatus.BACKLOG,
            blocked_by=["T1"]
        )
        t3 = Task(
            project_id=sample_project.id,
            task_id="T3",
            title="Unblocked medium priority",
            priority=7,
            run_id=sample_run.id,
            status=TaskStatus.BACKLOG
        )
        db_session.add_all([t1, t2, t3])
        db_session.commit()

        service = TaskQueueService(db_session, sample_run.id)
        next_task = service.get_next_task()

        # Should return T3, not T2 (blocked) or T1 (lower priority than T3)
        assert next_task is not None
        assert next_task.task_id == "T3"

    def test_returns_none_when_queue_empty(self, db_session, sample_project, sample_run):
        """Should return None when no tasks are available."""
        service = TaskQueueService(db_session, sample_run.id)
        next_task = service.get_next_task()

        assert next_task is None

    def test_returns_none_when_all_tasks_blocked(self, db_session, sample_project, sample_run):
        """Should return None when all remaining tasks are blocked."""
        t1 = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="First task",
            priority=5,
            run_id=sample_run.id,
            status=TaskStatus.IN_PROGRESS  # Not done
        )
        t2 = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Blocked by T1",
            priority=10,
            run_id=sample_run.id,
            status=TaskStatus.BACKLOG,
            blocked_by=["T1"]
        )
        db_session.add_all([t1, t2])
        db_session.commit()

        service = TaskQueueService(db_session, sample_run.id)
        next_task = service.get_next_task()

        assert next_task is None  # T1 is in progress, T2 is blocked

    def test_skips_done_and_failed_tasks(self, db_session, sample_project, sample_run):
        """Should not return tasks that are already DONE or FAILED."""
        t1 = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Already done",
            priority=10,
            run_id=sample_run.id,
            status=TaskStatus.DONE
        )
        t2 = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Already failed",
            priority=9,
            run_id=sample_run.id,
            status=TaskStatus.FAILED
        )
        t3 = Task(
            project_id=sample_project.id,
            task_id="T3",
            title="Still pending",
            priority=5,
            run_id=sample_run.id,
            status=TaskStatus.BACKLOG
        )
        db_session.add_all([t1, t2, t3])
        db_session.commit()

        service = TaskQueueService(db_session, sample_run.id)
        next_task = service.get_next_task()

        assert next_task is not None
        assert next_task.task_id == "T3"


class TestMarkCompleted:
    """Tests for TaskQueueService.mark_completed()"""

    def test_marks_task_as_done(self, db_session, sample_project, sample_run):
        """Should set task status to DONE."""
        task = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Task to complete",
            run_id=sample_run.id,
            status=TaskStatus.IN_PROGRESS
        )
        db_session.add(task)
        db_session.commit()

        service = TaskQueueService(db_session, sample_run.id)
        service.mark_completed("T1")

        db_session.refresh(task)
        assert task.status == TaskStatus.DONE

    def test_sets_completed_flag(self, db_session, sample_project, sample_run):
        """Should set completed=True when marking done."""
        task = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Task to complete",
            run_id=sample_run.id,
            status=TaskStatus.IN_PROGRESS
        )
        db_session.add(task)
        db_session.commit()

        service = TaskQueueService(db_session, sample_run.id)
        service.mark_completed("T1")

        db_session.refresh(task)
        assert task.completed is True
        assert task.completed_at is not None  # Trigger should set this

    def test_unblocks_dependent_tasks(self, db_session, sample_project, sample_run):
        """Completing a task should unblock tasks that depend on it."""
        t1 = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Blocker",
            run_id=sample_run.id,
            status=TaskStatus.IN_PROGRESS
        )
        t2 = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Blocked by T1",
            run_id=sample_run.id,
            status=TaskStatus.BACKLOG,
            blocked_by=["T1"]
        )
        db_session.add_all([t1, t2])
        db_session.commit()

        # T2 should be blocked initially
        assert t2.is_blocked(db_session) is True

        service = TaskQueueService(db_session, sample_run.id)
        service.mark_completed("T1")

        # T2 should now be unblocked
        db_session.refresh(t1)
        db_session.refresh(t2)
        assert t2.is_blocked(db_session) is False


class TestMarkFailed:
    """Tests for TaskQueueService.mark_failed()"""

    def test_marks_task_as_failed(self, db_session, sample_project, sample_run):
        """Should set task status to FAILED."""
        task = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Failing task",
            run_id=sample_run.id,
            status=TaskStatus.IN_PROGRESS
        )
        db_session.add(task)
        db_session.commit()

        service = TaskQueueService(db_session, sample_run.id)
        service.mark_failed("T1")

        db_session.refresh(task)
        assert task.status == TaskStatus.FAILED

    def test_failed_task_blocks_dependents(self, db_session, sample_project, sample_run):
        """A failed task should still block dependent tasks."""
        t1 = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Will fail",
            run_id=sample_run.id,
            status=TaskStatus.IN_PROGRESS
        )
        t2 = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Blocked by T1",
            run_id=sample_run.id,
            status=TaskStatus.BACKLOG,
            blocked_by=["T1"]
        )
        db_session.add_all([t1, t2])
        db_session.commit()

        service = TaskQueueService(db_session, sample_run.id)
        service.mark_failed("T1")

        db_session.refresh(t2)
        # T2 should still be blocked because T1 is FAILED, not DONE
        assert t2.is_blocked(db_session) is True


class TestMarkInProgress:
    """Tests for TaskQueueService.mark_in_progress()"""

    def test_marks_task_as_in_progress(self, db_session, sample_project, sample_run):
        """Should set task status to IN_PROGRESS."""
        task = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Starting task",
            run_id=sample_run.id,
            status=TaskStatus.BACKLOG
        )
        db_session.add(task)
        db_session.commit()

        service = TaskQueueService(db_session, sample_run.id)
        service.mark_in_progress("T1")

        db_session.refresh(task)
        assert task.status == TaskStatus.IN_PROGRESS


class TestGetStatusSummary:
    """Tests for TaskQueueService.get_status_summary()"""

    def test_returns_counts_by_status(self, db_session, sample_project, sample_run):
        """Should return count of tasks in each status."""
        tasks = [
            Task(project_id=sample_project.id, task_id="T1", title="Done 1", run_id=sample_run.id, status=TaskStatus.DONE),
            Task(project_id=sample_project.id, task_id="T2", title="Done 2", run_id=sample_run.id, status=TaskStatus.DONE),
            Task(project_id=sample_project.id, task_id="T3", title="In Progress", run_id=sample_run.id, status=TaskStatus.IN_PROGRESS),
            Task(project_id=sample_project.id, task_id="T4", title="Backlog 1", run_id=sample_run.id, status=TaskStatus.BACKLOG),
            Task(project_id=sample_project.id, task_id="T5", title="Backlog 2", run_id=sample_run.id, status=TaskStatus.BACKLOG),
            Task(project_id=sample_project.id, task_id="T6", title="Backlog 3", run_id=sample_run.id, status=TaskStatus.BACKLOG),
            Task(project_id=sample_project.id, task_id="T7", title="Failed", run_id=sample_run.id, status=TaskStatus.FAILED),
        ]
        db_session.add_all(tasks)
        db_session.commit()

        service = TaskQueueService(db_session, sample_run.id)
        summary = service.get_status_summary()

        assert summary["done"] == 2
        assert summary["in_progress"] == 1
        assert summary["backlog"] == 3
        assert summary["failed"] == 1
        assert summary["total"] == 7

    def test_returns_zeros_for_empty_queue(self, db_session, sample_project, sample_run):
        """Should return zeros when no tasks exist."""
        service = TaskQueueService(db_session, sample_run.id)
        summary = service.get_status_summary()

        assert summary["done"] == 0
        assert summary["in_progress"] == 0
        assert summary["backlog"] == 0
        assert summary["failed"] == 0
        assert summary["total"] == 0


class TestGetAllTasks:
    """Tests for TaskQueueService.get_all_tasks()"""

    def test_returns_all_tasks_for_run(self, db_session, sample_project, sample_run):
        """Should return all tasks associated with the run."""
        t1 = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Task 1",
            run_id=sample_run.id
        )
        t2 = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Task 2",
            run_id=sample_run.id
        )
        db_session.add_all([t1, t2])
        db_session.commit()

        service = TaskQueueService(db_session, sample_run.id)
        tasks = service.get_all_tasks()

        assert len(tasks) == 2
        task_ids = [t.task_id for t in tasks]
        assert "T1" in task_ids
        assert "T2" in task_ids

    def test_only_returns_tasks_for_specified_run(self, db_session, sample_project, sample_run):
        """Should not return tasks from other runs."""
        # Create another run
        run2 = Run(
            project_id=sample_project.id,
            name="Run 2025-01-02_01"
        )
        db_session.add(run2)
        db_session.commit()

        t1 = Task(
            project_id=sample_project.id,
            task_id="T1",
            title="Task in run 1",
            run_id=sample_run.id
        )
        t2 = Task(
            project_id=sample_project.id,
            task_id="T2",
            title="Task in run 2",
            run_id=run2.id
        )
        db_session.add_all([t1, t2])
        db_session.commit()

        service = TaskQueueService(db_session, sample_run.id)
        tasks = service.get_all_tasks()

        assert len(tasks) == 1
        assert tasks[0].task_id == "T1"

    def test_returns_tasks_ordered_by_priority(self, db_session, sample_project, sample_run):
        """Should return tasks ordered by priority (highest first)."""
        t1 = Task(project_id=sample_project.id, task_id="T1", title="Low", priority=2, run_id=sample_run.id)
        t2 = Task(project_id=sample_project.id, task_id="T2", title="High", priority=9, run_id=sample_run.id)
        t3 = Task(project_id=sample_project.id, task_id="T3", title="Medium", priority=5, run_id=sample_run.id)
        db_session.add_all([t1, t2, t3])
        db_session.commit()

        service = TaskQueueService(db_session, sample_run.id)
        tasks = service.get_all_tasks()

        assert tasks[0].task_id == "T2"  # Priority 9
        assert tasks[1].task_id == "T3"  # Priority 5
        assert tasks[2].task_id == "T1"  # Priority 2
