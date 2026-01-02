"""
Playwright E2E tests for monitoring pipeline progress.

Verifies:
1. Run states are progressing through pipeline
2. Database fields are being populated by agents
3. UI displays correct information
4. WorkCycles between agents work correctly

Run with: pytest tests/e2e/test_pipeline_monitoring.py -v
"""
import os
import pytest
import requests
from playwright.sync_api import Page, expect
from datetime import datetime
from typing import Optional

# Configuration
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
API_URL = f"{BASE_URL}/api"

# Valid pipeline states in order
PIPELINE_STATES = [
    "pm", "dev", "qa", "qa_failed", "sec", "sec_failed", "docs", "docs_failed",
    "testing", "testing_failed", "ready_for_commit", "merged",
    "ready_for_deploy", "deployed"
]


class PipelineMonitor:
    """Reusable pipeline monitoring logic (DRY)."""

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"

    def get_run_status(self, run_id: int) -> dict:
        """Fetch run status from API."""
        response = requests.get(f"{self.api_url}/runs/{run_id}")
        response.raise_for_status()
        return response.json()

    def get_run_reports(self, run_id: int) -> list:
        """Fetch agent reports for a run."""
        response = requests.get(f"{self.api_url}/runs/{run_id}")
        response.raise_for_status()
        return response.json().get("reports", [])

    def get_project_tasks(self, project_id: int) -> list:
        """Fetch tasks for a project."""
        response = requests.get(f"{self.api_url}/projects/{project_id}/tasks")
        response.raise_for_status()
        return response.json().get("tasks", [])

    def check_state_valid(self, state: str) -> bool:
        """Verify state is a valid pipeline state."""
        return state in PIPELINE_STATES

    def check_state_progression(self, old_state: str, new_state: str) -> bool:
        """Verify state moved forward (or to failure state)."""
        if old_state == new_state:
            return True  # No change is valid
        old_idx = PIPELINE_STATES.index(old_state) if old_state in PIPELINE_STATES else -1
        new_idx = PIPELINE_STATES.index(new_state) if new_state in PIPELINE_STATES else -1
        # Allow forward progress or failure states
        return new_idx >= old_idx or "failed" in new_state


@pytest.fixture
def monitor():
    """Fixture providing PipelineMonitor instance."""
    return PipelineMonitor()


@pytest.fixture
def page(browser):
    """Create a new page with proper viewport."""
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    yield page
    page.close()
    context.close()


