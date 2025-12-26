"""JSON API views for Workflow Hub."""
import json
import os
import hashlib
from datetime import date, datetime
from django.http import JsonResponse, FileResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

from app.db import get_db
from app.models import (
    Project, Requirement, Task, TaskStatus, Run, RunState,
    AgentReport, ThreatIntel, ThreatStatus, AuditEvent, Webhook,
    BugReport, BugReportStatus, TaskAttachment, AttachmentType,
    validate_file_security, AttachmentSecurityError,
    Credential, CredentialType, Environment, EnvironmentType
)
from app.models.report import AgentRole, ReportStatus
from app.models.audit import log_event
from app.services.run_service import RunService

# Upload directory
UPLOAD_DIR = os.path.join(settings.BASE_DIR, 'uploads', 'attachments')


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


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
def project_update(request, project_id):
    """Update project details."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return JsonResponse({"error": "Project not found"}, status=404)

        # Update allowed fields
        if "name" in data:
            project.name = data["name"]
        if "description" in data:
            project.description = data["description"]
        if "repo_path" in data:
            project.repo_path = data["repo_path"]
        if "stack_tags" in data:
            project.stack_tags = data["stack_tags"]

        db.commit()
        db.refresh(project)
        log_event(db, "human", "update", "project", project.id, {"updated_fields": list(data.keys())})
        return JsonResponse({"project": project.to_dict()})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def project_execute(request, project_id):
    """
    Execute all pending tasks in a project through the agent pipeline.
    Creates a run and triggers the orchestrator.
    """
    import subprocess
    import threading

    data = _get_json_body(request) or {}
    max_iterations = data.get("max_iterations", 10)

    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return JsonResponse({"error": "Project not found"}, status=404)

        if not project.repo_path:
            return JsonResponse({"error": "Project has no repo_path configured"}, status=400)

        # Create a new run for this project
        service = RunService(db)
        run = service.create_run(project_id, f"Execute Project: {project.name}")

        # Trigger pipeline in background thread
        def run_pipeline():
            try:
                subprocess.run(
                    ["python3", "scripts/agent_runner.py", "pipeline",
                     "--run-id", str(run.id),
                     "--project-path", project.repo_path,
                     "--max-iterations", str(max_iterations)],
                    cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    timeout=1800  # 30 min timeout
                )
            except Exception as e:
                print(f"Pipeline error: {e}")

        thread = threading.Thread(target=run_pipeline, daemon=True)
        thread.start()

        return JsonResponse({
            "message": f"Pipeline started for project {project.name}",
            "run_id": run.id,
            "state": run.state.value
        }, status=202)
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
        return JsonResponse({"success": True, "task": task.to_dict()})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_execute(request, task_id):
    """
    Execute a specific task through the agent pipeline.
    Creates a run linked to this task and triggers the orchestrator.
    """
    import subprocess
    import threading

    data = _get_json_body(request) or {}
    max_iterations = data.get("max_iterations", 10)

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        project = task.project
        if not project.repo_path:
            return JsonResponse({"error": "Project has no repo_path configured"}, status=400)

        # Create a run for this specific task
        service = RunService(db)
        run = service.create_run(project.id, f"Execute Task: {task.task_id} - {task.title}")

        # Link the task to this run
        task.run_id = run.id
        task.status = TaskStatus.IN_PROGRESS
        db.commit()

        # Trigger pipeline in background thread
        def run_pipeline():
            try:
                subprocess.run(
                    ["python3", "scripts/agent_runner.py", "pipeline",
                     "--run-id", str(run.id),
                     "--project-path", project.repo_path,
                     "--max-iterations", str(max_iterations)],
                    cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    timeout=1800  # 30 min timeout
                )
            except Exception as e:
                print(f"Pipeline error: {e}")

        thread = threading.Thread(target=run_pipeline, daemon=True)
        thread.start()

        log_event(db, "human", "execute", "task", task_id, {"run_id": run.id})

        return JsonResponse({
            "message": f"Pipeline started for task {task.task_id}",
            "task": task.to_dict(),
            "run_id": run.id,
            "state": run.state.value
        }, status=202)
    finally:
        db.close()


@csrf_exempt
def task_attachment_upload(request, task_id):
    """Upload a file attachment to a task."""
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({"error": "No file provided"}, status=400)

    uploaded_file = request.FILES['file']
    file_content = uploaded_file.read()

    # Security validation
    try:
        mime_type = validate_file_security(file_content, uploaded_file.name)
    except AttachmentSecurityError as e:
        return JsonResponse({"error": str(e)}, status=400)

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        # Determine attachment type
        if mime_type.startswith('image/'):
            att_type = AttachmentType.IMAGE
        else:
            att_type = AttachmentType.TEXT

        # Generate secure filename
        file_hash = hashlib.sha256(file_content).hexdigest()
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        secure_filename = f"{task_id}_{file_hash[:16]}{ext}"

        # Ensure upload directory exists
        os.makedirs(UPLOAD_DIR, exist_ok=True)

        # Save file
        file_path = os.path.join(UPLOAD_DIR, secure_filename)
        with open(file_path, 'wb') as f:
            f.write(file_content)

        # Create attachment record
        attachment = TaskAttachment(
            task_id=task_id,
            filename=uploaded_file.name,
            file_path=file_path,
            mime_type=mime_type,
            file_size=len(file_content),
            checksum=file_hash,
            attachment_type=att_type,
            uploaded_at=datetime.utcnow()
        )
        db.add(attachment)
        db.commit()
        db.refresh(attachment)

        log_event(db, "human", "upload_attachment", "task", task_id,
                 {"filename": uploaded_file.name, "size": len(file_content)})

        return JsonResponse({"success": True, "attachment": attachment.to_dict()})
    except Exception as e:
        db.rollback()
        return JsonResponse({"error": str(e)}, status=500)
    finally:
        db.close()


def task_attachment_download(request, task_id, attachment_id):
    """Download a task attachment."""
    db = next(get_db())
    try:
        attachment = db.query(TaskAttachment).filter(
            TaskAttachment.id == attachment_id,
            TaskAttachment.task_id == task_id
        ).first()

        if not attachment:
            return JsonResponse({"error": "Attachment not found"}, status=404)

        if not os.path.exists(attachment.file_path):
            return JsonResponse({"error": "File not found on disk"}, status=404)

        response = FileResponse(
            open(attachment.file_path, 'rb'),
            content_type=attachment.mime_type
        )
        response['Content-Disposition'] = f'inline; filename="{attachment.filename}"'
        return response
    finally:
        db.close()


def task_attachments_list(request, task_id):
    """List all attachments for a task."""
    db = next(get_db())
    try:
        attachments = db.query(TaskAttachment).filter(
            TaskAttachment.task_id == task_id
        ).order_by(TaskAttachment.uploaded_at.desc()).all()

        return JsonResponse({
            "attachments": [a.to_dict() for a in attachments]
        })
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
def run_reset_to_dev(request, run_id):
    """Reset a failed run back to DEV stage for fixes."""
    db = next(get_db())
    try:
        data = json.loads(request.body) if request.body else {}
        actor = data.get("actor", "orchestrator")

        service = RunService(db)
        new_state, error = service.reset_to_dev(run_id, actor)
        if error:
            return JsonResponse({"error": error}, status=400)
        return JsonResponse({"state": new_state.value, "message": "Reset to DEV for fixes"})
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


# --- Credentials ---

def credentials_list(request, project_id):
    """List credentials for a project."""
    db = next(get_db())
    try:
        credentials = db.query(Credential).filter(Credential.project_id == project_id).all()
        return JsonResponse({"credentials": [c.to_dict() for c in credentials]})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def credential_create(request, project_id):
    """Create a credential for a project."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    db = next(get_db())
    try:
        cred_type = data.get("credential_type", "api_key")
        try:
            cred_type_enum = CredentialType(cred_type)
        except ValueError:
            cred_type_enum = CredentialType.OTHER

        credential = Credential(
            project_id=project_id,
            name=data.get("name"),
            credential_type=cred_type_enum,
            service=data.get("service"),
            description=data.get("description"),
            username=data.get("username"),
            password_encrypted=data.get("password"),  # TODO: Encrypt
            api_key_encrypted=data.get("api_key"),  # TODO: Encrypt
            token_encrypted=data.get("token"),  # TODO: Encrypt
            ssh_key_path=data.get("ssh_key_path"),
            ssh_key_encrypted=data.get("ssh_key"),  # TODO: Encrypt
            database_url_encrypted=data.get("database_url"),  # TODO: Encrypt
            environment=data.get("environment"),
        )
        db.add(credential)
        db.commit()
        db.refresh(credential)
        log_event(db, "human", "create", "credential", credential.id, {"name": credential.name})
        return JsonResponse({"credential": credential.to_dict()}, status=201)
    finally:
        db.close()


