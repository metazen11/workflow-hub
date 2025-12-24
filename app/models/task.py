"""Task model."""
import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, Table
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db import Base


class TaskStatus(enum.Enum):
    """Task status values."""
    BACKLOG = "backlog"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"


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
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.BACKLOG)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="tasks")
    requirements = relationship("Requirement", secondary=task_requirements, back_populates="tasks")

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value if self.status else None,
            "requirement_ids": [r.req_id for r in self.requirements],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
