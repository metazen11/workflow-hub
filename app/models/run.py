"""Run model with state machine."""
import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, JSON, Boolean
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
    DOCS = "docs"  # Documentation stage
    DOCS_FAILED = "docs_failed"
    READY_FOR_COMMIT = "ready_for_commit"
    MERGED = "merged"
    READY_FOR_DEPLOY = "ready_for_deploy"
    TESTING = "testing"  # Production testing via Playwright
    TESTING_FAILED = "testing_failed"
    DEPLOYED = "deployed"


# Valid state transitions
VALID_TRANSITIONS = {
    RunState.PM: [RunState.DEV],
    RunState.DEV: [RunState.QA],
    RunState.QA: [RunState.SEC, RunState.QA_FAILED],
    RunState.QA_FAILED: [RunState.DEV],  # retry goes back to dev
    RunState.SEC: [RunState.DOCS, RunState.SEC_FAILED],
    RunState.SEC_FAILED: [RunState.DEV],  # security issues go back to dev
    RunState.DOCS: [RunState.READY_FOR_COMMIT, RunState.DOCS_FAILED],
    RunState.DOCS_FAILED: [RunState.DOCS],  # retry docs
    RunState.READY_FOR_COMMIT: [RunState.MERGED],
    RunState.MERGED: [RunState.READY_FOR_DEPLOY],
    RunState.READY_FOR_DEPLOY: [RunState.TESTING],  # deploy then test
    RunState.TESTING: [RunState.DEPLOYED, RunState.TESTING_FAILED],
    RunState.TESTING_FAILED: [RunState.DEV],  # production issues go back to dev
    RunState.DEPLOYED: [],
}


class Run(Base):
    """A development run through the pipeline."""
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(500), nullable=False)  # e.g., "Run 2025-12-24_01" or task execution
    state = Column(Enum(RunState), default=RunState.PM)

    # Artifact storage
    pm_result = Column(JSON, nullable=True)
    dev_result = Column(JSON, nullable=True)
    qa_result = Column(JSON, nullable=True)
    sec_result = Column(JSON, nullable=True)
    docs_result = Column(JSON, nullable=True)  # Documentation updates
    testing_result = Column(JSON, nullable=True)  # Playwright/E2E test results

    killed = Column(Boolean, default=False, nullable=False)  # Soft delete flag
    killed_at = Column(DateTime(timezone=True), nullable=True)
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
            "docs_result": self.docs_result,
            "testing_result": self.testing_result,
            "killed": self.killed,
            "killed_at": self.killed_at.isoformat() if self.killed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