def credential_detail(request, credential_id):
    """Get credential details."""
    db = next(get_db())
    try:
        credential = db.query(Credential).filter(Credential.id == credential_id).first()
        if not credential:
            return JsonResponse({"error": "Credential not found"}, status=404)
        return JsonResponse({"credential": credential.to_dict()})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
def credential_update(request, credential_id):
    """Update a credential."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    db = next(get_db())
    try:
        credential = db.query(Credential).filter(Credential.id == credential_id).first()
        if not credential:
            return JsonResponse({"error": "Credential not found"}, status=404)

        # Update allowed fields
        for field in ["name", "service", "description", "username", "environment", "ssh_key_path"]:
            if field in data:
                setattr(credential, field, data[field])

        # Update encrypted fields (TODO: Encrypt before storing)
        for field in ["password", "api_key", "token", "ssh_key", "database_url"]:
            if field in data:
                setattr(credential, f"{field}_encrypted", data[field])

        if "credential_type" in data:
            try:
                credential.credential_type = CredentialType(data["credential_type"])
            except ValueError:
                pass

        db.commit()
        db.refresh(credential)
        log_event(db, "human", "update", "credential", credential.id, {"updated_fields": list(data.keys())})
        return JsonResponse({"credential": credential.to_dict()})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["DELETE"])
def credential_delete(request, credential_id):
    """Delete a credential."""
    db = next(get_db())
    try:
        credential = db.query(Credential).filter(Credential.id == credential_id).first()
        if not credential:
            return JsonResponse({"error": "Credential not found"}, status=404)

        db.delete(credential)
        db.commit()
        log_event(db, "human", "delete", "credential", credential_id, {})
        return JsonResponse({"success": True})
    finally:
        db.close()


# --- Environments ---

def environments_list(request, project_id):
    """List environments for a project."""
    db = next(get_db())
    try:
        environments = db.query(Environment).filter(Environment.project_id == project_id).all()
        return JsonResponse({"environments": [e.to_dict() for e in environments]})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def environment_create(request, project_id):
    """Create an environment for a project."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    db = next(get_db())
    try:
        env_type = data.get("env_type", "development")
        try:
            env_type_enum = EnvironmentType(env_type)
        except ValueError:
            env_type_enum = EnvironmentType.OTHER

        environment = Environment(
            project_id=project_id,
            name=data.get("name"),
            env_type=env_type_enum,
            description=data.get("description"),
            url=data.get("url"),
            ip_address=data.get("ip_address"),
            port=data.get("port"),
            path=data.get("path"),
            ssh_host=data.get("ssh_host"),
            ssh_port=data.get("ssh_port", 22),
            ssh_user=data.get("ssh_user"),
            ssh_key_path=data.get("ssh_key_path"),
            login_required=data.get("login_required", False),
            login_url=data.get("login_url"),
            auth_type=data.get("auth_type"),
            database_host=data.get("database_host"),
            database_port=data.get("database_port"),
            database_name=data.get("database_name"),
            deploy_command=data.get("deploy_command"),
            health_check_url=data.get("health_check_url"),
        )
        db.add(environment)
        db.commit()
        db.refresh(environment)
        log_event(db, "human", "create", "environment", environment.id, {"name": environment.name})
        return JsonResponse({"environment": environment.to_dict()}, status=201)
    finally:
        db.close()


