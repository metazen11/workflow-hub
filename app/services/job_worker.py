"""Job Worker - Background processing for LLM and agent queues.

Runs in background threads to process jobs from the queue.
Each worker type processes specific job types.
"""
import os
import time
import threading
import logging
import subprocess
import sys
from datetime import datetime
from typing import List, Optional, Callable

from app.db import SessionLocal
from app.models.llm_job import LLMJob, JobType, JobStatus, JobPriority
from app.services.job_queue_service import JobQueueService

logger = logging.getLogger(__name__)


class JobWorker:
    """Background worker that processes queued jobs.

    Each worker handles specific job types and runs in its own thread.
    Only one job is processed at a time per worker.
    """

    def __init__(
        self,
        worker_id: str,
        job_types: List[str],
        poll_interval: float = 1.0
    ):
        """Initialize worker.

        Args:
            worker_id: Unique identifier for this worker
            job_types: List of JobType.value strings to process
            poll_interval: Seconds between queue polls
        """
        self.worker_id = worker_id
        self.job_types = job_types
        self.poll_interval = poll_interval
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._current_job_id: Optional[int] = None

    def start(self):
        """Start worker in background thread."""
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(
            target=self._run_loop,
            name=f"JobWorker-{self.worker_id}",
            daemon=True
        )
        self.thread.start()
        logger.info(f"[{self.worker_id}] Worker started for job types: {self.job_types}")

    def stop(self):
        """Stop worker gracefully."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5.0)
        logger.info(f"[{self.worker_id}] Worker stopped")

    @property
    def is_busy(self) -> bool:
        """Check if worker is currently processing a job."""
        return self._current_job_id is not None

    def _run_loop(self):
        """Main worker loop - fetch and process jobs."""
        queue = JobQueueService()
        last_timeout_check = time.time()
        timeout_check_interval = 30  # Check for timeouts every 30 seconds

        while self.running:
            try:
                # Periodically check for timed out jobs
                if time.time() - last_timeout_check > timeout_check_interval:
                    timed_out = queue.check_timeouts()
                    if timed_out > 0:
                        logger.info(f"[{self.worker_id}] Timed out {timed_out} stale jobs")
                    last_timeout_check = time.time()

                # Get next job
                job = queue.get_next_job(self.job_types)

                if job:
                    self._current_job_id = job.id
                    self._process_job(job, queue)
                    self._current_job_id = None
                else:
                    # No jobs, wait before polling again
                    time.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"[{self.worker_id}] Error in worker loop: {e}")
                self._current_job_id = None
                time.sleep(self.poll_interval)

    def _process_job(self, job: LLMJob, queue: JobQueueService):
        """Execute the job based on its type."""
        logger.info(f"[{self.worker_id}] Processing job {job.id} ({job.job_type})")

        # Mark as running
        started_job = queue.start_job(job.id, self.worker_id)
        if not started_job:
            logger.warning(f"[{self.worker_id}] Could not start job {job.id} - may have been picked up by another worker")
            return

        try:
            result = None

            if job.job_type == JobType.LLM_COMPLETE.value:
                result = self._run_llm_complete(job)
            elif job.job_type == JobType.LLM_CHAT.value:
                result = self._run_llm_chat(job)
            elif job.job_type == JobType.LLM_QUERY.value:
                result = self._run_llm_query(job)
            elif job.job_type == JobType.VISION_ANALYZE.value:
                result = self._run_vision(job)
            elif job.job_type == JobType.AGENT_RUN.value:
                result = self._run_agent(job)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")

            queue.complete_job(job.id, result or {})
            logger.info(f"[{self.worker_id}] Job {job.id} completed successfully")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[{self.worker_id}] Job {job.id} failed: {error_msg}")
            queue.fail_job(job.id, error_msg)

    # === Job Type Handlers ===

    def _run_llm_complete(self, job: LLMJob) -> dict:
        """Run an LLM completion request."""
        from app.services.llm_service import LLMService

        llm = LLMService()
        request = job.request_data or {}

        prompt = request.get("prompt", "")
        system_prompt = request.get("system_prompt")
        model = request.get("model")
        temperature = request.get("temperature", 0.7)
        max_tokens = request.get("max_tokens")

        result = llm.complete(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )

        return {"content": result}

    def _run_llm_chat(self, job: LLMJob) -> dict:
        """Run an LLM chat request with message history."""
        from app.services.llm_service import LLMService

        llm = LLMService()
        request = job.request_data or {}

        messages = request.get("messages", [])
        model = request.get("model")
        temperature = request.get("temperature", 0.7)
        max_tokens = request.get("max_tokens")

        result = llm.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )

        return {"content": result}

    def _run_llm_query(self, job: LLMJob) -> dict:
        """Run a contextual LLM query (with project context)."""
        from app.services.llm_service import LLMService

        llm = LLMService()
        request = job.request_data or {}

        prompt = request.get("prompt", "")
        context = request.get("context", "")

        # Combine context with prompt
        full_prompt = f"{context}\n\n---\n\n{prompt}" if context else prompt

        result = llm.complete(
            prompt=full_prompt,
            system_prompt="You are a helpful assistant. Use the provided context to answer questions accurately.",
            temperature=0.5
        )

        return {"content": result}

    def _run_vision(self, job: LLMJob) -> dict:
        """Run vision analysis on an image."""
        from app.services.llm_service import get_image_description

        request = job.request_data or {}
        image_path = request.get("image_path", "")

        if not image_path or not os.path.exists(image_path):
            raise ValueError(f"Image not found: {image_path}")

        description = get_image_description(
            image_path,
            force_refresh=True,
            include_errors=True,
            include_text=True
        )

        return {"description": description or ""}

    def _run_agent(self, job: LLMJob) -> dict:
        """Run a Goose agent via subprocess."""
        request = job.request_data or {}

        task_id = request.get("task_id")
        agent_type = request.get("agent_type", "dev")
        project_path = request.get("project_path", "")
        run_id = request.get("run_id")

        if not project_path:
            raise ValueError("project_path is required for agent runs")

        # Build command
        runner_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "scripts",
            "agent_runner.py"
        )

        cmd = [
            sys.executable,
            runner_path,
            "task" if task_id else "run",
            "--agent", agent_type,
            "--project-path", project_path
        ]

        if task_id:
            cmd.extend(["--task-id", str(task_id)])
        if run_id:
            cmd.extend(["--run-id", str(run_id)])

        # Run with timeout
        timeout = job.timeout_seconds or 600

        logger.info(f"[{self.worker_id}] Running agent command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=project_path
            )

            return {
                "status": "pass" if result.returncode == 0 else "fail",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Agent timed out after {timeout}s")


# =============================================================================
# Worker Manager - Singleton for managing all workers
# =============================================================================

class WorkerManager:
    """Manages all job workers."""

    _instance: Optional['WorkerManager'] = None

    def __init__(self):
        self.workers: List[JobWorker] = []
        self._started = False

    @classmethod
    def get_instance(cls) -> 'WorkerManager':
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def start_all(self):
        """Start all workers."""
        if self._started:
            return

        # LLM Worker - handles completions and chat
        llm_worker = JobWorker(
            worker_id="llm",
            job_types=[
                JobType.LLM_COMPLETE.value,
                JobType.LLM_CHAT.value,
                JobType.LLM_QUERY.value
            ],
            poll_interval=0.5
        )
        self.workers.append(llm_worker)

        # Agent Worker - handles Goose agent runs
        agent_worker = JobWorker(
            worker_id="agent",
            job_types=[JobType.AGENT_RUN.value],
            poll_interval=1.0
        )
        self.workers.append(agent_worker)

        # Vision Worker - handles image analysis
        vision_worker = JobWorker(
            worker_id="vision",
            job_types=[JobType.VISION_ANALYZE.value],
            poll_interval=2.0
        )
        self.workers.append(vision_worker)

        # Start all workers
        for worker in self.workers:
            worker.start()

        self._started = True
        logger.info(f"Started {len(self.workers)} job workers")

    def stop_all(self):
        """Stop all workers."""
        for worker in self.workers:
            worker.stop()
        self.workers.clear()
        self._started = False
        logger.info("All job workers stopped")

    def get_status(self) -> dict:
        """Get status of all workers."""
        return {
            "started": self._started,
            "workers": [
                {
                    "id": w.worker_id,
                    "job_types": w.job_types,
                    "is_busy": w.is_busy,
                    "current_job": w._current_job_id
                }
                for w in self.workers
            ]
        }


def get_worker_manager() -> WorkerManager:
    """Get the worker manager singleton."""
    return WorkerManager.get_instance()


def start_workers():
    """Convenience function to start all workers."""
    manager = get_worker_manager()
    manager.start_all()


def stop_workers():
    """Convenience function to stop all workers."""
    manager = get_worker_manager()
    manager.stop_all()
