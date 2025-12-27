"""Project model."""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db import Base


class Project(Base):
    """A software project being managed."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Repository & Location
    repo_path = Column(String(512), nullable=True)  # Local path
    repository_url = Column(String(512), nullable=True)  # Git remote URL (https://github.com/...)
    repository_ssh_url = Column(String(512), nullable=True)  # Git SSH URL (git@github.com:...)
    primary_branch = Column(String(100), default="main")
    documentation_url = Column(String(512), nullable=True)

    # Git Credentials (links to credentials table)
    git_credential_id = Column(Integer, ForeignKey("credentials.id"), nullable=True)
    git_auth_method = Column(String(50), nullable=True)  # "ssh", "https_token", "https_basic"

    # Tech Stack
    stack_tags = Column(JSON, default=list)  # ["python", "flask", "postgresql"]
    languages = Column(JSON, default=list)  # ["Python", "JavaScript"]
    frameworks = Column(JSON, default=list)  # ["Flask", "React"]
    databases = Column(JSON, default=list)  # ["PostgreSQL", "Redis"]

    # Key Files & Structure
    key_files = Column(JSON, default=list)  # ["app.py", "config.py", "requirements.txt"]
    entry_point = Column(String(255), nullable=True)  # "app.py" or "main.py"
    config_files = Column(JSON, default=list)  # [".env", "config.yaml"]

    # Build & Deploy
    build_command = Column(Text, nullable=True)  # "pip install -r requirements.txt"
    test_command = Column(Text, nullable=True)  # "pytest tests/ -v"
    run_command = Column(Text, nullable=True)  # "python app.py"
    deploy_command = Column(Text, nullable=True)  # "docker-compose up -d"

    # Development Settings
    default_port = Column(Integer, nullable=True)  # 5051
    python_version = Column(String(20), nullable=True)  # "3.11"
    node_version = Column(String(20), nullable=True)  # "18"

    # Status
    is_active = Column(Boolean, default=True)
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    requirements = relationship("Requirement", back_populates="project", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    runs = relationship("Run", back_populates="project", cascade="all, delete-orphan")
    credentials = relationship("Credential", back_populates="project", foreign_keys="Credential.project_id", cascade="all, delete-orphan")
    environments = relationship("Environment", back_populates="project", cascade="all, delete-orphan")
    git_credential = relationship("Credential", foreign_keys=[git_credential_id], uselist=False)
    bugs = relationship("BugReport", back_populates="project", lazy="dynamic")

    def to_dict(self, include_children=False):
        result = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            # Repository
            "repo_path": self.repo_path,
            "repository_url": self.repository_url,
            "repository_ssh_url": self.repository_ssh_url,
            "primary_branch": self.primary_branch,
            "documentation_url": self.documentation_url,
            "git_credential_id": self.git_credential_id,
            "git_auth_method": self.git_auth_method,
            # Tech Stack
            "stack_tags": self.stack_tags or [],
            "languages": self.languages or [],
            "frameworks": self.frameworks or [],
            "databases": self.databases or [],
            # Key Files
            "key_files": self.key_files or [],
            "entry_point": self.entry_point,
            "config_files": self.config_files or [],
            # Build & Deploy
            "build_command": self.build_command,
            "test_command": self.test_command,
            "run_command": self.run_command,
            "deploy_command": self.deploy_command,
            # Development
            "default_port": self.default_port,
            "python_version": self.python_version,
            "node_version": self.node_version,
            # Status
            "is_active": self.is_active,
            "is_archived": self.is_archived,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_children:
            result["credentials_count"] = len(self.credentials) if self.credentials else 0
            result["environments_count"] = len(self.environments) if self.environments else 0
            result["tasks_count"] = len(self.tasks) if self.tasks else 0
            result["requirements_count"] = len(self.requirements) if self.requirements else 0

        return result
