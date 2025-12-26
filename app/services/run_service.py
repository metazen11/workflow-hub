"""Run state machine and gate enforcement service."""
from typing import Optional, Tuple, List
from app.models.run import Run, RunState, VALID_TRANSITIONS
from app.models.report import AgentReport, AgentRole, ReportStatus
from app.models.task import Task, TaskStatus
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
        """Create a new run for a project."""
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
            details={"name": name, "initial_state": "pm"}
        )

        # Dispatch webhook - new run created, PM agent should start
        dispatch_webhook(EVENT_RUN_CREATED, {
            "run_id": run.id,
            "project_id": project_id,
            "name": name,
            "state": "pm",
            "next_agent": "pm"
        })

        return run

    def submit_report(
        self,
        run_id: int,
        role: AgentRole,
        status: ReportStatus,
        summary: str = None,
        details: dict = None,
        actor: str = None
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
            details=details
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

        # Human approval required for deploy
        if current_state == RunState.READY_FOR_DEPLOY and actor != "human":
            return None, "Human approval required for deployment"

        # Perform transition
        old_state = current_state.value
        run.state = next_state
        self.db.commit()

        log_event(self.db, actor, "state_change", "run", run_id,
                 {"from": old_state, "to": next_state.value})

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
                status=TaskStatus.BACKLOG,
                priority=finding.get("priority", 5),
                run_id=run_id,
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

                    title = item.get("title", item.get("name", item.get("type", "Security issue")))
                    if severity in ("critical", "high"):
                        title = f"[{severity.upper()}] {title}"

                    findings.append({
                        "title": title,
                        "description": item.get("description", item.get("message", item.get("details", ""))),
                        "priority": priority,
                        "acceptance_criteria": [
                            item.get("remediation", item.get("fix", f"Address {severity} security issue"))
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
        }
        return agent_map.get(state)
