"""AppSettings model - persists application configuration.

Stores app-wide settings in the database (like .env but editable via UI).
Uses a key-value pattern for flexibility.

Future: Will require admin permissions to edit.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from app.db import Base


class AppSetting(Base):
    """Key-value settings storage.

    Stores configuration that would traditionally go in .env but needs
    to be editable at runtime without server restart.

    Attributes:
        key: Setting name (e.g., "LLM_MODEL", "AGENT_TIMEOUT")
        value: Setting value as string
        description: Human-readable description
        category: Grouping (llm, agent, ui, security, etc.)
        is_secret: If true, value is masked in UI (for API keys, etc.)
        editable: If false, read-only in UI
    """
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String(50), default="general", nullable=False, index=True)
    is_secret = Column(Boolean, default=False, nullable=False)
    editable = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Default settings to seed
    DEFAULT_SETTINGS = [
        # LLM Settings
        {"key": "LLM_BASE_URL", "value": "http://localhost:12434/engines/llama.cpp/v1",
         "description": "Base URL for LLM API (Docker Model Runner)", "category": "llm"},
        {"key": "LLM_MODEL", "value": "ai/qwen3-coder:latest",
         "description": "Default model for completions", "category": "llm"},
        {"key": "LLM_TIMEOUT", "value": "120",
         "description": "Timeout in seconds for LLM requests", "category": "llm"},
        {"key": "VISION_MODEL", "value": "ai/qwen3-vl:latest",
         "description": "Model for image analysis", "category": "llm"},

        # Agent Settings
        {"key": "AGENT_TIMEOUT", "value": "600",
         "description": "Timeout in seconds for agent runs", "category": "agent"},
        {"key": "AGENT_PROVIDER", "value": "goose",
         "description": "Agent CLI to use (goose, claude, etc.)", "category": "agent"},

        # Queue Settings
        {"key": "JOB_QUEUE_ENABLED", "value": "true",
         "description": "Enable background job queue", "category": "queue"},
        {"key": "JOB_POLL_INTERVAL", "value": "1",
         "description": "Seconds between queue polls", "category": "queue"},

        # UI Settings
        {"key": "QUEUE_POLL_INTERVAL", "value": "5000",
         "description": "Milliseconds between UI queue status updates", "category": "ui"},
        {"key": "SHOW_DEBUG_INFO", "value": "false",
         "description": "Show debug information in UI", "category": "ui"},
    ]

    @classmethod
    def get_all(cls, db, category=None):
        """Get all settings, optionally filtered by category."""
        query = db.query(cls)
        if category:
            query = query.filter(cls.category == category)
        return query.order_by(cls.category, cls.key).all()

    @classmethod
    def get(cls, db, key, default=None):
        """Get a setting value by key."""
        setting = db.query(cls).filter(cls.key == key).first()
        return setting.value if setting else default

    @classmethod
    def set(cls, db, key, value, description=None, category="general", is_secret=False):
        """Set a setting value, creating if it doesn't exist."""
        setting = db.query(cls).filter(cls.key == key).first()
        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            setting = cls(
                key=key,
                value=value,
                description=description,
                category=category,
                is_secret=is_secret
            )
            db.add(setting)
        db.commit()
        return setting

    @classmethod
    def seed_defaults(cls, db):
        """Seed default settings if they don't exist."""
        for default in cls.DEFAULT_SETTINGS:
            existing = db.query(cls).filter(cls.key == default["key"]).first()
            if not existing:
                setting = cls(**default)
                db.add(setting)
        db.commit()

    def to_dict(self, mask_secrets=True):
        """Serialize to dictionary."""
        value = self.value
        if mask_secrets and self.is_secret and value:
            value = "●" * 8  # Mask secret values

        return {
            "id": self.id,
            "key": self.key,
            "value": value,
            "description": self.description,
            "category": self.category,
            "is_secret": self.is_secret,
            "editable": self.editable,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<AppSetting(key='{self.key}', category='{self.category}')>"
