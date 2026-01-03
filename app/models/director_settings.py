"""DirectorSettings model - persists Director daemon configuration.

Stores Director settings in the database so they survive server restarts.
Uses a singleton pattern - only one row exists with id=1.
"""
from sqlalchemy import Column, Integer, Boolean, String, DateTime
from sqlalchemy.sql import func
from app.db import Base


class DirectorSettings(Base):
    """Persistent Director daemon settings.

    This is a singleton table - only one row exists (id=1).
    Settings are loaded on startup and updated via API.

    Attributes:
        enabled: Whether Director should auto-start on server boot
        poll_interval: Seconds between Director poll cycles
        enforce_tdd: Require tests before advancing past QA
        enforce_dry: Check for code duplication
        enforce_security: Run security checks before advancing past SEC
        include_images: Enable multimodal image processing in prompts
        vision_model: Model to use for image analysis
    """
    __tablename__ = "director_settings"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, default=False, nullable=False)
    poll_interval = Column(Integer, default=30, nullable=False)
    enforce_tdd = Column(Boolean, default=True, nullable=False)
    enforce_dry = Column(Boolean, default=True, nullable=False)
    enforce_security = Column(Boolean, default=True, nullable=False)
    include_images = Column(Boolean, default=False, nullable=False)
    vision_model = Column(String(100), default="ai/qwen3-vl", nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    daemon_started_at = Column(DateTime(timezone=True), nullable=True)

    @classmethod
    def get_settings(cls, db):
        """Get or create the singleton settings row."""
        settings = db.query(cls).filter(cls.id == 1).first()
        if not settings:
            settings = cls(id=1)
            db.add(settings)
            db.commit()
            db.refresh(settings)
        return settings

    @classmethod
    def update_settings(cls, db, **kwargs):
        """Update settings with given values."""
        settings = cls.get_settings(db)
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        db.commit()
        db.refresh(settings)
        return settings

    def to_dict(self):
        """Serialize to dictionary."""
        return {
            "enabled": self.enabled,
            "poll_interval": self.poll_interval,
            "enforce_tdd": self.enforce_tdd,
            "enforce_dry": self.enforce_dry,
            "enforce_security": self.enforce_security,
            "include_images": self.include_images,
            "vision_model": self.vision_model,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def is_daemon_running(self):
        """Check if daemon is running based on heartbeat timestamp."""
        import datetime
        if not self.daemon_started_at:
            return False
        # Consider daemon running if heartbeat is within last 2x poll interval
        max_age = self.poll_interval * 2
        elapsed = (datetime.datetime.now(datetime.timezone.utc) - self.daemon_started_at).total_seconds()
        return elapsed < max_age

    @classmethod
    def update_heartbeat(cls, db):
        """Update daemon heartbeat timestamp."""
        import datetime
        settings = cls.get_settings(db)
        settings.daemon_started_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()
        return settings

    @classmethod
    def clear_heartbeat(cls, db):
        """Clear daemon heartbeat (mark as stopped)."""
        settings = cls.get_settings(db)
        settings.daemon_started_at = None
        db.commit()
        return settings

    def __repr__(self):
        return f"<DirectorSettings(enabled={self.enabled}, poll_interval={self.poll_interval})>"
