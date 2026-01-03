"""Director Service - Orchestrates task pipeline flow.

The Director ensures tasks move through the pipeline:
BACKLOG → DEV → QA → SEC → DOCS → COMPLETE
         ↑______|  (loop back on failures)

This implements WH-014 (Director daemon) and WH-017 (Hybrid task/run flow).

The Director actively:
- Validates task readiness (description, acceptance criteria)
- Fills in missing acceptance criteria using templates
- Triggers agent execution when tasks are ready
- Monitors progress and advances pipeline stages
"""
import os
import time
import subprocess
import threading
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from sqlalchemy.orm import Session

from app.models.task import Task, TaskStatus, TaskPipelineStage
from app.models.run import Run, RunState
from app.models.project import Project
from app.models.report import AgentReport, AgentRole, ReportStatus
from app.models.audit import log_event
from app.services.quality_requirements_service import load_quality_requirements
from django.conf import settings


# Default acceptance criteria templates by task type pattern
ACCEPTANCE_CRITERIA_TEMPLATES = {
    "feature": [
        "Feature is implemented as described",
        "Unit tests cover core functionality",
        "No regressions in existing tests",
        "Code follows project style guidelines",
    ],
    "bugfix": [
        "Bug is fixed and no longer reproducible",
        "Regression test added to prevent recurrence",
        "Root cause documented in commit message",
    ],
    "refactor": [
        "Functionality unchanged (all existing tests pass)",
        "Code complexity reduced or maintainability improved",
        "No performance regressions",
    ],
    "security": [
        "Security vulnerability addressed",
        "Security test added to verify fix",
        "No new vulnerabilities introduced",
    ],
    "default": [
        "Task requirements are satisfied",
        "Tests pass without errors",
        "Code is reviewed and follows project conventions",
    ],
}


