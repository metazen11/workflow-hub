#!/usr/bin/env python3
"""
Agent Runner for Goose LLM Integration

This script is invoked by n8n when the Workflow Hub emits webhooks.
It runs Goose with appropriate prompts and submits results back to the Hub.

Usage:
    # From n8n webhook, invoke via HTTP server:
    python scripts/agent_runner.py serve --port 5001

    # Or run directly for a specific agent:
    python scripts/agent_runner.py run --agent pm --run-id 1 --project-path /path/to/repo

Environment:
    WORKFLOW_HUB_URL - Base URL of Workflow Hub API (default: http://localhost:8000)
    GOOSE_PROVIDER - LLM provider for Goose (e.g., anthropic, openai, ollama)
"""
import argparse
import json
import os
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests


WORKFLOW_HUB_URL = os.getenv("WORKFLOW_HUB_URL", "http://localhost:8000")


# Shared base instructions for ALL agents (DRY principle)
BASE_INSTRUCTIONS = """
## Context & Principles (READ FIRST)

Before starting any work, read ALL markdown files in the project for context:
- README.md - Project requirements and goals
- Any other *.md files - Additional context and documentation

Project path: {project_path}
Run ID: {run_id}

## Coding Principles (NON-NEGOTIABLE)

### Code Quality
- Write clean, readable code over clever code
- Follow existing patterns in the codebase
- One function = one responsibility
- Meaningful names for variables and functions

### Security
- Never hardcode secrets/credentials
- Validate all user input
- Use parameterized queries (no string concatenation for SQL)
- Check OWASP Top 10 vulnerabilities

### Testing
- Tests define truth - if it's not tested, it doesn't work
- Write tests that can fail meaningfully
- Test edge cases, not just happy paths

### Git
- Small, focused commits
- Clear commit messages: "T001: Add feature X"
- Don't commit secrets, large binaries, or generated files

### Documentation
- Update docs when behavior changes
- Document non-obvious decisions with comments

### Error Handling
- Handle errors gracefully with actionable messages
- Log enough context to debug, but not sensitive data

### Performance
- Measure before optimizing
- Don't over-engineer - start simple, iterate
"""