def environment_detail(request, environment_id):
    """Get environment details."""
    db = next(get_db())
    try:
        environment = db.query(Environment).filter(Environment.id == environment_id).first()
        if not environment:
            return JsonResponse({"error": "Environment not found"}, status=404)
        return JsonResponse({"environment": environment.to_dict()})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
def environment_update(request, environment_id):
    """Update an environment."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    db = next(get_db())
    try:
        environment = db.query(Environment).filter(Environment.id == environment_id).first()
        if not environment:
            return JsonResponse({"error": "Environment not found"}, status=404)

        # Update allowed fields
        for field in ["name", "description", "url", "ip_address", "port", "path",
                      "ssh_host", "ssh_port", "ssh_user", "ssh_key_path",
                      "login_required", "login_url", "auth_type",
                      "database_host", "database_port", "database_name",
                      "deploy_command", "health_check_url", "is_active"]:
            if field in data:
                setattr(environment, field, data[field])

        if "env_type" in data:
            try:
                environment.env_type = EnvironmentType(data["env_type"])
            except ValueError:
                pass

        db.commit()
        db.refresh(environment)
        log_event(db, "human", "update", "environment", environment.id, {"updated_fields": list(data.keys())})
        return JsonResponse({"environment": environment.to_dict()})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["DELETE"])
def environment_delete(request, environment_id):
    """Delete an environment."""
    db = next(get_db())
    try:
        environment = db.query(Environment).filter(Environment.id == environment_id).first()
        if not environment:
            return JsonResponse({"error": "Environment not found"}, status=404)

        db.delete(environment)
        db.commit()
        log_event(db, "human", "delete", "environment", environment_id, {})
        return JsonResponse({"success": True})
    finally:
        db.close()


# --- Orchestrator Context ---

def orchestrator_context(request, project_id):
    """
    Get full project context for orchestrator/agents.
    Includes project details, tasks, environments, and credentials (masked).
    """
    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return JsonResponse({"error": "Project not found"}, status=404)

        # Get all related data
        tasks = db.query(Task).filter(Task.project_id == project_id).all()
        environments = db.query(Environment).filter(Environment.project_id == project_id).all()
        credentials = db.query(Credential).filter(Credential.project_id == project_id).all()
        requirements = db.query(Requirement).filter(Requirement.project_id == project_id).all()

        return JsonResponse({
            "project": project.to_dict(include_children=True),
            "tasks": [t.to_dict() for t in tasks],
            "environments": [e.to_dict() for e in environments],
            "credentials": [c.to_dict() for c in credentials],  # Masked by default
            "requirements": [r.to_dict() for r in requirements],
        })
    finally:
        db.close()


def task_context(request, task_id):
    """
    Get full task context for orchestrator/agents.
    Includes task details with project and acceptance criteria.
    """
    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        project = task.project

        return JsonResponse({
            "task": task.to_dict(),
            "project": project.to_dict() if project else None,
            "requirements": [r.to_dict() for r in task.requirements],
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def project_refresh(request, project_id):
    """
    Refresh project information by scanning the repository.
    Detects tech stack, key files, etc.
    """
    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return JsonResponse({"error": "Project not found"}, status=404)

        if not project.repo_path or not os.path.exists(project.repo_path):
            return JsonResponse({"error": "Project repo_path not set or doesn't exist"}, status=400)

        # Scan repository for tech stack info
        repo_path = project.repo_path
        detected = {"languages": [], "frameworks": [], "key_files": [], "config_files": []}

        # Check for Python
        if os.path.exists(os.path.join(repo_path, "requirements.txt")):
            detected["languages"].append("Python")
            detected["key_files"].append("requirements.txt")
        if os.path.exists(os.path.join(repo_path, "setup.py")):
            detected["key_files"].append("setup.py")
        if os.path.exists(os.path.join(repo_path, "pyproject.toml")):
            detected["key_files"].append("pyproject.toml")

        # Check for Node.js
        if os.path.exists(os.path.join(repo_path, "package.json")):
            detected["languages"].append("JavaScript")
            detected["key_files"].append("package.json")

        # Check for common frameworks
        if os.path.exists(os.path.join(repo_path, "app.py")):
            detected["frameworks"].append("Flask")
            detected["key_files"].append("app.py")
            if not project.entry_point:
                project.entry_point = "app.py"

        if os.path.exists(os.path.join(repo_path, "manage.py")):
            detected["frameworks"].append("Django")
            detected["key_files"].append("manage.py")

        # Check for config files
        for config in [".env", ".env.example", "config.yaml", "config.json", "settings.py"]:
            if os.path.exists(os.path.join(repo_path, config)):
                detected["config_files"].append(config)

        # Update project
        if detected["languages"]:
            project.languages = list(set((project.languages or []) + detected["languages"]))
        if detected["frameworks"]:
            project.frameworks = list(set((project.frameworks or []) + detected["frameworks"]))
        if detected["key_files"]:
            project.key_files = list(set((project.key_files or []) + detected["key_files"]))
        if detected["config_files"]:
            project.config_files = list(set((project.config_files or []) + detected["config_files"]))

        db.commit()
        db.refresh(project)

        log_event(db, "system", "refresh", "project", project.id, {"detected": detected})

        return JsonResponse({
            "project": project.to_dict(),
            "detected": detected
        })
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


# --- Webhooks ---

def webhooks_list(request):
    """List all webhook configurations."""
    db = next(get_db())
    try:
        webhooks = db.query(Webhook).order_by(Webhook.created_at.desc()).all()
        return JsonResponse({"webhooks": [w.to_dict() for w in webhooks]})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def webhook_create(request):
    """Create a webhook configuration for n8n integration."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = data.get("name")
    url = data.get("url")
    events = data.get("events", [])

    if not name or not url:
        return JsonResponse({"error": "name and url required"}, status=400)

    if not events:
        return JsonResponse({"error": "at least one event type required"}, status=400)

    db = next(get_db())
    try:
        webhook = Webhook(
            name=name,
            url=url,
            secret=data.get("secret"),
            events=",".join(events) if isinstance(events, list) else events,
            active=data.get("active", True)
        )
        db.add(webhook)
        db.commit()
        db.refresh(webhook)
        log_event(db, "human", "create", "webhook", webhook.id, {"name": name, "url": url})
        return JsonResponse({"webhook": webhook.to_dict()}, status=201)
    finally:
        db.close()


