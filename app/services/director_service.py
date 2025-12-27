"""Director Service - Orchestrates task pipeline flow.

The Director ensures tasks move through the pipeline:
BACKLOG → DEV → QA → SEC → DOCS → COMPLETE
         ↑______|  (loop back on failures)

This implements WH-014 (Director daemon) and WH-017 (Hybrid task/run flow).
"""
import os
import time
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from sqlalchemy.orm import Session

from app.models.task import Task, TaskStatus, TaskPipelineStage
from app.models.run import Run, RunState
from app.models.project import Project
from app.models.report import AgentReport, AgentRole, ReportStatus
from app.models.audit import log_event


class DirectorService:
    """Orchestrates task progression through pipeline stages."""

    # Pipeline stage progression
    STAGE_ORDER = [
        TaskPipelineStage.NONE,
        TaskPipelineStage.DEV,
        TaskPipelineStage.QA,
        TaskPipelineStage.SEC,
        TaskPipelineStage.DOCS,
        TaskPipelineStage.COMPLETE,
    ]

    # Map stages to agent roles
    STAGE_TO_AGENT = {
        TaskPipelineStage.DEV: AgentRole.DEV,
        TaskPipelineStage.QA: AgentRole.QA,
        TaskPipelineStage.SEC: AgentRole.SECURITY,
        TaskPipelineStage.DOCS: AgentRole.DOCS,
    }

    def __init__(self, db: Session):
        self.db = db

    def get_next_task(self, run_id: int = None) -> Optional[Task]:
        """Get the next task that needs processing.

        Priority order:
        1. Tasks with failures that need to loop back to DEV
        2. Tasks in QA/SEC stages waiting for review
        3. Tasks in DEV stage
        4. BACKLOG tasks ready to start

        Args:
            run_id: Optional run ID to filter tasks

        Returns:
            Task to process, or None if no work available
        """
        query = self.db.query(Task).filter(
            Task.status != TaskStatus.DONE,
            Task.pipeline_stage != TaskPipelineStage.COMPLETE
        )

        if run_id:
            query = query.filter(Task.run_id == run_id)

        # Order by priority (higher first), then by stage (further along first)
        tasks = query.order_by(
            Task.priority.desc(),
            Task.pipeline_stage.desc()
        ).all()

        for task in tasks:
            # Skip blocked tasks
            if task.is_blocked(self.db):
                continue
            return task

        return None

    def advance_task(self, task: Task, report: AgentReport = None) -> Tuple[bool, str]:
        """Advance a task to the next pipeline stage.

        Args:
            task: Task to advance
            report: Optional agent report with pass/fail status

        Returns:
            Tuple of (success, message)
        """
        current_stage = task.pipeline_stage or TaskPipelineStage.NONE

        # Check report status if provided
        if report:
            if report.status == ReportStatus.FAIL:
                # Loop back to DEV on failure
                return self._loop_back_to_dev(task, report)

        # Get next stage
        try:
            current_idx = self.STAGE_ORDER.index(current_stage)
            next_idx = current_idx + 1

            if next_idx >= len(self.STAGE_ORDER):
                # Already at COMPLETE
                return False, "Task already complete"

            next_stage = self.STAGE_ORDER[next_idx]
        except ValueError:
            # Unknown stage, start from DEV
            next_stage = TaskPipelineStage.DEV

        # Update task
        old_stage = task.pipeline_stage
        task.pipeline_stage = next_stage

        if next_stage == TaskPipelineStage.DEV:
            task.status = TaskStatus.IN_PROGRESS
        elif next_stage == TaskPipelineStage.COMPLETE:
            task.status = TaskStatus.DONE
            task.completed = True
            task.completed_at = datetime.utcnow()

        self.db.commit()

        log_event(
            self.db,
            actor="director",
            action="advance_task",
            entity_type="task",
            entity_id=task.id,
            details={
                "from_stage": old_stage.value if old_stage else "none",
                "to_stage": next_stage.value,
                "task_id": task.task_id
            }
        )

        return True, f"Advanced from {old_stage.value if old_stage else 'none'} to {next_stage.value}"

    def _loop_back_to_dev(self, task: Task, report: AgentReport) -> Tuple[bool, str]:
        """Loop a task back to DEV stage after failure.

        Args:
            task: Task that failed
            report: Failure report with details

        Returns:
            Tuple of (success, message)
        """
        old_stage = task.pipeline_stage
        task.pipeline_stage = TaskPipelineStage.DEV
        task.status = TaskStatus.IN_PROGRESS

        self.db.commit()

        log_event(
            self.db,
            actor="director",
            action="loop_back",
            entity_type="task",
            entity_id=task.id,
            details={
                "from_stage": old_stage.value if old_stage else "none",
                "reason": report.summary if report else "Unknown failure",
                "task_id": task.task_id
            }
        )

        return True, f"Looped back from {old_stage.value if old_stage else 'none'} to DEV"

    def start_task(self, task: Task) -> Tuple[bool, str]:
        """Start a task that's in BACKLOG.

        Moves it to DEV stage and sets status to IN_PROGRESS.

        Args:
            task: Task to start

        Returns:
            Tuple of (success, message)
        """
        if task.status != TaskStatus.BACKLOG:
            return False, f"Task is not in BACKLOG (current: {task.status.value})"

        if task.is_blocked(self.db):
            return False, "Task is blocked by dependencies"

        task.status = TaskStatus.IN_PROGRESS
        task.pipeline_stage = TaskPipelineStage.DEV

        self.db.commit()

        log_event(
            self.db,
            actor="director",
            action="start_task",
            entity_type="task",
            entity_id=task.id,
            details={
                "task_id": task.task_id,
                "title": task.title
            }
        )

        return True, f"Started task {task.task_id}"

    def get_tasks_by_stage(self, stage: TaskPipelineStage, run_id: int = None) -> List[Task]:
        """Get all tasks at a specific pipeline stage.

        Args:
            stage: Pipeline stage to filter by
            run_id: Optional run ID to filter tasks

        Returns:
            List of tasks at the specified stage
        """
        query = self.db.query(Task).filter(Task.pipeline_stage == stage)

        if run_id:
            query = query.filter(Task.run_id == run_id)

        return query.order_by(Task.priority.desc()).all()

    def get_run_progress(self, run_id: int) -> Dict:
        """Get pipeline progress summary for a run.

        Args:
            run_id: Run ID to get progress for

        Returns:
            Dict with stage counts and completion percentage
        """
        tasks = self.db.query(Task).filter(Task.run_id == run_id).all()

        if not tasks:
            return {"total": 0, "stages": {}, "percent_complete": 0}

        stage_counts = {}
        for stage in TaskPipelineStage:
            stage_counts[stage.value] = 0

        for task in tasks:
            stage = task.pipeline_stage or TaskPipelineStage.NONE
            stage_counts[stage.value] += 1

        complete = stage_counts.get("complete", 0)
        total = len(tasks)

        return {
            "total": total,
            "stages": stage_counts,
            "percent_complete": round((complete / total) * 100, 1) if total > 0 else 0
        }

    def process_run(self, run_id: int, max_tasks: int = 10) -> Dict:
        """Process tasks for a run through the pipeline.

        This is the main orchestration method. It:
        1. Finds tasks that need work
        2. Determines what agent should handle them
        3. Returns the work queue for external execution

        Args:
            run_id: Run ID to process
            max_tasks: Maximum tasks to process in one batch

        Returns:
            Dict with work queue and status
        """
        work_queue = []
        processed = 0

        # Get all active tasks for this run (include NULL pipeline_stage)
        tasks = self.db.query(Task).filter(
            Task.run_id == run_id,
            Task.status != TaskStatus.DONE
        ).order_by(Task.priority.desc()).limit(max_tasks).all()

        for task in tasks:
            # Skip completed tasks
            if task.pipeline_stage == TaskPipelineStage.COMPLETE:
                continue

            if task.is_blocked(self.db):
                continue

            # Determine what needs to happen
            # Handle NULL pipeline_stage as NONE
            stage = task.pipeline_stage if task.pipeline_stage else TaskPipelineStage.NONE

            if stage == TaskPipelineStage.NONE:
                # Task needs to start - move to DEV
                success, msg = self.start_task(task)
                if success:
                    stage = TaskPipelineStage.DEV
                else:
                    continue  # Skip if can't start

            # Get the agent for this stage
            agent = self.STAGE_TO_AGENT.get(stage)
            if agent:
                work_queue.append({
                    "task_id": task.id,
                    "task_ref": task.task_id,
                    "title": task.title,
                    "stage": stage.value,
                    "agent": agent.value,
                    "priority": task.priority
                })
                processed += 1

        return {
            "run_id": run_id,
            "tasks_queued": len(work_queue),
            "work_queue": work_queue,
            "progress": self.get_run_progress(run_id)
        }


