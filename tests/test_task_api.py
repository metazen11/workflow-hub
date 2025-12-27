"""Tests for Task API endpoints."""
import pytest
import json
from django.test import Client
from app.models.task import Task


@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def sample_task(db_session, sample_project):
    """Create a sample task."""
    task = Task(
        project_id=sample_project.id,
        task_id="T001",
        title="Test Task",
        description="A test task description",
        priority=5
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture
def sample_tasks(db_session, sample_project):
    """Create multiple sample tasks."""
    tasks = []
    for i in range(3):
        task = Task(
            project_id=sample_project.id,
            task_id=f"T{i+1:03d}",
            title=f"Task {i+1}",
            description=f"Description {i+1}",
            priority=i+1
        )
        db_session.add(task)
        tasks.append(task)
    db_session.commit()
    for task in tasks:
        db_session.refresh(task)
    return tasks


class TestTaskAPI:
    """Test Task API endpoints."""

    def test_create_task(self, client, sample_project, db_session):
        """Test POST /api/projects/{id}/tasks/create."""
        response = client.post(
            f'/api/projects/{sample_project.id}/tasks/create',
            data=json.dumps({
                'title': 'New Task',
                'description': 'Task description',
                'priority': 3
            }),
            content_type='application/json'
        )

        assert response.status_code == 201
        data = response.json()
        assert 'task' in data
        assert data['task']['title'] == 'New Task'
        assert data['task']['task_id'] == 'T001'  # Auto-generated

    def test_create_task_auto_generates_task_id(self, client, sample_project, sample_task, db_session):
        """Test task_id is auto-generated when not provided."""
        response = client.post(
            f'/api/projects/{sample_project.id}/tasks/create',
            data=json.dumps({
                'title': 'Second Task'
            }),
            content_type='application/json'
        )

        assert response.status_code == 201
        data = response.json()
        assert data['task']['task_id'] == 'T002'  # Next after T001

    def test_create_task_missing_title(self, client, sample_project):
        """Test POST without title fails."""
        response = client.post(
            f'/api/projects/{sample_project.id}/tasks/create',
            data=json.dumps({'description': 'No title'}),
            content_type='application/json'
        )

        assert response.status_code == 400

    def test_list_tasks(self, client, sample_project, sample_tasks):
        """Test GET /api/projects/{id}/tasks."""
        response = client.get(f'/api/projects/{sample_project.id}/tasks')

        assert response.status_code == 200
        data = response.json()
        assert 'tasks' in data
        assert len(data['tasks']) == 3

    def test_update_task(self, client, sample_task, db_session):
        """Test PATCH /api/tasks/{id}/update."""
        response = client.patch(
            f'/api/tasks/{sample_task.id}/update',
            data=json.dumps({
                'title': 'Updated Title',
                'priority': 10
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['task']['title'] == 'Updated Title'
        assert data['task']['priority'] == 10

    def test_update_task_not_found(self, client, db_session):
        """Test PATCH /api/tasks/{id}/update with invalid ID."""
        response = client.patch(
            '/api/tasks/99999/update',
            data=json.dumps({'title': 'Updated'}),
            content_type='application/json'
        )

        assert response.status_code == 404

    def test_delete_task(self, client, sample_task, db_session):
        """Test DELETE /api/tasks/{id}/delete."""
        task_id = sample_task.id

        response = client.delete(f'/api/tasks/{task_id}/delete')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # Verify task is deleted from database
        deleted_task = db_session.query(Task).filter(Task.id == task_id).first()
        assert deleted_task is None

    def test_delete_task_via_post(self, client, sample_task, db_session):
        """Test POST /api/tasks/{id}/delete also works."""
        task_id = sample_task.id

        response = client.post(f'/api/tasks/{task_id}/delete')

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

    def test_delete_task_not_found(self, client, db_session):
        """Test DELETE /api/tasks/{id}/delete with invalid ID."""
        response = client.delete('/api/tasks/99999/delete')

        assert response.status_code == 404

    def test_update_task_status(self, client, sample_task, db_session):
        """Test POST /api/tasks/{id}/status."""
        response = client.post(
            f'/api/tasks/{sample_task.id}/status',
            data=json.dumps({'status': 'in_progress'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['task']['status'] == 'in_progress'
