"""Environment model for deployment targets."""
import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, Boolean, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db import Base


class EnvironmentType(enum.Enum):
    """Types of environments."""
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"
    CI_CD = "ci_cd"
    OTHER = "other"


class Environment(Base):
    """Deployment environment for a project."""
    __tablename__ = "environments"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)

    # Identification
    name = Column(String(255), nullable=False)  # e.g., "Production", "Staging EU"
    env_type = Column(Enum(EnvironmentType), default=EnvironmentType.DEVELOPMENT)
    description = Column(Text, nullable=True)

    # Location
    url = Column(String(512), nullable=True)  # https://api.example.com
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    port = Column(Integer, nullable=True)
    path = Column(String(512), nullable=True)  # /var/www/app

    # SSH Access
    ssh_host = Column(String(255), nullable=True)
    ssh_port = Column(Integer, default=22)
    ssh_user = Column(String(255), nullable=True)
    ssh_key_path = Column(String(512), nullable=True)
    ssh_key_encrypted = Column(Text, nullable=True)  # Encrypted key content

    # Login/Auth
    login_required = Column(Boolean, default=False)
    login_url = Column(String(512), nullable=True)
    auth_type = Column(String(50), nullable=True)  # basic, oauth, api_key

    # Database
    database_host = Column(String(255), nullable=True)
    database_port = Column(Integer, nullable=True)
    database_name = Column(String(255), nullable=True)
    database_url_encrypted = Column(Text, nullable=True)  # Full connection string, encrypted

    # Environment Variables (encrypted JSON)
    env_vars_encrypted = Column(Text, nullable=True)  # Encrypted JSON of env vars

    # Deployment
    deploy_command = Column(Text, nullable=True)  # e.g., "docker-compose up -d"
    health_check_url = Column(String(512), nullable=True)
    test_command = Column(Text, nullable=True)  # e.g., "pytest tests/e2e -v"
    rollback_command = Column(Text, nullable=True)  # e.g., "git checkout {commit_sha}"
    last_deploy_at = Column(DateTime(timezone=True), nullable=True)
    last_health_check_at = Column(DateTime(timezone=True), nullable=True)
    is_healthy = Column(Boolean, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="environments")

    def to_dict(self, include_secrets=False):
        """Convert to dict. Secrets are masked by default."""
        result = {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "env_type": self.env_type.value if self.env_type else None,
            "description": self.description,
            "url": self.url,
            "ip_address": self.ip_address,
            "port": self.port,
            "path": self.path,
            "ssh_host": self.ssh_host,
            "ssh_port": self.ssh_port,
            "ssh_user": self.ssh_user,
            "ssh_key_path": self.ssh_key_path,
            "login_required": self.login_required,
            "login_url": self.login_url,
            "auth_type": self.auth_type,
            "database_host": self.database_host,
            "database_port": self.database_port,
            "database_name": self.database_name,
            "deploy_command": self.deploy_command,
            "health_check_url": self.health_check_url,
            "test_command": self.test_command,
            "rollback_command": self.rollback_command,
            "last_deploy_at": self.last_deploy_at.isoformat() if self.last_deploy_at else None,
            "last_health_check_at": self.last_health_check_at.isoformat() if self.last_health_check_at else None,
            "is_healthy": self.is_healthy,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            # Indicate presence without revealing values
            "has_ssh_key": bool(self.ssh_key_encrypted or self.ssh_key_path),
            "has_database_url": bool(self.database_url_encrypted),
            "has_env_vars": bool(self.env_vars_encrypted),
        }

        if include_secrets:
            result["ssh_key_encrypted"] = self.ssh_key_encrypted
            result["database_url_encrypted"] = self.database_url_encrypted
            result["env_vars_encrypted"] = self.env_vars_encrypted

        return result