def run_director_daemon(db_getter, run_id: int = None, poll_interval: int = 30):
    """Run the Director as a background daemon.

    Polls for work and dispatches to agents.

    Args:
        db_getter: Function that returns a database session
        run_id: Optional specific run to monitor
        poll_interval: Seconds between polls
    """
    print(f"\n{'='*60}")
    print("DIRECTOR DAEMON STARTED")
    print(f"Poll interval: {poll_interval}s")
    if run_id:
        print(f"Monitoring run: {run_id}")
    print(f"{'='*60}\n")

    while True:
        try:
            db = db_getter()
            director = DirectorService(db)

            if run_id:
                result = director.process_run(run_id)
                if result["tasks_queued"] > 0:
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Work queue:")
                    for item in result["work_queue"]:
                        print(f"  - {item['task_ref']}: {item['title'][:40]}... → {item['agent'].upper()}")
                    print(f"  Progress: {result['progress']['percent_complete']}% complete")
            else:
                # Find runs that need processing
                runs = db.query(Run).filter(
                    Run.state.notin_([RunState.DEPLOYED, RunState.MERGED])
                ).all()

                for run in runs:
                    result = director.process_run(run.id)
                    if result["tasks_queued"] > 0:
                        print(f"\n[Run {run.id}] {result['tasks_queued']} tasks queued")

            db.close()

        except KeyboardInterrupt:
            print("\nDirector daemon stopped.")
            break
        except Exception as e:
            print(f"Error in director daemon: {e}")

        time.sleep(poll_interval)
