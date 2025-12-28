#!/usr/bin/env python3
"""
Agent Runner - Pluggable Agent Execution System

This script is invoked by n8n when the Workflow Hub emits webhooks.
It runs agents (via providers like Goose, Ollama, etc.) and submits results back to the Hub.

Usage:
    # From n8n webhook, invoke via HTTP server:
    python scripts/agent_runner.py serve --port 5001

    # Or run directly for a specific agent:
    python scripts/agent_runner.py run --agent pm --run-id 1 --project-path /path/to/repo

Environment:
    WORKFLOW_HUB_URL - Base URL of Workflow Hub API (default: http://localhost:8000)
    AGENT_PROVIDER   - Agent provider to use (default: goose)
    LLM_TIMEOUT      - Timeout for agent execution in seconds (default: 600)
"""
import argparse
import json
import os
import subprocess
import sys
import abc
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Optional
import requests

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


WORKFLOW_HUB_URL = os.getenv("WORKFLOW_HUB_URL", "http://localhost:8000")
AGENT_PROVIDER = os.getenv("AGENT_PROVIDER", "goose").lower()
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "600"))


# =============================================================================
# Abstract Base Class for Agent Providers
# =============================================================================

class AgentProvider(abc.ABC):
    """Abstract base class for agent providers."""
    
    @abc.abstractmethod
    def run_agent(self, role: str, run_id: int, project_path: str, prompt: str) -> Dict[str, Any]:
        """
        Run the agent with the given role and prompt.
        
        Args:
            role: The agent role (pm, dev, qa, security, etc.)
            run_id: The ID of the current run
            project_path: Absolute path to the project repository
            prompt: The full prompt text to send to the agent
            
        Returns:
            Dict containing 'status' (pass/fail), 'summary', and 'details'
        """
        pass

    def get_agent_prompt(self, role: str, run_id: int, project_path: str) -> str:
        """
        Load agent prompt from database and format with context.
        Includes full project details and handoff context in every prompt.
        """
        project_context = self._get_project_context(role, run_id, project_path)

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
                    run_id=run_id,
                    project_context=project_context,
                    **self._get_format_vars(project_path, run_id)
                )
                db.close()
                return f"{project_context}\n\n{prompt}"

            db.close()

        except Exception as e:
            print(f"Warning: Could not load prompt from DB for role '{role}': {e}")
            pass

        # Fallback: return minimal prompt if DB unavailable
        return f"""
{project_context}

## Your Role: {role.upper()}

Execute your role's responsibilities and output a JSON status report.
"""

    def _get_project_context(self, role: str, run_id: int, project_path: str) -> str:
        """Fetch full project details and handoff context from DB.

        Uses the handoff service to build comprehensive context including:
        - Project info (name, tech stack, commands)
        - Run state and goal
        - ALL previous agent reports (full history)
        - Recent git commits
        - Role-specific deliverables
        """
        try:
            from app.db import get_db
            from app.models.project import Project
            from app.models.run import Run
            from app.services.handoff_service import get_handoff_for_prompt

            db = next(get_db())

            # Get run and project details
            run = db.query(Run).filter(Run.id == run_id).first()
            if not run:
                db.close()
                return f"# Project Context\nProject Path: {project_path}\nRun ID: {run_id}"

            project = db.query(Project).filter(Project.id == run.project_id).first()
            if not project:
                db.close()
                return f"# Project Context\nProject Path: {project_path}\nRun ID: {run_id}"

            # Get handoff context (writes HANDOFF.md and returns context string)
            handoff_context = get_handoff_for_prompt(
                db=db,
                run_id=run_id,
                role=role,
                project_path=project.repo_path or project_path,
                write_file=True
            )

            # Build comprehensive context combining project info + handoff
            context = f"""# Project Context

## Project: {project.name}
- **ID**: {project.id}
- **Repository**: {project.repo_path or project_path}
- **Git URL**: {project.git_url or 'N/A'}
- **Branch**: {project.branch or 'main'}

## Technology Stack
{project.tech_stack or 'Not specified'}

## Key Files
{project.key_files or 'Not specified'}

## Build/Test/Run Commands
- **Build**: {project.build_cmd or 'Not specified'}
- **Test**: {project.test_cmd or 'Not specified'}
- **Run**: {project.run_cmd or 'Not specified'}

## IMPORTANT: Stay in your workspace!
You MUST work only within: {project.repo_path or project_path}
Do NOT modify files outside this directory.

## Proof-of-Work Requirements
You MUST provide evidence of your work by uploading proofs to the API:
- **Screenshots**: Capture UI states, test results, or visual changes
- **Logs**: Save command output, test results, or build logs
- **Reports**: Generate summary reports of your findings

Upload proofs using:
```bash
curl -X POST "http://localhost:8000/api/runs/{run_id}/proofs/upload" \\
  -F "stage=dev" \\
  -F "proof_type=screenshot" \\
  -F "description=description_here" \\
  -F "file=@/path/to/file.png"
```

Proof types: screenshot, log, report
Stages: dev, qa, sec, docs

---

{handoff_context}"""
            db.close()
            return context

        except Exception as e:
            print(f"Warning: Could not fetch project context: {e}")
            return f"# Project Context\nProject Path: {project_path}\nRun ID: {run_id}"

    def _get_format_vars(self, project_path: str, run_id: int) -> dict:
        """Get additional format variables for prompt templates."""
        return {
            "project_name": os.path.basename(project_path),
            "workspace": project_path,
        }

