"""
Test suite for T001: Setup project structure and dependencies
This test validates that the project has all required files and configurations.
"""
import os
import pytest
from pathlib import Path


class TestProjectSetup:
    """Tests for project setup and dependencies."""

    def test_project_directory_structure_exists(self):
        """Test that required project directory structure exists."""
        required_dirs = [
            'app',
            'app/models',
            'app/views',
            'app/services',
            'config',
            'tests',
            'alembic',
            'docker'
        ]
        
        for dir_path in required_dirs:
            assert os.path.exists(dir_path), f"Required directory {dir_path} does not exist"

    def test_requirements_txt_exists_and_has_dependencies(self):
        """Test that requirements.txt exists and contains required dependencies."""
        assert os.path.exists('requirements.txt'), "requirements.txt does not exist"
        
        with open('requirements.txt', 'r') as f:
            content = f.read()
            
        # Check for required dependencies
        required_deps = ['django', 'sqlalchemy', 'psycopg2-binary']
        for dep in required_deps:
            assert dep in content, f"Required dependency {dep} not found in requirements.txt"

    def test_django_project_is_initialized(self):
        """Test that Django project is properly initialized."""
        # Check that Django settings file exists
        assert os.path.exists('config/settings.py'), "Django settings.py does not exist"
        
        # Check that Django urls file exists  
        assert os.path.exists('config/urls.py'), "Django urls.py does not exist"
        
        # Check that Django wsgi file exists
        assert os.path.exists('config/wsgi.py'), "Django wsgi.py does not exist"

    def test_database_migrations_created(self):
        """Test that database migration files are created."""
        assert os.path.exists('alembic/'), "Alembic directory does not exist"
        assert os.path.exists('alembic.ini'), "Alembic config does not exist"

    def test_environment_variables_configured(self):
        """Test that environment variables are configured properly."""
        # Check that .env.example exists
        assert os.path.exists('.env.example'), ".env.example file does not exist"
        
        # Check that .env exists
        assert os.path.exists('.env'), ".env file does not exist"
        
        # Check that database URL is configured
        with open('.env', 'r') as f:
            content = f.read()
            assert 'DATABASE_URL' in content, "DATABASE_URL not found in .env"
            assert 'DJANGO_SECRET_KEY' in content, "DJANGO_SECRET_KEY not found in .env"
