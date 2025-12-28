"""
Explicit test for the Run Agent button on task detail page.
Run with: pytest tests/e2e/test_run_agent_button.py -v --headed
"""
import pytest
from playwright.sync_api import Page, expect, Dialog


def test_run_agent_button_exists(page: Page):
    """Test that the Run Agent button exists and is clickable."""
    page.goto("http://localhost:8000/ui/task/625/")
    page.wait_for_load_state("networkidle")

    # Find the Run Agent button
    run_agent_btn = page.locator("#run-agent-btn")
    expect(run_agent_btn).to_be_visible()
    expect(run_agent_btn).to_be_enabled()

    # Take screenshot before clicking
    page.screenshot(path="screenshots/01_before_click.png")
    print("Button found and visible!")


def test_run_agent_button_shows_confirm(page: Page):
    """Test that clicking Run Agent shows a confirmation dialog."""
    page.goto("http://localhost:8000/ui/task/625/")
    page.wait_for_load_state("networkidle")

    dialog_appeared = {"value": False, "message": ""}

    def handle_dialog(dialog: Dialog):
        dialog_appeared["value"] = True
        dialog_appeared["message"] = dialog.message
        print(f"Dialog appeared! Type: {dialog.type}, Message: {dialog.message}")
        # Dismiss the dialog (click Cancel)
        dialog.dismiss()

    # Set up dialog handler BEFORE clicking
    page.on("dialog", handle_dialog)

    # Find and click the button
    run_agent_btn = page.locator("#run-agent-btn")
    expect(run_agent_btn).to_be_visible()

    print("Clicking Run Agent button...")
    run_agent_btn.click()

    # Wait a moment for dialog
    page.wait_for_timeout(1000)

    # Take screenshot
    page.screenshot(path="screenshots/02_after_click.png")

    # Verify dialog appeared
    assert dialog_appeared["value"], "Confirmation dialog did not appear!"
    assert "agent" in dialog_appeared["message"].lower(), f"Unexpected dialog message: {dialog_appeared['message']}"
    print(f"Success! Dialog message: {dialog_appeared['message']}")


def test_run_agent_button_accepts_and_calls_api(page: Page):
    """Test that accepting the dialog triggers the API call and button stays disabled."""
    page.goto("http://localhost:8000/ui/task/625/")
    page.wait_for_load_state("networkidle")

    api_called = {"value": False, "response": None}

    def handle_dialog(dialog: Dialog):
        print(f"Dialog appeared: {dialog.message}")
        # Accept the dialog (click OK)
        dialog.accept()

    def handle_response(response):
        if "/api/tasks/625/execute" in response.url:
            api_called["value"] = True
            api_called["response"] = response
            print(f"API called! Status: {response.status}, URL: {response.url}")

    # Set up handlers - dismiss any alert dialogs that appear after
    def handle_alert(dialog: Dialog):
        if dialog.type == "alert":
            print(f"Alert dismissed: {dialog.message}")
            dialog.dismiss()
        else:
            dialog.accept()

    page.on("dialog", handle_alert)
    page.on("response", handle_response)

    # Find and click the button
    run_agent_btn = page.locator("#run-agent-btn")
    expect(run_agent_btn).to_be_visible()
    expect(run_agent_btn).to_be_enabled()

    print("Clicking Run Agent button and accepting dialog...")

    # Override handler for the first confirm
    page.once("dialog", lambda d: d.accept())

    run_agent_btn.click()

    # Wait for API call and button to update
    page.wait_for_timeout(2000)

    # Button should now be disabled and have running class
    expect(run_agent_btn).to_be_disabled()
    print("Button is disabled after starting agent")

    # Check button text changed
    btn_text = run_agent_btn.locator(".btn-text").text_content()
    print(f"Button text: {btn_text}")
    assert "Agent" in btn_text or "Running" in btn_text or "Starting" in btn_text, f"Unexpected button text: {btn_text}"

    # Take screenshot showing running state
    page.screenshot(path="screenshots/03_agent_running.png")

    # Verify API was called
    assert api_called["value"], "API endpoint was not called!"
    print(f"API response status: {api_called['response'].status}")


def test_run_agent_debug_console_errors(page: Page):
    """Debug test - capture any JavaScript console errors."""
    console_messages = []
    console_errors = []

    def handle_console(msg):
        console_messages.append(f"{msg.type}: {msg.text}")
        if msg.type == "error":
            console_errors.append(msg.text)
            print(f"CONSOLE ERROR: {msg.text}")

    def handle_page_error(error):
        console_errors.append(str(error))
        print(f"PAGE ERROR: {error}")

    page.on("console", handle_console)
    page.on("pageerror", handle_page_error)

    page.goto("http://localhost:8000/ui/task/625/")
    page.wait_for_load_state("networkidle")

    # Check if button exists
    run_agent_btn = page.locator("#run-agent-btn")

    if run_agent_btn.count() == 0:
        print("ERROR: Button #run-agent-btn not found!")
        # Try to find any button with Run Agent text
        alt_btn = page.locator("button:has-text('Run Agent')")
        print(f"Alternative buttons found: {alt_btn.count()}")
        page.screenshot(path="screenshots/debug_no_button.png")
        assert False, "Run Agent button not found"

    print(f"Button found. Clicking...")

    # Handle dialog
    def handle_dialog(dialog: Dialog):
        print(f"Dialog: {dialog.type} - {dialog.message}")
        dialog.dismiss()

    page.on("dialog", handle_dialog)

    # Click with force to bypass any overlay issues
    run_agent_btn.click(force=True)

    page.wait_for_timeout(2000)

    page.screenshot(path="screenshots/debug_after_click.png")

    # Print all console messages
    print("\n--- Console Messages ---")
    for msg in console_messages:
        print(msg)

    print("\n--- Console Errors ---")
    for err in console_errors:
        print(f"ERROR: {err}")

    # Fail if there were JS errors
    if console_errors:
        assert False, f"JavaScript errors detected: {console_errors}"


if __name__ == "__main__":
    import subprocess
    subprocess.run(["pytest", __file__, "-v", "--headed", "-s"])