# =============================================================================
# Goose Provider Implementation
# =============================================================================

class GooseProvider(AgentProvider):
    """Provider implementation for Goose AI agent."""
    
    def __init__(self):
        self.executable = self._find_goose_executable()

    def _find_goose_executable(self) -> str:
        """Find the goose executable, checking common locations."""
        explicit_path = os.getenv("GOOSE_PATH")
        if explicit_path and os.path.exists(explicit_path):
            return explicit_path

        common_paths = [
            "/opt/homebrew/bin/goose",
            "/usr/local/bin/goose",
            os.path.expanduser("~/.local/bin/goose"),
            "/usr/bin/goose",
        ]

        for path in common_paths:
            if os.path.exists(path):
                return path

        try:
            result = subprocess.run(["which", "goose"], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

        return "goose"

    def run_agent(self, role: str, run_id: int, project_path: str, prompt: str) -> Dict[str, Any]:
        if not prompt or len(prompt) < 10:
             return {"status": "fail", "summary": f"Invalid prompt for agent: {role}"}
        
        try:
            # Check executable availability
            if self.executable == "goose":
                try:
                    subprocess.run(["which", "goose"], capture_output=True, check=True)
                except subprocess.CalledProcessError:
                    return {
                        "status": "fail",
                        "summary": "Goose executable not found",
                        "details": {"error": "Ensure 'goose' is in PATH or set GOOSE_PATH"}
                    }

            print(f"  Running Goose ({role}) with {LLM_TIMEOUT}s timeout...")
            result = subprocess.run(
                [self.executable, "run", "--text", prompt],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=LLM_TIMEOUT
            )

            output = result.stdout
            report = self._parse_json_output(output)
            
            # If no JSON parsed, create a basic report from output
            if not report:
                # If exit code 0 but no JSON, it's a "soft" pass unless we have stricter rules
                status = "pass" if result.returncode == 0 else "fail"
                report = {
                    "status": status,
                    "summary": f"{role.upper()} agent execution completed",
                    "details": {}
                }

            # Always include full raw output for logging (no truncation)
            report["raw_output"] = output

            # Role-specific additional checks (checking specific result files)
            report = self._perform_role_checks(role, project_path, report)
            
            return report

        except subprocess.TimeoutExpired:
            return {
                "status": "fail",
                "summary": f"Agent timed out after {LLM_TIMEOUT}s",
                "details": {"timeout": LLM_TIMEOUT}
            }
        except Exception as e:
            return {
                "status": "fail",
                "summary": f"Error running Goose: {str(e)}",
                "details": {"error": str(e)}
            }

    def _parse_json_output(self, output: str) -> Optional[Dict]:
        """Attempt to extract and parse JSON from mixed output."""
        try:
            if "```json" in output:
                json_start = output.find("```json") + 7
                json_end = output.find("```", json_start)
                json_str = output[json_start:json_end].strip()
            elif "{" in output and "}" in output:
                # Last valid JSON block heuristic
                json_start = output.rfind("{")
                json_end = output.rfind("}") + 1
                json_str = output[json_start:json_end]
            else:
                return None
            
            return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            return None

    def _perform_role_checks(self, role: str, project_path: str, report: Dict) -> Dict:
        """Inject additional checks based on role (QA bugs file, Security report)."""
        
        # QA Agent Check
        if role == "qa":
            bugs_path = os.path.join(project_path, "bugs.json")
            if os.path.exists(bugs_path):
                try:
                    with open(bugs_path) as f:
                        bugs_data = json.load(f)
                    
                    bugs = bugs_data.get("bugs", [])
                    if bugs:
                        # Override report if bugs found
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

        # Security Agent Check
        elif role == "security":
            sec_path = os.path.join(project_path, "security_report.json")
            if os.path.exists(sec_path):
                try:
                    with open(sec_path) as f:
                        sec_report = json.load(f)
                    
                    vulnerabilities = sec_report.get("vulnerabilities", [])
                    high_critical = [v for v in vulnerabilities if v.get("severity") in ("critical", "high")]
                    
                    if high_critical:
                        return {
                            "status": "fail",
                            "summary": f"Security scan found {len(high_critical)} high/critical vulnerabilities",
                            "details": {
                                "vulnerabilities": vulnerabilities,
                                "high_critical_count": len(high_critical),
                                "report_file": "security_report.json"
                            }
                        }
                except Exception as e:
                    print(f"Warning: Could not read security_report.json: {e}")
        
        return report


# =============================================================================
# Factory & Mock Providers
# =============================================================================

class MockProvider(AgentProvider):
    """Mock provider for testing without an LLM."""
    def run_agent(self, role: str, run_id: int, project_path: str, prompt: str) -> Dict[str, Any]:
        return {
            "status": "pass",
            "summary": f"Mock execution for {role}",
            "details": {"mock": True, "run_id": run_id}
        }

def get_provider() -> AgentProvider:
    """Factory to get the configured agent provider."""
    if AGENT_PROVIDER == "mock":
        return MockProvider()
    elif AGENT_PROVIDER == "goose":
        return GooseProvider()
    else:
        # Default fallback or raise error
        print(f"Unknown provider '{AGENT_PROVIDER}', falling back to Goose")
        return GooseProvider()


# =============================================================================
# Main Runner Logic
# =============================================================================

def run_agent_logic(agent_type: str, run_id: int, project_path: str) -> Dict[str, Any]:
    provider = get_provider()
    prompt = provider.get_agent_prompt(agent_type, run_id, project_path)
    return provider.run_agent(agent_type, run_id, project_path, prompt)

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
                "actor": f"{AGENT_PROVIDER}-{agent_type}",
                "raw_output": report.get("raw_output", "")
            },
            timeout=30
        )

        if response.status_code != 201:
            print(f"Failed to submit report: {response.text}")
            return False

        print(f"Report submitted for run {run_id}, agent {agent_type}")

        # Always try to advance the state - the state machine handles pass/fail transitions
        advance_response = requests.post(
            f"{WORKFLOW_HUB_URL}/api/runs/{run_id}/advance",
            json={"actor": f"{AGENT_PROVIDER}-{agent_type}"},
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

# =============================================================================
# Webhook Server
# =============================================================================

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
        
        # Handle different event types
        if event in ("run_created", "state_change"):
            agent = payload.get("next_agent")
            run_id = payload.get("run_id")

            if agent and run_id:
                try:
                    # Resolve project path
                    run_resp = requests.get(f"{WORKFLOW_HUB_URL}/api/runs/{run_id}")
                    run_data = run_resp.json()
                    project_id = run_data.get("run", {}).get("project_id")

                    proj_resp = requests.get(f"{WORKFLOW_HUB_URL}/api/projects/{project_id}")
                    proj_data = proj_resp.json()
                    project_path = proj_data.get("project", {}).get("repo_path", ".")

                    print(f"Running {agent} agent for run {run_id}...")
                    report = run_agent_logic(agent, run_id, project_path)
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
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    print(f"Agent runner listening on port {port}")
    print(f"Provider: {AGENT_PROVIDER}")
    print(f"Workflow Hub URL: {WORKFLOW_HUB_URL}")
    server.serve_forever()

# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Agent Runner for Workflow Hub")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start webhook HTTP server")
    serve_parser.add_argument("--port", type=int, default=5001, help="Port to listen on")

    # run command - single agent
    run_parser = subparsers.add_parser("run", help="Run an agent directly")
    run_parser.add_argument("--agent", required=True, choices=["pm", "dev", "qa", "security", "docs", "director"])
    run_parser.add_argument("--run-id", type=int, required=True, help="Workflow Hub run ID")
    run_parser.add_argument("--project-path", default=".", help="Path to project repository")
    run_parser.add_argument("--submit", action="store_true", help="Submit report to Workflow Hub")

    args = parser.parse_args()

    if args.command == "serve":
        serve(args.port)
    elif args.command == "run":
        print(f"Running {args.agent} agent for run {args.run_id} using {AGENT_PROVIDER}...")
        report = run_agent_logic(args.agent, args.run_id, args.project_path)
        print(f"\nReport: {json.dumps(report, indent=2)}")

        if args.submit:
            submit_report(args.run_id, args.agent, report)

if __name__ == "__main__":
    main()
