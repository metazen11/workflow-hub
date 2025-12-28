"""Deployment history model for tracking deployments and enabling rollback."""
import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, Boolean, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db import Base


class DeploymentStatus(enum.Enum):
    """Status of a deployment."""
    PENDING = "pending"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class DeploymentHistory(Base):
    """Track deployment history for rollback capability."""
    __tablename__ = "deployment_history"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False, index=True)
    environment_id = Column(Integer, ForeignKey("environments.id"), nullable=False, index=True)

    # Version tracking
    version = Column(String(100), nullable=True)  # Semantic version if available
    commit_sha = Column(String(40), nullable=True)  # Git commit SHA
    previous_commit_sha = Column(String(40), nullable=True)  # For rollback reference

    # Deployment details
    status = Column(Enum(DeploymentStatus), default=DeploymentStatus.PENDING)
    deploy_command_used = Column(Text, nullable=True)  # Actual command executed
    deploy_output = Column(Text, nullable=True)  # Command output/logs

    # Health check results
    health_check_passed = Column(Boolean, nullable=True)
    health_check_response = Column(JSON, nullable=True)  # Store response details
    health_check_at = Column(DateTime(timezone=True), nullable=True)

    # Test results
    test_command_used = Column(Text, nullable=True)
    test_passed = Column(Boolean, nullable=True)
    test_output = Column(Text, nullable=True)
    test_at = Column(DateTime(timezone=True), nullable=True)

    # Rollback info
    is_rollback = Column(Boolean, default=False)
    rolled_back_from_id = Column(Integer, ForeignKey("deployment_history.id"), nullable=True)
    rolled_back_to_id = Column(Integer, ForeignKey("deployment_history.id"), nullable=True)
    rollback_reason = Column(Text, nullable=True)

    # Actor tracking
    triggered_by = Column(String(100), nullable=True)  # "agent", "human", "auto"
    approved_by = Column(String(255), nullable=True)  # Who approved deployment

    # Timestamps
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    run = relationship("Run", backref="deployments")
    environment = relationship("Environment", backref="deployments")

    def to_dict(self):
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "environment_id": self.environment_id,
            "version": self.version,
            "commit_sha": self.commit_sha,
            "previous_commit_sha": self.previous_commit_sha,
            "status": self.status.value if self.status else None,
            "deploy_command_used": self.deploy_command_used,
            "health_check_passed": self.health_check_passed,
            "health_check_at": self.health_check_at.isoformat() if self.health_check_at else None,
            "test_passed": self.test_passed,
            "test_at": self.test_at.isoformat() if self.test_at else None,
            "is_rollback": self.is_rollback,
            "rolled_back_from_id": self.rolled_back_from_id,
            "rollback_reason": self.rollback_reason,
            "triggered_by": self.triggered_by,
            "approved_by": self.approved_by,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
