"""Playwright UI tests with screenshots for Workflow Hub."""
import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def browser_context_args():
    return {"viewport": {"width": 1400, "height": 900}}


class TestWorkflowHubUI:
    """Visual UI tests with screenshots."""

    def test_dashboard(self, page: Page):
        """Test dashboard loads and take screenshot."""
        page.goto(f"{BASE_URL}/ui/")
        page.wait_for_load_state("networkidle")

        # Check title contains Workflow Hub
        expect(page).to_have_title("Dashboard - Workflow Hub")

        # Take screenshot
        page.screenshot(path="screenshots/01_dashboard.png", full_page=True)
        print("Screenshot saved: screenshots/01_dashboard.png")

    def test_run_detail_page(self, page: Page):
        """Test run detail page with tasks (regression test for RecursionError fix)."""
        page.goto(f"{BASE_URL}/ui/run/432/")
        page.wait_for_load_state("networkidle")

        # Check page loads without RecursionError
        expect(page.locator(".card")).to_be_visible()

        # Verify tasks are rendered (should be 16)
        task_rows = page.locator(".task-row")
        expect(task_rows.first).to_be_visible()

        # Take screenshot
        page.screenshot(path="screenshots/02_run_detail.png", full_page=True)
        print("Screenshot saved: screenshots/02_run_detail.png")

    def test_task_modal(self, page: Page):
        """Test task edit modal opens."""
        page.goto(f"{BASE_URL}/ui/run/432/")
        page.wait_for_load_state("networkidle")

        # Click first edit button
        edit_btn = page.locator(".edit-task-btn").first
        if edit_btn.is_visible():
            edit_btn.click()
            page.wait_for_timeout(500)  # Wait for modal animation

            # Take screenshot with modal open
            page.screenshot(path="screenshots/03_task_modal.png", full_page=True)
            print("Screenshot saved: screenshots/03_task_modal.png")
        else:
            print("No edit buttons found - skipping modal test")

    def test_add_task_modal(self, page: Page):
        """Test add task modal."""
        page.goto(f"{BASE_URL}/ui/run/432/")
        page.wait_for_load_state("networkidle")

        # Click Add Task button
        add_btn = page.locator("text=Add Task").first
        if add_btn.is_visible():
            add_btn.click()
            page.wait_for_timeout(500)

            # Fill in form
            page.fill("#task-title", "Test Task from Playwright")
            page.fill("#task-description", "This task was created by automated testing")

            page.screenshot(path="screenshots/04_add_task_modal.png", full_page=True)
            print("Screenshot saved: screenshots/04_add_task_modal.png")

    def test_projects_list(self, page: Page):
        """Test projects list page."""
        page.goto(f"{BASE_URL}/ui/projects/")
        page.wait_for_load_state("networkidle")

        page.screenshot(path="screenshots/05_projects_list.png", full_page=True)
        print("Screenshot saved: screenshots/05_projects_list.png")

    def test_runs_list(self, page: Page):
        """Test runs list page."""
        page.goto(f"{BASE_URL}/ui/runs/")
        page.wait_for_load_state("networkidle")

        page.screenshot(path="screenshots/06_runs_list.png", full_page=True)
        print("Screenshot saved: screenshots/06_runs_list.png")
