"""Tests for stale work_cycle cleanup API."""
import json
from django.test import Client

from app.models.task import Task, TaskStatus
from app.models.work_cycle import WorkCycle, WorkCycleStatus


def _client():
    return Client()


def test_cleanup_stale_work_cycles_marks_completed(db_session, sample_project):
    """Stale work_cycles for DONE tasks should be completed."""
    task = Task(
        project_id=sample_project.id,
        task_id="T900",
        title="Done Task",
        status=TaskStatus.DONE
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    work_cycle = WorkCycle(
        project_id=sample_project.id,
        task_id=task.id,
        to_role="dev",
        stage="dev",
        status=WorkCycleStatus.PENDING
    )
    db_session.add(work_cycle)
    db_session.commit()
    db_session.refresh(work_cycle)

    response = _client().post(
        "/api/work_cycles/cleanup-stale",
        data=json.dumps({}),
        content_type="application/json"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["updated_count"] == 1

    db_session.refresh(work_cycle)
    assert work_cycle.status == WorkCycleStatus.COMPLETED
    assert work_cycle.report_status == "pass"
    assert "stale" in (work_cycle.report_summary or "").lower()


def test_cleanup_stale_work_cycles_skips_active_tasks(db_session, sample_project):
    """Work_cycles for non-DONE tasks should not be updated."""
    task = Task(
        project_id=sample_project.id,
        task_id="T901",
        title="Active Task",
        status=TaskStatus.IN_PROGRESS
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    work_cycle = WorkCycle(
        project_id=sample_project.id,
        task_id=task.id,
        to_role="dev",
        stage="dev",
        status=WorkCycleStatus.PENDING
    )
    db_session.add(work_cycle)
    db_session.commit()

    response = _client().post(
        "/api/work_cycles/cleanup-stale",
        data=json.dumps({}),
        content_type="application/json"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["updated_count"] == 0

    db_session.refresh(work_cycle)
    assert work_cycle.status == WorkCycleStatus.PENDING


def test_delete_work_cycle_endpoint(db_session, sample_project):
    """Delete endpoint should remove a work_cycle."""
    task = Task(
        project_id=sample_project.id,
        task_id="T902",
        title="Task for delete",
        status=TaskStatus.IN_PROGRESS
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    work_cycle = WorkCycle(
        project_id=sample_project.id,
        task_id=task.id,
        to_role="dev",
        stage="dev",
        status=WorkCycleStatus.PENDING
    )
    db_session.add(work_cycle)
    db_session.commit()
    db_session.refresh(work_cycle)

    response = _client().post(f"/api/work_cycles/{work_cycle.id}/delete")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    deleted = db_session.query(WorkCycle).filter(WorkCycle.id == work_cycle.id).first()
    assert deleted is None
