"""Threat intelligence model."""
import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Enum
from sqlalchemy.sql import func
from app.db import Base


class ThreatStatus(enum.Enum):
    """Threat intel status."""
    NEW = "new"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    ACCEPTED = "accepted"  # risk accepted


class ThreatIntel(Base):
    """Threat intelligence entry."""
    __tablename__ = "threat_intel"

    id = Column(Integer, primary_key=True, index=True)
    date_reported = Column(Date, nullable=False)
    source = Column(String(255), nullable=False)  # e.g., "CVE", "internal", "pentest"
    summary = Column(Text, nullable=False)
    affected_tech = Column(String(255), nullable=True)  # e.g., "Django 4.x", "psycopg2"
    action = Column(Text, nullable=True)  # recommended action
    status = Column(Enum(ThreatStatus), default=ThreatStatus.NEW)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "date_reported": self.date_reported.isoformat() if self.date_reported else None,
            "source": self.source,
            "summary": self.summary,
            "affected_tech": self.affected_tech,
            "action": self.action,
            "status": self.status.value if self.status else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
