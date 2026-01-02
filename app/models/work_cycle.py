"""WorkCycle model for tracking agent work cycles.

WorkCycles represent a complete work cycle: context → work → report.
They are task-centric, allowing tasks to progress independently through the pipeline.

Key relationships:
- task_id: Required - work_cycles attach to tasks
- run_id: Optional - which run triggered this (context only)
- project_id: Required - for project-level queries

Lifecycle:
- PENDING: Waiting for agent to accept
- IN_PROGRESS: Agent is working
- COMPLETED: Agent submitted report (pass or fail)
- FAILED: Agent timed out or errored
- SKIPPED: Manually skipped by human
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship
import enum

from app.db import Base


class WorkCycleStatus(enum.Enum):
    """WorkCycle lifecycle states."""
    PENDING = "pending"          # Waiting for agent to accept
    IN_PROGRESS = "in_progress"  # Agent is working
    COMPLETED = "completed"      # Agent submitted report
    FAILED = "failed"            # Agent timed out or errored
    SKIPPED = "skipped"          # Manually skipped by human


class WorkCycle(Base):
    """A work_cycle represents one agent's work cycle on a task.

    Each time a task moves to a new pipeline stage, a work_cycle is created.
    The work_cycle tracks:
    - What context was given to the agent
    - What report the agent submitted
    - The lifecycle (pending → in_progress → completed)
    """
    __tablename__ = "work_cycles"

    id = Column(Integer, primary_key=True)

    # Relationships - task is primary, run/project for context
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=True, index=True)

    # Workflow
    from_role = Column(String(50), nullable=True)   # Who handed off (null if first)
    to_role = Column(String(50), nullable=False)    # Who should pick up (dev, qa, sec, docs, pm)
    stage = Column(String(50), nullable=False, index=True)  # Pipeline stage
    status = Column(SQLEnum(WorkCycleStatus), default=WorkCycleStatus.PENDING, index=True)

    # Context (what the agent receives)
    context = Column(JSON, nullable=True)           # Structured context for agent
    context_markdown = Column(Text, nullable=True)  # Full markdown context (stored in DB)
    context_file = Column(Text, nullable=True)      # Optional file path (backup)

    # Report (what the agent submits)
    report = Column(JSON, nullable=True)            # Agent's final report details
    report_status = Column(String(20), nullable=True)  # pass/fail
    report_summary = Column(Text, nullable=True)    # Summary of what agent did

    # Optional link to AgentReport for backward compatibility
    agent_report_id = Column(Integer, ForeignKey("agent_reports.id"), nullable=True)

    # Metadata
    created_by = Column(String(100), default="system")  # system, human, auto-trigger
    accepted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("Project", backref="work_cycles")
    task = relationship("Task", backref="work_cycles")
    run = relationship("Run", backref="work_cycles")
    agent_report = relationship("AgentReport", backref="work_cycle")

    def to_dict(self):
        """Full format for API responses."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "from_role": self.from_role,
            "to_role": self.to_role,
            "stage": self.stage,
            "status": self.status.value if self.status else None,
            "context": self.context,
            "context_markdown": self.context_markdown,
            "context_file": self.context_file,
            "report": self.report,
            "report_status": self.report_status,
            "report_summary": self.report_summary,
            "agent_report_id": self.agent_report_id,
            "created_by": self.created_by,
            "accepted_at": self.accepted_at.isoformat() if self.accepted_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_agent_context(self):
        """Compact format for agent memory/queries.

        Returns minimal info for listing work_cycle history.
        Use context_markdown for full context when working.
        """
        return {
            "id": self.id,
            "stage": self.stage,
            "to_role": self.to_role,
            "status": self.status.value if self.status else None,
            "report_status": self.report_status,
            "report_summary": self.report_summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def __repr__(self):
        return f"<WorkCycle {self.id}: task={self.task_id} stage={self.stage} to={self.to_role} status={self.status.value if self.status else None}>"
