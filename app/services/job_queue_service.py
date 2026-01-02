"""Job Queue Service.

Manages the priority queue for LLM requests and agent runs.
Provides enqueueing, dequeuing, and status tracking.
"""
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.llm_job import LLMJob, JobType, JobStatus, JobPriority


class JobQueueService:
    """Manages job queue for LLM and agent requests."""

    def __init__(self, db_session: Session = None):
        self.db = db_session
        self._owns_session = db_session is None

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db is None:
            self.db = SessionLocal()
            self._owns_session = True
        return self.db

    def _close_db(self):
        """Close database session if we own it."""
        if self._owns_session and self.db:
            self.db.close()
            self.db = None

    # === Enqueueing ===

    def enqueue_llm_request(
        self,
        job_type: str,
        request_data: Dict[str, Any],
        priority: int = JobPriority.NORMAL,
        project_id: int = None,
        task_id: int = None,
        session_id: int = None,
        timeout: int = 300
    ) -> LLMJob:
        """Add LLM request to queue.

        Args:
            job_type: Type of job (JobType.value)
            request_data: Serialized request parameters
            priority: Priority level (1=highest, 4=lowest)
            project_id: Optional project context
            task_id: Optional task context
            session_id: Optional LLM session for conversation continuity
            timeout: Timeout in seconds

        Returns:
            Created LLMJob record
        """
        db = self._get_db()
        try:
            # Calculate queue position
            pending_count = db.query(LLMJob).filter(
                LLMJob.status == JobStatus.PENDING.value
            ).count()

            job = LLMJob(
                job_type=job_type,
                status=JobStatus.PENDING.value,
                priority=priority,
                request_data=request_data,
                project_id=project_id,
                task_id=task_id,
                session_id=session_id,
                timeout_seconds=timeout,
                position_at_creation=pending_count + 1
            )

            db.add(job)
            db.commit()
            db.refresh(job)
            return job

        except Exception as e:
            db.rollback()
            raise e

    def enqueue_agent_run(
        self,
        task_id: int,
        agent_type: str,
        project_path: str,
        project_id: int = None,
        run_id: int = None,
        priority: int = JobPriority.HIGH,
        timeout: int = 600
    ) -> LLMJob:
        """Add agent run to queue.

        Args:
            task_id: Task to run agent on
            agent_type: Type of agent (dev, qa, sec, docs)
            project_path: Path to project repository
            project_id: Project ID
            run_id: Optional run ID for legacy flow
            priority: Priority level
            timeout: Timeout in seconds (default 10 minutes)

        Returns:
            Created LLMJob record
        """
        request_data = {
            "task_id": task_id,
            "agent_type": agent_type,
            "project_path": project_path,
            "run_id": run_id
        }

        return self.enqueue_llm_request(
            job_type=JobType.AGENT_RUN.value,
            request_data=request_data,
            priority=priority,
            project_id=project_id,
            task_id=task_id,
            timeout=timeout
        )

    def enqueue_vision_request(
        self,
        image_path: str,
        prompt: str = None,
        project_id: int = None,
        priority: int = JobPriority.LOW,
        timeout: int = 120
    ) -> LLMJob:
        """Add vision analysis to queue (low priority).

        Args:
            image_path: Path to image file
            prompt: Optional prompt for analysis
            project_id: Optional project context
            priority: Priority level (default LOW)
            timeout: Timeout in seconds

        Returns:
            Created LLMJob record
        """
        request_data = {
            "image_path": image_path,
            "prompt": prompt
        }

        return self.enqueue_llm_request(
            job_type=JobType.VISION_ANALYZE.value,
            request_data=request_data,
            priority=priority,
            project_id=project_id,
            timeout=timeout
        )

    # === Queue Management ===

    def get_next_job(self, job_types: List[str] = None) -> Optional[LLMJob]:
        """Get highest priority pending job.

        Args:
            job_types: List of JobType.value strings to filter by

        Returns:
            Next job to process, or None if queue is empty
        """
        db = self._get_db()
        try:
            query = db.query(LLMJob).filter(
                LLMJob.status == JobStatus.PENDING.value
            )

            if job_types:
                query = query.filter(LLMJob.job_type.in_(job_types))

            # Order by priority (ascending) then created_at (ascending)
            job = query.order_by(
                LLMJob.priority.asc(),
                LLMJob.created_at.asc()
            ).first()

            return job

        except Exception:
            return None

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status.

        Returns:
            Dict with queue lengths, running jobs, and estimated wait times
        """
        db = self._get_db()
        try:
            # Count by type and status
            pending_llm = db.query(LLMJob).filter(
                LLMJob.status == JobStatus.PENDING.value,
                LLMJob.job_type.in_([
                    JobType.LLM_COMPLETE.value,
                    JobType.LLM_CHAT.value,
                    JobType.LLM_QUERY.value
                ])
            ).count()

            pending_agents = db.query(LLMJob).filter(
                LLMJob.status == JobStatus.PENDING.value,
                LLMJob.job_type == JobType.AGENT_RUN.value
            ).count()

            pending_vision = db.query(LLMJob).filter(
                LLMJob.status == JobStatus.PENDING.value,
                LLMJob.job_type == JobType.VISION_ANALYZE.value
            ).count()

            running_jobs = db.query(LLMJob).filter(
                LLMJob.status == JobStatus.RUNNING.value
            ).all()

            # Calculate average wait time from recent completed jobs
            recent_completed = db.query(LLMJob).filter(
                LLMJob.status == JobStatus.COMPLETED.value,
                LLMJob.completed_at >= datetime.utcnow() - timedelta(hours=1)
            ).all()

            avg_wait = 0.0
            avg_runtime = 0.0
            if recent_completed:
                waits = [j.wait_time_seconds for j in recent_completed]
                runtimes = [j.run_time_seconds for j in recent_completed]
                avg_wait = sum(waits) / len(waits)
                avg_runtime = sum(runtimes) / len(runtimes)

            return {
                "pending": {
                    "llm": pending_llm,
                    "agent": pending_agents,
                    "vision": pending_vision,
                    "total": pending_llm + pending_agents + pending_vision
                },
                "running": [j.to_dict() for j in running_jobs],
                "running_count": len(running_jobs),
                "avg_wait_seconds": round(avg_wait, 1),
                "avg_runtime_seconds": round(avg_runtime, 1),
                "estimated_wait_seconds": round(
                    (pending_llm + pending_agents) * avg_runtime, 1
                ) if avg_runtime else 0
            }

        except Exception as e:
            return {"error": str(e)}

    def get_job_position(self, job_id: int) -> int:
        """Get position of job in queue.

        Args:
            job_id: Job ID to find

        Returns:
            Position in queue (1-based), or 0 if not pending
        """
        db = self._get_db()
        try:
            job = db.query(LLMJob).filter(LLMJob.id == job_id).first()
            if not job or job.status != JobStatus.PENDING.value:
                return 0

            # Count pending jobs with higher priority or earlier creation
            position = db.query(LLMJob).filter(
                LLMJob.status == JobStatus.PENDING.value,
                or_(
                    LLMJob.priority < job.priority,
                    and_(
                        LLMJob.priority == job.priority,
                        LLMJob.created_at < job.created_at
                    )
                )
            ).count()

            return position + 1

        except Exception:
            return 0

    # === Job Lifecycle ===

    def start_job(self, job_id: int, worker_id: str = None) -> Optional[LLMJob]:
        """Mark job as running.

        Args:
            job_id: Job ID to start
            worker_id: Optional worker identifier

        Returns:
            Updated job, or None if not found/already started
        """
        db = self._get_db()
        try:
            job = db.query(LLMJob).filter(
                LLMJob.id == job_id,
                LLMJob.status == JobStatus.PENDING.value
            ).first()

            if not job:
                return None

            job.status = JobStatus.RUNNING.value
            job.started_at = datetime.utcnow()
            job.worker_id = worker_id

            db.commit()
            db.refresh(job)
            return job

        except Exception as e:
            db.rollback()
            raise e

    def complete_job(self, job_id: int, result_data: Dict[str, Any]) -> Optional[LLMJob]:
        """Mark job as completed with result.

        Args:
            job_id: Job ID to complete
            result_data: Result data to store

        Returns:
            Updated job, or None if not found
        """
        db = self._get_db()
        try:
            job = db.query(LLMJob).filter(
                LLMJob.id == job_id,
                LLMJob.status == JobStatus.RUNNING.value
            ).first()

            if not job:
                return None

            job.status = JobStatus.COMPLETED.value
            job.completed_at = datetime.utcnow()
            job.result_data = result_data

            db.commit()
            db.refresh(job)
            return job

        except Exception as e:
            db.rollback()
            raise e

    def fail_job(self, job_id: int, error: str) -> Optional[LLMJob]:
        """Mark job as failed.

        Args:
            job_id: Job ID to fail
            error: Error message

        Returns:
            Updated job, or None if not found
        """
        db = self._get_db()
        try:
            job = db.query(LLMJob).filter(
                LLMJob.id == job_id,
                LLMJob.status == JobStatus.RUNNING.value
            ).first()

            if not job:
                return None

            job.status = JobStatus.FAILED.value
            job.completed_at = datetime.utcnow()
            job.error_message = error

            db.commit()
            db.refresh(job)
            return job

        except Exception as e:
            db.rollback()
            raise e

    def cancel_job(self, job_id: int) -> bool:
        """Cancel pending job.

        Args:
            job_id: Job ID to cancel

        Returns:
            True if cancelled, False if not found or not pending
        """
        db = self._get_db()
        try:
            job = db.query(LLMJob).filter(
                LLMJob.id == job_id,
                LLMJob.status == JobStatus.PENDING.value
            ).first()

            if not job:
                return False

            job.status = JobStatus.CANCELLED.value
            job.completed_at = datetime.utcnow()

            db.commit()
            return True

        except Exception as e:
            db.rollback()
            return False

    def force_kill_job(self, job_id: int, reason: str = "Killed by user") -> bool:
        """Force kill a running job.

        Unlike cancel_job, this works on RUNNING jobs.

        Args:
            job_id: Job ID to kill
            reason: Reason for killing

        Returns:
            True if killed, False if not found or not running
        """
        db = self._get_db()
        try:
            job = db.query(LLMJob).filter(
                LLMJob.id == job_id,
                LLMJob.status == JobStatus.RUNNING.value
            ).first()

            if not job:
                return False

            job.status = JobStatus.FAILED.value
            job.completed_at = datetime.utcnow()
            job.error_message = reason

            db.commit()
            return True

        except Exception as e:
            db.rollback()
            return False

    def kill_all_running(self, reason: str = "System cleanup") -> int:
        """Kill all running jobs.

        Args:
            reason: Reason for killing

        Returns:
            Number of jobs killed
        """
        db = self._get_db()
        try:
            running_jobs = db.query(LLMJob).filter(
                LLMJob.status == JobStatus.RUNNING.value
            ).all()

            count = 0
            for job in running_jobs:
                job.status = JobStatus.FAILED.value
                job.completed_at = datetime.utcnow()
                job.error_message = reason
                count += 1

            db.commit()
            return count

        except Exception as e:
            db.rollback()
            return 0

    def timeout_job(self, job_id: int) -> Optional[LLMJob]:
        """Mark job as timed out.

        Args:
            job_id: Job ID to timeout

        Returns:
            Updated job, or None if not found
        """
        db = self._get_db()
        try:
            job = db.query(LLMJob).filter(LLMJob.id == job_id).first()
            if not job:
                return None

            job.status = JobStatus.TIMEOUT.value
            job.completed_at = datetime.utcnow()
            job.error_message = "Job exceeded timeout"

            db.commit()
            db.refresh(job)
            return job

        except Exception as e:
            db.rollback()
            raise e

    def get_job(self, job_id: int) -> Optional[LLMJob]:
        """Get job by ID.

        Args:
            job_id: Job ID

        Returns:
            Job record or None
        """
        db = self._get_db()
        return db.query(LLMJob).filter(LLMJob.id == job_id).first()

    def wait_for_job(self, job_id: int, timeout: int = 120, poll_interval: float = 0.5) -> Optional[LLMJob]:
        """Wait for job to complete.

        Args:
            job_id: Job ID to wait for
            timeout: Maximum wait time in seconds
            poll_interval: Time between status checks

        Returns:
            Completed job, or None if timeout/cancelled
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            job = self.get_job(job_id)
            if job and job.is_terminal:
                return job
            time.sleep(poll_interval)
        return None

    # === Cleanup ===

    def cleanup_stale_jobs(self, max_age_hours: int = 24) -> int:
        """Clean up old completed/failed jobs.

        Args:
            max_age_hours: Maximum age in hours before deletion

        Returns:
            Number of jobs deleted
        """
        db = self._get_db()
        try:
            cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)

            deleted = db.query(LLMJob).filter(
                LLMJob.status.in_([
                    JobStatus.COMPLETED.value,
                    JobStatus.FAILED.value,
                    JobStatus.CANCELLED.value,
                    JobStatus.TIMEOUT.value
                ]),
                LLMJob.completed_at < cutoff
            ).delete(synchronize_session=False)

            db.commit()
            return deleted

        except Exception as e:
            db.rollback()
            return 0

    def check_timeouts(self) -> int:
        """Check and timeout stale running jobs.

        Returns:
            Number of jobs timed out
        """
        db = self._get_db()
        try:
            now = datetime.utcnow()
            timed_out = 0

            running_jobs = db.query(LLMJob).filter(
                LLMJob.status == JobStatus.RUNNING.value
            ).all()

            for job in running_jobs:
                if job.started_at:
                    elapsed = (now - job.started_at.replace(tzinfo=None)).total_seconds()
                    if elapsed > job.timeout_seconds:
                        job.status = JobStatus.TIMEOUT.value
                        job.completed_at = now
                        job.error_message = f"Job timed out after {elapsed:.0f}s"
                        timed_out += 1

            db.commit()
            return timed_out

        except Exception as e:
            db.rollback()
            return 0


# Singleton instance
_queue_service: Optional[JobQueueService] = None


def get_queue_service() -> JobQueueService:
    """Get or create queue service singleton."""
    global _queue_service
    if _queue_service is None:
        _queue_service = JobQueueService()
    return _queue_service