class DirectorService:
    """Orchestrates task progression through pipeline stages."""

    # Pipeline stage progression
    STAGE_ORDER = [
        TaskPipelineStage.NONE,
        TaskPipelineStage.PM,
        TaskPipelineStage.DEV,
        TaskPipelineStage.QA,
        TaskPipelineStage.SEC,
        TaskPipelineStage.DOCS,
        TaskPipelineStage.COMPLETE,
    ]

    # Map stages to agent roles
    STAGE_TO_AGENT = {
        TaskPipelineStage.PM: AgentRole.PM,
        TaskPipelineStage.DEV: AgentRole.DEV,
        TaskPipelineStage.QA: AgentRole.QA,
        TaskPipelineStage.SEC: AgentRole.SECURITY,
        TaskPipelineStage.DOCS: AgentRole.DOCS,
    }

    def __init__(self, db: Session):
        self.db = db

    def validate_task_readiness(self, task: Task) -> Tuple[bool, List[str]]:
        """Check if a task is ready for agent processing.

        Args:
            task: Task to validate

        Returns:
            Tuple of (is_ready, list_of_issues)
        """
        issues = []

        # Must have a title
        if not task.title or len(task.title.strip()) < 3:
            issues.append("Task needs a meaningful title")

        # Must have a description
        if not task.description or len(task.description.strip()) < 10:
            issues.append("Task needs a description (at least 10 chars)")

        # Must have acceptance criteria
        if not task.acceptance_criteria or len(task.acceptance_criteria) == 0:
            issues.append("Task needs acceptance criteria")

        return (len(issues) == 0, issues)

    def enrich_task(self, task: Task) -> Tuple[bool, str]:
        """Enrich a task with missing fields like acceptance criteria.

        Uses templates based on task title/description patterns.

        Args:
            task: Task to enrich

        Returns:
            Tuple of (modified, message)
        """
        modified = False
        messages = []

        # Generate acceptance criteria if missing
        if not task.acceptance_criteria or len(task.acceptance_criteria) == 0:
            criteria = self._generate_acceptance_criteria(task)
            task.acceptance_criteria = criteria
            modified = True
            messages.append(f"Added {len(criteria)} acceptance criteria")

            log_event(
                self.db,
                actor="director",
                action="enrich_task",
                entity_type="task",
                entity_id=task.id,
                details={
                    "task_id": task.task_id,
                    "added_criteria": criteria
                }
            )

        if modified:
            self.db.commit()

        return (modified, "; ".join(messages) if messages else "No enrichment needed")

    def _generate_acceptance_criteria(self, task: Task) -> List[str]:
        """Generate acceptance criteria based on task patterns.

        Args:
            task: Task to generate criteria for

        Returns:
            List of acceptance criteria strings
        """
        title_lower = (task.title or "").lower()
        desc_lower = (task.description or "").lower()
        combined = f"{title_lower} {desc_lower}"

        # Detect task type from keywords
        if any(word in combined for word in ["bug", "fix", "error", "broken", "crash"]):
            template_key = "bugfix"
        elif any(word in combined for word in ["security", "vulnerability", "exploit", "cve"]):
            template_key = "security"
        elif any(word in combined for word in ["refactor", "cleanup", "reorganize", "optimize"]):
            template_key = "refactor"
        elif any(word in combined for word in ["feature", "add", "implement", "create", "new"]):
            template_key = "feature"
        else:
            template_key = "default"

        return ACCEPTANCE_CRITERIA_TEMPLATES.get(template_key, ACCEPTANCE_CRITERIA_TEMPLATES["default"]).copy()

    def trigger_agent_for_task(self, task: Task) -> Tuple[bool, str, Optional[int]]:
        """Trigger agent execution for a task.

        Creates a run if needed and spawns agent_runner in background.

        Args:
            task: Task to run agent for

        Returns:
            Tuple of (success, message, run_id)
        """
        # Get project for this task
        project = self.db.query(Project).filter(Project.id == task.project_id).first()
        if not project:
            return (False, "Project not found", None)

        # Create a new run for this task
        # NOTE: task.run_id removed in refactor - always create new run per task execution
        from app.services.run_service import RunService
        run_service = RunService(self.db)
        run = run_service.create_run(
            project_id=project.id,
            name=f"Execute Task: {task.task_id} - {task.title[:50]}",
            actor="director"
        )
        self.db.commit()

        # Get project path
        project_path = project.repo_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "workspaces",
            project.name.lower().replace(" ", "_")
        )

        # Determine agent role based on pipeline stage
        stage = task.pipeline_stage
        if stage == TaskPipelineStage.DEV:
            agent_role = "dev"
        elif stage == TaskPipelineStage.QA:
            agent_role = "qa"
        elif stage == TaskPipelineStage.SEC:
            agent_role = "security"
        elif stage == TaskPipelineStage.DOCS:
            agent_role = "docs"
        else:
            agent_role = "pm"  # Default to PM for planning stages

        # Spawn agent_runner in background thread using task-centric mode
        def run_agent():
            try:
                agent_runner_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "scripts",
                    "agent_runner.py"
                )
                # Use task command for task-centric execution with work_cycle API
                cmd = [
                    "python", agent_runner_path, "task",
                    "--agent", agent_role,
                    "--task-id", str(task.id),
                    "--run-id", str(run.id),
                    "--project-path", project_path
                ]
                print(f"[Agent] Running: {' '.join(cmd)}")
                result = subprocess.run(
                    cmd,
                    timeout=1800,  # 30 minute timeout
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    print(f"[Agent] stderr: {result.stderr}")
                print(f"[Agent] stdout: {result.stdout[:500] if result.stdout else 'empty'}")
            except Exception as e:
                print(f"Agent execution error for task {task.task_id}: {e}")

        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()

        log_event(
            self.db,
            actor="director",
            action="trigger_agent",
            entity_type="task",
            entity_id=task.id,
            details={
                "task_id": task.task_id,
                "run_id": run.id,
                "stage": task.pipeline_stage.value if task.pipeline_stage else "none"
            }
        )

        return (True, f"Agent triggered for task {task.task_id}", run.id)

    def prepare_and_run_task(self, task: Task) -> Dict:
        """Prepare a task (enrich if needed) and trigger agent execution.

        This is the main entry point for the director to move tasks along.

        Args:
            task: Task to process

        Returns:
            Dict with result details
        """
        result = {
            "task_id": task.task_id,
            "enriched": False,
            "triggered": False,
            "run_id": None,
            "issues": [],
            "message": ""
        }

        # First, enrich the task if needed
        enriched, enrich_msg = self.enrich_task(task)
        result["enriched"] = enriched
        if enriched:
            result["message"] = enrich_msg

        # Validate readiness
        is_ready, issues = self.validate_task_readiness(task)
        if not is_ready:
            result["issues"] = issues
            result["message"] = f"Task not ready: {'; '.join(issues)}"
            return result

        # Trigger agent execution
        triggered, trigger_msg, run_id = self.trigger_agent_for_task(task)
        result["triggered"] = triggered
        result["run_id"] = run_id
        result["message"] = trigger_msg

        return result

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

        # NOTE: Task.run_id removed in refactor - filter by project of the run if run_id provided
        if run_id:
            from app.models.run import Run
            run = self.db.query(Run).filter(Run.id == run_id).first()
            if run:
                query = query.filter(Task.project_id == run.project_id)

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

        # Prevent completion if subtasks are incomplete
        if next_stage == TaskPipelineStage.COMPLETE and self._has_incomplete_subtasks(task):
            return False, "Cannot complete task with incomplete subtasks"

        # Apply configured subtask templates for this transition
        created_count = self._apply_subtask_templates(task, current_stage, next_stage)
        if created_count:
            return False, "Subtasks created for this transition; complete them before advancing"
        if self._has_incomplete_subtasks(task):
            return False, "Awaiting subtask completion before advancing"

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

    def _has_incomplete_subtasks(self, task: Task) -> bool:
        """Return True if any subtasks are not done."""
        return any(subtask.status != TaskStatus.DONE for subtask in (task.subtasks or []))

    def _apply_subtask_templates(
        self,
        task: Task,
        current_stage: TaskPipelineStage,
        next_stage: TaskPipelineStage
    ) -> int:
        """Create subtasks based on configured pipeline templates for a transition."""
        templates = self._get_subtask_templates(task.project_id)
        if not templates:
            return 0

        created = 0
        existing_titles = {subtask.title for subtask in (task.subtasks or [])}
        transition_from = (current_stage.value if current_stage else "none").lower()
        transition_to = (next_stage.value if next_stage else "none").lower()

        for template in templates:
            if template.get("trigger_from") != transition_from:
                continue
            if template.get("trigger_to") != transition_to:
                continue

            requirements = template.get("template_items")
            if not isinstance(requirements, list):
                template_path = template.get("template_path")
                if template_path and not os.path.isabs(template_path):
                    template_path = os.path.join(settings.BASE_DIR, template_path)
                requirements = load_quality_requirements(template_path)
            if not requirements:
                continue

            auto_stage = template.get("auto_assign_stage", "dev").lower()
            try:
                stage_enum = TaskPipelineStage.get_stage_map().get(auto_stage.upper()) or TaskPipelineStage.DEV
            except Exception:
                stage_enum = TaskPipelineStage.DEV

            for requirement in requirements:
                title = requirement.get("subtask_title") or f"Subtask: {requirement.get('title', 'Check')}"
                if title in existing_titles:
                    continue

                subtask = Task(
                    project_id=task.project_id,
                    task_id=self._next_task_id(task.project_id),
                    title=title,
                    description=requirement.get("description", ""),
                    status=TaskStatus.BACKLOG,
                    priority=task.priority,
                    pipeline_stage=stage_enum,
                    acceptance_criteria=requirement.get("acceptance_criteria", []),
                    parent_task_id=task.id
                )
                self.db.add(subtask)
                if template.get("inherit_requirements", True) and task.requirements:
                    subtask.requirements.extend(task.requirements)
                created += 1

        if created:
            self.db.commit()
            log_event(
                self.db,
                actor="director",
                action="create_subtasks_from_template",
                entity_type="task",
                entity_id=task.id,
                details={"count": created, "task_id": task.task_id}
            )

        return created

    def _get_subtask_templates(self, project_id: int) -> list:
        """Load subtask templates from active pipeline config or defaults."""
        try:
            from app.models.pipeline_config import PipelineConfig
            config = self.db.query(PipelineConfig).filter(
                PipelineConfig.project_id == project_id,
                PipelineConfig.is_active == True
            ).order_by(PipelineConfig.version.desc()).first()

            if config:
                if isinstance(config.settings, dict):
                    templates = config.settings.get("subtask_templates")
                    if isinstance(templates, list):
                        return templates
                if isinstance(config.nodes, list):
                    node_templates = []
                    for node in config.nodes:
                        if node.get("type") != "subtask":
                            continue
                        data = node.get("data") or {}
                        node_templates.append({
                            "trigger_from": (data.get("triggerFrom") or "pm").lower(),
                            "trigger_to": (data.get("triggerTo") or "dev").lower(),
                            "template_path": data.get("templatePath") or "config/qa_requirements.json",
                            "template_items": data.get("templateItems") if isinstance(data.get("templateItems"), list) else None,
                            "auto_assign_stage": (data.get("autoAssignStage") or "dev").lower(),
                            "inherit_requirements": bool(data.get("inheritRequirements", True)),
                        })
                    if node_templates:
                        return node_templates
        except Exception:
            pass

        # Default template (PM -> DEV)
        return [{
            "trigger_from": "pm",
            "trigger_to": "dev",
            "template_path": os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "qa_requirements.json"),
            "auto_assign_stage": "dev",
            "inherit_requirements": True
        }]

    def _next_task_id(self, project_id: int) -> str:
        """Generate next task_id for a project."""
        count = self.db.query(Task).filter(Task.project_id == project_id).count()
        return f"T{count + 1:03d}"

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

        # NOTE: Task.run_id removed in refactor - filter by project of the run if run_id provided
        if run_id:
            from app.models.run import Run
            run = self.db.query(Run).filter(Run.id == run_id).first()
            if run:
                query = query.filter(Task.project_id == run.project_id)

        return query.order_by(Task.priority.desc()).all()

    def get_run_progress(self, run_id: int) -> Dict:
        """Get pipeline progress summary for a run.

        Args:
            run_id: Run ID to get progress for

        Returns:
            Dict with stage counts and completion percentage
        """
        # NOTE: Task.run_id removed in refactor - get tasks by project of the run
        from app.models.run import Run
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return {"total": 0, "stages": {}, "percent_complete": 0}
        tasks = self.db.query(Task).filter(Task.project_id == run.project_id).all()

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

    def process_run(self, run_id: int, max_tasks: int = 10, auto_trigger: bool = False) -> Dict:
        """Process tasks for a run through the pipeline.

        This is the main orchestration method. It:
        1. Finds tasks that need work
        2. Enriches tasks with missing acceptance criteria
        3. Determines what agent should handle them
        4. Optionally triggers agent execution

        Args:
            run_id: Run ID to process
            max_tasks: Maximum tasks to process in one batch
            auto_trigger: If True, automatically trigger agent for each task

        Returns:
            Dict with work queue, enrichments, and status
        """
        work_queue = []
        enriched_tasks = []
        triggered_tasks = []
        processed = 0

        # Get all active tasks for this run's project (include NULL pipeline_stage)
        # NOTE: Task.run_id removed in refactor - get tasks by project of the run
        from app.models.run import Run
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return {"work_queue": [], "enriched": [], "triggered": [], "message": "Run not found"}
        tasks = self.db.query(Task).filter(
            Task.project_id == run.project_id,
            Task.status != TaskStatus.DONE
        ).order_by(Task.priority.desc()).limit(max_tasks).all()

        for task in tasks:
            # Skip completed tasks
            if task.pipeline_stage == TaskPipelineStage.COMPLETE:
                continue

            if task.is_blocked(self.db):
                continue

            # Enrich task if missing acceptance criteria
            enriched, enrich_msg = self.enrich_task(task)
            if enriched:
                enriched_tasks.append({
                    "task_id": task.task_id,
                    "message": enrich_msg
                })

            # Validate task is ready
            is_ready, issues = self.validate_task_readiness(task)
            if not is_ready:
                # Log but continue - task needs manual attention
                log_event(
                    self.db,
                    actor="director",
                    action="task_not_ready",
                    entity_type="task",
                    entity_id=task.id,
                    details={"issues": issues}
                )
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
                task_info = {
                    "task_id": task.id,
                    "task_ref": task.task_id,
                    "title": task.title,
                    "stage": stage.value,
                    "agent": agent.value,
                    "priority": task.priority
                }
                work_queue.append(task_info)
                processed += 1

                # Auto-trigger agent if requested
                if auto_trigger:
                    triggered, msg, triggered_run_id = self.trigger_agent_for_task(task)
                    if triggered:
                        triggered_tasks.append({
                            "task_id": task.task_id,
                            "run_id": triggered_run_id
                        })

        return {
            "run_id": run_id,
            "tasks_queued": len(work_queue),
            "tasks_enriched": len(enriched_tasks),
            "tasks_triggered": len(triggered_tasks),
            "work_queue": work_queue,
            "enriched": enriched_tasks,
            "triggered": triggered_tasks,
            "progress": self.get_run_progress(run_id)
        }


