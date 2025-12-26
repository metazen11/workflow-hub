"""Credential model for storing project secrets securely."""
import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db import Base


class CredentialType(enum.Enum):
    """Types of credentials."""
    API_KEY = "api_key"
    OAUTH = "oauth"
    BASIC_AUTH = "basic_auth"
    SSH_KEY = "ssh_key"
    DATABASE = "database"
    TOKEN = "token"
    CERTIFICATE = "certificate"
    OTHER = "other"


class Credential(Base):
    """Encrypted credentials for a project."""
    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)

    # Identification
    name = Column(String(255), nullable=False)  # e.g., "GitHub API", "Production DB"
    credential_type = Column(Enum(CredentialType), default=CredentialType.API_KEY)
    service = Column(String(255), nullable=True)  # e.g., "github", "aws", "postgresql"
    description = Column(Text, nullable=True)

    # Credential values (should be encrypted at rest)
    username = Column(String(255), nullable=True)
    password_encrypted = Column(Text, nullable=True)  # Encrypted
    api_key_encrypted = Column(Text, nullable=True)  # Encrypted
    token_encrypted = Column(Text, nullable=True)  # Encrypted

    # SSH specific
    ssh_key_path = Column(String(512), nullable=True)  # Path to key file
    ssh_key_encrypted = Column(Text, nullable=True)  # Encrypted key content
    ssh_passphrase_encrypted = Column(Text, nullable=True)  # Encrypted passphrase

    # Database specific
    database_url_encrypted = Column(Text, nullable=True)  # Encrypted connection string

    # OAuth specific
    client_id = Column(String(255), nullable=True)
    client_secret_encrypted = Column(Text, nullable=True)  # Encrypted
    refresh_token_encrypted = Column(Text, nullable=True)  # Encrypted

    # Metadata
    environment = Column(String(50), nullable=True)  # dev, staging, prod
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="credentials", foreign_keys=[project_id])

    def to_dict(self, include_secrets=False):
        """Convert to dict. Secrets are masked by default."""
        result = {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "credential_type": self.credential_type.value if self.credential_type else None,
            "service": self.service,
            "description": self.description,
            "username": self.username,
            "environment": self.environment,
            "is_active": self.is_active,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            # Indicate presence without revealing values
            "has_password": bool(self.password_encrypted),
            "has_api_key": bool(self.api_key_encrypted),
            "has_token": bool(self.token_encrypted),
            "has_ssh_key": bool(self.ssh_key_encrypted or self.ssh_key_path),
            "has_database_url": bool(self.database_url_encrypted),
        }

        if include_secrets:
            # Only include if explicitly requested (for internal use)
            result["password_encrypted"] = self.password_encrypted
            result["api_key_encrypted"] = self.api_key_encrypted
            result["token_encrypted"] = self.token_encrypted
            result["ssh_key_encrypted"] = self.ssh_key_encrypted
            result["database_url_encrypted"] = self.database_url_encrypted

        return result
