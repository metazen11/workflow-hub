"""Proof-of-Work model for tracking agent work artifacts.

Hybrid approach:
- Files stored in filesystem at workspaces/{project}/proof/tasks/{task_id}/
- Metadata tracked in database for querying and agent memory

Proofs are tied to TASKS (not runs) since:
- Tasks are the persistent work unit
- Runs are transient execution instances
- Agents need to see all proof history for a task across all runs
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum

from app.db import Base


class ProofType(enum.Enum):
    """Types of proof artifacts."""
    SCREENSHOT = "screenshot"
    LOG = "log"
    REPORT = "report"
    TEST_RESULT = "test_result"
    CODE_DIFF = "code_diff"
    OTHER = "other"


class Proof(Base):
    """Proof-of-work artifact metadata.

    Tracks evidence that agents produce during pipeline execution.
    Files are stored in filesystem, metadata here for querying.

    Primary relationship is to TASK - runs are tracked for context only.
    """
    __tablename__ = "proofs"

    id = Column(Integer, primary_key=True)

    # Primary relationships - task is required, run is optional context
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)  # Required
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=True, index=True)  # Optional - which run created it

    # Pipeline context
    stage = Column(String(50), nullable=False, index=True)  # dev, qa, sec, docs, pm

    # File info
    filename = Column(String(255), nullable=False)
    filepath = Column(Text, nullable=False)  # Full path to file
    proof_type = Column(SQLEnum(ProofType), default=ProofType.OTHER)
    file_size = Column(Integer, default=0)
    mime_type = Column(String(100), nullable=True)

    # Metadata for agent memory
    description = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)  # AI-generated summary of proof content
    created_by = Column(String(100), default="agent")  # agent, human, system

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("Project", backref="proofs")
    task = relationship("Task", backref="proofs")
    run = relationship("Run", backref="proofs")

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "stage": self.stage,
            "filename": self.filename,
            "filepath": self.filepath,
            "proof_type": self.proof_type.value if self.proof_type else "other",
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "description": self.description,
            "summary": self.summary,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "download_url": f"/api/tasks/{self.task_id}/proofs/{self.id}/download"
        }

    def to_agent_context(self):
        """Compact format for agent memory/context."""
        return {
            "id": self.id,
            "stage": self.stage,
            "type": self.proof_type.value if self.proof_type else "other",
            "filename": self.filename,
            "summary": self.summary or self.description or self.filename,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Proof {self.id}: {self.filename} (task={self.task_id}, stage={self.stage})>"