class TaskOrchestrator:
    """Algorithmic task orchestration with retry logic.

    This handles:
    - Auto-starting BACKLOG tasks when there's bandwidth
    - Tracking stuck tasks and retrying them
    - Moving tasks through the pipeline based on completion
    """

    MAX_RETRIES = 3
    RETRY_INTERVAL_SECONDS = 300  # 5 minutes
    MAX_CONCURRENT_PER_STAGE = 2  # Max tasks in progress per stage

    def __init__(self, db: Session):
        self.db = db
        self.director = DirectorService(db)
        # Track retry counts: {task_id: {"count": int, "last_attempt": datetime}}
        self._retry_tracker = {}

    def check_and_advance_stuck_tasks(self) -> List[Dict]:
        """Check for tasks that should be advanced and advance them.

        Returns list of actions taken.
        """
        actions = []

        # Find tasks in IN_PROGRESS status for each pipeline stage
        for stage in [TaskPipelineStage.DEV, TaskPipelineStage.QA,
                      TaskPipelineStage.SEC, TaskPipelineStage.DOCS]:

            in_progress_tasks = self.db.query(Task).filter(
                Task.pipeline_stage == stage,
                Task.status == TaskStatus.IN_PROGRESS
            ).all()

            for task in in_progress_tasks:
                # Check if task has a passing report
                if self._has_passing_report(task, stage):
                    # Advance to next stage
                    success, msg = self.director.advance_task(task)
                    if success:
                        actions.append({
                            "action": "advanced",
                            "task_id": task.id,
                            "from_stage": stage.value,
                            "message": msg
                        })
                        # Reset retry counter
                        if task.id in self._retry_tracker:
                            del self._retry_tracker[task.id]

        return actions

    def _has_passing_report(self, task: Task, stage: TaskPipelineStage) -> bool:
        """Check if task has a passing agent report for the current stage.

        This is where we'd check for proof-of-work or agent reports.
        NOTE: task.run_id removed in refactor - check reports for recent project runs.
        """
        # Map stage to role
        stage_to_role = {
            TaskPipelineStage.DEV: AgentRole.DEV,
            TaskPipelineStage.QA: AgentRole.QA,
            TaskPipelineStage.SEC: AgentRole.SECURITY,
            TaskPipelineStage.DOCS: AgentRole.DOCS,
        }

        role = stage_to_role.get(stage)
        if not role:
            return False

        # Get recent runs for this project and look for passing reports
        recent_runs = self.db.query(Run).filter(
            Run.project_id == task.project_id
        ).order_by(Run.created_at.desc()).limit(5).all()

        for run in recent_runs:
            report = self.db.query(AgentReport).filter(
                AgentReport.run_id == run.id,
                AgentReport.role == role,
                AgentReport.status == ReportStatus.PASS
            ).order_by(AgentReport.created_at.desc()).first()
            if report:
                return True

        return False

    def auto_start_backlog_tasks(self, max_to_start: int = 2) -> List[Dict]:
        """Auto-start BACKLOG tasks if there's bandwidth.

        Returns list of tasks started.
        """
        actions = []

        # Check current workload - how many tasks are in DEV?
        dev_count = self.db.query(Task).filter(
            Task.pipeline_stage == TaskPipelineStage.DEV,
            Task.status == TaskStatus.IN_PROGRESS
        ).count()

        # If we have room, start backlog tasks
        slots_available = self.MAX_CONCURRENT_PER_STAGE - dev_count
        if slots_available <= 0:
            return actions

        # Find BACKLOG tasks ordered by priority
        backlog_tasks = self.db.query(Task).filter(
            Task.status == TaskStatus.BACKLOG,
            Task.pipeline_stage.in_([TaskPipelineStage.NONE, None])
        ).order_by(Task.priority.desc()).limit(min(slots_available, max_to_start)).all()

        for task in backlog_tasks:
            if task.is_blocked(self.db):
                continue

            success, msg = self.director.start_task(task)
            if success:
                actions.append({
                    "action": "started",
                    "task_id": task.id,
                    "task_ref": task.task_id,
                    "title": task.title,
                    "message": msg
                })

        return actions

    def retry_stuck_tasks(self) -> List[Dict]:
        """Retry tasks that have been stuck.

        If a task has been in the same stage for too long without progress,
        retry up to MAX_RETRIES times.
        """
        actions = []
        now = datetime.utcnow()

        # Find tasks that might be stuck (IN_PROGRESS but no recent activity)
        stuck_tasks = self.db.query(Task).filter(
            Task.status == TaskStatus.IN_PROGRESS,
            Task.pipeline_stage.notin_([TaskPipelineStage.COMPLETE, TaskPipelineStage.NONE, None])
        ).all()

        for task in stuck_tasks:
            task_key = task.id

            # Get or create retry tracker entry
            if task_key not in self._retry_tracker:
                self._retry_tracker[task_key] = {
                    "count": 0,
                    "last_attempt": task.updated_at or task.created_at
                }

            tracker = self._retry_tracker[task_key]
            last_attempt = tracker["last_attempt"]

            # Check if enough time has passed for a retry
            if last_attempt:
                time_since = (now - last_attempt).total_seconds()
                if time_since < self.RETRY_INTERVAL_SECONDS:
                    continue  # Not time yet

            # Check if we've exceeded max retries
            if tracker["count"] >= self.MAX_RETRIES:
                # Mark task as blocked after max retries
                if task.status != TaskStatus.BLOCKED:
                    task.status = TaskStatus.BLOCKED
                    self.db.commit()
                    actions.append({
                        "action": "blocked",
                        "task_id": task.id,
                        "reason": f"Exceeded {self.MAX_RETRIES} retries"
                    })
                    log_event(self.db, "director", "block_task", "task", task.id, {
                        "reason": "max_retries_exceeded",
                        "retries": tracker["count"]
                    })
                continue

            # Retry: update tracker and actually trigger agent
            tracker["count"] += 1
            tracker["last_attempt"] = now

            # Actually trigger the agent for retry
            success, msg, run_id = self.director.trigger_agent_for_task(task)

            actions.append({
                "action": "retry",
                "task_id": task.id,
                "task_ref": task.task_id,
                "attempt": tracker["count"],
                "max_retries": self.MAX_RETRIES,
                "stage": task.pipeline_stage.value if task.pipeline_stage else "none",
                "run_id": run_id if success else None,
                "triggered": success
            })

            log_event(self.db, "director", "retry_task", "task", task.id, {
                "attempt": tracker["count"],
                "stage": task.pipeline_stage.value if task.pipeline_stage else "none",
                "triggered": success,
                "run_id": run_id if success else None
            })

        return actions

    def run_cycle(self, auto_trigger_agents: bool = True) -> Dict:
        """Run one orchestration cycle.

        This is the main director loop that:
        1. Enriches tasks missing acceptance criteria
        2. Advances tasks that have passing reports
        3. Auto-starts backlog tasks
        4. Triggers agents for tasks that need work
        5. Retries stuck tasks

        Args:
            auto_trigger_agents: If True, trigger agents for tasks needing work

        Returns summary of actions taken.
        """
        result = {
            "timestamp": datetime.utcnow().isoformat(),
            "enriched": [],
            "started": [],
            "advanced": [],
            "triggered": [],
            "retried": [],
            "blocked": []
        }

        # 1. Enrich tasks missing acceptance criteria
        enriched = self.enrich_incomplete_tasks()
        result["enriched"] = enriched

        # 2. Check for tasks that can be advanced (have passing reports)
        advanced = self.check_and_advance_stuck_tasks()
        for action in advanced:
            result["advanced"].append(action)

        # 3. Auto-start backlog tasks (move to DEV stage)
        started = self.auto_start_backlog_tasks()
        for action in started:
            result["started"].append(action)

        # 4. Trigger agents for tasks that need work
        if auto_trigger_agents:
            triggered = self.trigger_agents_for_ready_tasks()
            result["triggered"] = triggered

        # 5. Retry stuck tasks
        retried = self.retry_stuck_tasks()
        for action in retried:
            if action["action"] == "retry":
                result["retried"].append(action)
            elif action["action"] == "blocked":
                result["blocked"].append(action)

        return result

    def enrich_incomplete_tasks(self, max_tasks: int = 5) -> List[Dict]:
        """Find and enrich tasks missing acceptance criteria.

        Returns list of tasks that were enriched.
        """
        enriched = []

        # Find tasks without acceptance criteria
        tasks = self.db.query(Task).filter(
            Task.status.in_([TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS]),
            Task.pipeline_stage != TaskPipelineStage.COMPLETE
        ).limit(max_tasks * 2).all()  # Get more than needed to filter

        count = 0
        for task in tasks:
            if count >= max_tasks:
                break

            # Check if task needs enrichment
            if not task.acceptance_criteria or len(task.acceptance_criteria) == 0:
                modified, msg = self.director.enrich_task(task)
                if modified:
                    enriched.append({
                        "task_id": task.id,
                        "task_ref": task.task_id,
                        "title": task.title,
                        "message": msg
                    })
                    count += 1

        return enriched

    def trigger_agents_for_ready_tasks(self, max_triggers: int = 1) -> List[Dict]:
        """Trigger agents for tasks that are ready but not being worked on.

        Only triggers if the task doesn't have an active run already.

        Args:
            max_triggers: Maximum number of agents to trigger per cycle (default 1 to avoid overload)

        Returns list of tasks that had agents triggered.
        """
        triggered = []

        # Find tasks that are IN_PROGRESS but don't have an active run
        # or have a run that's in a failed/stuck state
        # Include PM stage for planning/scoping work
        tasks = self.db.query(Task).filter(
            Task.status == TaskStatus.IN_PROGRESS,
            Task.pipeline_stage.in_([
                TaskPipelineStage.PM,
                TaskPipelineStage.DEV,
                TaskPipelineStage.QA,
                TaskPipelineStage.SEC,
                TaskPipelineStage.DOCS
            ])
        ).order_by(Task.priority.desc()).limit(max_triggers * 3).all()

        count = 0
        for task in tasks:
            if count >= max_triggers:
                break

            # Check if task already has an active run for its project
            # NOTE: Task.run_id removed in refactor - check recent project runs instead
            recent_runs = self.db.query(Run).filter(
                Run.project_id == task.project_id,
                Run.killed == False
            ).order_by(Run.created_at.desc()).limit(3).all()

            has_active_run = False
            for run in recent_runs:
                active_states = [
                    RunState.PM, RunState.DEV, RunState.QA, RunState.SEC,
                    RunState.DOCS, RunState.TESTING
                ]
                if run.state in active_states:
                    # Check if this run has a failed report and is stale
                    # Auto-kill runs with failed reports after 5 minutes
                    latest_report = self.db.query(AgentReport).filter(
                        AgentReport.run_id == run.id
                    ).order_by(AgentReport.created_at.desc()).first()

                    if latest_report and latest_report.status == ReportStatus.FAIL:
                        from datetime import datetime, timedelta
                        stale_threshold = datetime.utcnow() - timedelta(minutes=5)
                        if latest_report.created_at.replace(tzinfo=None) < stale_threshold:
                            # Auto-kill stale failed run
                            run.killed = True
                            self.db.commit()
                            log_event(self.db, "director", "auto_kill_run", "run", run.id, {
                                "reason": "stale_failed_report",
                                "report_status": "fail",
                                "report_summary": latest_report.summary[:100] if latest_report.summary else None
                            })
                            continue  # Don't count this run as active

                    has_active_run = True
                    break

            if has_active_run:
                continue  # Skip - already has active run for this project

            # Validate task is ready
            is_ready, issues = self.director.validate_task_readiness(task)
            if not is_ready:
                continue  # Skip - not ready

            # Trigger agent
            success, msg, run_id = self.director.trigger_agent_for_task(task)
            if success:
                triggered.append({
                    "task_id": task.id,
                    "task_ref": task.task_id,
                    "title": task.title,
                    "run_id": run_id,
                    "stage": task.pipeline_stage.value if task.pipeline_stage else "none"
                })
                count += 1

        return triggered


