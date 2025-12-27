"""RoleConfig model - stores agent role configurations in the database.

This replaces the hardcoded ROLE_PROMPTS in agent_runner.py.
Each agent role (director, pm, dev, qa, security, docs, cicd) has a
configuration entry that includes its prompt and enforcement checks.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from app.db import Base


class RoleConfig(Base):
    """Configuration for an agent role.

    Stores prompts and settings for each agent role in the database,
    allowing runtime configuration without code changes.

    Attributes:
        role: Unique role identifier (e.g., "director", "pm", "dev")
        name: Display name (e.g., "Director", "Project Manager")
        description: What this role does
        prompt: Full prompt template for this agent
        checks: Enforcement rules (JSON) - primarily for Director
        requires_approval: If true, human must approve before execution
        active: Can be disabled without deletion
    """
    __tablename__ = "role_configs"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    prompt = Column(Text, nullable=False)
    checks = Column(JSON, nullable=True, default=dict)
    requires_approval = Column(Boolean, default=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "role": self.role,
            "name": self.name,
            "description": self.description,
            "prompt": self.prompt,
            "checks": self.checks or {},
            "requires_approval": self.requires_approval,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<RoleConfig(role='{self.role}', name='{self.name}', active={self.active})>"
