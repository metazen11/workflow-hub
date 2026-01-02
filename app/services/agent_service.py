"""
Agent Service - Triggers agent runners for pipeline stages.

This service provides Python methods to trigger agents programmatically,
using the job queue for serialized execution.
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

# Check if queue is enabled
USE_JOB_QUEUE = os.getenv("JOB_QUEUE_ENABLED", "true").lower() == "true"

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

    def trigger_agent(self, run_id: int = None, task_id: int = None,
                      agent_type: Optional[str] = None, async_mode: bool = True,
                      custom_prompt: str = None) -> dict:
        """
        Trigger an agent for a run or task.

        Args:
            run_id: The run ID to process (legacy flow)
            task_id: The task ID to process (new work_cycle flow)
            agent_type: Override agent type (defaults to current state's agent)
            async_mode: If True, run in background thread
            custom_prompt: Optional additional instructions for the agent

        Returns:
            dict with status and message
        """
        # Task-level execution (new work_cycle flow)
        if task_id:
            return self._trigger_agent_for_task(task_id, agent_type, async_mode)

        # Run-level execution (legacy flow)
        if not run_id:
            return {"status": "error", "message": "Either run_id or task_id is required"}

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

            # Use job queue if enabled
            if USE_JOB_QUEUE and async_mode:
                return self._enqueue_agent_job(
                    task_id=None,  # Legacy run-based flow
                    agent_type=agent_type,
                    project_path=project_path,
                    project_id=project.id,
                    run_id=run_id
                )

            # Fallback to direct subprocess (legacy or sync mode)
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

    def _trigger_agent_for_task(self, task_id: int, agent_type: str,
                                 async_mode: bool = True) -> dict:
        """
        Trigger an agent for a specific task (work_cycle flow).

        Args:
            task_id: The task ID to process
            agent_type: The agent type to run (dev, qa, sec, docs, etc.)
            async_mode: If True, enqueue for background processing

        Returns:
            dict with status and message
        """
        from app.models.task import Task

        db = self.db or next(get_db())
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return {"status": "error", "message": f"Task {task_id} not found"}

            project = db.query(Project).filter(Project.id == task.project_id).first()
            if not project:
                return {"status": "error", "message": f"Project not found for task {task_id}"}

            project_path = project.repo_path
            if not project_path:
                return {"status": "error", "message": "Project has no repo_path configured"}

            if not agent_type:
                return {"status": "error", "message": "agent_type is required for task execution"}

            # Use job queue if enabled
            if USE_JOB_QUEUE and async_mode:
                return self._enqueue_agent_job(
                    task_id=task_id,
                    agent_type=agent_type,
                    project_path=project_path,
                    project_id=project.id
                )

            # Fallback to direct subprocess (legacy or sync mode)
            if async_mode:
                # Run in background thread
                thread = threading.Thread(
                    target=self._run_task_agent_subprocess,
                    args=(task_id, agent_type, project_path),
                    daemon=True
                )
                thread.start()
                return {
                    "status": "started",
                    "message": f"Agent {agent_type} started for task {task_id}",
                    "task_id": task_id,
                    "agent": agent_type
                }
            else:
                # Run synchronously
                result = self._run_task_agent_subprocess(task_id, agent_type, project_path)
                return result

        finally:
            if not self.db:
                db.close()

    def _enqueue_agent_job(self, task_id: int, agent_type: str,
                           project_path: str, project_id: int = None,
                           run_id: int = None) -> dict:
        """
        Enqueue an agent job for background processing.

        Uses the job queue to serialize agent execution.
        """
        from app.services.job_queue_service import get_queue_service
        from app.models.llm_job import JobPriority

        queue = get_queue_service()

        try:
            job = queue.enqueue_agent_run(
                task_id=task_id,
                agent_type=agent_type,
                project_path=project_path,
                project_id=project_id,
                run_id=run_id,
                priority=JobPriority.HIGH,
                timeout=600  # 10 minutes
            )

            position = queue.get_job_position(job.id)

            return {
                "status": "queued",
                "message": f"Agent {agent_type} queued for task {task_id} (position {position})",
                "task_id": task_id,
                "agent": agent_type,
                "job_id": job.id,
                "position": position
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to enqueue agent: {str(e)}"
            }

    def _run_task_agent_subprocess(self, task_id: int, agent_type: str,
                                    project_path: str) -> dict:
        """Run the agent_runner.py script for a task as a subprocess."""
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "scripts", "agent_runner.py"
        )

        cmd = [
            "python", script_path, "task",
            "--task-id", str(task_id),
            "--agent", agent_type,
            "--project-path", project_path
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
                "message": f"Agent {agent_type} completed for task {task_id}",
                "stdout": result.stdout[-2000:] if result.stdout else "",
                "stderr": result.stderr[-500:] if result.stderr else "",
                "returncode": result.returncode
            }

        except subprocess.TimeoutExpired:
            return {"status": "fail", "message": "Agent timed out after 10 minutes"}
        except Exception as e:
            return {"status": "fail", "message": str(e)}

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
