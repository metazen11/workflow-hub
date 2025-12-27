"""
Agent Service - Triggers agent runners for pipeline stages.

This service provides Python methods to trigger agents programmatically,
either running them in-process or spawning subprocesses.
"""
import json
import os
import subprocess
import threading
from typing import Optional
import requests

from app.models.run import Run, RunState
from app.models.project import Project
from app.db import get_db


WORKFLOW_HUB_URL = os.getenv("WORKFLOW_HUB_URL", "http://localhost:8000")

# Map run states to agent types
STATE_TO_AGENT = {
    RunState.PM: "pm",
    RunState.DEV: "dev",
    RunState.QA: "qa",
    RunState.SEC: "security",
    RunState.DOCS: "docs",
    RunState.TESTING: "testing",
}


class AgentService:
    """Service for triggering and managing agent execution."""

    def __init__(self, db=None):
        self.db = db

    def get_agent_for_state(self, state: RunState) -> Optional[str]:
        """Get the agent type for a given run state."""
        return STATE_TO_AGENT.get(state)

    def trigger_agent(self, run_id: int, agent_type: Optional[str] = None,
                      async_mode: bool = True, custom_prompt: str = None) -> dict:
        """
        Trigger an agent for a run.

        Args:
            run_id: The run ID to process
            agent_type: Override agent type (defaults to current state's agent)
            async_mode: If True, run in background thread
            custom_prompt: Optional additional instructions for the agent

        Returns:
            dict with status and message
        """
        db = self.db or next(get_db())
        try:
            run = db.query(Run).filter(Run.id == run_id).first()
            if not run:
                return {"status": "error", "message": f"Run {run_id} not found"}

            project = db.query(Project).filter(Project.id == run.project_id).first()
            if not project:
                return {"status": "error", "message": f"Project not found for run {run_id}"}

            project_path = project.repo_path
            if not project_path:
                return {"status": "error", "message": "Project has no repo_path configured"}

            # Determine agent type
            if not agent_type:
                agent_type = self.get_agent_for_state(run.state)
                if not agent_type:
                    return {"status": "error", "message": f"No agent for state {run.state.value}"}

            if async_mode:
                # Run in background thread
                thread = threading.Thread(
                    target=self._run_agent_subprocess,
                    args=(run_id, agent_type, project_path, custom_prompt),
                    daemon=True
                )
                thread.start()
                return {
                    "status": "started",
                    "message": f"Agent {agent_type} started for run {run_id}",
                    "run_id": run_id,
                    "agent": agent_type
                }
            else:
                # Run synchronously
                result = self._run_agent_subprocess(run_id, agent_type, project_path, custom_prompt)
                return result

        finally:
            if not self.db:
                db.close()

    def trigger_pipeline(self, run_id: int, max_iterations: int = 10) -> dict:
        """
        Trigger the full pipeline for a run (PM → DEV → QA → SEC → ...).

        Runs in background thread.
        """
        db = self.db or next(get_db())
        try:
            run = db.query(Run).filter(Run.id == run_id).first()
            if not run:
                return {"status": "error", "message": f"Run {run_id} not found"}

            project = db.query(Project).filter(Project.id == run.project_id).first()
            if not project or not project.repo_path:
                return {"status": "error", "message": "Project has no repo_path"}

            # Start pipeline in background
            thread = threading.Thread(
                target=self._run_pipeline_subprocess,
                args=(run_id, project.repo_path, max_iterations),
                daemon=True
            )
            thread.start()

            return {
                "status": "started",
                "message": f"Pipeline started for run {run_id}",
                "run_id": run_id,
                "max_iterations": max_iterations
            }

        finally:
            if not self.db:
                db.close()

    def _run_agent_subprocess(self, run_id: int, agent_type: str,
                               project_path: str, custom_prompt: str = None) -> dict:
        """Run the agent_runner.py script as a subprocess."""
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "scripts", "agent_runner.py"
        )

        cmd = [
            "python", script_path, "run",
            "--agent", agent_type,
            "--run-id", str(run_id),
            "--project-path", project_path,
            "--submit"
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                env={**os.environ, "WORKFLOW_HUB_URL": WORKFLOW_HUB_URL}
            )

            return {
                "status": "pass" if result.returncode == 0 else "fail",
                "message": f"Agent {agent_type} completed",
                "stdout": result.stdout[-2000:] if result.stdout else "",
                "stderr": result.stderr[-500:] if result.stderr else "",
                "returncode": result.returncode
            }

        except subprocess.TimeoutExpired:
            return {"status": "fail", "message": "Agent timed out after 10 minutes"}
        except Exception as e:
            return {"status": "fail", "message": str(e)}

    def _run_pipeline_subprocess(self, run_id: int, project_path: str,
                                  max_iterations: int) -> dict:
        """Run the full pipeline as a subprocess."""
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "scripts", "agent_runner.py"
        )

        cmd = [
            "python", script_path, "pipeline",
            "--run-id", str(run_id),
            "--project-path", project_path,
            "--max-iterations", str(max_iterations)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout for full pipeline
                env={**os.environ, "WORKFLOW_HUB_URL": WORKFLOW_HUB_URL}
            )

            return {
                "status": "pass" if result.returncode == 0 else "fail",
                "message": "Pipeline completed",
                "stdout": result.stdout[-5000:] if result.stdout else "",
                "returncode": result.returncode
            }

        except subprocess.TimeoutExpired:
            return {"status": "fail", "message": "Pipeline timed out"}
        except Exception as e:
            return {"status": "fail", "message": str(e)}


# Convenience functions for direct use
def trigger_agent(run_id: int, agent_type: str = None, async_mode: bool = True) -> dict:
    """Trigger an agent for a run."""
    service = AgentService()
    return service.trigger_agent(run_id, agent_type, async_mode)


def trigger_pipeline(run_id: int, max_iterations: int = 10) -> dict:
    """Trigger the full pipeline for a run."""
    service = AgentService()
    return service.trigger_pipeline(run_id, max_iterations)