# Role-specific prompts that extend BASE_INSTRUCTIONS
ROLE_PROMPTS = {
    "pm": """
## Your Role: Product Manager

Your task is to:
1. Read the project README.md to understand the goal
2. Break down the project into small, testable development tasks
3. Write tasks to `tasks.json` in the project root
4. Each task must have clear acceptance criteria

## Required Output File: tasks.json

Create or UPDATE `tasks.json` in the project root. If the file exists, add new tasks to it (upsert pattern - don't overwrite existing tasks).

Structure:

```json
{{
  "project": "Project Name",
  "tasks": [
    {{
      "id": "T001",
      "title": "Short title",
      "description": "What needs to be done",
      "acceptance_criteria": [
        "Specific testable criterion 1",
        "Specific testable criterion 2"
      ],
      "priority": 1,
      "blocked_by": []
    }}
  ]
}}
```

## Guidelines
- Tasks should be small (completable in one session)
- Each task should be independently testable
- Use blocked_by to set dependencies (e.g., "T002" blocked_by ["T001"])
- Priority 1 = highest, 10 = lowest

## Final Output
After creating tasks.json, output a JSON summary:
```json
{{
  "status": "pass",
  "summary": "Created X tasks for project",
  "details": {{
    "tasks_file": "tasks.json",
    "task_count": X,
    "task_ids": ["T001", "T002", ...]
  }}
}}
```
""",

    "dev": """
## Your Role: Developer

Your task is to:
1. Read `tasks.json` to find the next task to implement
2. Read the task's acceptance criteria carefully
3. Write code that satisfies ALL acceptance criteria
4. Commit your changes with a clear message

## Workflow
1. Read tasks.json - find task with status "pending" or "in_progress"
2. Update task status to "in_progress" in tasks.json
3. Implement the feature following the acceptance criteria
4. Write clean, simple code (DRY principle)
5. Commit changes: `git add . && git commit -m "T001: Description"`
6. Update task status to "done" in tasks.json

## Code Principles
- Keep it simple - minimum code to satisfy requirements
- No over-engineering
- Check existing patterns before creating new ones
- One function/class = one responsibility

## Final Output
```json
{{
  "status": "pass",
  "summary": "Implemented T001: Task title",
  "details": {{
    "task_id": "T001",
    "files_changed": ["file1.py", "file2.py"],
    "commit_hash": "abc123"
  }}
}}
```
""",

    "qa": """
## Your Role: QA Engineer

Your task is to:
1. Read the task from `tasks.json` that DEV just completed
2. Read the acceptance criteria for that task
3. Write tests that verify EACH acceptance criterion
4. Run all tests and report results

## Input Files
- `tasks.json` - Find task with status "done" that needs testing
- `README.md` - Understand the project requirements
- Source code files - What DEV implemented

## Output Files
- `tests/test_*.py` - Pytest test files
- Update `tasks.json` - Set task status to "tested" or create bug entry

## Workflow
1. Read tasks.json, find task marked "done"
2. Read the acceptance criteria for that task
3. Write pytest tests in tests/ directory
4. Run: `pytest tests/ -v`
5. If tests pass: update task status to "tested"
6. If tests fail: create bug in `bugs.json`

## bugs.json format (if tests fail - UPSERT, don't overwrite existing bugs)
```json
{{
  "bugs": [
    {{
      "id": "B001",
      "task_id": "T001",
      "title": "What failed",
      "steps_to_reproduce": ["Step 1", "Step 2"],
      "expected": "What should happen",
      "actual": "What actually happened"
    }}
  ]
}}
```

## Final Output
```json
{{
  "status": "pass" or "fail",
  "summary": "All 5 tests passed" or "2/5 tests failed",
  "details": {{
    "tests_run": 5,
    "tests_passed": 5,
    "tests_failed": 0,
    "bugs_created": []
  }}
}}
```
""",

    "security": """
## Your Role: Security Engineer

Your task is to:
1. Scan all source code for security vulnerabilities
2. Check for OWASP Top 10 issues
3. Review any dependencies for known vulnerabilities
4. Document findings in security_report.json

## Input Files
- All source code files (*.py, *.js, *.html)
- `requirements.txt` - Check for vulnerable packages
- `package.json` - If exists, check npm packages

## Output File: security_report.json
```json
{{
  "scan_date": "2025-12-24",
  "status": "pass" or "fail",
  "vulnerabilities": [
    {{
      "id": "SEC001",
      "severity": "high|medium|low",
      "file": "app.py",
      "line": 42,
      "issue": "SQL Injection vulnerability",
      "recommendation": "Use parameterized queries"
    }}
  ],
  "dependency_issues": [],
  "summary": "No critical vulnerabilities found"
}}
```

## Security Checks
1. SQL Injection - Look for string concatenation in queries
2. XSS - Look for unescaped user input in HTML
3. CSRF - Check forms have protection
4. Secrets - No hardcoded passwords/API keys
5. Input validation - User input is sanitized

## Final Output
```json
{{
  "status": "pass" or "fail",
  "summary": "No vulnerabilities found" or "Found 2 issues",
  "details": {{
    "critical": 0,
    "high": 0,
    "medium": 1,
    "low": 1,
    "report_file": "security_report.json"
  }}
}}
```
""",
}


