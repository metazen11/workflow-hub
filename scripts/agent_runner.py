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

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


WORKFLOW_HUB_URL = os.getenv("WORKFLOW_HUB_URL", "http://localhost:8000")

# LLM Provider configuration - supports multiple backends
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "goose")  # goose, claude, openai, ollama

# Timeout configuration - local LLMs can be slow
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "600"))  # 10 minutes default for local LLMs

# Find Goose executable (may not be in subprocess PATH)
def find_goose_executable():
    """Find the goose executable, checking common locations."""
    # Check if explicitly set
    explicit_path = os.getenv("GOOSE_PATH")
    if explicit_path and os.path.exists(explicit_path):
        return explicit_path

    # Common installation locations
    common_paths = [
        "/opt/homebrew/bin/goose",  # Homebrew on Apple Silicon
        "/usr/local/bin/goose",     # Homebrew on Intel Mac
        os.path.expanduser("~/.local/bin/goose"),  # pipx
        "/usr/bin/goose",           # System install
    ]

    for path in common_paths:
        if os.path.exists(path):
            return path

    # Try which command
    try:
        result = subprocess.run(["which", "goose"], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass

    return "goose"  # Fallback to PATH lookup

GOOSE_EXECUTABLE = find_goose_executable()


def get_agent_prompt(role: str, run_id: int, project_path: str) -> str:
    """
    Load agent prompt from database and format with context.

    Prompts are stored in the role_configs table (see WH-010).
    This replaces the hardcoded ROLE_PROMPTS dict (DRY principle).
    """
    try:
        from app.db import get_db
        from app.models.role_config import RoleConfig

        db = next(get_db())
        config = db.query(RoleConfig).filter(
            RoleConfig.role == role,
            RoleConfig.active == True
        ).first()

        if config and config.prompt:
            # Format the prompt with context variables
            prompt = config.prompt.format(
                project_path=project_path,
                run_id=run_id
            )
            db.close()
            return prompt

        db.close()

    except Exception as e:
        print(f"Warning: Could not load prompt from DB for role '{role}': {e}")

    # Fallback: return minimal prompt if DB unavailable
    return f"""
## Your Role: {role.upper()}

Project path: {project_path}
Run ID: {run_id}

Execute your role's responsibilities and output a JSON status report.
"""


def get_role_config(role: str) -> dict:
    """
    Load full role configuration from database.

    Returns the RoleConfig as a dict including checks and approval requirements.
    """
    try:
        from app.db import get_db
        from app.models.role_config import RoleConfig

        db = next(get_db())
        config = db.query(RoleConfig).filter(
            RoleConfig.role == role,
            RoleConfig.active == True
        ).first()

        if config:
            result = config.to_dict()
            db.close()
            return result

        db.close()

    except Exception as e:
        print(f"Warning: Could not load config from DB for role '{role}': {e}")

    return {"role": role, "requires_approval": False, "checks": {}}


def run_goose(agent_type: str, run_id: int, project_path: str) -> dict:
    """Run Goose with the appropriate prompt for the agent type."""
    # Load prompt from database (DRY - prompts stored in role_configs table)
    prompt = get_agent_prompt(agent_type, run_id, project_path)
    if not prompt or len(prompt) < 50:
        return {"status": "fail", "summary": f"Could not load prompt for agent: {agent_type}"}

    try:
        # Check if Goose is available
        if not GOOSE_EXECUTABLE or GOOSE_EXECUTABLE == "goose":
            # Verify goose is in PATH
            try:
                subprocess.run(["which", "goose"], capture_output=True, check=True)
            except subprocess.CalledProcessError:
                return {
                    "status": "fail",
                    "summary": f"Goose not found. Searched: /opt/homebrew/bin/goose, ~/.local/bin/goose, PATH",
                    "details": {"goose_path": GOOSE_EXECUTABLE, "error": "executable_not_found"}
                }

        # Run goose with the prompt (use configurable timeout for local LLMs)
        print(f"  Running Goose with {LLM_TIMEOUT}s timeout...")
        result = subprocess.run(
            [GOOSE_EXECUTABLE, "run", "--text", prompt],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=LLM_TIMEOUT
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

        # For QA agent, check bugs.json file
        if agent_type == "qa":
            bugs_path = os.path.join(project_path, "bugs.json")
            if os.path.exists(bugs_path):
                try:
                    with open(bugs_path) as f:
                        bugs_data = json.load(f)

                    bugs = bugs_data.get("bugs", [])
                    if bugs:
                        return {
                            "status": "fail",
                            "summary": f"QA found {len(bugs)} bugs",
                            "details": {
                                "bugs": bugs,
                                "bugs_count": len(bugs),
                                "bugs_file": "bugs.json"
                            }
                        }
                except Exception as e:
                    print(f"Warning: Could not read bugs.json: {e}")

        # For security agent, check the security_report.json file
        if agent_type == "security":
            security_report_path = os.path.join(project_path, "security_report.json")
            if os.path.exists(security_report_path):
                try:
                    with open(security_report_path) as f:
                        sec_report = json.load(f)

                    vulnerabilities = sec_report.get("vulnerabilities", [])
                    # Count by severity
                    high_count = len([v for v in vulnerabilities if v.get("severity") in ("critical", "high")])
                    medium_count = len([v for v in vulnerabilities if v.get("severity") == "medium"])
                    low_count = len([v for v in vulnerabilities if v.get("severity") == "low"])

                    # Fail if any high/critical vulnerabilities found
                    if high_count > 0:
                        return {
                            "status": "fail",
                            "summary": f"Security scan found {high_count} high/critical vulnerabilities",
                            "details": {
                                "vulnerabilities": vulnerabilities,
                                "critical": len([v for v in vulnerabilities if v.get("severity") == "critical"]),
                                "high": high_count,
                                "medium": medium_count,
                                "low": low_count,
                                "report_file": "security_report.json"
                            }
                        }
                    else:
                        # Pass if only medium/low issues
                        return {
                            "status": "pass",
                            "summary": f"Security scan complete - {medium_count} medium, {low_count} low issues",
                            "details": {
                                "vulnerabilities": vulnerabilities,
                                "critical": 0,
                                "high": 0,
                                "medium": medium_count,
                                "low": low_count,
                                "report_file": "security_report.json"
                            }
                        }
                except Exception as e:
                    print(f"Warning: Could not read security_report.json: {e}")

        # Fallback: assume success if goose completed
        return {
            "status": "pass" if result.returncode == 0 else "fail",
            "summary": f"{agent_type.upper()} agent completed",
            "details": {"output": output[:2000]}  # Truncate long output
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "fail",
            "summary": f"Agent timed out after {LLM_TIMEOUT}s. Increase LLM_TIMEOUT env var for slower models.",
            "details": {"timeout_seconds": LLM_TIMEOUT}
        }
    except FileNotFoundError as e:
        return {
            "status": "fail",
            "summary": f"Goose executable not found at: {GOOSE_EXECUTABLE}",
            "details": {
                "error": str(e),
                "searched_paths": [
                    "/opt/homebrew/bin/goose",
                    "/usr/local/bin/goose",
                    "~/.local/bin/goose",
                    "/usr/bin/goose"
                ],
                "suggestion": "Install with: brew install goose-ai OR pipx install goose-ai"
            }
        }
    except Exception as e:
        return {
            "status": "fail",
            "summary": f"Error running Goose: {str(e)}",
            "details": {"error_type": type(e).__name__, "error": str(e)}
        }


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

        # Always try to advance the state - the state machine handles pass/fail transitions
        # For QA/SEC: pass → next stage, fail → QA_FAILED/SEC_FAILED
        advance_response = requests.post(
            f"{WORKFLOW_HUB_URL}/api/runs/{run_id}/advance",
            json={"actor": f"goose-{agent_type}"},
            timeout=30
        )
        if advance_response.status_code == 200:
            result = advance_response.json()
            new_state = result.get("state", "unknown")
            print(f"Run {run_id} advanced to: {new_state}")
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
