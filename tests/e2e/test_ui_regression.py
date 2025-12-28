"""
Comprehensive UI Regression Tests with Screenshots.

This test suite covers all UI actions in Workflow Hub:
- Dashboard navigation
- Project CRUD
- Run CRUD
- Task CRUD
- Agent triggers
- Pipeline controls
- All modals and forms

Screenshots are saved to screenshots/regression/ for visual comparison.
Run with: pytest tests/e2e/test_ui_regression.py -v --headed
"""
import os
import pytest
from datetime import datetime
from playwright.sync_api import Page, expect


BASE_URL = os.getenv("WORKFLOW_HUB_URL", "http://localhost:8000")
SCREENSHOT_DIR = "screenshots/regression"


@pytest.fixture(scope="session", autouse=True)
def setup_screenshot_dir():
    """Create screenshot directory if it doesn't exist."""
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    # Create timestamped subdirectory for this test run
    run_dir = os.path.join(SCREENSHOT_DIR, datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


@pytest.fixture(scope="session")
def browser_context_args():
    """Configure browser viewport."""
    return {"viewport": {"width": 1400, "height": 900}}


def screenshot(page: Page, name: str, setup_screenshot_dir):
    """Take and save a screenshot with timestamp."""
    path = os.path.join(setup_screenshot_dir, f"{name}.png")
    page.screenshot(path=path, full_page=True)
    print(f"Screenshot: {path}")
    return path


class TestDashboard:
    """Dashboard page tests."""

    def test_dashboard_loads(self, page: Page, setup_screenshot_dir):
        """Test dashboard loads correctly."""
        page.goto(f"{BASE_URL}/ui/")
        page.wait_for_load_state("networkidle")

        expect(page).to_have_title("Dashboard - Workflow Hub")
        expect(page.locator(".card").first).to_be_visible()

        screenshot(page, "01_dashboard", setup_screenshot_dir)

    def test_dashboard_stats(self, page: Page, setup_screenshot_dir):
        """Verify dashboard statistics are displayed."""
        page.goto(f"{BASE_URL}/ui/")
        page.wait_for_load_state("networkidle")

        # Check stat cards exist
        stats = page.locator(".stat-card")
        expect(stats.first).to_be_visible()

        screenshot(page, "02_dashboard_stats", setup_screenshot_dir)

    def test_dashboard_director_panel(self, page: Page, setup_screenshot_dir):
        """Test Director control panel."""
        page.goto(f"{BASE_URL}/ui/")
        page.wait_for_load_state("networkidle")

        # Look for Director panel - use .first for strict mode
        director = page.locator("text=Director").first
        if director.is_visible():
            screenshot(page, "03_dashboard_director", setup_screenshot_dir)


class TestProjectsUI:
    """Project management UI tests."""

    def test_projects_list(self, page: Page, setup_screenshot_dir):
        """Test projects list page."""
        page.goto(f"{BASE_URL}/ui/projects/")
        page.wait_for_load_state("networkidle")

        expect(page).to_have_title("Projects - Workflow Hub")
        screenshot(page, "10_projects_list", setup_screenshot_dir)

    def test_project_detail(self, page: Page, setup_screenshot_dir):
        """Test project detail page."""
        page.goto(f"{BASE_URL}/ui/projects/")
        page.wait_for_load_state("networkidle")

        # Click first project link
        project_link = page.locator("a[href*='/ui/project/']").first
        if project_link.is_visible():
            project_link.click()
            page.wait_for_load_state("networkidle")
            screenshot(page, "11_project_detail", setup_screenshot_dir)

    def test_project_edit_form(self, page: Page, setup_screenshot_dir):
        """Test project edit form fields."""
        page.goto(f"{BASE_URL}/ui/projects/")
        page.wait_for_load_state("networkidle")

        # Navigate to first project
        project_link = page.locator("a[href*='/ui/project/']").first
        if project_link.is_visible():
            project_link.click()
            page.wait_for_load_state("networkidle")

            # Check form fields exist
            expect(page.locator("#project-name")).to_be_visible()
            screenshot(page, "12_project_edit_form", setup_screenshot_dir)

    def test_project_save(self, page: Page, setup_screenshot_dir):
        """Test project save functionality."""
        page.goto(f"{BASE_URL}/ui/projects/")
        page.wait_for_load_state("networkidle")

        project_link = page.locator("a[href*='/ui/project/']").first
        if project_link.is_visible():
            project_link.click()
            page.wait_for_load_state("networkidle")

            # Click first save button (project details)
            save_btn = page.locator("button:has-text('Save')").first
            if save_btn.is_visible():
                save_btn.click()
                page.wait_for_timeout(1000)
                screenshot(page, "13_project_save_result", setup_screenshot_dir)


class TestRunsUI:
    """Run management UI tests."""

    def test_runs_list(self, page: Page, setup_screenshot_dir):
        """Test runs list page."""
        page.goto(f"{BASE_URL}/ui/runs/")
        page.wait_for_load_state("networkidle")

        expect(page).to_have_title("Runs - Workflow Hub")
        screenshot(page, "20_runs_list", setup_screenshot_dir)

    def test_runs_filter(self, page: Page, setup_screenshot_dir):
        """Test run filtering."""
        page.goto(f"{BASE_URL}/ui/runs/")
        page.wait_for_load_state("networkidle")

        # Try filtering by state
        state_filter = page.locator("#filter-state")
        if state_filter.is_visible():
            state_filter.select_option("dev")
            page.wait_for_timeout(500)
            screenshot(page, "21_runs_filtered", setup_screenshot_dir)

    def test_create_run_modal(self, page: Page, setup_screenshot_dir):
        """Test create run modal."""
        page.goto(f"{BASE_URL}/ui/runs/")
        page.wait_for_load_state("networkidle")

        # Click New Run button
        new_run_btn = page.locator("button:has-text('New Run')")
        if new_run_btn.is_visible():
            new_run_btn.click()
            page.wait_for_timeout(500)

            # Check modal is visible
            modal = page.locator("#create-run-modal")
            expect(modal).to_be_visible()
            screenshot(page, "22_create_run_modal", setup_screenshot_dir)

    def test_run_detail(self, page: Page, setup_screenshot_dir):
        """Test run detail page."""
        page.goto(f"{BASE_URL}/ui/runs/")
        page.wait_for_load_state("networkidle")

        # Click first run link
        run_link = page.locator("a[href*='/ui/run/']").first
        if run_link.is_visible():
            run_link.click()
            page.wait_for_load_state("networkidle")
            screenshot(page, "23_run_detail", setup_screenshot_dir)

    def test_run_controls(self, page: Page, setup_screenshot_dir):
        """Test run control buttons."""
        page.goto(f"{BASE_URL}/ui/runs/")
        page.wait_for_load_state("networkidle")

        run_link = page.locator("a[href*='/ui/run/']").first
        if run_link.is_visible():
            run_link.click()
            page.wait_for_load_state("networkidle")

            # Check control buttons
            controls = page.locator(".run-controls, .state-control")
            if controls.is_visible():
                screenshot(page, "24_run_controls", setup_screenshot_dir)


class TestTasksUI:
    """Task management UI tests."""

    def test_task_board(self, page: Page, setup_screenshot_dir):
        """Test task board view."""
        page.goto(f"{BASE_URL}/ui/projects/")
        page.wait_for_load_state("networkidle")

        # Find a project with board link
        board_link = page.locator("a[href*='/board']").first
        if board_link.is_visible():
            board_link.click()
            page.wait_for_load_state("networkidle")
            screenshot(page, "30_task_board", setup_screenshot_dir)

    def test_task_detail(self, page: Page, setup_screenshot_dir):
        """Test task detail page."""
        # Go to a run with tasks
        page.goto(f"{BASE_URL}/ui/runs/")
        page.wait_for_load_state("networkidle")

        run_link = page.locator("a[href*='/ui/run/']").first
        if run_link.is_visible():
            run_link.click()
            page.wait_for_load_state("networkidle")

            # Click on a task
            task_link = page.locator("a[href*='/ui/task/']").first
            if task_link.is_visible():
                task_link.click()
                page.wait_for_load_state("networkidle")
                screenshot(page, "31_task_detail", setup_screenshot_dir)

    def test_task_edit_modal(self, page: Page, setup_screenshot_dir):
        """Test task edit modal."""
        page.goto(f"{BASE_URL}/ui/runs/")
        page.wait_for_load_state("networkidle")

        run_link = page.locator("a[href*='/ui/run/']").first
        if run_link.is_visible():
            run_link.click()
            page.wait_for_load_state("networkidle")

            # Click edit task button
            edit_btn = page.locator(".edit-task-btn, button:has-text('Edit')").first
            if edit_btn.is_visible():
                edit_btn.click()
                page.wait_for_timeout(500)
                screenshot(page, "32_task_edit_modal", setup_screenshot_dir)

    def test_add_task(self, page: Page, setup_screenshot_dir):
        """Test add task functionality."""
        page.goto(f"{BASE_URL}/ui/runs/")
        page.wait_for_load_state("networkidle")

        run_link = page.locator("a[href*='/ui/run/']").first
        if run_link.is_visible():
            run_link.click()
            page.wait_for_load_state("networkidle")

            # Click Add Task button
            add_btn = page.locator("button:has-text('Add Task')")
            if add_btn.is_visible():
                add_btn.click()
                page.wait_for_timeout(500)
                screenshot(page, "33_add_task_modal", setup_screenshot_dir)


class TestAgentTriggers:
    """Agent trigger UI tests."""

    def test_trigger_agent_button(self, page: Page, setup_screenshot_dir):
        """Test agent trigger button exists."""
        page.goto(f"{BASE_URL}/ui/runs/")
        page.wait_for_load_state("networkidle")

        run_link = page.locator("a[href*='/ui/run/']").first
        if run_link.is_visible():
            run_link.click()
            page.wait_for_load_state("networkidle")

            # Check for agent trigger section
            trigger_btn = page.locator("button:has-text('Run Agent'), button:has-text('Trigger')")
            if trigger_btn.first.is_visible():
                screenshot(page, "40_agent_trigger_section", setup_screenshot_dir)

    def test_agent_select_dropdown(self, page: Page, setup_screenshot_dir):
        """Test agent selection dropdown."""
        page.goto(f"{BASE_URL}/ui/runs/")
        page.wait_for_load_state("networkidle")

        run_link = page.locator("a[href*='/ui/run/']").first
        if run_link.is_visible():
            run_link.click()
            page.wait_for_load_state("networkidle")

            agent_select = page.locator("#agent-select")
            if agent_select.is_visible():
                agent_select.click()
                page.wait_for_timeout(300)
                screenshot(page, "41_agent_select_dropdown", setup_screenshot_dir)


class TestBugsUI:
    """Bug reports UI tests."""

    def test_bugs_list(self, page: Page, setup_screenshot_dir):
        """Test bugs list page."""
        page.goto(f"{BASE_URL}/ui/bugs/")
        page.wait_for_load_state("networkidle")

        screenshot(page, "50_bugs_list", setup_screenshot_dir)


class TestNavigation:
    """Navigation and menu tests."""

    def test_sidebar_navigation(self, page: Page, setup_screenshot_dir):
        """Test sidebar navigation."""
        page.goto(f"{BASE_URL}/ui/")
        page.wait_for_load_state("networkidle")

        # Check sidebar links - use .first to avoid strict mode violation
        sidebar = page.locator(".sidebar, nav").first
        if sidebar.is_visible():
            screenshot(page, "60_sidebar", setup_screenshot_dir)

    def test_navigation_links(self, page: Page, setup_screenshot_dir):
        """Test all main navigation links work."""
        pages_to_test = [
            ("/ui/", "Dashboard"),
            ("/ui/projects/", "Projects"),
            ("/ui/runs/", "Runs"),
            ("/ui/bugs/", "Bugs"),
        ]

        for url, name in pages_to_test:
            page.goto(f"{BASE_URL}{url}")
            page.wait_for_load_state("networkidle")

            # Verify page loads (no error)
            expect(page.locator("body")).to_be_visible()

        screenshot(page, "61_navigation_complete", setup_screenshot_dir)


class TestErrorHandling:
    """Error handling tests."""

    def test_404_page(self, page: Page, setup_screenshot_dir):
        """Test 404 error page."""
        page.goto(f"{BASE_URL}/ui/nonexistent/")
        page.wait_for_load_state("networkidle")

        screenshot(page, "70_404_page", setup_screenshot_dir)

    def test_invalid_run_id(self, page: Page, setup_screenshot_dir):
        """Test invalid run ID handling."""
        page.goto(f"{BASE_URL}/ui/run/999999/")
        page.wait_for_load_state("networkidle")

        screenshot(page, "71_invalid_run", setup_screenshot_dir)


class TestProofOfWork:
    """Proof of work UI tests."""

    def test_proof_section_on_task(self, page: Page, setup_screenshot_dir):
        """Test proof section exists on task detail."""
        page.goto(f"{BASE_URL}/ui/runs/")
        page.wait_for_load_state("networkidle")

        run_link = page.locator("a[href*='/ui/run/']").first
        if run_link.is_visible():
            run_link.click()
            page.wait_for_load_state("networkidle")

            task_link = page.locator("a[href*='/ui/task/']").first
            if task_link.is_visible():
                task_link.click()
                page.wait_for_load_state("networkidle")

                # Look for proof section
                proof_section = page.locator("text=Proof, text=Evidence")
                if proof_section.first.is_visible():
                    screenshot(page, "80_proof_section", setup_screenshot_dir)


# Convenience function to run all tests and generate report
def run_all_tests():
    """Run all UI regression tests."""
    import subprocess
    result = subprocess.run([
        "pytest", __file__, "-v",
        "--html=screenshots/regression/report.html",
        "--self-contained-html"
    ], capture_output=True, text=True)
    print(result.stdout)
    print(result.stderr)
    return result.returncode


if __name__ == "__main__":
    run_all_tests()
