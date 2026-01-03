"""Tests for QA quality subtasks creation and gating."""
import json
import os

from app.models.task import Task, TaskStatus, TaskPipelineStage
from app.models.report import AgentReport, AgentRole, ReportStatus
from app.services.director_service import DirectorService


def _load_quality_requirements():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base_dir, "config", "qa_requirements.json")
    with open(path, "r") as f:
        return json.load(f)


def test_quality_subtasks_created_on_pm_to_dev(db_session, sample_project, sample_run):
    """Advancing from PM to DEV should create quality subtasks and block advancement."""
    task = Task(
        project_id=sample_project.id,
        task_id="T100",
        title="Parent Task",
        status=TaskStatus.IN_PROGRESS,
        pipeline_stage=TaskPipelineStage.PM
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    report = AgentReport(
        run_id=sample_run.id,
        role=AgentRole.PM,
        status=ReportStatus.PASS
    )

    director = DirectorService(db_session)
    success, message = director.advance_task(task, report)

    assert success is False
    assert "Subtasks created" in message

    requirements = _load_quality_requirements()
    subtasks = db_session.query(Task).filter(Task.parent_task_id == task.id).all()
    assert len(subtasks) == len(requirements)


def test_parent_cannot_complete_with_incomplete_subtasks(db_session, sample_project, sample_run):
    """Parent should not complete if subtasks are incomplete."""
    parent = Task(
        project_id=sample_project.id,
        task_id="T200",
        title="Parent Task",
        status=TaskStatus.IN_PROGRESS,
        pipeline_stage=TaskPipelineStage.DOCS
    )
    child = Task(
        project_id=sample_project.id,
        task_id="T201",
        title="Child Task",
        status=TaskStatus.BACKLOG,
        pipeline_stage=TaskPipelineStage.NONE,
        parent=parent
    )
    db_session.add_all([parent, child])
    db_session.commit()

    report = AgentReport(
        run_id=sample_run.id,
        role=AgentRole.DOCS,
        status=ReportStatus.PASS
    )

    director = DirectorService(db_session)
    success, message = director.advance_task(parent, report)

    assert success is False
    assert "incomplete subtasks" in message
