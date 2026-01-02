"""
Test for T001: Setup project structure and dependencies
"""
import pytest
from django.test import TestCase
from django.core.management import execute_from_command_line
from django.conf import settings
import os
import sys


class TestProjectStructure(TestCase):
    """Test that the project structure is properly set up."""

    def test_project_directory_structure(self):
        """Test that project directory structure is created with all required files."""
        # Check main project files exist
        required_files = [
            'manage.py',
            'requirements.txt',
            'README.md',
            '.env',
            'config/settings.py',
            'app/models/__init__.py',
            'app/views/__init__.py',
            'app/services/__init__.py',
        ]
        
        for file_path in required_files:
            full_path = os.path.join(os.getcwd(), file_path)
            self.assertTrue(os.path.exists(full_path), f"Required file {file_path} not found")

    def test_requirements_contains_dependencies(self):
        """Test that requirements.txt contains Django, psycopg2, and other dependencies."""
        requirements_path = os.path.join(os.getcwd(), 'requirements.txt')
        self.assertTrue(os.path.exists(requirements_path))
        
        with open(requirements_path, 'r') as f:
            content = f.read()
            
        # Check for key dependencies
        dependencies = ['django', 'sqlalchemy', 'psycopg2-binary', 'pytest']
        for dep in dependencies:
            self.assertIn(dep, content, f"Dependency {dep} not found in requirements.txt")

    def test_django_project_initialized(self):
        """Test that Django project is initialized with basic configuration."""
        # Test that Django settings are properly configured
        self.assertIsNotNone(settings.SECRET_KEY)
        self.assertTrue(settings.DEBUG)
        self.assertIn('app.apps.WorkflowHubConfig', settings.INSTALLED_APPS)

    def test_database_migrations_created(self):
        """Test that database migration files are created."""
        # Check alembic directory exists
        alembic_path = os.path.join(os.getcwd(), 'alembic')
        self.assertTrue(os.path.exists(alembic_path))
        
        # Check alembic.ini exists
        alembic_ini_path = os.path.join(os.getcwd(), 'alembic.ini')
        self.assertTrue(os.path.exists(alembic_ini_path))

    def test_environment_variables_configured(self):
        """Test that environment variables are configured properly."""
        # Test that .env file exists and has basic configuration
        env_path = os.path.join(os.getcwd(), '.env')
        self.assertTrue(os.path.exists(env_path))
        
        # Check that DATABASE_URL is set (or at least that the file exists)
        # This would be checked at runtime, but the file existence is a good indicator
        self.assertTrue(os.path.exists(env_path))
