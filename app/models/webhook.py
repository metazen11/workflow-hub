"""Webhook configuration model."""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.db import Base


class Webhook(Base):
    """Webhook endpoint for event notifications."""
    __tablename__ = "webhooks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)  # n8n webhook URL
    secret = Column(String(100), nullable=True)  # Optional HMAC secret
    events = Column(String(500), nullable=False)  # Comma-separated: "state_change,report_submitted"
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "events": self.events.split(",") if self.events else [],
            "active": self.active,
        }