def webhook_detail(request, webhook_id):
    """Get webhook details."""
    db = next(get_db())
    try:
        webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
        if not webhook:
            return JsonResponse({"error": "Webhook not found"}, status=404)
        return JsonResponse({"webhook": webhook.to_dict()})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def webhook_update(request, webhook_id):
    """Update a webhook configuration."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    db = next(get_db())
    try:
        webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
        if not webhook:
            return JsonResponse({"error": "Webhook not found"}, status=404)

        if "name" in data:
            webhook.name = data["name"]
        if "url" in data:
            webhook.url = data["url"]
        if "secret" in data:
            webhook.secret = data["secret"]
        if "events" in data:
            events = data["events"]
            webhook.events = ",".join(events) if isinstance(events, list) else events
        if "active" in data:
            webhook.active = data["active"]

        db.commit()
        log_event(db, "human", "update", "webhook", webhook_id, data)
        return JsonResponse({"webhook": webhook.to_dict()})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["DELETE", "POST"])
def webhook_delete(request, webhook_id):
    """Delete a webhook configuration."""
    db = next(get_db())
    try:
        webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
        if not webhook:
            return JsonResponse({"error": "Webhook not found"}, status=404)

        db.delete(webhook)
        db.commit()
        log_event(db, "human", "delete", "webhook", webhook_id, {})
        return JsonResponse({"deleted": True})
    finally:
        db.close()


# --- Bug Reports ---

def _add_cors_headers(response):
    """Add CORS headers for cross-origin widget requests."""
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, POST, PATCH, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


def _notify_webhooks(db, event_type: str, payload: dict):
    """Send notifications to registered webhooks for an event.

    Args:
        db: Database session
        event_type: Event type (e.g., 'bug_created', 'state_change')
        payload: Data to send to webhook
    """
    import threading
    import requests
    import hmac
    import hashlib
    import json

    from app.models.webhook import Webhook

    webhooks = db.query(Webhook).filter(Webhook.active == True).all()

    for webhook in webhooks:
        events = webhook.events.split(",") if webhook.events else []
        if event_type not in events and "*" not in events:
            continue

        def send_webhook(url, secret, data):
            try:
                headers = {"Content-Type": "application/json"}
                body = json.dumps(data)

                if secret:
                    signature = hmac.new(
                        secret.encode(), body.encode(), hashlib.sha256
                    ).hexdigest()
                    headers["X-Webhook-Signature"] = signature

                requests.post(url, data=body, headers=headers, timeout=10)
            except Exception as e:
                print(f"Webhook failed: {url} - {e}")

        # Send async to not block response
        thread = threading.Thread(
            target=send_webhook,
            args=(webhook.url, webhook.secret, payload)
        )
        thread.start()


def bug_list(request):
    """List all bug reports."""
    db = next(get_db())
    try:
        bugs = db.query(BugReport).order_by(BugReport.created_at.desc()).all()
        response = JsonResponse({"bugs": [b.to_dict() for b in bugs]})
        return _add_cors_headers(response)
    finally:
        db.close()


@csrf_exempt
def bug_create(request):
    """Create a new bug report. Supports CORS for cross-origin widget."""
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        response = JsonResponse({})
        return _add_cors_headers(response)

    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    data = _get_json_body(request)
    if not data:
        response = JsonResponse({"error": "Invalid JSON"}, status=400)
        return _add_cors_headers(response)

    title = data.get("title")
    if not title:
        response = JsonResponse({"error": "title is required"}, status=400)
        return _add_cors_headers(response)

    db = next(get_db())
    try:
        report = BugReport(
            title=title,
            description=data.get("description"),
            screenshot=data.get("screenshot"),
            url=data.get("url"),
            user_agent=request.headers.get("User-Agent"),
            app_name=data.get("app_name")
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        log_event(db, "human", "create", "bug_report", report.id, {"title": title})

        # Notify team via webhooks
        _notify_webhooks(db, "bug_created", {
            "event": "bug_created",
            "bug": {
                "id": report.id,
                "title": report.title,
                "description": report.description,
                "app_name": report.app_name,
                "url": report.url,
                "status": report.status.value,
                "created_at": report.created_at.isoformat() if report.created_at else None,
                "dashboard_url": f"http://localhost:8000/ui/bugs/{report.id}/"
            }
        })

        response = JsonResponse({"id": report.id, "status": "created"}, status=201)
        return _add_cors_headers(response)
    finally:
        db.close()


def bug_detail(request, bug_id):
    """Get a single bug report."""
    db = next(get_db())
    try:
        bug = db.query(BugReport).filter(BugReport.id == bug_id).first()
        if not bug:
            return JsonResponse({"error": "Bug report not found"}, status=404)
        return JsonResponse({"bug": bug.to_dict()})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["PATCH", "POST"])
def bug_update_status(request, bug_id):
    """Update bug report status."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    status_str = data.get("status")
    if not status_str:
        return JsonResponse({"error": "status is required"}, status=400)

    # Validate status value
    try:
        new_status = BugReportStatus(status_str)
    except ValueError:
        valid = [s.value for s in BugReportStatus]
        return JsonResponse({"error": f"Invalid status. Must be one of: {valid}"}, status=400)

    db = next(get_db())
    try:
        bug = db.query(BugReport).filter(BugReport.id == bug_id).first()
        if not bug:
            return JsonResponse({"error": "Bug report not found"}, status=404)

        bug.status = new_status

        # Set resolved_at if status is resolved
        if new_status == BugReportStatus.RESOLVED:
            from datetime import datetime, timezone
            bug.resolved_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(bug)
        log_event(db, "human", "update", "bug_report", bug_id, {"status": status_str})
        return JsonResponse({"bug": bug.to_dict()})
    finally:
        db.close()


