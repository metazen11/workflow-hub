"""Run state machine and gate enforcement service."""
import os
import subprocess
from typing import Optional, Tuple, List
from app.models.run import Run, RunState, VALID_TRANSITIONS
from app.models.project import Project
from app.models.report import AgentReport, AgentRole, ReportStatus
from app.models.task import Task, TaskStatus, TaskPipelineStage
from app.models.audit import log_event
from app.services.webhook_service import (
    dispatch_webhook, EVENT_STATE_CHANGE, EVENT_REPORT_SUBMITTED,
    EVENT_RUN_CREATED, EVENT_GATE_FAILED, EVENT_READY_FOR_DEPLOY
)


class RunService:
    """Service for managing run state transitions and gate enforcement."""

    def __init__(self, db):
        self.db = db

    def create_run(self, project_id: int, name: str, actor: str = "human") -> Run:
        """Create a new run for a project.

        Automatically:
        - Initializes git repo in project workspace if not exists
        - Creates initial commit if repo is empty
        """
        # Get project to check/init git repo
        project = self.db.query(Project).filter(Project.id == project_id).first()

        # Auto-initialize git repo if project has repo_path
        git_info = {"initialized": False}
        if project and project.repo_path:
            git_info = self._ensure_git_repo(project.repo_path, project)

        run = Run(project_id=project_id, name=name, state=RunState.PM)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        log_event(
            self.db,
            actor=actor,
            action="create",
            entity_type="run",
            entity_id=run.id,
            details={
                "name": name,
                "initial_state": "pm",
                "git_initialized": git_info.get("initialized", False),
                "git_branch": git_info.get("branch"),
                "git_remote": git_info.get("remote_url")
            }
        )

        # Dispatch webhook - new run created, PM agent should start
        dispatch_webhook(EVENT_RUN_CREATED, {
            "run_id": run.id,
            "project_id": project_id,
            "name": name,
            "state": "pm",
            "next_agent": "pm",
            "git_info": git_info
        })

        return run

    def _ensure_git_repo(self, repo_path: str, project: Project = None) -> dict:
        """Ensure a git repository exists at the given path.

        Creates the directory and initializes git if needed.
        Extracts git info and updates project if provided.

        Returns dict with:
            - initialized: True if newly initialized, False if already existed
            - remote_url: Git remote URL if found
            - branch: Current branch name
            - error: Error message if any
        """
        result = {
            "initialized": False,
            "remote_url": None,
            "branch": None,
            "error": None
        }

        if not repo_path:
            return result

        try:
            # Create directory if it doesn't exist
            if not os.path.exists(repo_path):
                os.makedirs(repo_path, exist_ok=True)

            git_dir = os.path.join(repo_path, ".git")

            # Check if git repo already exists
            if os.path.exists(git_dir):
                # Repo exists - extract info
                result["initialized"] = False
                result = self._extract_git_info(repo_path, result)
            else:
                # Initialize new git repository
                subprocess.run(
                    ["git", "init"],
                    cwd=repo_path,
                    capture_output=True,
                    check=True
                )

                # Create .gitignore with common patterns
                gitignore_path = os.path.join(repo_path, ".gitignore")
                if not os.path.exists(gitignore_path):
                    with open(gitignore_path, "w") as f:
                        f.write("""# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
ENV/
.env
.env.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# Testing
.coverage
htmlcov/
.pytest_cache/
.tox/

# Build
dist/
build/
*.egg-info/

# OS
.DS_Store
Thumbs.db

# Secrets - NEVER commit these
*.pem
*.key
credentials.json
secrets.yaml
""")

                # Create initial commit
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=repo_path,
                    capture_output=True
                )
                subprocess.run(
                    ["git", "commit", "-m", "Initial commit - Project initialized by Workflow Hub"],
                    cwd=repo_path,
                    capture_output=True
                )

                result["initialized"] = True
                result = self._extract_git_info(repo_path, result)

            # Update project with git info if provided
            if project:
                self._update_project_git_info(project, result)

        except Exception as e:
            result["error"] = str(e)
            print(f"Git initialization warning: {e}")

        return result

    def _extract_git_info(self, repo_path: str, result: dict) -> dict:
        """Extract git information from an existing repository."""
        try:
            # Get current branch
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            if branch_result.returncode == 0:
                result["branch"] = branch_result.stdout.strip() or "main"

            # Get remote URL (origin)
            remote_result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            if remote_result.returncode == 0:
                result["remote_url"] = remote_result.stdout.strip()

        except Exception as e:
            print(f"Git info extraction warning: {e}")

        return result

    def _update_project_git_info(self, project: Project, git_info: dict):
        """Update project with extracted git information."""
        try:
            changed = False

            # Update branch if not already set
            if git_info.get("branch") and not project.primary_branch:
                project.primary_branch = git_info["branch"]
                changed = True

            # Update remote URL based on format
            remote_url = git_info.get("remote_url")
            if remote_url:
                if remote_url.startswith("git@"):
                    # SSH URL format: git@github.com:user/repo.git
                    if not project.repository_ssh_url:
                        project.repository_ssh_url = remote_url
                        project.git_auth_method = "ssh"
                        changed = True
                elif remote_url.startswith("http"):
                    # HTTPS URL format: https://github.com/user/repo.git
                    if not project.repository_url:
                        project.repository_url = remote_url
                        # Determine auth method - if URL has token, use https_token
                        if "@" in remote_url and "github.com" in remote_url:
                            project.git_auth_method = "https_token"
                        else:
                            project.git_auth_method = "https_basic"
                        changed = True

            if changed:
                self.db.commit()

        except Exception as e:
            print(f"Project git update warning: {e}")

    def submit_report(
        self,
        run_id: int,
        role: AgentRole,
        status: ReportStatus,
        summary: str = None,
        details: dict = None,
        actor: str = None,
        raw_output: str = None
    ) -> Tuple[AgentReport, Optional[str]]:
        """
        Submit an agent report for a run.
        Returns (report, error_message).
        """
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return None, "Run not found"

        # Create the report
        report = AgentReport(
            run_id=run_id,
            role=role,
            status=status,
            summary=summary,
            details=details,
            raw_output=raw_output
        )
        self.db.add(report)

        # Store result in run artifact
        result_data = {
            "status": status.value,
            "summary": summary,
            "details": details
        }

        if role == AgentRole.PM:
            run.pm_result = result_data
        elif role == AgentRole.DEV:
            run.dev_result = result_data
        elif role == AgentRole.QA:
            run.qa_result = result_data
        elif role == AgentRole.SECURITY:
            run.sec_result = result_data

        self.db.commit()
        self.db.refresh(report)

        log_event(
            self.db,
            actor=actor or role.value,
            action="submit_report",
            entity_type="run",
            entity_id=run_id,
            details={"role": role.value, "status": status.value}
        )

        # Dispatch webhook - report submitted
        dispatch_webhook(EVENT_REPORT_SUBMITTED, {
            "run_id": run_id,
            "role": role.value,
            "status": status.value,
            "summary": summary,
            "current_state": run.state.value
        })

        return report, None

    def advance_state(
        self,
        run_id: int,
        actor: str = "human"
    ) -> Tuple[Optional[RunState], Optional[str]]:
        """
        Attempt to advance the run to the next state.
        Enforces QA/Security gates.
        Returns (new_state, error_message).
        """
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return None, "Run not found"

        current_state = run.state
        next_state = self._get_next_state(run)

        if not next_state:
            return None, f"No valid transition from {current_state.value}"

        # Gate enforcement
        if current_state == RunState.QA:
            qa_report = self._get_latest_report(run_id, AgentRole.QA)
            if not qa_report:
                return None, "QA report required before advancing"
            if qa_report.status != ReportStatus.PASS:
                run.state = RunState.QA_FAILED
                self.db.commit()
                log_event(self.db, actor, "state_change", "run", run_id,
                         {"from": current_state.value, "to": "qa_failed", "reason": "QA failed"})
                dispatch_webhook(EVENT_GATE_FAILED, {
                    "run_id": run_id,
                    "gate": "qa",
                    "reason": "QA tests failed"
                })
                return RunState.QA_FAILED, "QA gate failed"

        if current_state == RunState.SEC:
            sec_report = self._get_latest_report(run_id, AgentRole.SECURITY)
            if not sec_report:
                return None, "Security report required before advancing"
            if sec_report.status != ReportStatus.PASS:
                run.state = RunState.SEC_FAILED
                self.db.commit()
                log_event(self.db, actor, "state_change", "run", run_id,
                         {"from": current_state.value, "to": "sec_failed", "reason": "Security failed"})
                dispatch_webhook(EVENT_GATE_FAILED, {
                    "run_id": run_id,
                    "gate": "security",
                    "reason": "Security check failed"
                })
                return RunState.SEC_FAILED, "Security gate failed"

        if current_state == RunState.DOCS:
            docs_report = self._get_latest_report(run_id, AgentRole.DOCS)
            if not docs_report:
                return None, "Documentation report required before advancing"
            if docs_report.status != ReportStatus.PASS:
                run.state = RunState.DOCS_FAILED
                self.db.commit()
                log_event(self.db, actor, "state_change", "run", run_id,
                         {"from": current_state.value, "to": "docs_failed", "reason": "Docs failed"})
                dispatch_webhook(EVENT_GATE_FAILED, {
                    "run_id": run_id,
                    "gate": "docs",
                    "reason": "Documentation check failed"
                })
                return RunState.DOCS_FAILED, "Documentation gate failed"

        # Human approval required for deploy
        if current_state == RunState.READY_FOR_DEPLOY and actor != "human":
            return None, "Human approval required for deployment"

        # Perform transition
        old_state = current_state.value
        run.state = next_state
        self.db.commit()

        log_event(self.db, actor, "state_change", "run", run_id,
                 {"from": old_state, "to": next_state.value})

        # Sync task pipeline stages with run state
        self._sync_task_stages_with_run(run, next_state)

        # Dispatch webhook - state changed
        next_agent = self._get_agent_for_state(next_state)
        dispatch_webhook(EVENT_STATE_CHANGE, {
            "run_id": run_id,
            "from_state": old_state,
            "to_state": next_state.value,
            "next_agent": next_agent
        })

        # Special webhook for ready_for_deploy (human approval needed)
        if next_state == RunState.READY_FOR_DEPLOY:
            dispatch_webhook(EVENT_READY_FOR_DEPLOY, {
                "run_id": run_id,
                "message": "Human approval required for deployment"
            })

        return next_state, None

    def set_state(
        self,
        run_id: int,
        new_state: str,
        actor: str = "human"
    ) -> Tuple[Optional[RunState], Optional[str]]:
        """
        Manually set run state (human override).
        Bypasses gate enforcement for admin/debugging purposes.
        Returns (new_state, error_message).
        """
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return None, "Run not found"

        # Parse state string to enum (accepts either case)
        state_upper = new_state.upper()
        state_lower = new_state.lower()
        target_state = None
        for s in RunState:
            if s.name == state_upper or s.value == state_lower:
                target_state = s
                break

        if not target_state:
            valid_states = [s.value for s in RunState]
            return None, f"Invalid state '{new_state}'. Valid: {valid_states}"

        old_state = run.state.value
        run.state = target_state
        self.db.commit()

        log_event(self.db, actor, "force_state_change", "run", run_id,
                 {"from": old_state, "to": target_state.value, "forced": True})

        dispatch_webhook(EVENT_STATE_CHANGE, {
            "run_id": run_id,
            "from_state": old_state,
            "to_state": target_state.value,
            "next_agent": self._get_agent_for_state(target_state),
            "forced": True
        })

        return target_state, None

    def retry_from_failed(self, run_id: int, actor: str = "human") -> Tuple[Optional[RunState], Optional[str]]:
        """Retry a failed QA or Security stage."""
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return None, "Run not found"

        if run.state == RunState.QA_FAILED:
            run.state = RunState.QA
            next_agent = "qa"
        elif run.state == RunState.SEC_FAILED:
            run.state = RunState.SEC
            next_agent = "security"
        else:
            return None, "Run is not in a failed state"

        self.db.commit()
        log_event(self.db, actor, "retry", "run", run_id, {"new_state": run.state.value})

        dispatch_webhook(EVENT_STATE_CHANGE, {
            "run_id": run_id,
            "from_state": "failed",
            "to_state": run.state.value,
            "next_agent": next_agent,
            "is_retry": True
        })

        return run.state, None

    def reset_to_dev(self, run_id: int, actor: str = "orchestrator", create_tasks: bool = True) -> Tuple[Optional[RunState], Optional[str]]:
        """Reset a failed run back to DEV stage for fixes.

        Args:
            run_id: The run to reset
            actor: Who is performing the action
            create_tasks: If True, create tasks from the failed report findings
        """
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return None, "Run not found"

        old_state = run.state.value
        allowed_states = {RunState.QA_FAILED, RunState.SEC_FAILED, RunState.QA, RunState.SEC}

        if run.state not in allowed_states:
            return None, f"Cannot reset to DEV from state: {old_state}"

        # Create tasks from findings before resetting
        tasks_created = []
        if create_tasks:
            if run.state in (RunState.QA_FAILED, RunState.QA):
                tasks_created = self.create_tasks_from_findings(run_id, AgentRole.QA)
            elif run.state in (RunState.SEC_FAILED, RunState.SEC):
                tasks_created = self.create_tasks_from_findings(run_id, AgentRole.SECURITY)

        run.state = RunState.DEV
        self.db.commit()

        log_event(self.db, actor, "reset_to_dev", "run", run_id,
                 {"from_state": old_state, "to_state": "dev", "tasks_created": len(tasks_created)})

        dispatch_webhook(EVENT_STATE_CHANGE, {
            "run_id": run_id,
            "from_state": old_state,
            "to_state": "dev",
            "next_agent": "dev",
            "is_loopback": True,
            "tasks_created": [t.task_id for t in tasks_created]
        })

        return RunState.DEV, None

    def create_tasks_from_findings(
        self,
        run_id: int,
        role: AgentRole,
        actor: str = "orchestrator"
    ) -> List[Task]:
        """Create tasks from QA/Security findings in the latest report.

        Parses the report details and creates a task for each finding.
        Returns list of created tasks.
        """
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return []

        report = self._get_latest_report(run_id, role)
        if not report or not report.details:
            return []

        details = report.details
        findings = []

        # Parse findings based on role and report structure
        if role == AgentRole.QA:
            # QA findings: look for failing_tests, issues, errors
            findings.extend(self._extract_qa_findings(details))
        elif role == AgentRole.SECURITY:
            # Security findings: look for vulnerabilities, issues, findings
            findings.extend(self._extract_security_findings(details))

        # Get existing task count for numbering
        existing_count = self.db.query(Task).filter(Task.project_id == run.project_id).count()

        created_tasks = []
        for i, finding in enumerate(findings):
            task_num = existing_count + i + 1
            task_id = f"T{task_num:03d}"

            # Check if similar task already exists (avoid duplicates)
            existing = self.db.query(Task).filter(
                Task.project_id == run.project_id,
                Task.title == finding["title"]
            ).first()

            if existing:
                # Update existing task if not completed
                if existing.status != TaskStatus.DONE:
                    existing.priority = max(existing.priority or 5, finding.get("priority", 5))
                    existing.run_id = run_id
                continue

            task = Task(
                project_id=run.project_id,
                task_id=task_id,
                title=finding["title"],
                description=finding.get("description", ""),
                status=TaskStatus.IN_PROGRESS,  # Ready for DEV work
                priority=finding.get("priority", 5),
                run_id=run_id,
                pipeline_stage=TaskPipelineStage.DEV,  # Start in DEV stage
                acceptance_criteria=finding.get("acceptance_criteria", [])
            )
            self.db.add(task)
            created_tasks.append(task)

            log_event(self.db, actor, "create_task_from_finding", "task", None,
                     {"task_id": task_id, "source": role.value, "run_id": run_id})

        self.db.commit()

        # Refresh to get IDs
        for task in created_tasks:
            self.db.refresh(task)

        return created_tasks

    def _extract_qa_findings(self, details: dict) -> List[dict]:
        """Extract findings from QA report details."""
        findings = []

        # Handle failing_tests array
        failing_tests = details.get("failing_tests", [])
        for test in failing_tests:
            if isinstance(test, str):
                findings.append({
                    "title": f"Fix failing test: {test}",
                    "description": f"Test '{test}' is failing and needs to be fixed.",
                    "priority": 8,
                    "acceptance_criteria": [f"Test {test} passes"]
                })
            elif isinstance(test, dict):
                findings.append({
                    "title": f"Fix failing test: {test.get('name', 'unknown')}",
                    "description": test.get("error", test.get("message", "")),
                    "priority": test.get("priority", 8),
                    "acceptance_criteria": [f"Test {test.get('name', '')} passes"]
                })

        # Handle issues/errors arrays
        for key in ["issues", "errors", "failures"]:
            items = details.get(key, [])
            for item in items:
                if isinstance(item, str):
                    findings.append({
                        "title": f"Fix: {item[:100]}",
                        "description": item,
                        "priority": 7
                    })
                elif isinstance(item, dict):
                    findings.append({
                        "title": item.get("title", item.get("name", f"Fix {key} issue")),
                        "description": item.get("description", item.get("message", "")),
                        "priority": item.get("priority", 7)
                    })

        return findings

    def _extract_security_findings(self, details: dict) -> List[dict]:
        """Extract findings from Security report details."""
        findings = []

        # Priority mapping for security severity
        severity_priority = {
            "critical": 10,
            "high": 9,
            "medium": 7,
            "low": 5,
            "info": 3
        }

        # Handle various security report formats
        for key in ["vulnerabilities", "issues", "findings", "security_issues", "vulnerabilities_found"]:
            items = details.get(key, [])
            for item in items:
                if isinstance(item, str):
                    findings.append({
                        "title": f"Security: {item[:100]}",
                        "description": item,
                        "priority": 8
                    })
                elif isinstance(item, dict):
                    severity = item.get("severity", "medium").lower()
                    priority = severity_priority.get(severity, 7)

                    # Build title from available fields
                    title = item.get("title", item.get("name", item.get("issue", item.get("type", "Security issue"))))
                    if severity in ("critical", "high"):
                        title = f"[{severity.upper()}] {title}"

                    # Build description from issue details
                    desc_parts = []
                    if item.get("issue"):
                        desc_parts.append(f"Issue: {item['issue']}")
                    if item.get("file"):
                        desc_parts.append(f"File: {item['file']}:{item.get('line', '?')}")
                    if item.get("recommendation"):
                        desc_parts.append(f"Fix: {item['recommendation']}")
                    description = item.get("description", item.get("message", "\n".join(desc_parts) if desc_parts else ""))

                    findings.append({
                        "title": title,
                        "description": description,
                        "priority": priority,
                        "acceptance_criteria": [
                            item.get("recommendation", item.get("remediation", item.get("fix", f"Address {severity} security issue")))
                        ]
                    })

        return findings

    def _get_next_state(self, run: Run) -> Optional[RunState]:
        """Get the next valid state (primary path, not failed states)."""
        transitions = VALID_TRANSITIONS.get(run.state, [])
        for state in transitions:
            if "FAILED" not in state.value.upper():
                return state
        return None

    def _get_latest_report(self, run_id: int, role: AgentRole) -> Optional[AgentReport]:
        """Get the most recent report for a role."""
        return (
            self.db.query(AgentReport)
            .filter(AgentReport.run_id == run_id, AgentReport.role == role)
            .order_by(AgentReport.created_at.desc())
            .first()
        )

    def _get_agent_for_state(self, state: RunState) -> Optional[str]:
        """Get the agent responsible for a state."""
        agent_map = {
            RunState.PM: "pm",
            RunState.DEV: "dev",
            RunState.QA: "qa",
            RunState.SEC: "security",
            RunState.DOCS: "docs",
        }
        return agent_map.get(state)

    def _initialize_task_stages(self, run: Run, stage: TaskPipelineStage) -> int:
        """Initialize all run tasks to a pipeline stage.

        Sets tasks that are at NONE stage to the specified stage.
        Returns count of tasks updated.
        """
        tasks = self.db.query(Task).filter(
            Task.run_id == run.id,
            Task.pipeline_stage == TaskPipelineStage.NONE
        ).all()

        for task in tasks:
            task.pipeline_stage = stage
            task.status = TaskStatus.IN_PROGRESS

        self.db.commit()
        return len(tasks)

    def _sync_task_stages_with_run(self, run: Run, run_state: RunState) -> int:
        """Sync task pipeline stages when run state changes.

        Maps run states to task pipeline stages and advances tasks accordingly:
        - DEV run state → DEV task stage (initialize)
        - QA run state → QA task stage
        - SEC run state → SEC task stage
        - DOCS run state → DOCS task stage
        - DEPLOYED run state → COMPLETE task stage

        Only advances tasks that are behind the target stage.
        Returns count of tasks updated.
        """
        # Map run state to target task stage
        state_to_stage = {
            RunState.PM: None,  # No task stage for PM
            RunState.DEV: TaskPipelineStage.DEV,
            RunState.QA: TaskPipelineStage.QA,
            RunState.SEC: TaskPipelineStage.SEC,
            RunState.DOCS: TaskPipelineStage.DOCS,
            RunState.READY_FOR_COMMIT: TaskPipelineStage.DOCS,
            RunState.MERGED: TaskPipelineStage.DOCS,
            RunState.READY_FOR_DEPLOY: TaskPipelineStage.DOCS,
            RunState.TESTING: TaskPipelineStage.DOCS,
            RunState.DEPLOYED: TaskPipelineStage.COMPLETE,
        }

        target_stage = state_to_stage.get(run_state)
        if not target_stage:
            return 0  # No task stage update for this run state

        # Stage ordering for comparison
        stage_order = [
            TaskPipelineStage.NONE,
            TaskPipelineStage.DEV,
            TaskPipelineStage.QA,
            TaskPipelineStage.SEC,
            TaskPipelineStage.DOCS,
            TaskPipelineStage.COMPLETE
        ]
        target_index = stage_order.index(target_stage)

        # Get all tasks linked to this run
        tasks = self.db.query(Task).filter(Task.run_id == run.id).all()

        updated = 0
        for task in tasks:
            current_stage = task.pipeline_stage or TaskPipelineStage.NONE
            current_index = stage_order.index(current_stage)

            # Only advance if behind target
            if current_index < target_index:
                task.pipeline_stage = target_stage

                # Update task status
                if target_stage == TaskPipelineStage.COMPLETE:
                    task.status = TaskStatus.DONE
                    task.completed = True
                    task.completed_at = datetime.utcnow()
                else:
                    task.status = TaskStatus.IN_PROGRESS

                updated += 1

        if updated > 0:
            self.db.commit()

        return updated

    def get_task_progress(self, run_id: int) -> dict:
        """Get task pipeline progress summary for a run.

        Returns dict with:
            - total_tasks: Total number of tasks
            - stage_counts: Count per pipeline stage
            - completed: Number of completed tasks
            - progress_percent: Overall completion percentage
            - ready_to_advance: True if all tasks passed current stage
        """
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return {"error": "Run not found"}

        tasks = self.db.query(Task).filter(Task.run_id == run_id).all()

        # Count by stage
        stage_counts = {stage.value: 0 for stage in TaskPipelineStage}
        for task in tasks:
            stage = task.pipeline_stage or TaskPipelineStage.NONE
            stage_counts[stage.value] += 1

        total = len(tasks)
        completed = stage_counts.get("complete", 0)
        progress_pct = (completed / total * 100) if total > 0 else 0

        # Check if ready to advance based on current run state
        ready_to_advance = self._check_tasks_ready_for_advance(run, tasks)

        return {
            "run_id": run_id,
            "total_tasks": total,
            "stage_counts": stage_counts,
            "completed": completed,
            "progress_percent": round(progress_pct, 1),
            "ready_to_advance": ready_to_advance
        }

    def _check_tasks_ready_for_advance(self, run: Run, tasks: list) -> bool:
        """Check if all tasks have completed the current run stage.

        For run at DEV: All tasks should be at QA or beyond
        For run at QA: All tasks should be at SEC or beyond
        For run at SEC: All tasks should be at DOCS or beyond
        """
        if not tasks:
            return True  # No tasks = no blockers

        # Map run state to minimum required task stage
        run_to_min_stage = {
            RunState.DEV: TaskPipelineStage.QA,
            RunState.QA: TaskPipelineStage.SEC,
            RunState.SEC: TaskPipelineStage.DOCS,
            RunState.DOCS: TaskPipelineStage.COMPLETE,
        }

        min_stage = run_to_min_stage.get(run.state)
        if not min_stage:
            return True  # Other states don't need task checks

        # Stage ordering for comparison
        stage_order = [
            TaskPipelineStage.NONE,
            TaskPipelineStage.DEV,
            TaskPipelineStage.QA,
            TaskPipelineStage.SEC,
            TaskPipelineStage.DOCS,
            TaskPipelineStage.COMPLETE
        ]
        min_index = stage_order.index(min_stage)

        for task in tasks:
            task_stage = task.pipeline_stage or TaskPipelineStage.NONE
            if stage_order.index(task_stage) < min_index:
                return False  # Task hasn't reached minimum stage

        return True
