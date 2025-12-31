"""Task model."""
import enum
from typing import List, Optional
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, Table, JSON, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Session
from app.db import Base


class TaskStatus(enum.Enum):
    """Task status values."""
    BACKLOG = "backlog"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"  # Added for workflow queue


class TaskPipelineStage(enum.Enum):
    """Pipeline stage a task is currently in.

    Each stage has a value (db storage) and a label (UI display).
    When adding new stages, add them here and the UI will auto-update.

    Pipeline flow: NONE → PM → DEV → QA → SEC → DOCS → COMPLETE

    NOTE: Values must be UPPERCASE to match PostgreSQL native enum storage.
    """
    NONE = "NONE"  # Not in pipeline yet (backlog)
    PM = "PM"  # Being planned/defined by PM agent (requirements, acceptance criteria)
    DEV = "DEV"  # Being implemented by DEV agent
    QA = "QA"  # Being tested by QA agent
    SEC = "SEC"  # Being reviewed by Security agent
    DOCS = "DOCS"  # Documentation stage
    COMPLETE = "COMPLETE"  # Passed all stages

    @property
    def label(self) -> str:
        """Human-readable label for UI display."""
        labels = {
            'NONE': 'Backlog',
            'PM': 'Planning (PM)',
            'DEV': 'Development',
            'QA': 'QA',
            'SEC': 'Security',
            'DOCS': 'Documentation',
            'COMPLETE': 'Complete',
        }
        return labels.get(self.value, self.name.title())

    @classmethod
    def get_stage_map(cls) -> dict:
        """Build stage map for API lookups (case-insensitive).

        Returns dict mapping uppercase stage values to enum members.
        Use: stage_map = TaskPipelineStage.get_stage_map()
             stage = stage_map.get(user_input.upper())
        """
        return {stage.value.upper(): stage for stage in cls}

    @classmethod
    def valid_stages(cls) -> list:
        """Return list of valid stage values (lowercase for display)."""
        return [stage.value.lower() for stage in cls]


# Association table for Task <-> Requirement many-to-many
task_requirements = Table(
    "task_requirements",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("tasks.id"), primary_key=True),
    Column("requirement_id", Integer, ForeignKey("requirements.id"), primary_key=True),
)


class Task(Base):
    """A task (T1, T2, etc.) linked to requirements."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    task_id = Column(String(20), nullable=False)  # e.g., "T1", "T2"
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    acceptance_criteria = Column(JSON, default=list)  # List of testable criteria
    status = Column(Enum(TaskStatus), default=TaskStatus.BACKLOG)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Workflow queue fields
    priority = Column(Integer, default=5)  # 1-10, higher = more important
    blocked_by = Column(JSON, default=list)  # List of task_ids that must complete first
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=True)  # Link to workflow run
    pipeline_stage = Column(Enum(TaskPipelineStage), default=TaskPipelineStage.NONE)  # Current pipeline stage
    completed = Column(Boolean, default=False)  # Explicit completion flag for memory/history
    completed_at = Column(DateTime(timezone=True), nullable=True)  # When task was completed

    # Relationships
    project = relationship("Project", back_populates="tasks")
    requirements = relationship("Requirement", secondary=task_requirements, back_populates="tasks")
    run = relationship("Run", backref="tasks")

    def is_blocked(self, session: Session) -> bool:
        """Check if this task is blocked by incomplete dependencies.

        Args:
            session: SQLAlchemy session for querying dependency status

        Returns:
            True if any dependency task is not DONE, False otherwise
        """
        if not self.blocked_by:
            return False

        # Query for all blocking tasks that are not DONE
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
            "pipeline_stage": self.pipeline_stage.value if self.pipeline_stage else "none",
            "priority": self.priority,
            "blocked_by": self.blocked_by or [],
            "run_id": self.run_id,
            "completed": self.completed,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "requirement_ids": [r.req_id for r in self.requirements],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
