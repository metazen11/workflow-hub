"""PipelineConfig model - stores visual pipeline configurations.

Used by the Next.js Pipeline Editor to store pipeline designs:
- Node positions and types (stages, agents, queues, decisions)
- Edge connections between nodes
- Canvas settings (zoom, pan)
- Pipeline settings (Director config, timeouts, etc.)
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class PipelineConfig(Base):
    """Visual pipeline configuration.

    Stores the complete state of a pipeline editor design including
    all nodes, edges, canvas position, and settings.

    Attributes:
        project_id: Optional link to a project (can be global/template)
        name: Configuration name (e.g., "Default Pipeline", "TDD Pipeline")
        description: What this pipeline is for
        version: Auto-incremented version number
        is_active: Whether this is the active pipeline for the project
        canvas_config: Zoom, pan position (JSONB)
        nodes: Array of node definitions (JSONB)
        edges: Array of edge connections (JSONB)
        settings: Pipeline settings like Director config (JSONB)
        created_by: Who created this configuration
    """
    __tablename__ = "pipeline_configs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True)

    # JSONB columns for flexible schema
    canvas_config = Column(JSON, default={"zoom": 1, "panX": 0, "panY": 0})
    nodes = Column(JSON, nullable=False, default=list)
    edges = Column(JSON, nullable=False, default=list)
    settings = Column(JSON, default=dict)

    created_by = Column(String(100), default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship
    project = relationship("Project", back_populates="pipeline_configs")

    def to_dict(self):
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "is_active": self.is_active,
            "canvas_config": self.canvas_config or {"zoom": 1, "panX": 0, "panY": 0},
            "nodes": self.nodes or [],
            "edges": self.edges or [],
            "settings": self.settings or {},
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<PipelineConfig(id={self.id}, name='{self.name}', version={self.version})>"


class PipelineConfigHistory(Base):
    """Version history for pipeline configurations.

    Stores previous versions of pipeline configs for audit trail
    and potential rollback.

    Attributes:
        pipeline_config_id: Parent configuration
        version: Version number at time of save
        nodes: Snapshot of nodes at this version
        edges: Snapshot of edges at this version
        settings: Snapshot of settings at this version
        change_summary: Description of what changed
        created_by: Who made this change
    """
    __tablename__ = "pipeline_config_history"

    id = Column(Integer, primary_key=True, index=True)
    pipeline_config_id = Column(Integer, ForeignKey("pipeline_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    nodes = Column(JSON, nullable=False)
    edges = Column(JSON, nullable=False)
    settings = Column(JSON, nullable=True)
    change_summary = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    pipeline_config = relationship("PipelineConfig", backref="history")

    def to_dict(self):
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "pipeline_config_id": self.pipeline_config_id,
            "version": self.version,
            "nodes": self.nodes,
            "edges": self.edges,
            "settings": self.settings,
            "change_summary": self.change_summary,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<PipelineConfigHistory(config_id={self.pipeline_config_id}, version={self.version})>"
