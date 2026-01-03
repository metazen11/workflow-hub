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

# Import vision preprocessing for image path handling
try:
    from scripts.mcp_vision_server import preprocess_prompt as vision_preprocess
    VISION_ENABLED = True
except ImportError:
    VISION_ENABLED = False
    def vision_preprocess(prompt, context="", compact=True):
        return prompt  # No-op if vision not available


WORKFLOW_HUB_URL = os.getenv("WORKFLOW_HUB_URL", "http://localhost:8000")
AGENT_PROVIDER = os.getenv("AGENT_PROVIDER", "goose").lower()
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "600"))
VISION_PREPROCESS = os.getenv("VISION_PREPROCESS", "true").lower() == "true"


# =============================================================================
# Abstract Base Class for Agent Providers
# =============================================================================

class AgentProvider(abc.ABC):
    """Abstract base class for agent providers."""

    @abc.abstractmethod
    def run_agent(self, role: str, run_id: int, project_path: str, prompt: str, task_id: int = None) -> Dict[str, Any]:
        """
        Run the agent with the given role and prompt.

        Args:
            role: The agent role (pm, dev, qa, security, etc.)
            run_id: The ID of the current run
            project_path: Absolute path to the project repository
            prompt: The full prompt text to send to the agent
            task_id: Optional task ID for session persistence

        Returns:
            Dict containing 'status' (pass/fail), 'summary', and 'details'
        """
        pass

    def get_agent_prompt(self, role: str, run_id: int, project_path: str, task_id: int = None) -> str:
        """
        Load agent prompt from database and format with context.
        Includes full project details and work_cycle context in every prompt.
        """
        project_context = self._get_project_context(role, run_id, project_path)

        try:
            from app.db import get_db
            from app.models.role_config import RoleConfig
            from app.models.task import Task

            db = next(get_db())

            # Get task_id if not provided
            # NOTE: Task.run_id removed in refactor - get task from run's project
            if not task_id:
                from app.models.run import Run
                run = db.query(Run).filter(Run.id == run_id).first()
                if run:
                    # Get most recent in-progress task for this project
                    from app.models.task import TaskStatus
                    task = db.query(Task).filter(
                        Task.project_id == run.project_id,
                        Task.status == TaskStatus.IN_PROGRESS
                    ).order_by(Task.updated_at.desc()).first()
                    task_id = task.id if task else None

            config = db.query(RoleConfig).filter(
                RoleConfig.role == role,
                RoleConfig.active == True
            ).first()

            if config and config.prompt:
                # Format the prompt with context variables
                # Note: _get_format_vars includes task_id, so don't pass it separately
                format_vars = self._get_format_vars(project_path, run_id, task_id)
                prompt = config.prompt.format(
                    project_path=project_path,
                    run_id=run_id,
                    project_context=project_context,
                    **format_vars
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
        """Fetch full project details and work_cycle context from DB.

        Uses the work_cycle service to build comprehensive context including:
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
            from app.models.task import Task, TaskStatus
            from app.services.work_cycle_service import get_work_cycle_for_prompt

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

            # Get primary task for this run (for task-specific work_cycle file)
            # NOTE: Task.run_id removed in refactor - get in-progress task from project
            task = db.query(Task).filter(
                Task.project_id == run.project_id,
                Task.status == TaskStatus.IN_PROGRESS
            ).order_by(Task.updated_at.desc()).first()
            task_id = task.task_id if task else None

            # Get work_cycle context (writes WORK_CYCLE_{run_id}_{task_id}.md)
            work_cycle_context = get_work_cycle_for_prompt(
                db=db,
                run_id=run_id,
                role=role,
                project_path=project.repo_path or project_path,
                task_id=task_id,
                write_file=True
            )

            # Build tech stack string from available fields
            tech_stack_parts = []
            if project.languages:
                tech_stack_parts.append(f"Languages: {', '.join(project.languages)}")
            if project.frameworks:
                tech_stack_parts.append(f"Frameworks: {', '.join(project.frameworks)}")
            if project.databases:
                tech_stack_parts.append(f"Databases: {', '.join(project.databases)}")
            tech_stack = '\n'.join(tech_stack_parts) if tech_stack_parts else 'Not specified'

            # Build comprehensive context combining project info + work_cycle
            context = f"""# Project Context

## Project: {project.name}
- **ID**: {project.id}
- **Repository**: {project.repo_path or project_path}
- **Git URL**: {project.repository_url or 'N/A'}
- **Branch**: {project.primary_branch or 'main'}

## Technology Stack
{tech_stack}

## Key Files
{', '.join(project.key_files) if project.key_files else 'Not specified'}

## Build/Test/Run Commands
- **Build**: {project.build_command or 'Not specified'}
- **Test**: {project.test_command or 'Not specified'}
- **Run**: {project.run_command or 'Not specified'}

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

{work_cycle_context}"""
            db.close()
            return context

        except Exception as e:
            print(f"Warning: Could not fetch project context: {e}")
            return f"# Project Context\nProject Path: {project_path}\nRun ID: {run_id}"

    def _get_format_vars(self, project_path: str, run_id: int, task_id: int = None) -> dict:
        """Get additional format variables for prompt templates."""
        return {
            "project_name": os.path.basename(project_path),
            "workspace": project_path,
            "task_id": task_id or "N/A",
        }

# =============================================================================
# Goose Provider Implementation
# =============================================================================

class GooseProvider(AgentProvider):
    """Provider implementation for Goose AI agent with session persistence.

    Sessions are stored in {project_path}/.goose/sessions/task_{id}/
    This allows agents to maintain conversation context across multiple calls.
    """

    def __init__(self):
        self.executable = self._find_goose_executable()

    def _get_session_name(self, task_id: int = None, run_id: int = None) -> str:
        """Generate session name for a task or run."""
        if task_id:
            return f"task_{task_id}"
        elif run_id:
            return f"run_{run_id}"
        return "default"

    def _session_exists(self, project_path: str, session_name: str) -> bool:
        """Check if a Goose session exists."""
        session_dir = os.path.join(project_path, ".goose", "sessions", session_name)
        return os.path.exists(session_dir)

    def clear_session(self, project_path: str, task_id: int = None, run_id: int = None) -> bool:
        """Clear a Goose session to start fresh.

        Args:
            project_path: Path to the project
            task_id: Task ID whose session to clear
            run_id: Run ID whose session to clear (if no task_id)

        Returns:
            True if session was cleared, False if it didn't exist
        """
        import shutil
        session_name = self._get_session_name(task_id, run_id)
        session_dir = os.path.join(project_path, ".goose", "sessions", session_name)

        if os.path.exists(session_dir):
            shutil.rmtree(session_dir)
            print(f"  Cleared Goose session: {session_name}")
            return True
        return False

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

    def run_agent(self, role: str, run_id: int, project_path: str, prompt: str, task_id: int = None) -> Dict[str, Any]:
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

            # Determine session name for context persistence
            # Each task gets its own session to maintain conversation history
            session_name = f"task_{task_id}" if task_id else f"run_{run_id}"
            session_dir = os.path.join(project_path, ".goose", "sessions", session_name)

            # Build command using goose run (supports both new and resumed sessions)
            # goose run -n <name> -t <prompt> for new session
            # goose run -n <name> --resume -t <prompt> for resuming
            if os.path.exists(session_dir):
                # Resume existing session - Goose will have context from previous calls
                print(f"  Resuming Goose session '{session_name}' ({role}) with {LLM_TIMEOUT}s timeout...")
                cmd = [self.executable, "run", "-n", session_name, "--resume", "-t", prompt]
            else:
                # Start new session for this task
                print(f"  Starting new Goose session '{session_name}' ({role}) with {LLM_TIMEOUT}s timeout...")
                cmd = [self.executable, "run", "-n", session_name, "-t", prompt]

            result = subprocess.run(
                cmd,
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

            # Include session info for debugging/tracking
            report["session"] = {
                "name": session_name,
                "resumed": os.path.exists(session_dir),
                "path": session_dir
            }

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
    def run_agent(self, role: str, run_id: int, project_path: str, prompt: str, task_id: int = None) -> Dict[str, Any]:
        return {
            "status": "pass",
            "summary": f"Mock execution for {role}",
            "details": {"mock": True, "run_id": run_id, "task_id": task_id}
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
# Automatic Proof Capture
# =============================================================================

def upload_proof(run_id: int, stage: str, proof_type: str, content: bytes,
                 filename: str, description: str) -> bool:
    """Upload a proof file to Workflow Hub."""
    import io
    try:
        # Use requests with files parameter for multipart upload
        files = {
            'file': (filename, io.BytesIO(content), 'application/octet-stream')
        }
        data = {
            'stage': stage,
            'proof_type': proof_type,
            'description': description
        }
        response = requests.post(
            f"{WORKFLOW_HUB_URL}/api/runs/{run_id}/proofs/upload",
            files=files,
            data=data,
            timeout=30
        )
        if response.status_code in (200, 201):
            print(f"  Uploaded proof: {filename}")
            return True
        else:
            print(f"  Failed to upload proof {filename} (status {response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"  Error uploading proof: {e}")
        return False


def get_existing_proof_hashes(run_id: int, stage: str) -> set:
    """Get (proof_type, size) tuples of existing proofs to avoid duplicates."""
    try:
        response = requests.get(
            f"{WORKFLOW_HUB_URL}/api/runs/{run_id}/proofs",
            timeout=10
        )
        if response.status_code == 200:
            proofs = response.json().get("proofs", [])
            # Use (proof_type, size) as dedup key - same type & size = duplicate
            return {(p.get("proof_type", ""), p.get("size", 0))
                    for p in proofs if p.get("stage") == stage}
    except Exception as e:
        print(f"  Warning: Could not fetch existing proofs: {e}")
    return set()


def capture_automatic_proofs(agent_type: str, run_id: int, project_path: str,
                             report: Dict[str, Any]) -> int:
    """Automatically capture and upload proofs after agent execution.

    Returns the number of proofs successfully uploaded.
    Deduplicates by checking existing proofs before uploading.
    """
    print(f"Capturing automatic proofs for {agent_type}...")
    proofs_uploaded = 0
    stage = agent_type  # dev, qa, sec, docs, etc.

    # Get existing proofs to avoid duplicates
    existing = get_existing_proof_hashes(run_id, stage)
    if existing:
        print(f"  Found {len(existing)} existing proof(s), will skip duplicates")

    def should_upload(proof_type: str, content: bytes, filename: str) -> bool:
        """Check if this file should be uploaded (not a duplicate)."""
        key = (proof_type, len(content))
        if key in existing:
            print(f"  Skipping duplicate: {filename} ({proof_type}, {len(content)} bytes)")
            return False
        return True

    # 1. Always upload the raw output as a log (but skip if same size exists)
    raw_output = report.get("raw_output", "")
    if raw_output:
        content = raw_output.encode("utf-8")
        filename = f"{agent_type}_output.log"
        if should_upload("log", content, filename):
            success = upload_proof(
                run_id=run_id,
                stage=stage,
                proof_type="log",
                content=content,
                filename=filename,
                description=f"{agent_type.upper()} agent execution log"
            )
            if success:
                proofs_uploaded += 1

    # 2. Role-specific proof capture
    if agent_type == "docs":
        # Upload documentation files that were created/modified
        doc_patterns = [
            ("README.md", "Main README documentation"),
            ("docs/API.md", "API documentation"),
            ("docs/SETUP.md", "Setup documentation"),
            ("CHANGELOG.md", "Changelog"),
        ]
        for doc_path, description in doc_patterns:
            full_path = os.path.join(project_path, doc_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "rb") as f:
                        content = f.read()
                    filename = os.path.basename(doc_path)
                    if should_upload("report", content, filename):
                        success = upload_proof(
                            run_id=run_id,
                            stage=stage,
                            proof_type="report",
                            content=content,
                            filename=filename,
                            description=description
                        )
                        if success:
                            proofs_uploaded += 1
                except Exception as e:
                    print(f"  Could not upload {doc_path}: {e}")

    elif agent_type == "qa":
        # Upload test result files
        test_patterns = [
            ("pytest_results.xml", "Pytest XML results"),
            ("test_output.log", "Test output log"),
            ("bugs.json", "Bugs found by QA"),
        ]
        for test_path, description in test_patterns:
            full_path = os.path.join(project_path, test_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "rb") as f:
                        content = f.read()
                    if should_upload("log", content, test_path):
                        success = upload_proof(
                            run_id=run_id,
                            stage=stage,
                            proof_type="log",
                            content=content,
                            filename=test_path,
                            description=description
                        )
                        if success:
                            proofs_uploaded += 1
                except Exception as e:
                    print(f"  Could not upload {test_path}: {e}")

    elif agent_type == "security":
        # Upload security scan results
        sec_patterns = [
            ("security_report.json", "Security scan report"),
            ("vulnerabilities.json", "Vulnerabilities found"),
        ]
        for sec_path, description in sec_patterns:
            full_path = os.path.join(project_path, sec_path)
            if os.path.exists(full_path):
                try:
                    with open(full_path, "rb") as f:
                        content = f.read()
                    if should_upload("report", content, sec_path):
                        success = upload_proof(
                            run_id=run_id,
                            stage=stage,
                            proof_type="report",
                            content=content,
                            filename=sec_path,
                            description=description
                        )
                        if success:
                            proofs_uploaded += 1
                except Exception as e:
                    print(f"  Could not upload {sec_path}: {e}")

    # 3. Look for any screenshots the agent may have taken
    screenshots_dir = os.path.join(project_path, "screenshots")
    if os.path.exists(screenshots_dir):
        for filename in os.listdir(screenshots_dir):
            if filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                full_path = os.path.join(screenshots_dir, filename)
                try:
                    with open(full_path, "rb") as f:
                        content = f.read()
                    if should_upload("screenshot", content, filename):
                        success = upload_proof(
                            run_id=run_id,
                            stage=stage,
                            proof_type="screenshot",
                            content=content,
                            filename=filename,
                            description=f"Screenshot: {filename}"
                        )
                        if success:
                            proofs_uploaded += 1
                except Exception as e:
                    print(f"  Could not upload screenshot {filename}: {e}")

    print(f"Uploaded {proofs_uploaded} proof(s)")
    return proofs_uploaded


# =============================================================================
# Main Runner Logic
# =============================================================================

def run_agent_logic(agent_type: str, run_id: int, project_path: str) -> Dict[str, Any]:
    provider = get_provider()
    prompt = provider.get_agent_prompt(agent_type, run_id, project_path)

    # Preprocess prompt for vision (analyze any image paths)
    if VISION_PREPROCESS and VISION_ENABLED:
        print(f"Preprocessing prompt for vision analysis...")
        prompt = vision_preprocess(prompt, context=f"Task for {agent_type} agent", compact=True)

    report = provider.run_agent(agent_type, run_id, project_path, prompt)

    # Automatically capture and upload proofs after agent completes
    proofs_count = capture_automatic_proofs(agent_type, run_id, project_path, report)
    report["proofs_uploaded"] = proofs_count

    return report


# =============================================================================
# Task-Centric WorkCycle Functions
# =============================================================================

def get_or_create_task_work_cycle(task_id: int, to_role: str, stage: str, run_id: int = None) -> Optional[Dict]:
    """Get current work_cycle or create one if none exists.

    Returns the work_cycle data including context_markdown for the agent prompt.
    """
    try:
        # First, try to get existing work_cycle
        response = requests.get(
            f"{WORKFLOW_HUB_URL}/api/tasks/{task_id}/work_cycle",
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("work_cycle"):
                return data["work_cycle"]

        # No pending work_cycle - create one
        create_response = requests.post(
            f"{WORKFLOW_HUB_URL}/api/tasks/{task_id}/work_cycle/create",
            json={
                "to_role": to_role,
                "stage": stage,
                "run_id": run_id,
                "created_by": f"{AGENT_PROVIDER}-agent"
            },
            timeout=30
        )

        if create_response.status_code == 201:
            return create_response.json().get("work_cycle")
        else:
            print(f"Failed to create work_cycle: {create_response.text}")
            return None

    except Exception as e:
        print(f"Error getting/creating work_cycle: {e}")
        return None


def accept_task_work_cycle(task_id: int, work_cycle_id: int = None) -> bool:
    """Accept a task work_cycle (mark as in_progress)."""
    try:
        response = requests.post(
            f"{WORKFLOW_HUB_URL}/api/tasks/{task_id}/work_cycle/accept",
            json={"work_cycle_id": work_cycle_id} if work_cycle_id else {},
            timeout=30
        )

        if response.status_code == 200:
            print(f"WorkCycle accepted for task {task_id}")
            return True
        else:
            print(f"Failed to accept work_cycle: {response.text}")
            return False

    except Exception as e:
        print(f"Error accepting work_cycle: {e}")
        return False


def complete_task_work_cycle(task_id: int, report: Dict, work_cycle_id: int = None) -> bool:
    """Complete a task work_cycle with the agent's report."""
    try:
        response = requests.post(
            f"{WORKFLOW_HUB_URL}/api/tasks/{task_id}/work_cycle/complete",
            json={
                "work_cycle_id": work_cycle_id,
                "report_status": report.get("status", "fail"),
                "report_summary": report.get("summary", ""),
                "report_details": report.get("details", {})
            },
            timeout=30
        )

        if response.status_code == 200:
            print(f"WorkCycle completed for task {task_id}")
            return True
        else:
            print(f"Failed to complete work_cycle: {response.text}")
            return False

    except Exception as e:
        print(f"Error completing work_cycle: {e}")
        return False


def run_agent_for_task(task_id: int, agent_type: str, stage: str = None,
                       run_id: int = None, project_path: str = None) -> Dict[str, Any]:
    """Run an agent for a specific task using the work_cycle API.

    This is the task-centric execution flow:
    1. Get or create work_cycle for the task
    2. Accept the work_cycle (mark in_progress)
    3. Run the agent with work_cycle context
    4. Complete the work_cycle with the report

    Args:
        task_id: The task to work on
        agent_type: Agent role (dev, qa, sec, docs)
        stage: Pipeline stage (defaults to agent_type)
        run_id: Optional run ID for context
        project_path: Path to project (auto-detected if not provided)

    Returns:
        Agent report dict
    """
    stage = stage or agent_type

    # Get task details if project_path not provided
    if not project_path:
        try:
            task_resp = requests.get(f"{WORKFLOW_HUB_URL}/api/tasks/{task_id}/details", timeout=30)
            if task_resp.status_code == 200:
                task_data = task_resp.json().get("task", {})
                project_path = task_data.get("project", {}).get("repo_path", ".")
            else:
                project_path = "."
        except Exception:
            project_path = "."

    # Step 1: Get or create work_cycle
    print(f"Getting work_cycle for task {task_id}...")
    work_cycle = get_or_create_task_work_cycle(task_id, agent_type, stage, run_id)

    if not work_cycle:
        return {
            "status": "fail",
            "summary": "Could not create/get work_cycle for task",
            "details": {"task_id": task_id}
        }

    work_cycle_id = work_cycle.get("id")

    # Step 2: Accept the work_cycle
    if work_cycle.get("status") == "pending":
        if not accept_task_work_cycle(task_id, work_cycle_id):
            return {
                "status": "fail",
                "summary": "Could not accept work_cycle",
                "details": {"work_cycle_id": work_cycle_id}
            }

    # Step 3: Build prompt using work_cycle context
    provider = get_provider()

    # Use work_cycle context_markdown as the primary context
    context_markdown = work_cycle.get("context_markdown", "")

    # Get role-specific prompt from DB
    try:
        from app.db import get_db
        from app.models.role_config import RoleConfig

        db = next(get_db())
        config = db.query(RoleConfig).filter(
            RoleConfig.role == agent_type,
            RoleConfig.active == True
        ).first()

        role_prompt = config.prompt if config else ""
        db.close()
    except Exception as e:
        print(f"Warning: Could not load prompt from DB: {e}")
        role_prompt = ""

    # Combine context and role prompt
    full_prompt = f"""# Task WorkCycle Context

{context_markdown}

---

## Your Role: {agent_type.upper()}

{role_prompt if role_prompt else f'''
Execute your role's responsibilities for this task.
When complete, output a JSON status report with:
- "status": "pass" or "fail"
- "summary": Brief description of what you did
- "details": Any relevant details
'''}
"""

    # Step 4: Preprocess prompt for vision (analyze any image paths)
    if VISION_PREPROCESS and VISION_ENABLED:
        print(f"Preprocessing prompt for vision analysis...")
        full_prompt = vision_preprocess(full_prompt, context=f"Task for {agent_type} agent", compact=True)

    # Step 5: Run the agent (with task_id for session persistence)
    print(f"Running {agent_type} agent for task {task_id}...")
    report = provider.run_agent(agent_type, run_id or 0, project_path, full_prompt, task_id=task_id)

    # Capture proofs
    proofs_count = capture_automatic_proofs(agent_type, run_id or task_id, project_path, report)
    report["proofs_uploaded"] = proofs_count

    # Step 5: Complete the work_cycle
    complete_task_work_cycle(task_id, report, work_cycle_id)

    return report


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

    # run command - single agent (legacy run-centric mode)
    run_parser = subparsers.add_parser("run", help="Run an agent for a run (legacy mode)")
    run_parser.add_argument("--agent", required=True, choices=["pm", "dev", "qa", "security", "docs", "director"])
    run_parser.add_argument("--run-id", type=int, required=True, help="Workflow Hub run ID")
    run_parser.add_argument("--project-path", default=".", help="Path to project repository")
    run_parser.add_argument("--submit", action="store_true", help="Submit report to Workflow Hub")

    # task command - task-centric mode with work_cycle API
    task_parser = subparsers.add_parser("task", help="Run an agent for a task (uses work_cycle API)")
    task_parser.add_argument("--agent", required=True, choices=["pm", "dev", "qa", "security", "sec", "docs", "director"])
    task_parser.add_argument("--task-id", type=int, required=True, help="Task ID to work on")
    task_parser.add_argument("--run-id", type=int, help="Optional run ID for context")
    task_parser.add_argument("--stage", help="Pipeline stage (defaults to agent type)")
    task_parser.add_argument("--project-path", help="Path to project (auto-detected if not provided)")

    args = parser.parse_args()

    if args.command == "serve":
        serve(args.port)
    elif args.command == "run":
        # Legacy run-centric mode
        print(f"Running {args.agent} agent for run {args.run_id} using {AGENT_PROVIDER}...")
        report = run_agent_logic(args.agent, args.run_id, args.project_path)
        print(f"\nReport: {json.dumps(report, indent=2)}")

        if args.submit:
            submit_report(args.run_id, args.agent, report)

    elif args.command == "task":
        # Task-centric mode with work_cycle API
        agent_type = args.agent
        # Normalize 'sec' to 'security' for consistency
        if agent_type == "sec":
            agent_type = "security"

        print(f"Running {agent_type} agent for task {args.task_id} using {AGENT_PROVIDER}...")
        print("Using work_cycle API for context and reporting...")

        report = run_agent_for_task(
            task_id=args.task_id,
            agent_type=agent_type,
            stage=args.stage,
            run_id=args.run_id,
            project_path=args.project_path
        )

        print(f"\nReport: {json.dumps(report, indent=2)}")


if __name__ == "__main__":
    main()
