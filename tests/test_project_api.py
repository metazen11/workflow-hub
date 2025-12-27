"""Tests for Project API endpoints.

TDD: Tests written first to define expected behavior.
"""
import pytest
from django.test import Client


@pytest.fixture
def client():
    """Django test client."""
    return Client()


class TestProjectCreate:
    """Tests for project_create endpoint - must support all Project model fields."""

    def test_create_project_minimal(self, client, db_session):
        """Create project with just required field (name)."""
        response = client.post(
            '/api/projects/create',
            data={
                "name": "Test Project"
            },
            content_type='application/json'
        )
        assert response.status_code == 201
        data = response.json()
        assert data["project"]["name"] == "Test Project"

    def test_create_project_with_tech_stack(self, client, db_session):
        """Create project with languages, frameworks, databases."""
        response = client.post(
            '/api/projects/create',
            data={
                "name": "Full Stack App",
                "description": "A comprehensive application",
                "languages": ["Python", "JavaScript", "TypeScript"],
                "frameworks": ["Django", "React", "TailwindCSS"],
                "databases": ["PostgreSQL", "Redis"],
                "stack_tags": ["python", "react", "postgresql"]
            },
            content_type='application/json'
        )
        assert response.status_code == 201
        data = response.json()
        project = data["project"]
        assert project["languages"] == ["Python", "JavaScript", "TypeScript"]
        assert project["frameworks"] == ["Django", "React", "TailwindCSS"]
        assert project["databases"] == ["PostgreSQL", "Redis"]
        assert project["stack_tags"] == ["python", "react", "postgresql"]

    def test_create_project_with_key_files(self, client, db_session):
        """Create project with key_files, entry_point, config_files."""
        response = client.post(
            '/api/projects/create',
            data={
                "name": "Key Files Project",
                "key_files": ["app.py", "models.py", "views.py", "requirements.txt"],
                "entry_point": "app.py",
                "config_files": [".env", "config.yaml", "settings.py"]
            },
            content_type='application/json'
        )
        assert response.status_code == 201
        data = response.json()
        project = data["project"]
        assert project["key_files"] == ["app.py", "models.py", "views.py", "requirements.txt"]
        assert project["entry_point"] == "app.py"
        assert project["config_files"] == [".env", "config.yaml", "settings.py"]

    def test_create_project_with_commands(self, client, db_session):
        """Create project with build, test, run, deploy commands."""
        response = client.post(
            '/api/projects/create',
            data={
                "name": "Commands Project",
                "build_command": "pip install -r requirements.txt",
                "test_command": "pytest tests/ -v",
                "run_command": "python app.py",
                "deploy_command": "docker-compose up -d"
            },
            content_type='application/json'
        )
        assert response.status_code == 201
        data = response.json()
        project = data["project"]
        assert project["build_command"] == "pip install -r requirements.txt"
        assert project["test_command"] == "pytest tests/ -v"
        assert project["run_command"] == "python app.py"
        assert project["deploy_command"] == "docker-compose up -d"

    def test_create_project_with_dev_settings(self, client, db_session):
        """Create project with development settings."""
        response = client.post(
            '/api/projects/create',
            data={
                "name": "Dev Settings Project",
                "default_port": 5000,
                "python_version": "3.11",
                "node_version": "20"
            },
            content_type='application/json'
        )
        assert response.status_code == 201
        data = response.json()
        project = data["project"]
        assert project["default_port"] == 5000
        assert project["python_version"] == "3.11"
        assert project["node_version"] == "20"

    def test_create_project_with_repository_info(self, client, db_session):
        """Create project with repository URLs and branch."""
        response = client.post(
            '/api/projects/create',
            data={
                "name": "Repo Info Project",
                "repo_path": "/path/to/repo",
                "repository_url": "https://github.com/user/repo",
                "repository_ssh_url": "git@github.com:user/repo.git",
                "primary_branch": "develop",
                "documentation_url": "https://docs.example.com"
            },
            content_type='application/json'
        )
        assert response.status_code == 201
        data = response.json()
        project = data["project"]
        assert project["repo_path"] == "/path/to/repo"
        assert project["repository_url"] == "https://github.com/user/repo"
        assert project["repository_ssh_url"] == "git@github.com:user/repo.git"
        assert project["primary_branch"] == "develop"
        assert project["documentation_url"] == "https://docs.example.com"

    def test_create_project_all_fields(self, client, db_session):
        """Create project with ALL supported fields - comprehensive test."""
        response = client.post(
            '/api/projects/create',
            data={
                "name": "Complete Project",
                "description": "A project with all fields populated",
                # Repository
                "repo_path": "/Users/dev/projects/complete",
                "repository_url": "https://github.com/org/complete-project",
                "repository_ssh_url": "git@github.com:org/complete-project.git",
                "primary_branch": "main",
                "documentation_url": "https://docs.complete-project.io",
                # Tech Stack
                "stack_tags": ["python", "flask", "postgresql", "redis"],
                "languages": ["Python", "JavaScript"],
                "frameworks": ["Flask", "Vue.js"],
                "databases": ["PostgreSQL", "Redis", "Elasticsearch"],
                # Key Files
                "key_files": ["app.py", "wsgi.py", "config.py"],
                "entry_point": "wsgi.py",
                "config_files": [".env", "config.yaml"],
                # Commands
                "build_command": "pip install -r requirements.txt && npm install",
                "test_command": "pytest tests/ -v --cov",
                "run_command": "gunicorn wsgi:app",
                "deploy_command": "kubectl apply -f k8s/",
                # Dev Settings
                "default_port": 8080,
                "python_version": "3.12",
                "node_version": "21"
            },
            content_type='application/json'
        )
        assert response.status_code == 201
        data = response.json()
        project = data["project"]

        # Verify all fields were saved
        assert project["name"] == "Complete Project"
        assert project["description"] == "A project with all fields populated"
        assert project["repo_path"] == "/Users/dev/projects/complete"
        assert project["repository_url"] == "https://github.com/org/complete-project"
        assert project["repository_ssh_url"] == "git@github.com:org/complete-project.git"
        assert project["primary_branch"] == "main"
        assert project["documentation_url"] == "https://docs.complete-project.io"
        assert project["stack_tags"] == ["python", "flask", "postgresql", "redis"]
        assert project["languages"] == ["Python", "JavaScript"]
        assert project["frameworks"] == ["Flask", "Vue.js"]
        assert project["databases"] == ["PostgreSQL", "Redis", "Elasticsearch"]
        assert project["key_files"] == ["app.py", "wsgi.py", "config.py"]
        assert project["entry_point"] == "wsgi.py"
        assert project["config_files"] == [".env", "config.yaml"]
        assert project["build_command"] == "pip install -r requirements.txt && npm install"
        assert project["test_command"] == "pytest tests/ -v --cov"
        assert project["run_command"] == "gunicorn wsgi:app"
        assert project["deploy_command"] == "kubectl apply -f k8s/"
        assert project["default_port"] == 8080
        assert project["python_version"] == "3.12"
        assert project["node_version"] == "21"


class TestProjectUpdate:
    """Tests to verify project_update handles all fields (already implemented)."""

    def test_update_project_tech_stack(self, client, db_session, sample_project):
        """Update project tech stack fields."""
        response = client.patch(
            f'/api/projects/{sample_project.id}/update',
            data={
                "languages": ["Python", "Rust"],
                "frameworks": ["FastAPI"],
                "databases": ["PostgreSQL"]
            },
            content_type='application/json'
        )
        assert response.status_code == 200
        data = response.json()
        assert data["project"]["languages"] == ["Python", "Rust"]
        assert data["project"]["frameworks"] == ["FastAPI"]
        assert data["project"]["databases"] == ["PostgreSQL"]

    def test_update_project_commands(self, client, db_session, sample_project):
        """Update project command fields."""
        response = client.patch(
            f'/api/projects/{sample_project.id}/update',
            data={
                "build_command": "make build",
                "test_command": "make test",
                "run_command": "make run"
            },
            content_type='application/json'
        )
        assert response.status_code == 200
        data = response.json()
        assert data["project"]["build_command"] == "make build"
        assert data["project"]["test_command"] == "make test"
        assert data["project"]["run_command"] == "make run"
