"""Tests for Bug Report API endpoints."""
import pytest
import json
from django.test import Client
from app.models.bug_report import BugReport, BugReportStatus


@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def sample_bug(db_session):
    """Create a sample bug report."""
    bug = BugReport(
        title="Test Bug",
        description="Something is broken",
        url="http://localhost:5050/kanban",
        app_name="Todo App"
    )
    db_session.add(bug)
    db_session.commit()
    db_session.refresh(bug)
    return bug


@pytest.fixture
def sample_bugs(db_session):
    """Create multiple sample bug reports."""
    bugs = []
    for i in range(3):
        bug = BugReport(
            title=f"Bug {i+1}",
            description=f"Description {i+1}",
            app_name="Test App"
        )
        db_session.add(bug)
        bugs.append(bug)
    db_session.commit()
    for bug in bugs:
        db_session.refresh(bug)
    return bugs


class TestBugAPI:
    """Test Bug Report API endpoints."""

    def test_submit_bug_report(self, client, db_session):
        """Test POST /api/bugs/create."""
        response = client.post(
            '/api/bugs/create',
            data=json.dumps({
                'title': 'Test bug',
                'description': 'Something broke',
                'screenshot': 'data:image/png;base64,abc123',
                'url': 'http://localhost:5050/kanban',
                'app_name': 'Todo App'
            }),
            content_type='application/json'
        )

        assert response.status_code == 201
        data = response.json()
        assert 'id' in data
        assert data['status'] == 'created'

    def test_submit_bug_report_minimal(self, client, db_session):
        """Test POST with only required fields."""
        response = client.post(
            '/api/bugs/create',
            data=json.dumps({'title': 'Minimal bug'}),
            content_type='application/json'
        )

        assert response.status_code == 201
        data = response.json()
        assert 'id' in data

    def test_submit_bug_report_missing_title(self, client):
        """Test POST without title fails."""
        response = client.post(
            '/api/bugs/create',
            data=json.dumps({'description': 'No title provided'}),
            content_type='application/json'
        )

        assert response.status_code == 400

    def test_list_bug_reports(self, client, sample_bugs, db_session):
        """Test GET /api/bugs - should include our sample bugs."""
        # Get count before and after creating sample bugs
        response = client.get('/api/bugs')

        assert response.status_code == 200
        data = response.json()
        assert 'bugs' in data
        # Check that our sample bugs are in the list
        assert len(data['bugs']) >= 3
        bug_titles = [b['title'] for b in data['bugs']]
        assert 'Bug 1' in bug_titles
        assert 'Bug 2' in bug_titles
        assert 'Bug 3' in bug_titles

    def test_list_bug_reports_returns_list(self, client, db_session):
        """Test GET /api/bugs returns a list (may be empty or populated)."""
        response = client.get('/api/bugs')

        assert response.status_code == 200
        data = response.json()
        assert 'bugs' in data
        assert isinstance(data['bugs'], list)

    def test_get_bug_detail(self, client, sample_bug):
        """Test GET /api/bugs/<id>."""
        response = client.get(f'/api/bugs/{sample_bug.id}')

        assert response.status_code == 200
        data = response.json()
        assert data['bug']['id'] == sample_bug.id
        assert data['bug']['title'] == 'Test Bug'

    def test_get_bug_detail_not_found(self, client, db_session):
        """Test GET /api/bugs/<id> with invalid ID."""
        response = client.get('/api/bugs/99999')

        assert response.status_code == 404

    def test_update_bug_status(self, client, sample_bug, db_session):
        """Test PATCH /api/bugs/<id>/status."""
        response = client.patch(
            f'/api/bugs/{sample_bug.id}/status',
            data=json.dumps({'status': 'resolved'}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.json()
        assert data['bug']['status'] == 'resolved'

        # Verify in database
        db_session.refresh(sample_bug)
        assert sample_bug.status == BugReportStatus.RESOLVED

    def test_update_bug_status_invalid(self, client, sample_bug):
        """Test PATCH with invalid status."""
        response = client.patch(
            f'/api/bugs/{sample_bug.id}/status',
            data=json.dumps({'status': 'invalid_status'}),
            content_type='application/json'
        )

        assert response.status_code == 400

    def test_update_bug_status_not_found(self, client, db_session):
        """Test PATCH /api/bugs/<id>/status with invalid ID."""
        response = client.patch(
            '/api/bugs/99999/status',
            data=json.dumps({'status': 'resolved'}),
            content_type='application/json'
        )

        assert response.status_code == 404