def activity_feed(request):
    """Get combined activity feed for dashboard.

    Returns recent bugs, runs, and audit events combined and sorted by time.
    """
    db = next(get_db())
    try:
        limit = int(request.GET.get('limit', 20))

        activity = []

        # Recent bugs (exclude killed)
        recent_bugs = db.query(BugReport).filter(BugReport.killed == False).order_by(BugReport.created_at.desc()).limit(limit).all()
        for b in recent_bugs:
            activity.append({
                'type': 'bug',
                'id': b.id,
                'title': f'Bug #{b.id}: {b.title}',
                'description': f'{b.app_name or "Unknown app"} - {b.status.value}',
                'status': b.status.value,
                'timestamp': b.created_at.isoformat() if b.created_at else None,
                'url': f'/ui/bugs/{b.id}/'
            })

        # Recent runs (exclude killed)
        recent_runs = db.query(Run).filter(Run.killed == False).order_by(Run.created_at.desc()).limit(limit).all()
        for r in recent_runs:
            activity.append({
                'type': 'run',
                'id': r.id,
                'title': f'Run: {r.name}',
                'description': f'State: {r.state.value}',
                'status': r.state.value,
                'timestamp': r.created_at.isoformat() if r.created_at else None,
                'url': f'/ui/run/{r.id}/'
            })

        # Recent audit events
        recent_events = db.query(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(limit).all()
        for e in recent_events:
            activity.append({
                'type': 'audit',
                'id': e.id,
                'title': f'{e.action.title()} {e.entity_type}',
                'description': f'by {e.actor}',
                'status': e.action,
                'timestamp': e.timestamp.isoformat() if e.timestamp else None,
                'url': None
            })

        # Sort by timestamp descending
        activity.sort(key=lambda x: x['timestamp'] or '', reverse=True)

        return JsonResponse({
            'activity': activity[:limit],
            'count': len(activity[:limit])
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def bug_kill(request, bug_id):
    """Kill (soft delete) a bug report. Preserves history."""
    from datetime import datetime, timezone

    db = next(get_db())
    try:
        bug = db.query(BugReport).filter(BugReport.id == bug_id).first()
        if not bug:
            return JsonResponse({"error": "Bug report not found"}, status=404)

        bug.killed = True
        bug.killed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(bug)

        log_event(db, "human", "kill", "bug_report", bug_id, {"title": bug.title})
        return JsonResponse({"success": True, "bug": bug.to_dict()})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def run_kill(request, run_id):
    """Kill (soft delete) a run. Preserves history."""
    from datetime import datetime, timezone

    db = next(get_db())
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JsonResponse({"error": "Run not found"}, status=404)

        run.killed = True
        run.killed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)

        log_event(db, "human", "kill", "run", run_id, {"name": run.name})
        return JsonResponse({"success": True, "run": run.to_dict()})
    finally:
        db.close()
