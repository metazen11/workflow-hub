"""Run model with state machine."""
import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db import Base


class RunState(enum.Enum):
    """Run states in the workflow pipeline."""
    PM = "pm"
    DEV = "dev"
    QA = "qa"
    QA_FAILED = "qa_failed"
    SEC = "sec"
    SEC_FAILED = "sec_failed"
    READY_FOR_COMMIT = "ready_for_commit"
    MERGED = "merged"
    READY_FOR_DEPLOY = "ready_for_deploy"
    DEPLOYED = "deployed"


# Valid state transitions
VALID_TRANSITIONS = {
    RunState.PM: [RunState.DEV],
    RunState.DEV: [RunState.QA],
    RunState.QA: [RunState.SEC, RunState.QA_FAILED],
    RunState.QA_FAILED: [RunState.QA],  # retry
    RunState.SEC: [RunState.READY_FOR_COMMIT, RunState.SEC_FAILED],
    RunState.SEC_FAILED: [RunState.SEC],  # retry
    RunState.READY_FOR_COMMIT: [RunState.MERGED],
    RunState.MERGED: [RunState.READY_FOR_DEPLOY],
    RunState.READY_FOR_DEPLOY: [RunState.DEPLOYED],  # requires human approval
    RunState.DEPLOYED: [],
}


class Run(Base):
    """A development run through the pipeline."""
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(100), nullable=False)  # e.g., "Run 2025-12-24_01"
    state = Column(Enum(RunState), default=RunState.PM)

    # Artifact storage
    pm_result = Column(JSON, nullable=True)
    dev_result = Column(JSON, nullable=True)
    qa_result = Column(JSON, nullable=True)
    sec_result = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="runs")
    reports = relationship("AgentReport", back_populates="run", cascade="all, delete-orphan")

    def can_transition_to(self, new_state: RunState) -> bool:
        """Check if transition to new_state is valid."""
        return new_state in VALID_TRANSITIONS.get(self.state, [])

    def transition_to(self, new_state: RunState) -> bool:
        """Attempt to transition to new state. Returns True if successful."""
        if self.can_transition_to(new_state):
            self.state = new_state
            return True
        return False

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "state": self.state.value if self.state else None,
            "pm_result": self.pm_result,
            "dev_result": self.dev_result,
            "qa_result": self.qa_result,
            "sec_result": self.sec_result,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
