"""TaskAttachment model for secure file uploads."""
import enum
import hashlib
import magic
import os
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db import Base


class AttachmentType(enum.Enum):
    """Allowed attachment types."""
    IMAGE = "image"
    TEXT = "text"
    DOCUMENT = "document"


# Security: Allowed MIME types with their extensions
ALLOWED_MIME_TYPES = {
    # Images
    "image/png": {"ext": [".png"], "type": AttachmentType.IMAGE, "max_size": 10 * 1024 * 1024},
    "image/jpeg": {"ext": [".jpg", ".jpeg"], "type": AttachmentType.IMAGE, "max_size": 10 * 1024 * 1024},
    "image/gif": {"ext": [".gif"], "type": AttachmentType.IMAGE, "max_size": 5 * 1024 * 1024},
    "image/webp": {"ext": [".webp"], "type": AttachmentType.IMAGE, "max_size": 10 * 1024 * 1024},
    # Text files
    "text/plain": {"ext": [".txt", ".md", ".log"], "type": AttachmentType.TEXT, "max_size": 1 * 1024 * 1024},
    "text/markdown": {"ext": [".md"], "type": AttachmentType.TEXT, "max_size": 1 * 1024 * 1024},
    "application/json": {"ext": [".json"], "type": AttachmentType.TEXT, "max_size": 1 * 1024 * 1024},
    # Documents
    "application/pdf": {"ext": [".pdf"], "type": AttachmentType.DOCUMENT, "max_size": 20 * 1024 * 1024},
}

# Dangerous patterns to reject
DANGEROUS_PATTERNS = [
    b"<%",  # ASP/JSP
    b"<?php",  # PHP
    b"#!/",  # Shell scripts
    b"<script",  # JavaScript
    b"javascript:",  # JS URLs
    b"data:text/html",  # Data URLs
    b"eval(",  # Eval
    b"exec(",  # Exec
]


class AttachmentSecurityError(Exception):
    """Raised when file fails security validation."""
    pass


def validate_file_security(content: bytes, filename: str, claimed_mime: str = None) -> dict:
    """Validate file content for security.

    Args:
        content: File content bytes
        filename: Original filename
        claimed_mime: MIME type claimed by client (optional)

    Returns:
        Dict with validated mime_type, attachment_type, and file extension

    Raises:
        AttachmentSecurityError: If file fails validation
    """
    # Check file size
    max_overall_size = 20 * 1024 * 1024  # 20MB absolute max
    if len(content) > max_overall_size:
        raise AttachmentSecurityError(f"File too large: {len(content)} bytes (max {max_overall_size})")

    # Detect actual MIME type using libmagic
    try:
        detected_mime = magic.from_buffer(content, mime=True)
    except Exception as e:
        raise AttachmentSecurityError(f"Could not detect file type: {e}")

    # Validate MIME type is allowed
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise AttachmentSecurityError(f"File type not allowed: {detected_mime}")

    mime_config = ALLOWED_MIME_TYPES[detected_mime]

    # Check specific size limit for this type
    if len(content) > mime_config["max_size"]:
        raise AttachmentSecurityError(
            f"File too large for {detected_mime}: {len(content)} bytes (max {mime_config['max_size']})"
        )

    # Validate file extension
    _, ext = os.path.splitext(filename.lower())
    if ext not in mime_config["ext"]:
        raise AttachmentSecurityError(
            f"Extension {ext} not valid for {detected_mime}. Allowed: {mime_config['ext']}"
        )

    # If client claimed a MIME type, verify it matches
    if claimed_mime and claimed_mime != detected_mime:
        # Allow some flexibility for text types
        if not (claimed_mime.startswith("text/") and detected_mime.startswith("text/")):
            raise AttachmentSecurityError(
                f"MIME type mismatch: claimed {claimed_mime}, detected {detected_mime}"
            )

    # Scan for dangerous patterns
    content_lower = content.lower()
    for pattern in DANGEROUS_PATTERNS:
        if pattern.lower() in content_lower:
            raise AttachmentSecurityError(f"Dangerous content pattern detected")

    # For images, verify they're valid (basic check)
    if mime_config["type"] == AttachmentType.IMAGE:
        # PNG signature
        if detected_mime == "image/png" and not content.startswith(b'\x89PNG'):
            raise AttachmentSecurityError("Invalid PNG signature")
        # JPEG signature
        if detected_mime == "image/jpeg" and not content.startswith(b'\xff\xd8\xff'):
            raise AttachmentSecurityError("Invalid JPEG signature")
        # GIF signature
        if detected_mime == "image/gif" and not content.startswith(b'GIF'):
            raise AttachmentSecurityError("Invalid GIF signature")

    return {
        "mime_type": detected_mime,
        "attachment_type": mime_config["type"],
        "extension": ext,
        "size": len(content),
    }


class TaskAttachment(Base):
    """A file attachment on a task."""
    __tablename__ = "task_attachments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)

    # File metadata
    filename = Column(String(255), nullable=False)  # Original filename (sanitized)
    stored_filename = Column(String(255), nullable=False)  # UUID-based stored name
    mime_type = Column(String(100), nullable=False)
    attachment_type = Column(Enum(AttachmentType), nullable=False)
    size = Column(Integer, nullable=False)  # File size in bytes
    checksum = Column(String(64), nullable=False)  # SHA-256 hash

    # Security tracking
    scanned = Column(Boolean, default=True)  # Passed security scan
    scan_result = Column(Text, nullable=True)  # Any notes from scan

    # Storage path (relative to uploads directory)
    storage_path = Column(String(512), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    uploaded_by = Column(String(100), default="human")  # human or agent name

    # Relationships
    task = relationship("Task", backref="attachments")

    @staticmethod
    def compute_checksum(content: bytes) -> str:
        """Compute SHA-256 checksum of file content."""
        return hashlib.sha256(content).hexdigest()

    def to_dict(self) -> dict:
        """Serialize attachment to dictionary."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "attachment_type": self.attachment_type.value if self.attachment_type else None,
            "size": self.size,
            "checksum": self.checksum,
            "scanned": self.scanned,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "uploaded_by": self.uploaded_by,
            "download_url": f"/api/tasks/{self.task_id}/attachments/{self.id}/download",
        }
