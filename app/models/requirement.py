"""Requirement model."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Table
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db import Base


# Join table for Task-Requirement many-to-many relationship
task_requirements = Table(
    'task_requirements',
    Base.metadata,
    Column('task_id', Integer, ForeignKey('tasks.id', ondelete='CASCADE'), primary_key=True),
    Column('requirement_id', Integer, ForeignKey('requirements.id', ondelete='CASCADE'), primary_key=True)
)


class Requirement(Base):
    """A requirement for a project (R1, R2, etc.)."""
    __tablename__ = "requirements"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    req_id = Column(String(20), nullable=False)  # e.g., "R1", "R2"
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    acceptance_criteria = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="requirements")
    tasks = relationship("Task", secondary="task_requirements", back_populates="requirements")

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "req_id": self.req_id,
            "title": self.title,
            "description": self.description,
            "acceptance_criteria": self.acceptance_criteria,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