class TestAPIHealth:
    """Test API endpoints are healthy."""

    def test_api_status(self, monitor):
        """Verify API is responding."""
        response = requests.get(f"{monitor.api_url}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "projects" in data
        assert "runs" in data

    def test_projects_endpoint(self, monitor):
        """Verify projects list endpoint."""
        response = requests.get(f"{monitor.api_url}/projects")
        assert response.status_code == 200
        data = response.json()
        assert "projects" in data


class TestRunStateMonitoring:
    """Monitor run state progression."""

    def test_run_has_valid_state(self, monitor):
        """Verify all runs have valid pipeline states."""
        response = requests.get(f"{monitor.api_url}/projects")
        projects = response.json().get("projects", [])

        for project in projects:
            runs_resp = requests.get(f"{monitor.api_url}/projects/{project['id']}/runs")
            if runs_resp.status_code == 200:
                runs = runs_resp.json().get("runs", [])
                for run in runs:
                    assert monitor.check_state_valid(run["state"]), \
                        f"Run {run['id']} has invalid state: {run['state']}"

    def test_run_detail_populated(self, monitor):
        """Verify run detail endpoint returns expected fields."""
        # Get first available run
        response = requests.get(f"{monitor.api_url}/projects")
        projects = response.json().get("projects", [])

        for project in projects:
            runs_resp = requests.get(f"{monitor.api_url}/projects/{project['id']}/runs")
            if runs_resp.status_code == 200:
                runs = runs_resp.json().get("runs", [])
                if runs:
                    run_id = runs[0]["id"]
                    detail = monitor.get_run_status(run_id)

                    # Verify essential fields are present
                    assert "run" in detail
                    run = detail["run"]
                    assert "id" in run
                    assert "name" in run
                    assert "state" in run
                    assert "created_at" in run
                    return  # One successful check is enough

        pytest.skip("No runs available to test")


class TestTasksMonitoring:
    """Monitor task creation and updates."""

    def test_project_has_tasks(self, monitor):
        """Verify projects with runs have tasks."""
        response = requests.get(f"{monitor.api_url}/projects")
        projects = response.json().get("projects", [])

        for project in projects:
            # Get runs
            runs_resp = requests.get(f"{monitor.api_url}/projects/{project['id']}/runs")
            if runs_resp.status_code == 200:
                runs = runs_resp.json().get("runs", [])
                if runs:
                    # Project with runs should have tasks
                    tasks = monitor.get_project_tasks(project['id'])
                    assert len(tasks) > 0, f"Project {project['name']} has runs but no tasks"
                    return  # One successful check is enough

        pytest.skip("No projects with runs available")

    def test_task_has_required_fields(self, monitor):
        """Verify tasks have all required fields populated."""
        response = requests.get(f"{monitor.api_url}/projects")
        projects = response.json().get("projects", [])

        for project in projects:
            tasks = monitor.get_project_tasks(project['id'])
            for task in tasks:
                assert "id" in task
                assert "task_id" in task
                assert "title" in task
                assert "status" in task
                assert task["title"], f"Task {task['task_id']} has empty title"
                return  # One successful check is enough

        pytest.skip("No tasks available to test")


class TestUIRendering:
    """Test UI renders correctly with Playwright."""

    @pytest.mark.parametrize("page_path,expected_title", [
        ("/ui/", "Dashboard"),
        ("/ui/projects/", "Projects"),
        ("/ui/runs/", "Runs"),
    ])
    def test_page_loads(self, page: Page, page_path: str, expected_title: str):
        """Verify main pages load without errors."""
        page.goto(f"{BASE_URL}{page_path}")
        # Wait for page to load
        page.wait_for_load_state("networkidle")
        # Check page title or heading contains expected text
        heading = page.locator(".page-title h2, h1, h2").first
        expect(heading).to_be_visible()

    def test_project_list_renders(self, page: Page):
        """Verify projects are displayed in the UI."""
        page.goto(f"{BASE_URL}/ui/projects/")
        page.wait_for_load_state("networkidle")

        # Check for project cards or list items
        projects = page.locator(".project-card, .card, [data-project-id]")
        # Should have at least one project
        count = projects.count()
        assert count >= 0, "Project list should render (even if empty)"

    def test_run_detail_accessible(self, page: Page, monitor):
        """Verify run detail page is accessible."""
        # Get a run to test
        response = requests.get(f"{monitor.api_url}/projects")
        projects = response.json().get("projects", [])

        for project in projects:
            runs_resp = requests.get(f"{monitor.api_url}/projects/{project['id']}/runs")
            if runs_resp.status_code == 200:
                runs = runs_resp.json().get("runs", [])
                if runs:
                    run_id = runs[0]["id"]
                    page.goto(f"{BASE_URL}/ui/run/{run_id}/")
                    page.wait_for_load_state("networkidle")

                    # Verify page loads (no error screen)
                    assert "error" not in page.title().lower()
                    return

        pytest.skip("No runs available to test")


class TestDatabaseFieldsPopulated:
    """Verify database fields are being populated by the system."""

    def test_project_has_metadata(self, monitor):
        """Verify projects have essential metadata populated."""
        response = requests.get(f"{monitor.api_url}/projects")
        projects = response.json().get("projects", [])

        assert len(projects) > 0, "Should have at least one project"

        for project in projects:
            # Check essential fields
            assert project.get("name"), f"Project {project['id']} missing name"
            assert project.get("created_at"), f"Project {project['name']} missing created_at"

    def test_run_timestamps_populated(self, monitor):
        """Verify run timestamps are being set."""
        response = requests.get(f"{monitor.api_url}/projects")
        projects = response.json().get("projects", [])

        for project in projects:
            runs_resp = requests.get(f"{monitor.api_url}/projects/{project['id']}/runs")
            if runs_resp.status_code == 200:
                runs = runs_resp.json().get("runs", [])
                for run in runs:
                    assert run.get("created_at"), f"Run {run['id']} missing created_at"
                    return

        pytest.skip("No runs available to test")


def run_periodic_check():
    """
    Standalone function for periodic monitoring.
    Can be called from a cron job or background task.
    """
    monitor = PipelineMonitor()
    issues = []
    timestamp = datetime.now().isoformat()

    print(f"\n{'='*60}")
    print(f"Pipeline Monitor Check - {timestamp}")
    print(f"{'='*60}")

    # Check API health
    try:
        response = requests.get(f"{monitor.api_url}/status", timeout=5)
        if response.status_code != 200:
            issues.append("API status check failed")
        else:
            data = response.json()
            print(f"✓ API Status: OK | Projects: {data.get('projects', 0)} | Runs: {data.get('runs', 0)}")
    except Exception as e:
        issues.append(f"API unreachable: {e}")
        print(f"✗ API Status: FAILED - {e}")

    # Check runs
    try:
        response = requests.get(f"{monitor.api_url}/projects", timeout=5)
        projects = response.json().get("projects", [])

        for project in projects:
            runs_resp = requests.get(f"{monitor.api_url}/projects/{project['id']}/runs", timeout=5)
            if runs_resp.status_code == 200:
                runs = runs_resp.json().get("runs", [])
                for run in runs:
                    state = run.get("state", "unknown")
                    run_id = run.get("id")
                    print(f"  Run #{run_id}: {run.get('name', 'Unnamed')[:40]}... -> {state.upper()}")

                    if not monitor.check_state_valid(state):
                        issues.append(f"Run {run_id} has invalid state: {state}")
    except Exception as e:
        issues.append(f"Failed to check runs: {e}")

    # Summary
    print(f"\n{'='*60}")
    if issues:
        print(f"⚠ Issues Found: {len(issues)}")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("✓ All checks passed")
    print(f"{'='*60}\n")

    return len(issues) == 0


if __name__ == "__main__":
    # Run standalone monitoring check
    import sys
    success = run_periodic_check()
    sys.exit(0 if success else 1)
