"""JSON API views for Workflow Hub."""
import json
from datetime import date
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from app.db import get_db
from app.models import (
    Project, Requirement, Task, TaskStatus, Run, RunState,
    AgentReport, ThreatIntel, ThreatStatus, AuditEvent
)
from app.models.report import AgentRole, ReportStatus
from app.models.audit import log_event
from app.services.run_service import RunService


def _get_json_body(request):
    """Parse JSON body from request."""
    try:
        return json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return None


def api_status(request):
    """System status endpoint."""
    db = next(get_db())
    try:
        project_count = db.query(Project).count()
        run_count = db.query(Run).count()
        return JsonResponse({
            "status": "ok",
            "projects": project_count,
            "runs": run_count,
        })
    finally:
        db.close()


# --- Projects ---

def projects_list(request):
    """List all projects."""
    db = next(get_db())
    try:
        projects = db.query(Project).order_by(Project.created_at.desc()).all()
        return JsonResponse({"projects": [p.to_dict() for p in projects]})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def project_create(request):
    """Create a new project."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = data.get("name")
    if not name:
        return JsonResponse({"error": "name required"}, status=400)

    db = next(get_db())
    try:
        project = Project(
            name=name,
            description=data.get("description"),
            repo_path=data.get("repo_path"),
            stack_tags=data.get("stack_tags", [])
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        log_event(db, "human", "create", "project", project.id, {"name": name})
        return JsonResponse({"project": project.to_dict()}, status=201)
    finally:
        db.close()


def project_detail(request, project_id):
    """Get project details with requirements, tasks, and runs."""
    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return JsonResponse({"error": "Project not found"}, status=404)

        return JsonResponse({
            "project": project.to_dict(),
            "requirements": [r.to_dict() for r in project.requirements],
            "tasks": [t.to_dict() for t in project.tasks],
            "runs": [r.to_dict() for r in project.runs],
        })
    finally:
        db.close()


# --- Requirements ---

def requirements_list(request, project_id):
    """List requirements for a project."""
    db = next(get_db())
    try:
        reqs = db.query(Requirement).filter(Requirement.project_id == project_id).all()
        return JsonResponse({"requirements": [r.to_dict() for r in reqs]})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def requirement_create(request, project_id):
    """Create a requirement for a project."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    db = next(get_db())
    try:
        req = Requirement(
            project_id=project_id,
            req_id=data.get("req_id"),
            title=data.get("title"),
            description=data.get("description"),
            acceptance_criteria=data.get("acceptance_criteria")
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        log_event(db, "human", "create", "requirement", req.id, {"req_id": req.req_id})
        return JsonResponse({"requirement": req.to_dict()}, status=201)
    finally:
        db.close()


# --- Tasks ---

def tasks_list(request, project_id):
    """List tasks for a project."""
    db = next(get_db())
    try:
        tasks = db.query(Task).filter(Task.project_id == project_id).all()
        return JsonResponse({"tasks": [t.to_dict() for t in tasks]})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_create(request, project_id):
    """Create a task for a project."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    db = next(get_db())
    try:
        task = Task(
            project_id=project_id,
            task_id=data.get("task_id"),
            title=data.get("title"),
            description=data.get("description"),
            status=TaskStatus.BACKLOG
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        log_event(db, "human", "create", "task", task.id, {"task_id": task.task_id})
        return JsonResponse({"task": task.to_dict()}, status=201)
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_update_status(request, task_id):
    """Update task status."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    status_str = data.get("status")
    try:
        new_status = TaskStatus(status_str)
    except ValueError:
        return JsonResponse({"error": f"Invalid status: {status_str}"}, status=400)

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        old_status = task.status.value
        task.status = new_status
        db.commit()
        log_event(db, "human", "update_status", "task", task_id,
                 {"from": old_status, "to": new_status.value})
        return JsonResponse({"task": task.to_dict()})
    finally:
        db.close()


# --- Runs ---

def runs_list(request, project_id):
    """List runs for a project."""
    db = next(get_db())
    try:
        runs = db.query(Run).filter(Run.project_id == project_id).order_by(Run.created_at.desc()).all()
        return JsonResponse({"runs": [r.to_dict() for r in runs]})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def run_create(request, project_id):
    """Create a new run for a project."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = data.get("name")
    if not name:
        return JsonResponse({"error": "name required"}, status=400)

    db = next(get_db())
    try:
        service = RunService(db)
        run = service.create_run(project_id, name)
        return JsonResponse({"run": run.to_dict()}, status=201)
    finally:
        db.close()


def run_detail(request, run_id):
    """Get run details with reports."""
    db = next(get_db())
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JsonResponse({"error": "Run not found"}, status=404)

        reports = db.query(AgentReport).filter(AgentReport.run_id == run_id).all()
        return JsonResponse({
            "run": run.to_dict(),
            "reports": [r.to_dict() for r in reports],
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def run_submit_report(request, run_id):
    """Submit an agent report for a run."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    try:
        role = AgentRole(data.get("role"))
        status = ReportStatus(data.get("status"))
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    db = next(get_db())
    try:
        service = RunService(db)
        report, error = service.submit_report(
            run_id=run_id,
            role=role,
            status=status,
            summary=data.get("summary"),
            details=data.get("details"),
            actor=data.get("actor", role.value)
        )
        if error:
            return JsonResponse({"error": error}, status=400)
        return JsonResponse({"report": report.to_dict()}, status=201)
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def run_advance(request, run_id):
    """Advance run to next state."""
    data = _get_json_body(request) or {}
    actor = data.get("actor", "human")

    db = next(get_db())
    try:
        service = RunService(db)
        new_state, error = service.advance_state(run_id, actor)
        if error:
            return JsonResponse({"error": error, "state": new_state.value if new_state else None}, status=400)
        return JsonResponse({"state": new_state.value})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def run_retry(request, run_id):
    """Retry a failed run stage."""
    db = next(get_db())
    try:
        service = RunService(db)
        new_state, error = service.retry_from_failed(run_id)
        if error:
            return JsonResponse({"error": error}, status=400)
        return JsonResponse({"state": new_state.value})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def run_approve_deploy(request, run_id):
    """Human approval for deployment (R8)."""
    db = next(get_db())
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JsonResponse({"error": "Run not found"}, status=404)

        if run.state != RunState.READY_FOR_DEPLOY:
            return JsonResponse({"error": f"Run must be in READY_FOR_DEPLOY state, currently: {run.state.value}"}, status=400)

        service = RunService(db)
        new_state, error = service.advance_state(run_id, actor="human")
        if error:
            return JsonResponse({"error": error}, status=400)

        return JsonResponse({"state": new_state.value, "message": "Deployment approved"})
    finally:
        db.close()


# --- Threat Intel ---

def threat_intel_list(request):
    """List all threat intel entries."""
    db = next(get_db())
    try:
        entries = db.query(ThreatIntel).order_by(ThreatIntel.date_reported.desc()).all()
        return JsonResponse({"threat_intel": [e.to_dict() for e in entries]})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def threat_intel_create(request):
    """Create a threat intel entry."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    db = next(get_db())
    try:
        entry = ThreatIntel(
            date_reported=date.fromisoformat(data.get("date_reported", date.today().isoformat())),
            source=data.get("source"),
            summary=data.get("summary"),
            affected_tech=data.get("affected_tech"),
            action=data.get("action"),
            status=ThreatStatus.NEW
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        log_event(db, "security", "create", "threat_intel", entry.id, {"source": entry.source})
        return JsonResponse({"threat_intel": entry.to_dict()}, status=201)
    finally:
        db.close()


# --- Audit Log ---

def audit_log(request):
    """List recent audit events."""
    limit = int(request.GET.get("limit", 100))
    db = next(get_db())
    try:
        events = db.query(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(limit).all()
        return JsonResponse({"audit_events": [e.to_dict() for e in events]})
    finally:
        db.close()
