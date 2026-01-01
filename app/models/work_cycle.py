"""WorkCycle model for tracking agent work sessions.

WorkCycles represent a complete work session: context → work → artifacts → claim validation.
This is the renamed/simplified version of the Handoff model.

Key relationships:
- task_id: Required - work cycles attach to tasks
- project_id: Required - for project-level queries

Lifecycle:
- PENDING: Waiting for agent to start
- IN_PROGRESS: Agent is working
- VALIDATING: Running claim tests
- COMPLETED: Agent finished, claims validated
- FAILED: Agent errored or claims failed
- SKIPPED: Manually skipped by human
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
import enum

from app.db import Base


class WorkCycleStatus(enum.Enum):
    """WorkCycle lifecycle states."""
    PENDING = "pending"          # Waiting for agent to start
    IN_PROGRESS = "in_progress"  # Agent is working
    VALIDATING = "validating"    # Running claim tests
    COMPLETED = "completed"      # Agent finished successfully
    FAILED = "failed"            # Agent errored or claims failed
    SKIPPED = "skipped"          # Manually skipped by human


class WorkCycle(Base):
    """A work cycle represents one agent's work session on a task.

    Each time a task is started, a work cycle is created.
    The work cycle tracks:
    - What context was given to the agent
    - What artifacts the agent produced
    - Claim test results
    """
    __tablename__ = "work_cycles"

    id = Column(Integer, primary_key=True)

    # Relationships - task is primary
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)

    # Workflow
    agent_role = Column(String(50), nullable=True)   # Which agent worked (dev, qa, sec, etc.)
    status = Column(SQLEnum(WorkCycleStatus), default=WorkCycleStatus.PENDING, index=True)

    # Context (what the agent receives)
    context = Column(JSON, nullable=True)           # Structured context for agent
    context_markdown = Column(Text, nullable=True)  # Full markdown context

    # Artifacts (what the agent produces)
    artifacts = Column(JSON, nullable=True)         # List of file paths, outputs, etc.
    summary = Column(Text, nullable=True)           # Summary of what agent did

    # Claim validation results
    claim_results = Column(JSON, nullable=True)     # Test results for all claims
    claims_passed = Column(Integer, default=0)
    claims_failed = Column(Integer, default=0)

    # Metadata
    created_by = Column(String(100), default="system")  # system, human, auto-trigger
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("Project", backref="work_cycles")
    task = relationship("Task", backref="work_cycles")

    def to_dict(self):
        """Full format for API responses."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "agent_role": self.agent_role,
            "status": self.status.value if self.status else None,
            "context": self.context,
            "context_markdown": self.context_markdown,
            "artifacts": self.artifacts,
            "summary": self.summary,
            "claim_results": self.claim_results,
            "claims_passed": self.claims_passed,
            "claims_failed": self.claims_failed,
            "created_by": self.created_by,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_summary(self):
        """Compact format for listings."""
        return {
            "id": self.id,
            "agent_role": self.agent_role,
            "status": self.status.value if self.status else None,
            "summary": self.summary,
            "claims_passed": self.claims_passed,
            "claims_failed": self.claims_failed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def __repr__(self):
        return f"<WorkCycle {self.id}: task={self.task_id} agent={self.agent_role} status={self.status.value if self.status else None}>"
