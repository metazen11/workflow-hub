"""LLM Session model for conversation persistence.

Follows Goose's session pattern but uses PostgreSQL:
- Sessions identified by name (e.g., task_123, run_456)
- Messages stored as JSON array
- Token tracking for cost monitoring
- Project/task/run associations for context

Sessions enable multi-turn LLM conversations with memory.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship

from app.db import Base


class LLMSession(Base):
    """LLM conversation session with message history.

    Similar to Goose sessions but database-backed for:
    - Query and search across sessions
    - Agent memory (what was discussed for each task)
    - Cost tracking (token usage)
    - Session resumption
    """
    __tablename__ = "llm_sessions"

    id = Column(Integer, primary_key=True)

    # Session identifier (e.g., "task_123", "run_456", "project_789")
    # Unique per project to allow scoped lookups
    name = Column(String(255), nullable=False, index=True)

    # Context associations (all optional, but at least one recommended)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=True, index=True)

    # Working directory (like Goose's working_dir)
    working_dir = Column(Text, nullable=True)

    # Model configuration
    model = Column(String(100), nullable=True)  # e.g., "ai/qwen3-coder"
    provider = Column(String(50), default="docker")  # docker, ollama, openai, etc.

    # Message history - array of {role, content, timestamp}
    # Format: [{"role": "system"|"user"|"assistant", "content": "...", "ts": "..."}]
    messages = Column(JSON, default=list)

    # Token tracking (like Goose)
    total_tokens = Column(Integer, default=0)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)

    # Metadata
    created_by = Column(String(100), default="system")  # agent role, user, system
    active = Column(Boolean, default=True)  # False when session is closed/archived

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_message_at = Column(DateTime, nullable=True)

    # Relationships
    project = relationship("Project", backref="llm_sessions")
    task = relationship("Task", backref="llm_sessions")
    run = relationship("Run", backref="llm_sessions")

    def add_message(self, role: str, content: str, tokens: int = None):
        """Add a message to the session history.

        Args:
            role: Message role (system, user, assistant)
            content: Message content
            tokens: Optional token count for this message
        """
        if self.messages is None:
            self.messages = []

        message = {
            "role": role,
            "content": content,
            "ts": datetime.utcnow().isoformat()
        }
        if tokens:
            message["tokens"] = tokens

        # SQLAlchemy needs a new list to detect the change
        self.messages = self.messages + [message]
        self.last_message_at = datetime.utcnow()

        # Update token counts
        if tokens:
            self.total_tokens = (self.total_tokens or 0) + tokens
            if role in ("user", "system"):
                self.input_tokens = (self.input_tokens or 0) + tokens
            elif role == "assistant":
                self.output_tokens = (self.output_tokens or 0) + tokens

    def get_messages_for_api(self) -> list:
        """Get messages in OpenAI API format (without timestamps)."""
        return [
            {"role": m["role"], "content": m["content"]}
            for m in (self.messages or [])
        ]

    def get_last_n_messages(self, n: int = 10) -> list:
        """Get the last N messages."""
        messages = self.messages or []
        return messages[-n:] if len(messages) > n else messages

    def clear_messages(self, keep_system: bool = True):
        """Clear message history.

        Args:
            keep_system: If True, keep system messages
        """
        if keep_system:
            self.messages = [m for m in (self.messages or []) if m.get("role") == "system"]
        else:
            self.messages = []
        self.last_message_at = datetime.utcnow()

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "name": self.name,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "working_dir": self.working_dir,
            "model": self.model,
            "provider": self.provider,
            "message_count": len(self.messages or []),
            "total_tokens": self.total_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "created_by": self.created_by,
            "active": self.active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
        }

    def to_dict_with_messages(self, last_n: int = None):
        """Convert to dictionary including message history.

        Args:
            last_n: If set, only include last N messages
        """
        result = self.to_dict()
        if last_n:
            result["messages"] = self.get_last_n_messages(last_n)
        else:
            result["messages"] = self.messages or []
        return result

    def to_export_format(self):
        """Export format similar to Goose's JSON export."""
        return {
            "id": self.id,
            "name": self.name,
            "working_dir": self.working_dir,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "total_tokens": self.total_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "provider_name": self.provider,
            "model_config": {
                "model_name": self.model,
            },
            "conversation": self.messages or [],
            "metadata": {
                "project_id": self.project_id,
                "task_id": self.task_id,
                "run_id": self.run_id,
            }
        }

    def __repr__(self):
        return f"<LLMSession {self.id}: {self.name} ({len(self.messages or [])} messages)>"
