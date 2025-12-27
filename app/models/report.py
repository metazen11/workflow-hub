"""Agent report model."""
import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db import Base


class AgentRole(enum.Enum):
    """Agent roles.

    Roles:
        DIRECTOR - Supervisory agent that enforces standards and course corrects
        PM - Project Manager, breaks down requirements into tasks
        DEV - Developer, implements code to satisfy tests
        QA - Quality Assurance, writes tests before implementation (TDD)
        SECURITY - Security review and vulnerability scanning
        DOCS - Documentation generation and updates
        CICD - Deployment agent (requires human approval)
    """
    DIRECTOR = "director"
    PM = "pm"
    DEV = "dev"
    QA = "qa"
    SECURITY = "security"
    DOCS = "docs"
    CICD = "cicd"


class ReportStatus(enum.Enum):
    """Report status."""
    PASS = "pass"
    FAIL = "fail"
    PENDING = "pending"


class AgentReport(Base):
    """Report submitted by an agent for a run."""
    __tablename__ = "agent_reports"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    role = Column(Enum(AgentRole), nullable=False)
    status = Column(Enum(ReportStatus), default=ReportStatus.PENDING)

    # Report content
    summary = Column(Text, nullable=True)
    details = Column(JSON, nullable=True)  # Flexible JSON for role-specific data

    # QA-specific fields stored in details:
    # - tests_added: list of test names
    # - tests_changed: list of test names
    # - commands_run: list of commands
    # - failing_tests: list of test names
    # - requirements_covered: list of req_ids

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    run = relationship("Run", back_populates="reports")

    def to_dict(self):
        return {
            "id": self.id,
            "run_id": self.run_id,
            "role": self.role.value if self.role else None,
            "status": self.status.value if self.status else None,
            "summary": self.summary,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
