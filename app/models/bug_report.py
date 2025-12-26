"""BugReport model for tracking user-submitted bug reports."""
import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, Boolean
from sqlalchemy.sql import func
from app.db import Base


class BugReportStatus(enum.Enum):
    """Bug report status values."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class BugReport(Base):
    """A bug report submitted via the widget."""
    __tablename__ = "bug_reports"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    screenshot = Column(Text, nullable=True)  # Base64 encoded image
    url = Column(String(512), nullable=True)  # Page URL where bug was reported
    user_agent = Column(String(512), nullable=True)  # Browser info
    app_name = Column(String(100), nullable=True)  # Which app submitted the report
    status = Column(Enum(BugReportStatus), default=BugReportStatus.OPEN)
    killed = Column(Boolean, default=False, nullable=False)  # Soft delete flag
    killed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        """Serialize bug report to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "screenshot": self.screenshot,
            "url": self.url,
            "user_agent": self.user_agent,
            "app_name": self.app_name,
            "status": self.status.value if self.status else None,
            "killed": self.killed,
            "killed_at": self.killed_at.isoformat() if self.killed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }
