"""WorkCycle Service - Task-centric agent work sessions.

Simplified service for managing WorkCycles (formerly Handoffs).
Each WorkCycle represents one agent's work session on a task:
1. Agent picks up task → WorkCycle created (PENDING)
2. Agent starts work → WorkCycle becomes IN_PROGRESS
3. Agent finishes → WorkCycle moves to VALIDATING
4. Claims are tested → WorkCycle becomes COMPLETED or FAILED

No more Run-based orchestration. Tasks are the primary unit.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy.orm import Session

from app.models.task import Task, TaskStatus
from app.models.work_cycle import WorkCycle, WorkCycleStatus
from app.models.project import Project
from app.models.claim import Claim, ClaimTest


class WorkCycleService:
    """Service for managing WorkCycles."""

    def __init__(self, db: Session):
        self.db = db

    def start_task(
        self,
        task_id: int,
        agent_role: str = None,
        context: Dict = None,
        created_by: str = "system"
    ) -> Tuple[WorkCycle, Optional[str]]:
        """Start working on a task - creates a new WorkCycle.

        Args:
            task_id: Task to start working on
            agent_role: Which agent type is working (dev, qa, etc.)
            context: Optional context dict for the agent
            created_by: Who initiated this (system, human, agent)

        Returns:
            (WorkCycle, error) tuple
        """
        task = self.db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return None, f"Task {task_id} not found"

        # Check task is not already in progress
        if task.status == TaskStatus.IN_PROGRESS:
            # Check if there's an active work cycle
            active = self.db.query(WorkCycle).filter(
                WorkCycle.task_id == task_id,
                WorkCycle.status.in_([WorkCycleStatus.PENDING, WorkCycleStatus.IN_PROGRESS])
            ).first()
            if active:
                return active, None  # Return existing

        # Check task is not blocked
        if task.is_blocked(self.db):
            return None, f"Task {task.task_id} is blocked by dependencies"

        # Create work cycle
        work_cycle = WorkCycle(
            project_id=task.project_id,
            task_id=task_id,
            agent_role=agent_role,
            status=WorkCycleStatus.IN_PROGRESS,
            context=context,
            created_by=created_by,
            started_at=datetime.utcnow()
        )

        # Update task status
        task.status = TaskStatus.IN_PROGRESS

        self.db.add(work_cycle)
        self.db.commit()
        self.db.refresh(work_cycle)

        return work_cycle, None

    def complete_work(
        self,
        work_cycle_id: int,
        summary: str = None,
        artifacts: List[str] = None
    ) -> Tuple[WorkCycle, Optional[str]]:
        """Complete the work phase, move to validation.

        Args:
            work_cycle_id: WorkCycle to complete
            summary: Summary of what was done
            artifacts: List of file paths or outputs produced

        Returns:
            (WorkCycle, error) tuple
        """
        wc = self.db.query(WorkCycle).filter(WorkCycle.id == work_cycle_id).first()
        if not wc:
            return None, f"WorkCycle {work_cycle_id} not found"

        if wc.status != WorkCycleStatus.IN_PROGRESS:
            return None, f"WorkCycle is not in progress (status: {wc.status.value})"

        wc.status = WorkCycleStatus.VALIDATING
        wc.summary = summary
        wc.artifacts = artifacts or []

        # Update task status
        task = self.db.query(Task).filter(Task.id == wc.task_id).first()
        if task:
            task.status = TaskStatus.VALIDATING

        self.db.commit()
        self.db.refresh(wc)

        return wc, None

    def run_validation(
        self,
        work_cycle_id: int
    ) -> Tuple[WorkCycle, Optional[str]]:
        """Run claim tests for the work cycle.

        This runs all tests for claims attached to the task
        and records the results.

        Args:
            work_cycle_id: WorkCycle to validate

        Returns:
            (WorkCycle, error) tuple
        """
        wc = self.db.query(WorkCycle).filter(WorkCycle.id == work_cycle_id).first()
        if not wc:
            return None, f"WorkCycle {work_cycle_id} not found"

        if wc.status != WorkCycleStatus.VALIDATING:
            return None, f"WorkCycle is not in validating state (status: {wc.status.value})"

        task = self.db.query(Task).filter(Task.id == wc.task_id).first()
        if not task:
            return None, "Task not found"

        # Get claims for this task
        claims = self.db.query(Claim).filter(
            (Claim.task_id == wc.task_id) |
            ((Claim.project_id == wc.project_id) & (Claim.task_id.is_(None)))
        ).all()

        if not claims:
            # No claims to validate - auto-pass
            wc.status = WorkCycleStatus.COMPLETED
            wc.completed_at = datetime.utcnow()
            wc.claims_passed = 0
            wc.claims_failed = 0

            task.status = TaskStatus.DONE
            task.completed = True
            task.completed_at = datetime.utcnow()

            self.db.commit()
            self.db.refresh(wc)
            return wc, None

        # Run tests for each claim
        from app.services.claim_service import ClaimService
        claim_service = ClaimService(self.db)

        passed = 0
        failed = 0
        results = []

        for claim in claims:
            # Get tests for this claim
            tests = self.db.query(ClaimTest).filter(ClaimTest.claim_id == claim.id).all()

            for test in tests:
                evidence, error = claim_service.run_test(test.id)
                result = {
                    "claim_id": claim.id,
                    "claim_text": claim.claim_text,
                    "test_id": test.id,
                    "test_name": test.name,
                    "passed": evidence.supports_claim if evidence else False,
                    "error": error
                }
                results.append(result)

                if evidence and evidence.supports_claim:
                    passed += 1
                else:
                    failed += 1

        wc.claim_results = results
        wc.claims_passed = passed
        wc.claims_failed = failed
        wc.completed_at = datetime.utcnow()

        # Determine final status
        if failed > 0:
            wc.status = WorkCycleStatus.FAILED
            task.status = TaskStatus.FAILED
        else:
            wc.status = WorkCycleStatus.COMPLETED
            task.status = TaskStatus.DONE
            task.completed = True
            task.completed_at = datetime.utcnow()

        # Update task claim counts
        task.claims_total = len(claims)
        task.claims_validated = passed
        task.claims_failed = failed

        self.db.commit()
        self.db.refresh(wc)

        return wc, None

    def fail_work_cycle(
        self,
        work_cycle_id: int,
        reason: str = None
    ) -> Tuple[WorkCycle, Optional[str]]:
        """Mark a work cycle as failed.

        Args:
            work_cycle_id: WorkCycle to fail
            reason: Reason for failure

        Returns:
            (WorkCycle, error) tuple
        """
        wc = self.db.query(WorkCycle).filter(WorkCycle.id == work_cycle_id).first()
        if not wc:
            return None, f"WorkCycle {work_cycle_id} not found"

        wc.status = WorkCycleStatus.FAILED
        wc.completed_at = datetime.utcnow()
        wc.summary = reason or "Work cycle failed"

        # Update task
        task = self.db.query(Task).filter(Task.id == wc.task_id).first()
        if task:
            task.status = TaskStatus.FAILED

        self.db.commit()
        self.db.refresh(wc)

        return wc, None

    def get_work_cycle(self, work_cycle_id: int) -> Optional[WorkCycle]:
        """Get a work cycle by ID."""
        return self.db.query(WorkCycle).filter(WorkCycle.id == work_cycle_id).first()

    def get_task_work_cycles(self, task_id: int, limit: int = 20) -> List[WorkCycle]:
        """Get work cycles for a task, most recent first."""
        return self.db.query(WorkCycle).filter(
            WorkCycle.task_id == task_id
        ).order_by(WorkCycle.created_at.desc()).limit(limit).all()

    def get_active_work_cycle(self, task_id: int) -> Optional[WorkCycle]:
        """Get the currently active work cycle for a task."""
        return self.db.query(WorkCycle).filter(
            WorkCycle.task_id == task_id,
            WorkCycle.status.in_([
                WorkCycleStatus.PENDING,
                WorkCycleStatus.IN_PROGRESS,
                WorkCycleStatus.VALIDATING
            ])
        ).order_by(WorkCycle.created_at.desc()).first()

    def get_project_work_cycles(
        self,
        project_id: int,
        status: WorkCycleStatus = None,
        limit: int = 50
    ) -> List[WorkCycle]:
        """Get work cycles for a project."""
        query = self.db.query(WorkCycle).filter(WorkCycle.project_id == project_id)

        if status:
            query = query.filter(WorkCycle.status == status)

        return query.order_by(WorkCycle.created_at.desc()).limit(limit).all()