def run_goose(agent_type: str, run_id: int, project_path: str) -> dict:
    """Run Goose with the appropriate prompt for the agent type."""
    role_prompt = ROLE_PROMPTS.get(agent_type)
    if not role_prompt:
        return {"status": "fail", "summary": f"Unknown agent type: {agent_type}"}

    # Combine BASE_INSTRUCTIONS with role-specific prompt (DRY)
    full_prompt = BASE_INSTRUCTIONS + role_prompt
    prompt = full_prompt.format(project_path=project_path, run_id=run_id)

    try:
        # Run goose with the prompt
        # Note: Adjust this command based on your Goose installation
        result = subprocess.run(
            ["goose", "run", "--text", prompt],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        output = result.stdout

        # Try to extract JSON from output
        try:
            # Look for JSON block in output
            if "```json" in output:
                json_start = output.find("```json") + 7
                json_end = output.find("```", json_start)
                json_str = output[json_start:json_end].strip()
            elif "{" in output and "}" in output:
                json_start = output.rfind("{")
                json_end = output.rfind("}") + 1
                json_str = output[json_start:json_end]
            else:
                json_str = None

            if json_str:
                report = json.loads(json_str)
                return report
        except json.JSONDecodeError:
            pass

        # Fallback: assume success if goose completed
        return {
            "status": "pass" if result.returncode == 0 else "fail",
            "summary": f"{agent_type.upper()} agent completed",
            "details": {"output": output[:2000]}  # Truncate long output
        }

    except subprocess.TimeoutExpired:
        return {"status": "fail", "summary": "Agent timed out"}
    except FileNotFoundError:
        return {"status": "fail", "summary": "Goose not found. Install with: pipx install goose-ai"}
    except Exception as e:
        return {"status": "fail", "summary": f"Error: {str(e)}"}


def submit_report(run_id: int, agent_type: str, report: dict):
    """Submit agent report back to Workflow Hub."""
    role_map = {"pm": "pm", "dev": "dev", "qa": "qa", "security": "security"}
    role = role_map.get(agent_type, agent_type)

    try:
        response = requests.post(
            f"{WORKFLOW_HUB_URL}/api/runs/{run_id}/report",
            json={
                "role": role,
                "status": report.get("status", "fail"),
                "summary": report.get("summary", ""),
                "details": report.get("details", {}),
                "actor": f"goose-{agent_type}"
            },
            timeout=30
        )

        if response.status_code != 201:
            print(f"Failed to submit report: {response.text}")
            return False

        print(f"Report submitted for run {run_id}, agent {agent_type}")

        # If passed, try to advance the state
        if report.get("status") == "pass":
            advance_response = requests.post(
                f"{WORKFLOW_HUB_URL}/api/runs/{run_id}/advance",
                json={"actor": f"goose-{agent_type}"},
                timeout=30
            )
            if advance_response.status_code == 200:
                print(f"Run {run_id} advanced to next state")
            else:
                print(f"Could not advance: {advance_response.text}")

        return True

    except Exception as e:
        print(f"Error submitting report: {e}")
        return False


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for receiving webhooks from n8n."""

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        event = data.get("event")
        payload = data.get("payload", {})

        print(f"Received webhook: {event}")
        print(f"Payload: {json.dumps(payload, indent=2)}")

        # Handle different event types
        if event in ("run_created", "state_change"):
            agent = payload.get("next_agent")
            run_id = payload.get("run_id")

            if agent and run_id:
                # Get project path from run
                try:
                    run_resp = requests.get(f"{WORKFLOW_HUB_URL}/api/runs/{run_id}")
                    run_data = run_resp.json()
                    project_id = run_data.get("run", {}).get("project_id")

                    proj_resp = requests.get(f"{WORKFLOW_HUB_URL}/api/projects/{project_id}")
                    proj_data = proj_resp.json()
                    project_path = proj_data.get("project", {}).get("repo_path", ".")

                    # Run the agent
                    print(f"Running {agent} agent for run {run_id}...")
                    report = run_goose(agent, run_id, project_path)

                    # Submit the report
                    submit_report(run_id, agent, report)

                except Exception as e:
                    print(f"Error processing webhook: {e}")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode())

    def log_message(self, format, *args):
        print(f"[Webhook] {args[0]}")


def serve(port: int):
    """Start HTTP server to receive webhooks."""
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    print(f"Agent runner listening on port {port}")
    print(f"Workflow Hub URL: {WORKFLOW_HUB_URL}")
    print("\nConfigure n8n to POST webhooks to: http://localhost:{port}/")
    server.serve_forever()


def get_run_state(run_id: int) -> dict:
    """Get current run state from Workflow Hub."""
    try:
        resp = requests.get(f"{WORKFLOW_HUB_URL}/api/runs/{run_id}", timeout=10)
        return resp.json().get("run", {})
    except Exception as e:
        print(f"Error getting run state: {e}")
        return {}


def loop_back_to_dev(run_id: int) -> bool:
    """When QA/SEC fails, loop back to DEV stage."""
    try:
        # First reset to dev state via API
        resp = requests.post(
            f"{WORKFLOW_HUB_URL}/api/runs/{run_id}/reset-to-dev",
            json={"actor": "orchestrator"},
            timeout=10
        )
        if resp.status_code == 200:
            print(f"  → Looped back to DEV stage")
            return True
        else:
            # Fallback: try retry endpoint
            resp = requests.post(
                f"{WORKFLOW_HUB_URL}/api/runs/{run_id}/retry",
                json={"actor": "orchestrator"},
                timeout=10
            )
            return resp.status_code == 200
    except Exception as e:
        print(f"Error looping back: {e}")
        return False


def run_pipeline(run_id: int, project_path: str, max_iterations: int = 10):
    """
    Automated pipeline orchestrator.
    Runs agents in sequence, handling failures and loopbacks.

    Pipeline: PM → DEV → QA → SEC → (human approval) → DEPLOYED
              ↑__________|  (loops back on QA/SEC failure)
    """
    STATE_TO_AGENT = {
        "pm": "pm",
        "dev": "dev",
        "qa": "qa",
        "sec": "security",
        "security": "security",
    }

    TERMINAL_STATES = {"deployed", "ready_for_deploy", "testing", "docs"}
    FAILED_STATES = {"qa_failed", "sec_failed"}

    iteration = 0

    print(f"\n{'='*60}")
    print(f"AUTOMATED PIPELINE - Run {run_id}")
    print(f"Project: {project_path}")
    print(f"{'='*60}\n")

    while iteration < max_iterations:
        iteration += 1

        # Get current state
        run_data = get_run_state(run_id)
        state = run_data.get("state", "unknown")

        print(f"\n[Iteration {iteration}] Current state: {state.upper()}")

        # Check terminal states
        if state in TERMINAL_STATES:
            print(f"\n✓ Pipeline reached {state.upper()} - stopping")
            if state == "ready_for_deploy":
                print("  → Human approval required for deployment")
            break

        # Handle failed states - loop back to DEV
        if state in FAILED_STATES:
            print(f"  ✗ {state.upper()} detected - looping back to DEV")
            if loop_back_to_dev(run_id):
                state = "dev"
            else:
                print("  ✗ Failed to loop back - stopping")
                break

        # Get agent for current state
        agent = STATE_TO_AGENT.get(state)
        if not agent:
            print(f"  ✗ No agent for state '{state}' - stopping")
            break

        # Run the agent
        print(f"  → Running {agent.upper()} agent...")
        report = run_goose(agent, run_id, project_path)

        status = report.get("status", "unknown")
        summary = report.get("summary", "No summary")
        print(f"  → Result: {status.upper()} - {summary}")

        # Submit report
        submit_report(run_id, agent, report)

        # Small delay to let state machine update
        import time
        time.sleep(1)

    if iteration >= max_iterations:
        print(f"\n✗ Max iterations ({max_iterations}) reached - stopping")

    # Final state
    final_run = get_run_state(run_id)
    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETE - Final state: {final_run.get('state', 'unknown').upper()}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Goose Agent Runner for Workflow Hub")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start webhook HTTP server")
    serve_parser.add_argument("--port", type=int, default=5001, help="Port to listen on")

    # run command - single agent
    run_parser = subparsers.add_parser("run", help="Run an agent directly")
    run_parser.add_argument("--agent", required=True, choices=["pm", "dev", "qa", "security"])
    run_parser.add_argument("--run-id", type=int, required=True, help="Workflow Hub run ID")
    run_parser.add_argument("--project-path", default=".", help="Path to project repository")
    run_parser.add_argument("--submit", action="store_true", help="Submit report to Workflow Hub")

    # pipeline command - automated full pipeline
    pipeline_parser = subparsers.add_parser("pipeline", help="Run automated pipeline (PM→DEV→QA→SEC)")
    pipeline_parser.add_argument("--run-id", type=int, required=True, help="Workflow Hub run ID")
    pipeline_parser.add_argument("--project-path", required=True, help="Path to project repository")
    pipeline_parser.add_argument("--max-iterations", type=int, default=10, help="Max pipeline iterations")

    args = parser.parse_args()

    if args.command == "serve":
        serve(args.port)
    elif args.command == "run":
        print(f"Running {args.agent} agent for run {args.run_id}...")
        report = run_goose(args.agent, args.run_id, args.project_path)
        print(f"\nReport: {json.dumps(report, indent=2)}")

        if args.submit:
            submit_report(args.run_id, args.agent, report)
    elif args.command == "pipeline":
        run_pipeline(args.run_id, args.project_path, args.max_iterations)


if __name__ == "__main__":
    main()
