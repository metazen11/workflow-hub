"""Task Queue Service - Priority-based task queue with dependency management.

Uses database-backed Task model for persistence and dependency tracking.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Task, TaskStatus


class TaskQueueService:
    """Service for managing task queue with priorities and dependencies."""

    def __init__(self, session: Session, run_id: int):
        """Initialize service with database session and run ID.

        Args:
            session: SQLAlchemy session for database operations
            run_id: ID of the workflow run to manage tasks for
        """
        self.session = session
        self.run_id = run_id

    def get_next_task(self) -> Optional[Task]:
        """Get the highest priority unblocked task.

        Returns:
            The next task to work on, or None if no tasks available
        """
        # Get all backlog tasks for this run, ordered by priority (highest first)
        candidates = self.session.query(Task).filter(
            Task.run_id == self.run_id,
            Task.status == TaskStatus.BACKLOG
        ).order_by(Task.priority.desc()).all()

        # Find first unblocked task
        for task in candidates:
            if not task.is_blocked(self.session):
                return task

        return None

    def mark_completed(self, task_id: str) -> None:
        """Mark a task as completed.

        Args:
            task_id: The task_id (e.g., "T1") to mark as done
        """
        task = self.session.query(Task).filter(
            Task.run_id == self.run_id,
            Task.task_id == task_id
        ).first()

        if task:
            task.status = TaskStatus.DONE
            task.completed = True
            self.session.commit()

    def mark_failed(self, task_id: str) -> None:
        """Mark a task as failed.

        Args:
            task_id: The task_id (e.g., "T1") to mark as failed
        """
        task = self.session.query(Task).filter(
            Task.run_id == self.run_id,
            Task.task_id == task_id
        ).first()

        if task:
            task.status = TaskStatus.FAILED
            self.session.commit()

    def mark_in_progress(self, task_id: str) -> None:
        """Mark a task as in progress.

        Args:
            task_id: The task_id (e.g., "T1") to mark as in progress
        """
        task = self.session.query(Task).filter(
            Task.run_id == self.run_id,
            Task.task_id == task_id
        ).first()

        if task:
            task.status = TaskStatus.IN_PROGRESS
            self.session.commit()

    def get_status_summary(self) -> dict:
        """Get count of tasks in each status.

        Returns:
            Dict with counts: {done, in_progress, backlog, failed, total}
        """
        counts = self.session.query(
            Task.status,
            func.count(Task.id)
        ).filter(
            Task.run_id == self.run_id
        ).group_by(Task.status).all()

        summary = {
            "done": 0,
            "in_progress": 0,
            "backlog": 0,
            "blocked": 0,
            "failed": 0,
            "total": 0
        }

        for status, count in counts:
            if status == TaskStatus.DONE:
                summary["done"] = count
            elif status == TaskStatus.IN_PROGRESS:
                summary["in_progress"] = count
            elif status == TaskStatus.BACKLOG:
                summary["backlog"] = count
            elif status == TaskStatus.BLOCKED:
                summary["blocked"] = count
            elif status == TaskStatus.FAILED:
                summary["failed"] = count
            summary["total"] += count

        return summary

    def get_all_tasks(self) -> List[Task]:
        """Get all tasks for this run, ordered by priority (highest first).

        Returns:
            List of Task objects
        """
        return self.session.query(Task).filter(
            Task.run_id == self.run_id
        ).order_by(Task.priority.desc()).all()
