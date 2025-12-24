"""Audit event model."""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from app.db import Base


class AuditEvent(Base):
    """Audit log entry for all state changes."""
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    actor = Column(String(100), nullable=False)  # "human", "pm", "dev", "qa", "security"
    action = Column(String(100), nullable=False)  # e.g., "state_change", "create", "update"
    entity_type = Column(String(50), nullable=False)  # e.g., "run", "project", "task"
    entity_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True)  # Additional context

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "actor": self.actor,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "details": self.details,
        }


def log_event(db, actor: str, action: str, entity_type: str, entity_id: int = None, details: dict = None):
    """Helper to create audit log entry."""
    event = AuditEvent(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.add(event)
    db.commit()
    return event