def run_director_daemon(db_getter, run_id: int = None, poll_interval: int = 30, auto_trigger: bool = True):
    """Run the Director as a background daemon.

    Polls for work and dispatches to agents algorithmically.

    The daemon:
    - Enriches tasks missing acceptance criteria
    - Auto-starts BACKLOG tasks when there's bandwidth
    - Advances tasks when agent reports pass
    - Triggers agents for tasks that need work
    - Retries stuck tasks (up to 3 times, 5 min intervals)
    - Blocks tasks that exceed retry limits
    - Updates database heartbeat for status monitoring

    Args:
        db_getter: Function that returns a database session
        run_id: Optional specific run to monitor
        poll_interval: Seconds between polls
        auto_trigger: If True, automatically trigger agents for ready tasks
    """
    print(f"\n{'='*60}")
    print("DIRECTOR DAEMON STARTED (Active Orchestration Mode)")
    print(f"Poll interval: {poll_interval}s")
    print(f"Auto-trigger agents: {auto_trigger}")
    print(f"Max retries: {TaskOrchestrator.MAX_RETRIES}")
    print(f"Retry interval: {TaskOrchestrator.RETRY_INTERVAL_SECONDS}s")
    if run_id:
        print(f"Monitoring run: {run_id}")
    print(f"{'='*60}\n")

    # Persistent orchestrator to track retries across cycles
    orchestrator = None

    while True:
        try:
            db = next(db_getter())

            # Update heartbeat in database for status monitoring
            try:
                from app.models.director_settings import DirectorSettings
                DirectorSettings.update_heartbeat(db)
            except Exception as e:
                print(f"Failed to update heartbeat: {e}")

            # Initialize or update orchestrator with fresh db session
            if orchestrator is None:
                orchestrator = TaskOrchestrator(db)
            else:
                orchestrator.db = db
                orchestrator.director.db = db

            # Run orchestration cycle
            result = orchestrator.run_cycle(auto_trigger_agents=auto_trigger)

            # Log any activity
            total_actions = (
                len(result.get("enriched", [])) +
                len(result.get("started", [])) +
                len(result.get("advanced", [])) +
                len(result.get("triggered", [])) +
                len(result.get("retried", [])) +
                len(result.get("blocked", []))
            )

            if total_actions > 0:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Orchestration cycle:")
                if result.get("enriched"):
                    print(f"  Enriched: {len(result['enriched'])} tasks")
                    for a in result["enriched"]:
                        print(f"    - {a.get('task_ref', a['task_id'])}: {a.get('message', '')}")
                if result.get("started"):
                    print(f"  Started: {len(result['started'])} tasks")
                    for a in result["started"]:
                        print(f"    - {a.get('task_ref', a['task_id'])}: {a.get('title', '')[:40]}")
                if result.get("advanced"):
                    print(f"  Advanced: {len(result['advanced'])} tasks")
                    for a in result["advanced"]:
                        print(f"    - Task {a['task_id']}: {a['message']}")
                if result.get("triggered"):
                    print(f"  Triggered Agents: {len(result['triggered'])} tasks")
                    for a in result["triggered"]:
                        print(f"    - {a.get('task_ref', a['task_id'])}: run={a.get('run_id')} stage={a.get('stage')}")
                if result.get("retried"):
                    print(f"  Retried: {len(result['retried'])} tasks")
                    for a in result["retried"]:
                        print(f"    - {a.get('task_ref', a['task_id'])}: attempt {a['attempt']}/{a['max_retries']}")
                if result.get("blocked"):
                    print(f"  Blocked: {len(result['blocked'])} tasks")
                    for a in result["blocked"]:
                        print(f"    - Task {a['task_id']}: {a.get('reason', '')}")

            db.close()

        except KeyboardInterrupt:
            print("\nDirector daemon stopped.")
            break
        except Exception as e:
            import traceback
            print(f"Error in director daemon: {e}")
            traceback.print_exc()

        time.sleep(poll_interval)
