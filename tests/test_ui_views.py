import unittest
from unittest.mock import MagicMock, patch
from django.test import RequestFactory
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# We need to configure django settings before importing views
from django.conf import settings
if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        INSTALLED_APPS=['app'],
        TEMPLATES=[{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [], 'APP_DIRS': True}],
        SECRET_KEY='test',
        BASE_DIR=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )

from app.views.ui import task_board_view, task_view
from app.models import Project, Task, TaskPipelineStage

class TestTaskBoardView(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("app.views.ui.get_db")
    @patch("app.views.ui.render")
    def patch_render_and_db(self, mock_render, mock_get_db):
        return mock_render, mock_get_db

    @patch("app.views.ui.get_db")
    @patch("app.views.ui.render")
    @patch("app.views.ui._get_open_bugs_count")
    def test_task_board_success(self, mock_bugs_count, mock_render, mock_get_db):
        mock_bugs_count.return_value = 5

        # Mock DB session
        db_session = MagicMock()
        mock_get_db.return_value = iter([db_session])

        # Mock Project
        project = MagicMock(id=1)
        project.name = "Test Project"
        db_session.query.return_value.filter.return_value.first.return_value = project
        
        # Mock Tasks
        task1 = MagicMock(id=1, title="Task 1", pipeline_stage=TaskPipelineStage.DEV)
        task2 = MagicMock(id=2, title="Task 2", pipeline_stage=TaskPipelineStage.QA)
        project.tasks = [task1, task2]

        request = self.factory.get('/ui/projects/1/board')
        response = task_board_view(request, 1)

        # Verify render called
        self.assertTrue(mock_render.called)
        args, kwargs = mock_render.call_args
        context = args[2]
        
        self.assertEqual(context['project'].name, "Test Project")
        self.assertEqual(len(context['board']['dev']), 1)
        self.assertEqual(len(context['board']['qa']), 1)
        self.assertEqual(context['active_page'], 'projects')

    @patch("app.views.ui.get_db")
    def test_task_board_not_found(self, mock_get_db):
        db_session = MagicMock()
        mock_get_db.return_value = iter([db_session])
        
        # Mock No Project
        db_session.query.return_value.filter.return_value.first.return_value = None
        
        request = self.factory.get('/ui/projects/999/board')
        response = task_board_view(request, 999)
        
        self.assertEqual(response.status_code, 404)

    @patch("app.views.ui._get_open_bugs_count")
    @patch("app.views.ui.get_db")
    @patch("app.views.ui.render")
    def test_task_view_success(self, mock_render, mock_get_db, mock_get_bugs):
        # Mock DB session
        db_session = MagicMock()
        mock_get_db.return_value = iter([db_session])
        
        # Mock bugs count
        mock_get_bugs.return_value = 0

        # Mock Task
        task = MagicMock(id=625, task_id="T-625", title="Test Task", priority=1)
        # Fix: Ensure status enum access works
        task.status.value = 'in_progress'
        task.project.name = "Test Project"
        task.created_at.strftime.return_value = "2023-01-01"
        
        db_session.query.return_value.filter.return_value.first.return_value = task
        
        # Mock Attachments
        db_session.query.return_value.filter.return_value.all.return_value = []

        request = self.factory.get('/ui/task/625/')
        response = task_view(request, 625)

        # Verify render called
        self.assertTrue(mock_render.called)
        args, kwargs = mock_render.call_args
        self.assertEqual(args[1], 'task_detail.html')
        context = args[2]
        self.assertEqual(context['task']['title'], "Test Task")
        
        # We can't easily test template syntax here without full integration test or using Django's test client with real templates.
        # But we can try to render the template string if we load it.
        # For now, let's fix the syntax error we know exists.

if __name__ == "__main__":
    unittest.main()
