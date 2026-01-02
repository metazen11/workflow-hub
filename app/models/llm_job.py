"""LLM Job Queue Model.

Database-backed job queue for managing LLM requests and agent runs.
Provides priority-based queuing to prevent resource contention.
"""
import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON, Enum
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db import Base


class JobType(enum.Enum):
    """Type of job in the queue."""
    LLM_COMPLETE = "llm_complete"      # Simple completion
    LLM_CHAT = "llm_chat"              # Chat with message history
    LLM_QUERY = "llm_query"            # Contextual query
    VISION_ANALYZE = "vision_analyze"  # Image analysis
    AGENT_RUN = "agent_run"            # Goose agent execution


class JobStatus(enum.Enum):
    """Status of a queued job."""
    PENDING = "pending"      # Waiting in queue
    RUNNING = "running"      # Currently executing
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"        # Finished with error
    CANCELLED = "cancelled"  # Cancelled by user
    TIMEOUT = "timeout"      # Exceeded timeout


class JobPriority:
    """Priority levels for jobs (lower number = higher priority)."""
    CRITICAL = 1   # User-facing, blocking UI
    HIGH = 2       # Agent work cycles, pipeline advancement
    NORMAL = 3     # Background enrichment, doc generation
    LOW = 4        # Vision preprocessing, optional analysis


class LLMJob(Base):
    """A job in the LLM/Agent processing queue."""
    __tablename__ = "llm_jobs"

    id = Column(Integer, primary_key=True, index=True)

    # Job type and status
    job_type = Column(String(50), nullable=False)  # JobType.value
    status = Column(String(20), default="pending")  # JobStatus.value
    priority = Column(Integer, default=3)  # 1=highest, 4=lowest

    # Request data (serialized)
    request_data = Column(JSON, nullable=False)

    # Context (optional links)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("llm_sessions.id"), nullable=True)

    # Result data
    result_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    # Timing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    timeout_seconds = Column(Integer, default=300)  # 5 minutes default

    # Tracking
    worker_id = Column(String(50), nullable=True)  # Which worker picked this up
    position_at_creation = Column(Integer, nullable=True)  # Queue position when created

    # Relationships
    project = relationship("Project", foreign_keys=[project_id])
    task = relationship("Task", foreign_keys=[task_id])

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "priority": self.priority,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "result_data": self.result_data,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "timeout_seconds": self.timeout_seconds,
            "worker_id": self.worker_id,
            "position_at_creation": self.position_at_creation,
        }

    @property
    def is_terminal(self) -> bool:
        """Check if job is in a terminal state."""
        return self.status in (
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.CANCELLED.value,
            JobStatus.TIMEOUT.value
        )

    @property
    def wait_time_seconds(self) -> float:
        """Time spent waiting in queue (before started)."""
        if not self.started_at:
            return (datetime.utcnow() - self.created_at.replace(tzinfo=None)).total_seconds()
        return (self.started_at.replace(tzinfo=None) - self.created_at.replace(tzinfo=None)).total_seconds()

    @property
    def run_time_seconds(self) -> float:
        """Time spent running (after started)."""
        if not self.started_at:
            return 0
        end_time = self.completed_at or datetime.utcnow()
        if hasattr(end_time, 'replace'):
            end_time = end_time.replace(tzinfo=None)
        return (end_time - self.started_at.replace(tzinfo=None)).total_seconds()
