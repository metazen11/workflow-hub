"""Task model - Simplified for core refactor.

Tasks are the primary unit of work. They:
- Belong to a Project
- Have Claims that define what must be true when done
- Have WorkCycles that track agent work sessions
- Have simple states: BACKLOG → IN_PROGRESS → VALIDATING → DONE

No more pipeline stages (PM, DEV, QA, SEC). Claims define validation.
"""
import enum
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, JSON, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Session
from app.db import Base


class TaskStatus(enum.Enum):
    """Task status values - simplified."""
    BACKLOG = "backlog"          # Not started
    IN_PROGRESS = "in_progress"  # Agent working
    VALIDATING = "validating"    # Running claim tests
    BLOCKED = "blocked"          # Waiting on dependencies
    DONE = "done"                # Complete, claims validated
    FAILED = "failed"            # Claims failed, needs investigation


class Task(Base):
    """A task - the primary unit of work."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    task_id = Column(String(20), nullable=False)  # e.g., "T001", "T002"
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.BACKLOG)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Priority and blocking
    priority = Column(Integer, default=5)  # 1-10, higher = more important
    blocked_by = Column(JSON, default=list)  # List of task_ids that must complete first

    # Completion tracking
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Claim validation summary (denormalized for quick access)
    claims_total = Column(Integer, default=0)
    claims_validated = Column(Integer, default=0)
    claims_failed = Column(Integer, default=0)

    # Relationships
    project = relationship("Project", back_populates="tasks")
    # work_cycles and claims relationships defined via backref

    def is_blocked(self, session: Session) -> bool:
        """Check if this task is blocked by incomplete dependencies."""
        if not self.blocked_by:
            return False

        blocking_tasks = session.query(Task).filter(
            Task.project_id == self.project_id,
            Task.task_id.in_(self.blocked_by),
            Task.status != TaskStatus.DONE
        ).count()

        return blocking_tasks > 0

    def to_dict(self) -> dict:
        """Serialize task to dictionary."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value if self.status else None,
            "priority": self.priority,
            "blocked_by": self.blocked_by or [],
            "completed": self.completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "claims_total": self.claims_total,
            "claims_validated": self.claims_validated,
            "claims_failed": self.claims_failed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_summary(self) -> dict:
        """Compact format for listings."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "title": self.title,
            "status": self.status.value if self.status else None,
            "priority": self.priority,
            "claims_total": self.claims_total,
            "claims_validated": self.claims_validated,
        }
