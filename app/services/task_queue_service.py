"""Task Queue Service - Priority-based task queue with dependency management.

Uses database-backed Task model for persistence and dependency tracking.
NOTE: Refactored to work with project_id instead of run_id (Task.run_id removed in refactor).
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Task, TaskStatus


class TaskQueueService:
    """Service for managing task queue with priorities and dependencies.

    NOTE: This service now operates on project_id instead of run_id.
    The run_id parameter is kept for backward compatibility but is used
    to look up the associated project.
    """

    def __init__(self, session: Session, run_id: int = None, project_id: int = None):
        """Initialize service with database session and run/project ID.

        Args:
            session: SQLAlchemy session for database operations
            run_id: ID of the workflow run (used to look up project)
            project_id: ID of the project to manage tasks for (preferred)
        """
        self.session = session
        self.run_id = run_id

        # Resolve project_id from run_id if not provided directly
        if project_id:
            self.project_id = project_id
        elif run_id:
            from app.models.run import Run
            run = session.query(Run).filter(Run.id == run_id).first()
            self.project_id = run.project_id if run else None
        else:
            self.project_id = None

    def get_next_task(self) -> Optional[Task]:
        """Get the highest priority unblocked task.

        Returns:
            The next task to work on, or None if no tasks available
        """
        if not self.project_id:
            return None

        # Get all backlog tasks for this project, ordered by priority (highest first)
        candidates = self.session.query(Task).filter(
            Task.project_id == self.project_id,
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
        if not self.project_id:
            return

        task = self.session.query(Task).filter(
            Task.project_id == self.project_id,
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
        if not self.project_id:
            return

        task = self.session.query(Task).filter(
            Task.project_id == self.project_id,
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
        if not self.project_id:
            return

        task = self.session.query(Task).filter(
            Task.project_id == self.project_id,
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
        summary = {
            "done": 0,
            "in_progress": 0,
            "backlog": 0,
            "blocked": 0,
            "failed": 0,
            "total": 0
        }

        if not self.project_id:
            return summary

        counts = self.session.query(
            Task.status,
            func.count(Task.id)
        ).filter(
            Task.project_id == self.project_id
        ).group_by(Task.status).all()

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
        """Get all tasks for this project, ordered by priority (highest first).

        Returns:
            List of Task objects
        """
        if not self.project_id:
            return []

        return self.session.query(Task).filter(
            Task.project_id == self.project_id
        ).order_by(Task.priority.desc()).all()
