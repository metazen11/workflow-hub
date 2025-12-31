"""JSON API views for Workflow Hub."""
import json
import os
import hashlib
import threading
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
    Credential, CredentialType, Environment, EnvironmentType,
    Handoff, HandoffStatus, Proof
)
from app.models.task import TaskPipelineStage
from app.models.report import AgentRole, ReportStatus
from app.models.audit import log_event
from app.services.run_service import RunService

# Upload directory
UPLOAD_DIR = os.path.join(settings.BASE_DIR, 'uploads', 'attachments')

# Workspaces directory - where project repositories are created
WORKSPACES_DIR = os.getenv("WORKSPACES_DIR", os.path.join(settings.BASE_DIR, 'workspaces'))


def _slugify(name: str) -> str:
    """Convert name to filesystem-safe slug."""
    import re
    # Convert to lowercase, replace spaces/special chars with hyphens
    slug = re.sub(r'[^\w\s-]', '', name.lower())
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')
    return slug or 'project'


def _generate_workspace_path(name: str) -> str:
    """Generate a unique workspace path for a project."""
    base_slug = _slugify(name)
    workspace_path = os.path.join(WORKSPACES_DIR, base_slug)

    # Ensure uniqueness by appending number if needed
    counter = 1
    while os.path.exists(workspace_path):
        workspace_path = os.path.join(WORKSPACES_DIR, f"{base_slug}-{counter}")
        counter += 1

    return workspace_path


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
    """Create a new project with all supported fields."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = data.get("name")
    if not name:
        return JsonResponse({"error": "name required"}, status=400)

    db = next(get_db())
    try:
        # Auto-generate workspace path if not provided
        repo_path = data.get("repo_path")
        if not repo_path:
            repo_path = _generate_workspace_path(name)

        # Create project with all supported fields
        project = Project(
            name=name,
            description=data.get("description"),
            # Repository & Location
            repo_path=repo_path,
            repository_url=data.get("repository_url"),
            repository_ssh_url=data.get("repository_ssh_url"),
            primary_branch=data.get("primary_branch", "main"),
            documentation_url=data.get("documentation_url"),
            git_credential_id=data.get("git_credential_id"),
            git_auth_method=data.get("git_auth_method"),
            # Tech Stack (JSON arrays)
            stack_tags=data.get("stack_tags", []),
            languages=data.get("languages", []),
            frameworks=data.get("frameworks", []),
            databases=data.get("databases", []),
            # Key Files & Structure (JSON arrays)
            key_files=data.get("key_files", []),
            entry_point=data.get("entry_point"),
            config_files=data.get("config_files", []),
            # Build & Deploy Commands
            build_command=data.get("build_command"),
            test_command=data.get("test_command"),
            run_command=data.get("run_command"),
            deploy_command=data.get("deploy_command"),
            # Development Settings
            default_port=data.get("default_port"),
            python_version=data.get("python_version"),
            node_version=data.get("node_version"),
            # Status
            is_active=data.get("is_active", True),
            is_archived=data.get("is_archived", False),
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        log_event(db, "human", "create", "project", project.id, {"name": name})
        return JsonResponse({"project": project.to_dict()}, status=201)
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def project_discover(request):
    """Discover project metadata from an existing folder.

    POST /api/projects/discover
    Body: {"path": "/path/to/project", "create": false}

    Returns discovered metadata. If create=true, also creates the project.
    """
    import sys
    import os
    scripts_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'scripts')
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)

    from discover_project import ProjectDiscovery

    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    path = data.get("path")
    if not path:
        return JsonResponse({"error": "path required"}, status=400)

    try:
        discovery = ProjectDiscovery(path)
        result = discovery.discover()
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"Discovery failed: {e}"}, status=500)

    # Optionally create the project
    if data.get("create"):
        db = next(get_db())
        try:
            project = Project(
                name=result['name'],
                description=result['description'],
                repo_path=result['repo_path'],
                repository_url=result['repository_url'],
                repository_ssh_url=result['repository_ssh_url'],
                primary_branch=result['primary_branch'],
                languages=result['languages'],
                frameworks=result['frameworks'],
                databases=result['databases'],
                stack_tags=result['stack_tags'],
                key_files=result['key_files'],
                entry_point=result['entry_point'],
                config_files=result['config_files'],
                build_command=result['build_command'],
                test_command=result['test_command'],
                run_command=result['run_command'],
            )
            db.add(project)
            db.commit()
            db.refresh(project)
            log_event(db, "human", "create", "project", project.id, {
                "name": result['name'],
                "auto_discovered": True
            })
            return JsonResponse({
                "discovered": result,
                "project": project.to_dict(),
                "created": True
            }, status=201)
        finally:
            db.close()

    return JsonResponse({"discovered": result, "created": False})


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
    """Update project details with input validation and sanitization."""
    import html
    import re

    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Field validation rules
    FIELD_RULES = {
        "name": {"max_length": 200, "type": str, "pattern": r"^[\w\s\-\.]+$"},
        "description": {"max_length": 2000, "type": str},
        "repo_path": {"max_length": 500, "type": str},
        "repository_url": {"max_length": 500, "type": str, "pattern": r"^https?://"},
        "repository_ssh_url": {"max_length": 500, "type": str, "pattern": r"^git@"},
        "primary_branch": {"max_length": 100, "type": str, "pattern": r"^[\w\-/\.]+$"},
        "documentation_url": {"max_length": 500, "type": str, "pattern": r"^https?://"},
        "entry_point": {"max_length": 300, "type": str},
        "build_command": {"max_length": 1000, "type": str},
        "test_command": {"max_length": 1000, "type": str},
        "run_command": {"max_length": 1000, "type": str},
        "deploy_command": {"max_length": 1000, "type": str},
        "default_port": {"type": int, "min": 1, "max": 65535},
        "python_version": {"max_length": 20, "type": str},
        "node_version": {"max_length": 20, "type": str},
        "is_active": {"type": bool},
        "is_archived": {"type": bool},
        "git_credential_id": {"type": int},
        "git_auth_method": {"max_length": 50, "type": str},
    }

    def sanitize_string(value):
        """Sanitize string input to prevent XSS."""
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        # HTML escape to prevent XSS
        value = html.escape(value.strip())
        # Remove null bytes and control characters (except newlines/tabs)
        value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value)
        return value

    def validate_field(field, value):
        """Validate a field value against its rules. Returns (validated_value, error)."""
        rules = FIELD_RULES.get(field, {"type": str, "max_length": 500})

        # Allow None/null values (clears the field)
        if value is None or value == "" or value == "-":
            return None, None

        expected_type = rules.get("type", str)

        if expected_type == int:
            try:
                value = int(value)
            except (ValueError, TypeError):
                return None, f"{field} must be a number"
            if "min" in rules and value < rules["min"]:
                return None, f"{field} must be at least {rules['min']}"
            if "max" in rules and value > rules["max"]:
                return None, f"{field} must be at most {rules['max']}"
        elif expected_type == bool:
            if isinstance(value, str):
                value = value.lower() in ("true", "1", "yes")
            value = bool(value)
        elif expected_type == str:
            value = sanitize_string(str(value))
            max_len = rules.get("max_length", 500)
            if len(value) > max_len:
                return None, f"{field} exceeds maximum length of {max_len}"
            # Pattern validation (only warn, don't block - allows flexibility)
            pattern = rules.get("pattern")
            if pattern and value and not re.match(pattern, value):
                # Log warning but allow - pattern is advisory
                pass

        return value, None

    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return JsonResponse({"error": "Project not found"}, status=404)

        # Update allowed fields - scalars with validation
        scalar_fields = [
            "name", "description", "repo_path", "repository_url", "repository_ssh_url",
            "primary_branch", "documentation_url", "git_credential_id", "git_auth_method",
            "entry_point", "build_command", "test_command", "run_command", "deploy_command",
            "default_port", "python_version", "node_version", "is_active", "is_archived"
        ]
        errors = []
        updated_fields = []

        for field in scalar_fields:
            if field in data:
                validated_value, error = validate_field(field, data[field])
                if error:
                    errors.append(error)
                else:
                    setattr(project, field, validated_value)
                    updated_fields.append(field)

        if errors:
            return JsonResponse({"error": "; ".join(errors)}, status=400)

        # Update allowed fields - arrays (JSON columns) with sanitization
        array_fields = [
            "stack_tags", "languages", "frameworks", "databases", "key_files", "config_files"
        ]
        for field in array_fields:
            if field in data:
                arr_value = data[field]
                if isinstance(arr_value, list):
                    # Sanitize each element, limit to 200 chars per item
                    arr_value = [sanitize_string(str(v))[:200] for v in arr_value if v]
                setattr(project, field, arr_value)
                updated_fields.append(field)

        # Handle additional_commands (JSON dict)
        if "additional_commands" in data:
            cmd_value = data["additional_commands"]
            if isinstance(cmd_value, dict):
                # Don't HTML-escape command values (they need && etc)
                # Just validate structure and sanitize keys
                sanitized = {}
                for k, v in cmd_value.items():
                    key = re.sub(r'[^\w\-_]', '', str(k))[:50]  # Alphanumeric keys only
                    if key and v:
                        sanitized[key] = str(v)[:2000]  # Allow longer commands
                setattr(project, "additional_commands", sanitized)
                updated_fields.append("additional_commands")

        db.commit()
        db.refresh(project)
        log_event(db, "human", "update", "project", project.id, {"updated_fields": updated_fields})
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
    """Create a task for a project.

    Supports full task creation including pipeline_stage.
    Auto-parses screenshot/image file paths from description and attaches them.

    Body:
        title (required): Task title
        description: Task description (may contain file paths like /path/to/image.png)
        priority: 1-10 (default 5)
        pipeline_stage: none|pm|dev|qa|sec|docs|complete (default none)
        blocked_by: List of blocking task IDs
        acceptance_criteria: List of criteria strings
        run_id: Associate with a run
        auto_attach: If true, parse description for file paths and attach (default true)
    """
    import os
    import re
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    title = data.get("title")
    if not title:
        return JsonResponse({"error": "title is required"}, status=400)

    db = next(get_db())
    try:
        # Auto-generate task_id if not provided
        task_id = data.get("task_id")
        if not task_id:
            # Get next task number for this project
            max_task = db.query(Task).filter(Task.project_id == project_id).count()
            task_id = f"T{max_task + 1:03d}"

        # Parse pipeline_stage if provided
        pipeline_stage = None
        stage_str = data.get("pipeline_stage", data.get("stage"))
        if stage_str:
            stage_map = TaskPipelineStage.get_stage_map()
            if stage_str.lower() in stage_map:
                pipeline_stage = stage_map[stage_str.lower()]
            # Accept 'backlog' as alias for 'none'
            elif stage_str.lower() == 'backlog':
                pipeline_stage = TaskPipelineStage.NONE

        task = Task(
            project_id=project_id,
            task_id=task_id,
            title=title,
            description=data.get("description"),
            priority=data.get("priority", 5),
            blocked_by=data.get("blocked_by", []),
            acceptance_criteria=data.get("acceptance_criteria", []),
            run_id=data.get("run_id"),
            status=TaskStatus.BACKLOG,
            pipeline_stage=pipeline_stage
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        # Auto-attach files referenced in description
        attached_files = []
        auto_attach = data.get("auto_attach", True)
        description = data.get("description", "")

        if auto_attach and description:
            # Parse file paths from description - match paths like /path/to/file.png or ./file.png
            # Supports: absolute paths, relative paths, and screenshot/image extensions
            file_pattern = r'(?:^|\s)([/.][\w/.-]+\.(?:png|jpg|jpeg|gif|webp|pdf|txt|md|log))\b'
            potential_files = re.findall(file_pattern, description, re.IGNORECASE)

            for file_path in potential_files:
                # Expand relative paths
                if file_path.startswith('./') or not file_path.startswith('/'):
                    # Try relative to project repo_path if available
                    project = db.query(Project).filter(Project.id == project_id).first()
                    if project and project.repo_path:
                        full_path = os.path.join(project.repo_path, file_path)
                    else:
                        full_path = os.path.abspath(file_path)
                else:
                    full_path = file_path

                # Check if file exists and try to attach it
                if os.path.isfile(full_path):
                    try:
                        from app.models.attachment import TaskAttachment, validate_file_security
                        import uuid

                        with open(full_path, 'rb') as f:
                            content = f.read()

                        filename = os.path.basename(full_path)
                        validation = validate_file_security(content, filename)

                        # Create stored filename with UUID
                        stored_filename = f"{uuid.uuid4().hex}_{filename}"

                        # Ensure uploads directory exists
                        upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads', 'tasks', str(task.id))
                        os.makedirs(upload_dir, exist_ok=True)

                        # Save file
                        storage_path = os.path.join('tasks', str(task.id), stored_filename)
                        full_storage_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads', storage_path)
                        with open(full_storage_path, 'wb') as f:
                            f.write(content)

                        # Create attachment record
                        attachment = TaskAttachment(
                            task_id=task.id,
                            filename=filename,
                            stored_filename=stored_filename,
                            mime_type=validation['mime_type'],
                            attachment_type=validation['attachment_type'],
                            size=validation['size'],
                            checksum=TaskAttachment.compute_checksum(content),
                            storage_path=storage_path,
                            uploaded_by='auto'
                        )
                        db.add(attachment)
                        attached_files.append(filename)
                    except Exception as e:
                        # Log but don't fail task creation
                        print(f"Warning: Could not auto-attach {full_path}: {e}")

            if attached_files:
                db.commit()

        log_event(db, "human", "create", "task", task.id, {"task_id": task.task_id})

        result = {"task": task.to_dict()}
        if attached_files:
            result["auto_attached"] = attached_files
        return JsonResponse(result, status=201)
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
@require_http_methods(["PATCH"])
def task_update(request, task_id):
    """Update task details (title, description, priority, etc.)."""
    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        updated_fields = []

        if "title" in data:
            task.title = data["title"]
            updated_fields.append("title")

        if "description" in data:
            task.description = data["description"]
            updated_fields.append("description")

        if "priority" in data:
            task.priority = int(data["priority"])
            updated_fields.append("priority")

        if "blocked_by" in data:
            task.blocked_by = data["blocked_by"]
            updated_fields.append("blocked_by")

        if "acceptance_criteria" in data:
            task.acceptance_criteria = data["acceptance_criteria"]
            updated_fields.append("acceptance_criteria")

        if "run_id" in data:
            task.run_id = data["run_id"]
            updated_fields.append("run_id")

        db.commit()
        db.refresh(task)
        log_event(db, "human", "update", "task", task_id, {"updated_fields": updated_fields})
        return JsonResponse({"success": True, "task": task.to_dict()})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["DELETE", "POST"])
def task_delete(request, task_id):
    """Delete a task."""
    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        try:
            task_info = {"task_id": task.task_id, "title": task.title}
            db.delete(task)
            db.commit()
            log_event(db, "human", "delete", "task", task_id, task_info)
            return JsonResponse({"success": True, "message": f"Task {task_id} deleted"})
        except Exception as e:
            db.rollback()
            return JsonResponse({"error": str(e)}, status=500)
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

        # Capture values before commit (SQLAlchemy expires objects after commit)
        run_id = run.id
        task_id_str = task.task_id
        task_dict = task.to_dict()
        state_value = run.state.value
        project_repo_path = project.repo_path

        # Log event and commit
        log_event(db, "human", "execute", "task", task_id, {"run_id": run_id})
        db.commit()

        # Trigger pipeline in background thread (use captured values, not ORM objects)
        def run_pipeline():
            try:
                subprocess.run(
                    ["python3", "scripts/agent_runner.py", "pipeline",
                     "--run-id", str(run_id),
                     "--project-path", project_repo_path,
                     "--max-iterations", str(max_iterations)],
                    cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    timeout=1800  # 30 min timeout
                )
            except Exception as e:
                print(f"Pipeline error: {e}")

        thread = threading.Thread(target=run_pipeline, daemon=True)
        thread.start()

        return JsonResponse({
            "message": f"Pipeline started for task {task_id_str}",
            "task": task_dict,
            "run_id": run_id,
            "state": state_value
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
        # Convert to lowercase for enum lookup (standardized on lowercase)
        role_str = data.get("role", "").lower()
        status_str = data.get("status", "").lower()
        role = AgentRole(role_str)
        status = ReportStatus(status_str)
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
            actor=data.get("actor", role.value),
            raw_output=data.get("raw_output")
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
def run_set_state(request, run_id):
    """Manually set run state (human override, bypasses gates)."""
    data = _get_json_body(request)
    if not data or "state" not in data:
        return JsonResponse({"error": "state is required"}, status=400)

    db = next(get_db())
    try:
        service = RunService(db)
        new_state, error = service.set_state(run_id, data["state"], actor="human")
        if error:
            return JsonResponse({"error": error}, status=400)
        return JsonResponse({"state": new_state.value, "forced": True})
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
    """Reset a failed run back to DEV stage for fixes.

    Automatically creates tasks from QA/Security findings.
    Pass {"create_tasks": false} to skip task creation.
    """
    db = next(get_db())
    try:
        data = json.loads(request.body) if request.body else {}
        actor = data.get("actor", "orchestrator")
        create_tasks = data.get("create_tasks", True)

        service = RunService(db)

        # Get tasks that will be created (for response)
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JsonResponse({"error": "Run not found"}, status=404)

        new_state, error = service.reset_to_dev(run_id, actor, create_tasks=create_tasks)
        if error:
            return JsonResponse({"error": error}, status=400)

        # Get incomplete tasks for this project to show dev what to work on
        incomplete_tasks = db.query(Task).filter(
            Task.project_id == run.project_id,
            Task.status != TaskStatus.DONE
        ).order_by(Task.priority.desc()).all()

        return JsonResponse({
            "status": "success",
            "state": new_state.value,
            "message": "Reset to DEV for fixes",
            "tasks_to_fix": [
                {
                    "task_id": t.task_id,
                    "title": t.title,
                    "priority": t.priority,
                    "description": t.description[:200] if t.description else None
                }
                for t in incomplete_tasks
            ]
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def run_create_tasks_from_findings(request, run_id):
    """Manually create tasks from the latest QA or Security report findings."""
    db = next(get_db())
    try:
        data = json.loads(request.body) if request.body else {}
        role = data.get("role", "security")  # qa or security

        if role not in ("qa", "security"):
            return JsonResponse({"error": "Role must be 'qa' or 'security'"}, status=400)

        from app.models.report import AgentRole
        agent_role = AgentRole.QA if role == "qa" else AgentRole.SECURITY

        service = RunService(db)
        tasks = service.create_tasks_from_findings(run_id, agent_role)

        return JsonResponse({
            "status": "success",
            "tasks_created": len(tasks),
            "tasks": [
                {
                    "id": t.id,
                    "task_id": t.task_id,
                    "title": t.title,
                    "priority": t.priority
                }
                for t in tasks
            ]
        })
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


@csrf_exempt
@require_http_methods(["POST"])
def run_trigger_agent(request, run_id):
    """Trigger an agent for a run (runs in background)."""
    from app.services.agent_service import AgentService

    data = _get_json_body(request) or {}
    agent_type = data.get("agent")  # Optional override
    custom_prompt = data.get("prompt")
    async_mode = data.get("async", True)

    service = AgentService()
    result = service.trigger_agent(
        run_id=run_id,
        agent_type=agent_type,
        async_mode=async_mode,
        custom_prompt=custom_prompt
    )

    status_code = 200 if result.get("status") in ("started", "pass") else 400
    return JsonResponse(result, status=status_code)


@csrf_exempt
@require_http_methods(["POST"])
def run_trigger_pipeline(request, run_id):
    """Trigger the full pipeline for a run (PM → DEV → QA → SEC → ...)."""
    from app.services.agent_service import AgentService

    data = _get_json_body(request) or {}
    max_iterations = data.get("max_iterations", 10)

    service = AgentService()
    result = service.trigger_pipeline(run_id=run_id, max_iterations=max_iterations)

    status_code = 200 if result.get("status") == "started" else 400
    return JsonResponse(result, status=status_code)


@csrf_exempt
@require_http_methods(["POST"])
def run_director_process(request, run_id):
    """Have the director process and advance tasks for a run.

    The director will:
    - Enrich tasks with missing acceptance criteria
    - Validate task readiness
    - Optionally trigger agent execution

    Body:
        auto_trigger (bool): If True, automatically trigger agents for ready tasks
        max_tasks (int): Max tasks to process (default 10)
    """
    from app.services.director_service import DirectorService

    data = _get_json_body(request) or {}
    auto_trigger = data.get("auto_trigger", False)
    max_tasks = data.get("max_tasks", 10)

    db = next(get_db())
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JsonResponse({"error": "Run not found"}, status=404)

        director = DirectorService(db)
        result = director.process_run(
            run_id=run_id,
            max_tasks=max_tasks,
            auto_trigger=auto_trigger
        )

        log_event(
            db,
            actor="api",
            action="director_process",
            entity_type="run",
            entity_id=run_id,
            details={
                "tasks_enriched": result.get("tasks_enriched", 0),
                "tasks_triggered": result.get("tasks_triggered", 0),
                "tasks_queued": result.get("tasks_queued", 0)
            }
        )

        return JsonResponse(result)
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_director_prepare(request, task_id):
    """Have the director prepare and optionally run a specific task.

    The director will:
    - Enrich the task with missing acceptance criteria
    - Validate task readiness
    - Optionally trigger agent execution

    Body:
        auto_trigger (bool): If True, automatically trigger agent for this task
    """
    from app.services.director_service import DirectorService

    data = _get_json_body(request) or {}
    auto_trigger = data.get("auto_trigger", True)

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        director = DirectorService(db)

        # Prepare (enrich + validate)
        result = director.prepare_and_run_task(task) if auto_trigger else {
            "task_id": task.task_id,
            "enriched": False,
            "triggered": False,
            "message": ""
        }

        # If not auto-triggering, just enrich
        if not auto_trigger:
            enriched, msg = director.enrich_task(task)
            is_ready, issues = director.validate_task_readiness(task)
            result["enriched"] = enriched
            result["issues"] = issues
            result["message"] = msg if enriched else ("Ready for agent" if is_ready else "; ".join(issues))

        return JsonResponse(result)
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

        from app.services.crypto_service import encrypt
        credential = Credential(
            project_id=project_id,
            name=data.get("name"),
            credential_type=cred_type_enum,
            service=data.get("service"),
            description=data.get("description"),
            username=data.get("username"),
            password_encrypted=encrypt(data.get("password", "")),
            api_key_encrypted=encrypt(data.get("api_key", "")),
            token_encrypted=encrypt(data.get("token", "")),
            ssh_key_path=data.get("ssh_key_path"),
            ssh_key_encrypted=encrypt(data.get("ssh_key", "")),
            database_url_encrypted=encrypt(data.get("database_url", "")),
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

        # Update encrypted fields
        from app.services.crypto_service import encrypt
        for field in ["password", "api_key", "token", "ssh_key", "database_url"]:
            if field in data:
                setattr(credential, f"{field}_encrypted", encrypt(data[field] or ""))

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

    GET /api/projects/{id}/context

    Returns everything an agent needs to work on a project:
    - Project metadata and all commands
    - Key file contents (CLAUDE.md, coding_principles.md, todo.json, etc.)
    - Tasks, environments, credentials (masked), requirements
    - Recent handoffs, proofs, and audit events

    Query params:
    - include_files: true/false (default true) - include key file contents
    - include_history: true/false (default true) - include handoffs/proofs
    - max_file_size: int (default 50000) - max bytes per file
    """
    import os

    include_files = request.GET.get("include_files", "true").lower() == "true"
    include_history = request.GET.get("include_history", "true").lower() == "true"
    max_file_size = int(request.GET.get("max_file_size", 50000))

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

        result = {
            "project": project.to_dict(include_children=True),
            "tasks": [t.to_dict() for t in tasks],
            "environments": [e.to_dict() for e in environments],
            "credentials": [c.to_dict() for c in credentials],  # Masked by default
            "requirements": [r.to_dict() for r in requirements],
        }

        # Commands summary for easy agent access
        result["commands"] = {
            "build": project.build_command,
            "test": project.test_command,
            "run": project.run_command,
            "deploy": project.deploy_command,
            **(project.additional_commands or {})
        }

        # Include key file contents if requested and repo_path exists
        if include_files and project.repo_path and os.path.isdir(project.repo_path):
            file_contents = {}

            # Priority files for agent context
            priority_files = [
                "CLAUDE.md",
                "coding_principles.md",
                "todo.json",
                "_spec/BRIEF.md",
                "_spec/HANDOFF.md",
                "_spec/SESSION_CONTEXT.md",
            ]

            # Add project's key_files
            all_files = priority_files + (project.key_files or [])
            seen = set()

            for filename in all_files:
                if filename in seen:
                    continue
                seen.add(filename)

                filepath = os.path.join(project.repo_path, filename)
                if os.path.isfile(filepath):
                    try:
                        size = os.path.getsize(filepath)
                        if size <= max_file_size:
                            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                                file_contents[filename] = {
                                    "content": f.read(),
                                    "size": size
                                }
                        else:
                            file_contents[filename] = {
                                "content": f"[File too large: {size} bytes, max {max_file_size}]",
                                "size": size,
                                "truncated": True
                            }
                    except Exception as e:
                        file_contents[filename] = {"error": str(e)}

            result["files"] = file_contents

        # Include recent history if requested
        if include_history:
            # Recent handoffs
            recent_handoffs = db.query(Handoff).filter(
                Handoff.project_id == project_id
            ).order_by(Handoff.created_at.desc()).limit(10).all()
            result["recent_handoffs"] = [h.to_dict() for h in recent_handoffs]

            # Recent proofs
            recent_proofs = db.query(Proof).filter(
                Proof.project_id == project_id
            ).order_by(Proof.created_at.desc()).limit(10).all()
            result["recent_proofs"] = [p.to_dict() for p in recent_proofs]

            # Recent audit events for this project
            recent_events = db.query(AuditEvent).filter(
                AuditEvent.entity_type == "project",
                AuditEvent.entity_id == project_id
            ).order_by(AuditEvent.timestamp.desc()).limit(20).all()
            result["recent_events"] = [
                {
                    "id": e.id,
                    "action": e.action,
                    "actor": e.actor,
                    "details": e.details,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None
                } for e in recent_events
            ]

        return JsonResponse(result)
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
    """List recent audit events, optionally filtered by project, entity_type, or entity_id."""
    limit = int(request.GET.get("limit", 100))
    project_id = request.GET.get("project_id")
    entity_type = request.GET.get("entity_type")
    entity_id = request.GET.get("entity_id")

    db = next(get_db())
    try:
        # Direct entity filter (e.g., specific task or run)
        if entity_type and entity_id:
            events = db.query(AuditEvent).filter(
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == int(entity_id)
            ).order_by(AuditEvent.timestamp.desc()).limit(limit).all()
            return JsonResponse({"events": [e.to_dict() for e in events]})

        if project_id:
            # Filter events related to a project (runs, tasks, project itself)
            project_id = int(project_id)

            # Get all run IDs for this project
            run_ids = [r.id for r in db.query(Run.id).filter(Run.project_id == project_id).all()]
            # Get all task IDs for this project
            task_ids = [t.id for t in db.query(Task.id).filter(Task.project_id == project_id).all()]

            from sqlalchemy import or_
            query = db.query(AuditEvent).filter(
                or_(
                    (AuditEvent.entity_type == "project") & (AuditEvent.entity_id == project_id),
                    (AuditEvent.entity_type == "run") & (AuditEvent.entity_id.in_(run_ids)) if run_ids else False,
                    (AuditEvent.entity_type == "task") & (AuditEvent.entity_id.in_(task_ids)) if task_ids else False,
                )
            )
        else:
            query = db.query(AuditEvent)

        events = query.order_by(AuditEvent.timestamp.desc()).limit(limit).all()
        return JsonResponse({"audit_events": [e.to_dict() for e in events]})
    finally:
        db.close()


def project_audit_log(request, project_id):
    """List audit events for a specific project."""
    limit = int(request.GET.get("limit", 100))

    db = next(get_db())
    try:
        # Get all run IDs for this project
        run_ids = [r.id for r in db.query(Run.id).filter(Run.project_id == project_id).all()]
        # Get all task IDs for this project
        task_ids = [t.id for t in db.query(Task.id).filter(Task.project_id == project_id).all()]

        from sqlalchemy import or_
        query = db.query(AuditEvent).filter(
            or_(
                (AuditEvent.entity_type == "project") & (AuditEvent.entity_id == project_id),
                (AuditEvent.entity_type == "run") & (AuditEvent.entity_id.in_(run_ids)) if run_ids else False,
                (AuditEvent.entity_type == "task") & (AuditEvent.entity_id.in_(task_ids)) if task_ids else False,
            )
        )

        events = query.order_by(AuditEvent.timestamp.desc()).limit(limit).all()
        return JsonResponse({
            "project_id": project_id,
            "audit_events": [e.to_dict() for e in events]
        })
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
        # Get project_id if provided (auto-captured from UI)
        project_id = data.get("project_id")
        if project_id:
            try:
                project_id = int(project_id)
            except (ValueError, TypeError):
                project_id = None

        report = BugReport(
            title=title,
            description=data.get("description"),
            screenshot=data.get("screenshot"),
            url=data.get("url"),
            user_agent=request.headers.get("User-Agent"),
            app_name=data.get("app_name"),
            project_id=project_id
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


# =============================================================================
# Task Pipeline API - Individual task workflow tracking
# =============================================================================

# Stage progression map: which stage follows which
STAGE_PROGRESSION = {
    TaskPipelineStage.NONE: TaskPipelineStage.DEV,
    TaskPipelineStage.DEV: TaskPipelineStage.QA,
    TaskPipelineStage.QA: TaskPipelineStage.SEC,
    TaskPipelineStage.SEC: TaskPipelineStage.DOCS,
    TaskPipelineStage.DOCS: TaskPipelineStage.COMPLETE,
}


@csrf_exempt
@require_http_methods(["GET"])
def task_queue(request):
    """
    Get next task(s) for an agent to work on.

    Query params:
        - run_id: Filter by specific run (required)
        - stage: Filter by pipeline stage (dev, qa, sec, docs)
        - limit: Max tasks to return (default 1)

    Returns tasks that need work at the specified stage.
    """
    run_id = request.GET.get("run_id")
    stage = request.GET.get("stage", "dev").lower()
    limit = int(request.GET.get("limit", 1))

    if not run_id:
        return JsonResponse({"error": "run_id required"}, status=400)

    # Use enum's DRY helper for stage lookup
    stage_map = TaskPipelineStage.get_stage_map()
    target_stage = stage_map.get(stage.upper())
    if not target_stage:
        return JsonResponse({"error": f"Invalid stage: {stage}. Valid: {', '.join(TaskPipelineStage.valid_stages())}"}, status=400)

    db = next(get_db())
    try:
        # Find tasks at this stage that aren't done
        tasks = db.query(Task).filter(
            Task.run_id == int(run_id),
            Task.pipeline_stage == target_stage,
            Task.status != TaskStatus.DONE
        ).order_by(Task.priority.desc()).limit(limit).all()

        return JsonResponse({
            "tasks": [t.to_dict() for t in tasks],
            "count": len(tasks),
            "stage": stage
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_advance_stage(request, task_id):
    """
    Advance a task to the next pipeline stage.

    Body (optional):
        - result: "pass" or "fail" (default: pass)
        - notes: Agent notes about the work done
        - actor: Who is advancing (default: agent)

    On pass: Task advances to next stage
    On fail: Task goes back to DEV stage
    """
    data = _get_json_body(request) or {}
    result = data.get("result", "pass").lower()
    notes = data.get("notes", "")
    actor = data.get("actor", "agent")

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        current_stage = task.pipeline_stage or TaskPipelineStage.NONE

        if result == "pass":
            # Advance to next stage
            next_stage = STAGE_PROGRESSION.get(current_stage, TaskPipelineStage.COMPLETE)
            task.pipeline_stage = next_stage

            if next_stage == TaskPipelineStage.COMPLETE:
                task.status = TaskStatus.DONE
                task.completed = True
                from datetime import datetime, timezone
                task.completed_at = datetime.now(timezone.utc)
        else:
            # Failed - loop back to DEV
            task.pipeline_stage = TaskPipelineStage.DEV
            task.status = TaskStatus.IN_PROGRESS

        db.commit()
        db.refresh(task)

        log_event(db, actor, "advance_stage", "task", task_id, {
            "from_stage": current_stage.value,
            "to_stage": task.pipeline_stage.value,
            "result": result,
            "notes": notes
        })

        return JsonResponse({
            "success": True,
            "task": task.to_dict(),
            "from_stage": current_stage.value,
            "to_stage": task.pipeline_stage.value
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_set_stage(request, task_id):
    """
    Set a task's pipeline stage directly.

    Body:
        - stage: Target stage (none, dev, qa, sec, docs, complete)
        - actor: Who is setting (default: agent)
    """
    data = _get_json_body(request) or {}
    stage_str = data.get("stage", "").lower()
    actor = data.get("actor", "agent")

    # Use enum's DRY helper for stage lookup
    stage_map = TaskPipelineStage.get_stage_map()
    stage_str_upper = stage_str.upper()

    if stage_str_upper not in stage_map:
        return JsonResponse({"error": f"Invalid stage: {stage_str}. Valid: {', '.join(TaskPipelineStage.valid_stages())}"}, status=400)

    stage_str = stage_str_upper  # Use uppercase for lookup

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        old_stage = task.pipeline_stage
        task.pipeline_stage = stage_map[stage_str]

        if stage_map[stage_str] == TaskPipelineStage.COMPLETE:
            task.status = TaskStatus.DONE
            task.completed = True
            from datetime import datetime, timezone
            task.completed_at = datetime.now(timezone.utc)
        elif stage_map[stage_str] in (TaskPipelineStage.PM, TaskPipelineStage.DEV, TaskPipelineStage.QA, TaskPipelineStage.SEC, TaskPipelineStage.DOCS):
            task.status = TaskStatus.IN_PROGRESS

        db.commit()
        db.refresh(task)

        log_event(db, actor, "set_stage", "task", task_id, {
            "from_stage": old_stage.value if old_stage else "none",
            "to_stage": task.pipeline_stage.value
        })

        return JsonResponse({
            "success": True,
            "task": task.to_dict()
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["GET"])
def run_task_progress(request, run_id):
    """
    Get task pipeline progress for a run.

    Returns count of tasks at each pipeline stage.
    """
    db = next(get_db())
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JsonResponse({"error": "Run not found"}, status=404)

        tasks = db.query(Task).filter(Task.run_id == run_id).all()

        # Count by stage
        stage_counts = {stage.value: 0 for stage in TaskPipelineStage}
        for task in tasks:
            stage = task.pipeline_stage or TaskPipelineStage.NONE
            stage_counts[stage.value] += 1

        # Calculate progress percentage
        total = len(tasks)
        completed = stage_counts.get("complete", 0)
        progress_pct = (completed / total * 100) if total > 0 else 0

        return JsonResponse({
            "run_id": run_id,
            "total_tasks": total,
            "stage_counts": stage_counts,
            "completed": completed,
            "progress_percent": round(progress_pct, 1),
            "tasks": [t.to_dict() for t in tasks]
        })
    finally:
        db.close()


# =============================================================================
# Director / Task Pipeline Endpoints
# =============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def director_process_run(request, run_id):
    """Process a run's tasks through the pipeline.

    POST /api/runs/{run_id}/director/process

    Triggers the Director to:
    1. Find tasks needing work
    2. Start BACKLOG tasks
    3. Return work queue for agents

    Returns:
        {
            "run_id": 432,
            "tasks_queued": 5,
            "work_queue": [...],
            "progress": {...}
        }
    """
    from app.services.director_service import DirectorService

    db = next(get_db())
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JsonResponse({"error": "Run not found"}, status=404)

        director = DirectorService(db)
        result = director.process_run(run_id)

        return JsonResponse(result)
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_advance(request, task_id):
    """Advance a task to the next pipeline stage.

    POST /api/tasks/{task_id}/advance

    Body:
        {
            "report_status": "pass" or "fail",  # Optional
            "report_summary": "..."              # Optional
        }

    Returns:
        {
            "success": true,
            "message": "Advanced from dev to qa",
            "task": {...}
        }
    """
    from app.services.director_service import DirectorService

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        data = json.loads(request.body) if request.body else {}

        # Create a mock report if status provided
        report = None
        if "report_status" in data:
            report = AgentReport(
                run_id=task.run_id or 0,
                role=AgentRole.DEV,
                status=ReportStatus.PASS if data["report_status"] == "pass" else ReportStatus.FAIL,
                summary=data.get("report_summary", "")
            )

        director = DirectorService(db)
        success, message = director.advance_task(task, report)

        db.refresh(task)

        return JsonResponse({
            "success": success,
            "message": message,
            "task": task.to_dict()
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_start(request, task_id):
    """Start a task (move from BACKLOG to DEV).

    POST /api/tasks/{task_id}/start

    Returns:
        {
            "success": true,
            "message": "Started task T001",
            "task": {...}
        }
    """
    from app.services.director_service import DirectorService

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        director = DirectorService(db)
        success, message = director.start_task(task)

        db.refresh(task)

        return JsonResponse({
            "success": success,
            "message": message,
            "task": task.to_dict()
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_loop_back(request, task_id):
    """Loop a task back to DEV stage (e.g., after QA/SEC failure).

    POST /api/tasks/{task_id}/loop-back

    Body:
        {
            "reason": "Tests failed - need to fix validation"
        }

    Returns:
        {
            "success": true,
            "message": "Looped back from qa to DEV",
            "task": {...}
        }
    """
    from app.services.director_service import DirectorService

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        data = json.loads(request.body) if request.body else {}

        # Create failure report
        report = AgentReport(
            run_id=task.run_id or 0,
            role=AgentRole.QA,
            status=ReportStatus.FAIL,
            summary=data.get("reason", "Looped back by user")
        )

        director = DirectorService(db)
        success, message = director._loop_back_to_dev(task, report)

        db.refresh(task)

        return JsonResponse({
            "success": success,
            "message": message,
            "task": task.to_dict()
        })
    finally:
        db.close()


# --- Task Details ---

def task_details(request, task_id):
    """Get full task details for editing.

    GET /api/tasks/{task_id}/details
    """
    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)
        return JsonResponse({"task": task.to_dict()})
    finally:
        db.close()


# --- Director Control Panel ---

# Global variable to track director daemon state
_director_daemon_thread = None
_director_daemon_running = False
_director_settings = {
    "poll_interval": 30,
    "auto_start": False,
    "enforce_tdd": True,
    "enforce_dry": True,
    "enforce_security": True,
    "include_images": False,  # Enable multimodal image processing in agent prompts
    "vision_model": "ai/qwen3-vl",  # Model to use for image analysis (ai/gemma3, ai/qwen3-vl)
}


def director_status(request):
    """Get Director daemon status and statistics.

    GET /api/director/status
    """
    global _director_daemon_running, _director_settings

    db = next(get_db())
    try:
        # Count director actions from audit log
        from app.models.audit import AuditEvent
        from datetime import datetime, timedelta

        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        one_day_ago = datetime.utcnow() - timedelta(days=1)

        tasks_reviewed_hour = db.query(AuditEvent).filter(
            AuditEvent.actor == "director",
            AuditEvent.timestamp >= one_hour_ago
        ).count()

        tasks_reviewed_day = db.query(AuditEvent).filter(
            AuditEvent.actor == "director",
            AuditEvent.timestamp >= one_day_ago
        ).count()

        total_actions = db.query(AuditEvent).filter(
            AuditEvent.actor == "director"
        ).count()

        # Get recent activity
        recent_activity = db.query(AuditEvent).filter(
            AuditEvent.actor == "director"
        ).order_by(AuditEvent.timestamp.desc()).limit(10).all()

        return JsonResponse({
            "running": _director_daemon_running,
            "settings": _director_settings,
            "stats": {
                "tasks_reviewed_hour": tasks_reviewed_hour,
                "tasks_reviewed_day": tasks_reviewed_day,
                "total_actions": total_actions
            },
            "recent_activity": [e.to_dict() for e in recent_activity]
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def director_start(request):
    """Start the Director daemon.

    POST /api/director/start
    """
    global _director_daemon_thread, _director_daemon_running, _director_settings

    if _director_daemon_running:
        return JsonResponse({"status": "already_running", "message": "Director is already running"})

    data = _get_json_body(request) or {}
    run_id = data.get("run_id")
    poll_interval = data.get("poll_interval", _director_settings["poll_interval"])

    from app.services.director_service import run_director_daemon

    def daemon_wrapper():
        global _director_daemon_running
        _director_daemon_running = True
        try:
            run_director_daemon(get_db, run_id=run_id, poll_interval=poll_interval)
        finally:
            _director_daemon_running = False

    _director_daemon_thread = threading.Thread(target=daemon_wrapper, daemon=True)
    _director_daemon_thread.start()

    return JsonResponse({
        "status": "started",
        "message": f"Director started with poll interval {poll_interval}s",
        "run_id": run_id
    })


@csrf_exempt
@require_http_methods(["POST"])
def director_stop(request):
    """Stop the Director daemon.

    POST /api/director/stop

    Note: This sets a flag - the daemon will stop on next poll cycle.
    """
    global _director_daemon_running

    if not _director_daemon_running:
        return JsonResponse({"status": "not_running", "message": "Director is not running"})

    # Signal stop (daemon checks this and exits)
    _director_daemon_running = False

    return JsonResponse({
        "status": "stopping",
        "message": "Director will stop on next poll cycle"
    })


@csrf_exempt
@require_http_methods(["POST"])
def director_settings_update(request):
    """Update Director settings.

    POST /api/director/settings
    """
    global _director_settings

    data = _get_json_body(request) or {}

    if "poll_interval" in data:
        _director_settings["poll_interval"] = int(data["poll_interval"])
    if "auto_start" in data:
        _director_settings["auto_start"] = bool(data["auto_start"])
    if "enforce_tdd" in data:
        _director_settings["enforce_tdd"] = bool(data["enforce_tdd"])
    if "enforce_dry" in data:
        _director_settings["enforce_dry"] = bool(data["enforce_dry"])
    if "enforce_security" in data:
        _director_settings["enforce_security"] = bool(data["enforce_security"])
    if "include_images" in data:
        _director_settings["include_images"] = bool(data["include_images"])
    if "vision_model" in data:
        _director_settings["vision_model"] = str(data["vision_model"])

    return JsonResponse({
        "status": "updated",
        "settings": _director_settings
    })


def director_activity(request):
    """Get recent Director activity.

    GET /api/director/activity
    """
    db = next(get_db())
    try:
        from app.models.audit import AuditEvent

        limit = int(request.GET.get("limit", 50))
        activity = db.query(AuditEvent).filter(
            AuditEvent.actor == "director"
        ).order_by(AuditEvent.timestamp.desc()).limit(limit).all()

        return JsonResponse({
            "activity": [e.to_dict() for e in activity],
            "count": len(activity)
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def director_run_cycle(request):
    """Run a single Director orchestration cycle.

    POST /api/director/run-cycle

    This runs the algorithmic orchestration without needing the daemon:
    - Auto-starts BACKLOG tasks if there's bandwidth
    - Advances tasks that have passing reports
    - Tracks/retries stuck tasks

    Returns:
        {
            "started": [...],
            "advanced": [...],
            "retried": [...],
            "blocked": [...]
        }
    """
    from app.services.director_service import TaskOrchestrator

    db = next(get_db())
    try:
        orchestrator = TaskOrchestrator(db)
        result = orchestrator.run_cycle()

        # Add summary counts
        result["summary"] = {
            "started_count": len(result["started"]),
            "advanced_count": len(result["advanced"]),
            "retried_count": len(result["retried"]),
            "blocked_count": len(result["blocked"]),
            "total_actions": (len(result["started"]) + len(result["advanced"]) +
                            len(result["retried"]) + len(result["blocked"]))
        }

        return JsonResponse(result)
    finally:
        db.close()


# =============================================================================
# Proof-of-Work Endpoints
# =============================================================================

def task_proof_history(request, task_id):
    """Get complete proof history for a task (database-backed).

    GET /api/tasks/{task_id}/proof-history

    Returns all proofs ever created for this task across all runs.
    Optimized for agent context and project memory.

    Query params:
        - stage: Filter by stage (dev, qa, sec, docs)
        - format: 'full' or 'compact' (default: full)
    """
    from app.models.proof import Proof

    stage = request.GET.get("stage")
    fmt = request.GET.get("format", "full")

    db = next(get_db())
    try:
        query = db.query(Proof).filter(Proof.task_id == task_id)

        if stage:
            query = query.filter(Proof.stage == stage)

        proofs = query.order_by(Proof.created_at.desc()).all()

        if fmt == "compact":
            # Compact format for agent memory
            return JsonResponse({
                "task_id": task_id,
                "proofs": [p.to_agent_context() for p in proofs],
                "count": len(proofs)
            })
        else:
            return JsonResponse({
                "task_id": task_id,
                "proofs": [p.to_dict() for p in proofs],
                "count": len(proofs)
            })
    finally:
        db.close()


def project_proof_history(request, project_id):
    """Get proof history for entire project (database-backed).

    GET /api/projects/{project_id}/proof-history

    Returns all proofs for all tasks in the project.
    Useful for project-level memory and history.

    Query params:
        - stage: Filter by stage
        - task_id: Filter by specific task
        - limit: Max results (default 100)
    """
    from app.models.proof import Proof

    stage = request.GET.get("stage")
    task_filter = request.GET.get("task_id")
    limit = int(request.GET.get("limit", 100))

    db = next(get_db())
    try:
        query = db.query(Proof).filter(Proof.project_id == project_id)

        if stage:
            query = query.filter(Proof.stage == stage)
        if task_filter:
            query = query.filter(Proof.task_id == int(task_filter))

        proofs = query.order_by(Proof.created_at.desc()).limit(limit).all()

        # Group by task for easier agent consumption
        by_task = {}
        for p in proofs:
            if p.task_id not in by_task:
                by_task[p.task_id] = []
            by_task[p.task_id].append(p.to_agent_context())

        return JsonResponse({
            "project_id": project_id,
            "proofs": [p.to_dict() for p in proofs],
            "by_task": by_task,
            "count": len(proofs)
        })
    finally:
        db.close()


def proof_list(request, entity_type, entity_id):
    """List proof artifacts for a run or task.

    GET /api/runs/{run_id}/proofs
    GET /api/tasks/{task_id}/proofs

    Query params:
        - stage: Filter by stage (dev, qa, sec, docs)
    """
    from app.services.proof_service import ProofService

    if entity_type not in ("runs", "tasks"):
        return JsonResponse({"error": "Invalid entity type"}, status=400)

    # Map URL path to entity type
    etype = "run" if entity_type == "runs" else "task"
    stage = request.GET.get("stage")

    db = next(get_db())
    try:
        service = ProofService(db)
        proofs = service.list_proofs(etype, entity_id, stage)

        return JsonResponse({
            "entity_type": etype,
            "entity_id": entity_id,
            "proofs": proofs,
            "count": len(proofs)
        })
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=404)
    finally:
        db.close()


def proof_summary(request, entity_type, entity_id):
    """Get proof summary for a run or task.

    GET /api/runs/{run_id}/proofs/summary
    GET /api/tasks/{task_id}/proofs/summary
    """
    from app.services.proof_service import ProofService

    if entity_type not in ("runs", "tasks"):
        return JsonResponse({"error": "Invalid entity type"}, status=400)

    etype = "run" if entity_type == "runs" else "task"

    db = next(get_db())
    try:
        service = ProofService(db)
        summary = service.get_proof_summary(etype, entity_id)

        return JsonResponse({
            "entity_type": etype,
            "entity_id": entity_id,
            "summary": summary
        })
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=404)
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def proof_upload(request, entity_type, entity_id):
    """Upload a proof artifact.

    POST /api/runs/{run_id}/proofs/upload
    POST /api/tasks/{task_id}/proofs/upload

    Body (multipart/form-data or JSON):
        - stage: Pipeline stage (dev, qa, sec, docs)
        - proof_type: Type of proof (screenshot, log, report)
        - description: Optional description
        - file: File data (for multipart)
        - content: Base64 encoded content (for JSON)
    """
    from app.services.proof_service import ProofService
    import base64

    if entity_type not in ("runs", "tasks"):
        return JsonResponse({"error": "Invalid entity type"}, status=400)

    etype = "run" if entity_type == "runs" else "task"

    db = next(get_db())
    try:
        service = ProofService(db)

        # Handle multipart form data
        if request.content_type and "multipart/form-data" in request.content_type:
            stage = request.POST.get("stage", "dev")
            proof_type = request.POST.get("proof_type", "screenshot")
            description = request.POST.get("description", "")

            if "file" not in request.FILES:
                return JsonResponse({"error": "No file provided"}, status=400)

            uploaded_file = request.FILES["file"]
            content = uploaded_file.read()
            ext = os.path.splitext(uploaded_file.name)[1].lower() or ".bin"
            
            # Auto-detect proof type from extension if user left it as default 'screenshot'
            # but uploaded a non-image file
            if proof_type == "screenshot" and ext not in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"]:
                if ext in [".csv", ".json", ".xml", ".html", ".md", ".txt", ".log"]:
                    proof_type = "log"
                elif ext in [".pdf", ".docx"]:
                    proof_type = "report"
            
        else:
            # Handle JSON with base64 content
            data = _get_json_body(request)
            if not data:
                return JsonResponse({"error": "Invalid JSON"}, status=400)

            stage = data.get("stage", "dev")
            proof_type = data.get("proof_type", "screenshot")
            description = data.get("description", "")
            content_b64 = data.get("content")

            if not content_b64:
                return JsonResponse({"error": "content (base64) required"}, status=400)

            try:
                content = base64.b64decode(content_b64)
            except Exception:
                return JsonResponse({"error": "Invalid base64 content"}, status=400)

            ext = data.get("extension", ".png")

        result = service.save_proof(
            entity_type=etype,
            entity_id=entity_id,
            stage=stage,
            proof_type=proof_type,
            content=content,
            extension=ext,
            description=description
        )

        # Save proof metadata to database for querying
        from app.models.proof import Proof, ProofType as ProofTypeEnum
        import mimetypes

        # Get task_id and project_id
        if etype == "task":
            task = db.query(Task).filter(Task.id == entity_id).first()
            task_id = entity_id
            project_id = task.project_id if task else None
            run_id = task.run_id if task else None
        else:  # run
            run = db.query(Run).filter(Run.id == entity_id).first()
            run_id = entity_id
            project_id = run.project_id if run else None
            # Try to find associated task
            task = db.query(Task).filter(Task.run_id == entity_id).first()
            task_id = task.id if task else None

        if task_id and project_id:
            # Map proof_type string to enum
            proof_type_enum = {
                "screenshot": ProofTypeEnum.SCREENSHOT,
                "log": ProofTypeEnum.LOG,
                "report": ProofTypeEnum.REPORT,
                "test_result": ProofTypeEnum.TEST_RESULT,
                "code_diff": ProofTypeEnum.CODE_DIFF,
            }.get(proof_type, ProofTypeEnum.OTHER)

            mime_type, _ = mimetypes.guess_type(result["filename"])

            proof_record = Proof(
                project_id=project_id,
                task_id=task_id,
                run_id=run_id,
                stage=stage,
                filename=result["filename"],
                filepath=result["path"],
                proof_type=proof_type_enum,
                file_size=result["size"],
                mime_type=mime_type,
                description=description,
                created_by="agent" if etype == "run" else "human"
            )
            db.add(proof_record)
            db.commit()
            result["proof_id"] = proof_record.id

        log_event(db, "agent", "upload_proof", etype, entity_id, {
            "stage": stage,
            "proof_type": proof_type,
            "size": result["size"]
        })

        return JsonResponse({"success": True, "proof": result}, status=201)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=404)
    finally:
        db.close()


def proof_view(request, entity_type, entity_id, filename):
    """View/download a proof artifact.

    GET /api/runs/{run_id}/proofs/{stage}/{filename}
    GET /api/tasks/{task_id}/proofs/{stage}/{filename}
    """
    from app.services.proof_service import ProofService
    import mimetypes

    if entity_type not in ("runs", "tasks"):
        return JsonResponse({"error": "Invalid entity type"}, status=400)

    etype = "run" if entity_type == "runs" else "task"

    # Extract stage from filename path
    parts = filename.split("/")
    if len(parts) == 2:
        stage, fname = parts
    else:
        stage = None
        fname = filename

    db = next(get_db())
    try:
        service = ProofService(db)

        if etype == "run":
            proof_dir = service.get_run_proof_dir(entity_id, stage)
        else:
            proof_dir = service.get_task_proof_dir(entity_id, stage)

        filepath = proof_dir / fname

        if not filepath.exists():
            return JsonResponse({"error": "Proof not found"}, status=404)

        # Security: ensure path is within proof directory
        try:
            filepath.resolve().relative_to(proof_dir.resolve())
        except ValueError:
            return JsonResponse({"error": "Invalid path"}, status=400)

        content_type, _ = mimetypes.guess_type(str(filepath))
        content_type = content_type or "application/octet-stream"

        with open(filepath, "rb") as f:
            response = HttpResponse(f.read(), content_type=content_type)
            response["Content-Disposition"] = f'inline; filename="{fname}"'
            return response
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=404)
    finally:
        db.close()


def proof_download(request, task_id, proof_id):
    """Download a proof artifact by database ID.

    GET /api/tasks/{task_id}/proofs/{proof_id}/download

    Uses the database record to locate and serve the file.
    This is the preferred method for agents - get proof history first,
    then download specific proofs by ID.
    """
    import mimetypes
    from app.models.proof import Proof

    db = next(get_db())
    try:
        proof = db.query(Proof).filter(
            Proof.id == proof_id,
            Proof.task_id == task_id
        ).first()

        if not proof:
            return JsonResponse({"error": "Proof not found"}, status=404)

        filepath = proof.filepath
        if not os.path.exists(filepath):
            return JsonResponse({
                "error": "Proof file not found on disk",
                "db_record": proof.to_dict()
            }, status=404)

        content_type = proof.mime_type
        if not content_type:
            content_type, _ = mimetypes.guess_type(filepath)
            content_type = content_type or "application/octet-stream"

        with open(filepath, "rb") as f:
            response = HttpResponse(f.read(), content_type=content_type)
            response["Content-Disposition"] = f'attachment; filename="{proof.filename}"'
            return response
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["DELETE", "POST"])
def proof_clear(request, entity_type, entity_id):
    """Clear proof artifacts.

    DELETE /api/runs/{run_id}/proofs
    DELETE /api/tasks/{task_id}/proofs

    Query params:
        - stage: Optional - only clear specific stage
    """
    from app.services.proof_service import ProofService

    if entity_type not in ("runs", "tasks"):
        return JsonResponse({"error": "Invalid entity type"}, status=400)

    etype = "run" if entity_type == "runs" else "task"
    stage = request.GET.get("stage")

    db = next(get_db())
    try:
        service = ProofService(db)
        count = service.clear_proofs(etype, entity_id, stage)

        log_event(db, "human", "clear_proofs", etype, entity_id, {
            "stage": stage,
            "files_removed": count
        })

        return JsonResponse({
            "success": True,
            "files_removed": count
        })
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=404)
    finally:
        db.close()


# =============================================================================
# Handoff Endpoints (Task-Centric Agent Work Cycles)
# =============================================================================

def task_handoff_current(request, task_id):
    """Get the current pending/in_progress handoff for a task.

    GET /api/tasks/{task_id}/handoff

    Returns the handoff that an agent should work on.
    Includes full context (structured + markdown).
    """
    from app.services import handoff_service

    db = next(get_db())
    try:
        handoff = handoff_service.get_current_handoff(db, task_id)

        if not handoff:
            return JsonResponse({
                "task_id": task_id,
                "handoff": None,
                "message": "No pending handoff for this task"
            })

        return JsonResponse({
            "task_id": task_id,
            "handoff": handoff.to_dict()
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_handoff_create(request, task_id):
    """Create a new handoff for a task.

    POST /api/tasks/{task_id}/handoff/create

    Body:
        - to_role: Agent role that should pick this up (dev, qa, sec, docs, pm)
        - stage: Pipeline stage (required)
        - run_id: Optional run ID for context
        - from_role: Previous agent role (optional)
        - created_by: Who created this (default: "system")
        - write_file: Whether to write context to file (default: true)

    Returns the created handoff with full context.
    """
    from app.services import handoff_service

    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    to_role = data.get("to_role")
    stage = data.get("stage")

    if not to_role:
        return JsonResponse({"error": "to_role is required"}, status=400)
    if not stage:
        return JsonResponse({"error": "stage is required"}, status=400)

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        # Check for existing pending handoff
        existing = handoff_service.get_current_handoff(db, task_id)
        if existing:
            return JsonResponse({
                "error": "Task already has a pending handoff",
                "existing_handoff_id": existing.id
            }, status=400)

        handoff = handoff_service.create_handoff(
            db=db,
            task_id=task_id,
            to_role=to_role,
            stage=stage,
            project_id=data.get("project_id"),
            run_id=data.get("run_id"),
            from_role=data.get("from_role"),
            created_by=data.get("created_by", "system"),
            write_file=data.get("write_file", True)
        )

        log_event(db, "system", "create_handoff", "task", task_id, {
            "handoff_id": handoff.id,
            "to_role": to_role,
            "stage": stage
        })

        return JsonResponse({
            "handoff": handoff.to_dict()
        }, status=201)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_handoff_accept(request, task_id):
    """Accept a handoff (agent starting work).

    POST /api/tasks/{task_id}/handoff/accept

    Body:
        - handoff_id: Optional specific handoff ID (uses current if not provided)

    Marks the handoff as IN_PROGRESS.
    """
    from app.services import handoff_service

    data = _get_json_body(request) or {}
    handoff_id = data.get("handoff_id")

    db = next(get_db())
    try:
        # Get handoff - either specified or current
        if handoff_id:
            handoff = handoff_service.get_handoff_by_id(db, handoff_id)
            if not handoff or handoff.task_id != task_id:
                return JsonResponse({"error": "Handoff not found for this task"}, status=404)
        else:
            handoff = handoff_service.get_current_handoff(db, task_id)
            if not handoff:
                return JsonResponse({"error": "No pending handoff for this task"}, status=404)

        handoff = handoff_service.accept_handoff(db, handoff.id)

        log_event(db, "agent", "accept_handoff", "task", task_id, {
            "handoff_id": handoff.id,
            "to_role": handoff.to_role,
            "stage": handoff.stage
        })

        return JsonResponse({
            "success": True,
            "handoff": handoff.to_dict()
        })
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_handoff_complete(request, task_id):
    """Complete a handoff with the agent's report.

    POST /api/tasks/{task_id}/handoff/complete

    Body:
        - handoff_id: Optional specific handoff ID (uses current if not provided)
        - report_status: "pass" or "fail" (required)
        - report_summary: Summary of what agent did (required)
        - report_details: Full report details as JSON (optional)
        - agent_report_id: Link to AgentReport record (optional)

    Marks the handoff as COMPLETED with the report.
    """
    from app.services import handoff_service

    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    report_status = data.get("report_status")
    if not report_status:
        return JsonResponse({"error": "report_status is required"}, status=400)
    if report_status not in ("pass", "fail"):
        return JsonResponse({"error": "report_status must be 'pass' or 'fail'"}, status=400)

    handoff_id = data.get("handoff_id")

    db = next(get_db())
    try:
        # Get handoff - either specified or current in_progress
        if handoff_id:
            handoff = handoff_service.get_handoff_by_id(db, handoff_id)
            if not handoff or handoff.task_id != task_id:
                return JsonResponse({"error": "Handoff not found for this task"}, status=404)
        else:
            handoff = handoff_service.get_current_handoff(db, task_id)
            if not handoff:
                return JsonResponse({"error": "No in-progress handoff for this task"}, status=404)

        handoff = handoff_service.complete_handoff(
            db=db,
            handoff_id=handoff.id,
            report_status=report_status,
            report_summary=data.get("report_summary"),
            report_details=data.get("report_details"),
            agent_report_id=data.get("agent_report_id")
        )

        log_event(db, "agent", "complete_handoff", "task", task_id, {
            "handoff_id": handoff.id,
            "to_role": handoff.to_role,
            "stage": handoff.stage,
            "report_status": report_status
        })

        return JsonResponse({
            "success": True,
            "handoff": handoff.to_dict()
        })
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_handoff_fail(request, task_id):
    """Mark a handoff as failed (timeout, error, etc.).

    POST /api/tasks/{task_id}/handoff/fail

    Body:
        - handoff_id: Optional specific handoff ID (uses current if not provided)
        - reason: Reason for failure (optional)

    Marks the handoff as FAILED.
    """
    from app.services import handoff_service

    data = _get_json_body(request) or {}
    handoff_id = data.get("handoff_id")
    reason = data.get("reason")

    db = next(get_db())
    try:
        # Get handoff - either specified or current
        if handoff_id:
            handoff = handoff_service.get_handoff_by_id(db, handoff_id)
            if not handoff or handoff.task_id != task_id:
                return JsonResponse({"error": "Handoff not found for this task"}, status=404)
        else:
            handoff = handoff_service.get_current_handoff(db, task_id)
            if not handoff:
                return JsonResponse({"error": "No active handoff for this task"}, status=404)

        handoff = handoff_service.fail_handoff(db, handoff.id, reason)

        log_event(db, "system", "fail_handoff", "task", task_id, {
            "handoff_id": handoff.id,
            "reason": reason
        })

        return JsonResponse({
            "success": True,
            "handoff": handoff.to_dict()
        })
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    finally:
        db.close()


def task_handoff_history(request, task_id):
    """Get handoff history for a task.

    GET /api/tasks/{task_id}/handoff/history

    Query params:
        - stage: Filter by pipeline stage
        - limit: Max results (default: 50)
        - format: 'full' or 'compact' (default: full)

    Returns all handoffs for the task, ordered by creation date (newest first).
    Used for agent memory - understanding previous work cycles.
    """
    from app.services import handoff_service

    stage = request.GET.get("stage")
    limit = int(request.GET.get("limit", 50))
    fmt = request.GET.get("format", "full")

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        handoffs = handoff_service.get_handoff_history(
            db=db,
            task_id=task_id,
            stage=stage,
            limit=limit
        )

        if fmt == "compact":
            return JsonResponse({
                "task_id": task_id,
                "handoffs": [h.to_agent_context() for h in handoffs],
                "count": len(handoffs)
            })
        else:
            return JsonResponse({
                "task_id": task_id,
                "handoffs": [h.to_dict() for h in handoffs],
                "count": len(handoffs)
            })
    finally:
        db.close()


def project_handoff_history(request, project_id):
    """Get handoff history for a project.

    GET /api/projects/{project_id}/handoff/history

    Query params:
        - stage: Filter by pipeline stage
        - task_id: Filter by specific task
        - limit: Max results (default: 100)

    Returns all handoffs for the project, useful for project-level memory.
    """
    from app.services import handoff_service

    stage = request.GET.get("stage")
    task_filter = request.GET.get("task_id")
    limit = int(request.GET.get("limit", 100))

    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return JsonResponse({"error": "Project not found"}, status=404)

        handoffs = handoff_service.get_handoff_history(
            db=db,
            project_id=project_id,
            task_id=int(task_filter) if task_filter else None,
            stage=stage,
            limit=limit
        )

        # Group by task for easier consumption
        by_task = {}
        for h in handoffs:
            if h.task_id not in by_task:
                by_task[h.task_id] = []
            by_task[h.task_id].append(h.to_agent_context())

        return JsonResponse({
            "project_id": project_id,
            "handoffs": [h.to_dict() for h in handoffs],
            "by_task": by_task,
            "count": len(handoffs)
        })
    finally:
        db.close()


# =============================================================================
# Deployment Endpoints
# =============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def run_deploy(request, run_id):
    """Start deployment for a run.

    POST /api/runs/{run_id}/deploy

    Body:
        - environment_id: ID of environment to deploy to
        - approved_by: Name of approver (optional)

    Returns deployment record and initiates deployment in background.
    """
    from app.services.deployment_service import DeploymentService

    data = _get_json_body(request) or {}
    environment_id = data.get("environment_id")
    approved_by = data.get("approved_by")

    if not environment_id:
        return JsonResponse({"error": "environment_id is required"}, status=400)

    db = next(get_db())
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JsonResponse({"error": "Run not found"}, status=404)

        # Check run is in deployable state
        if run.state not in (RunState.READY_FOR_DEPLOY, RunState.TESTING):
            return JsonResponse({
                "error": f"Run must be in READY_FOR_DEPLOY or TESTING state, currently: {run.state.value}"
            }, status=400)

        service = DeploymentService(db)

        # Start deployment
        deployment, error = service.start_deployment(
            run_id=run_id,
            environment_id=environment_id,
            approved_by=approved_by,
            triggered_by="human" if approved_by else "agent"
        )

        if error:
            return JsonResponse({"error": error}, status=400)

        # Execute deployment in background
        def execute_async():
            from app.db import get_db
            db_session = next(get_db())
            try:
                svc = DeploymentService(db_session)
                svc.complete_deployment_flow(run_id, environment_id, approved_by)
            finally:
                db_session.close()

        thread = threading.Thread(target=execute_async, daemon=True)
        thread.start()

        return JsonResponse({
            "deployment": deployment.to_dict(),
            "message": "Deployment started",
            "status": "deploying"
        }, status=202)
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def run_rollback(request, run_id):
    """Rollback a deployment.

    POST /api/runs/{run_id}/rollback

    Body:
        - deployment_id: ID of deployment to rollback from (optional, defaults to latest)
        - target_deployment_id: ID of deployment to rollback to (optional)
        - reason: Reason for rollback

    Returns new rollback deployment record.
    """
    from app.services.deployment_service import DeploymentService

    data = _get_json_body(request) or {}
    deployment_id = data.get("deployment_id")
    target_deployment_id = data.get("target_deployment_id")
    reason = data.get("reason", "Manual rollback requested")

    db = next(get_db())
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JsonResponse({"error": "Run not found"}, status=404)

        service = DeploymentService(db)

        # If no deployment_id specified, find the latest for this run
        if not deployment_id:
            from app.models.deployment_history import DeploymentHistory
            latest = db.query(DeploymentHistory).filter(
                DeploymentHistory.run_id == run_id
            ).order_by(DeploymentHistory.created_at.desc()).first()

            if not latest:
                return JsonResponse({"error": "No deployments found for this run"}, status=404)
            deployment_id = latest.id

        # Perform rollback
        rollback_deployment, error = service.rollback(
            deployment_id=deployment_id,
            reason=reason,
            triggered_by="human",
            target_deployment_id=target_deployment_id
        )

        if error:
            return JsonResponse({"error": error}, status=400)

        # Execute rollback in background
        def execute_async():
            from app.db import get_db
            db_session = next(get_db())
            try:
                svc = DeploymentService(db_session)
                success, output = svc.execute_deployment(rollback_deployment.id)
                if success:
                    svc.run_health_check(rollback_deployment.id)
            finally:
                db_session.close()

        thread = threading.Thread(target=execute_async, daemon=True)
        thread.start()

        return JsonResponse({
            "rollback": rollback_deployment.to_dict(),
            "message": "Rollback started",
            "status": "rolling_back"
        }, status=202)
    finally:
        db.close()


def run_deployments(request, run_id):
    """Get deployment history for a run.

    GET /api/runs/{run_id}/deployments
    """
    from app.services.deployment_service import DeploymentService

    db = next(get_db())
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JsonResponse({"error": "Run not found"}, status=404)

        service = DeploymentService(db)
        deployments = service.get_deployment_history(run_id=run_id)

        return JsonResponse({
            "run_id": run_id,
            "deployments": [d.to_dict() for d in deployments],
            "count": len(deployments)
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["DELETE", "POST"])  # Allow POST as fallback for fetch
def project_delete(request, project_id):
    """Delete a project and all its related data."""
    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return JsonResponse({"error": "Project not found"}, status=404)
        
        project_name = project.name
        
        # Delete the project (cascading deletes will handle related records)
        db.delete(project)
        db.commit()
        
        log_event(db, "human", "delete", "project", project_id, {"name": project_name})
        return JsonResponse({"success": True, "message": f"Project '{project_name}' deleted successfully"})
    except Exception as e:
        db.rollback()
        return JsonResponse({"error": str(e)}, status=500)
    finally:
        db.close()


# --- LLM Service Endpoints ---
# Direct access to Docker Model Runner for lightweight completions without Goose

@csrf_exempt
@require_http_methods(["GET"])
def llm_models(request):
    """List available LLM models from Docker Model Runner.

    GET /api/llm/models
    """
    from app.services.llm_service import get_llm_service

    try:
        service = get_llm_service()
        models = service.list_models()
        return JsonResponse({"models": models})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=503)


@csrf_exempt
@require_http_methods(["POST"])
def llm_complete(request):
    """Generic LLM completion.

    POST /api/llm/complete
    Body: {"prompt": "...", "system_prompt": "...", "model": "...", "temperature": 0.7}
    """
    from app.services.llm_service import get_llm_service

    data = _get_json_body(request)
    if not data or "prompt" not in data:
        return JsonResponse({"error": "prompt is required"}, status=400)

    try:
        service = get_llm_service()
        content = service.complete(
            prompt=data["prompt"],
            system_prompt=data.get("system_prompt"),
            model=data.get("model"),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens")
        )
        return JsonResponse({
            "content": content,
            "model": data.get("model", service.default_model)
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=503)


@csrf_exempt
@require_http_methods(["POST"])
def llm_chat(request):
    """LLM chat completion with message history.

    POST /api/llm/chat
    Body: {"messages": [{"role": "user", "content": "..."}], "model": "...", "temperature": 0.7}
    """
    from app.services.llm_service import get_llm_service

    data = _get_json_body(request)
    if not data or "messages" not in data:
        return JsonResponse({"error": "messages array is required"}, status=400)

    try:
        service = get_llm_service()
        content = service.chat(
            messages=data["messages"],
            model=data.get("model"),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens")
        )
        return JsonResponse({
            "content": content,
            "model": data.get("model", service.default_model)
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=503)


@csrf_exempt
@require_http_methods(["POST"])
def llm_enrich_docs(request):
    """Enrich code with documentation.

    POST /api/llm/enrich-docs
    Body: {"code": "...", "language": "python", "include_examples": true}
    """
    from app.services.llm_service import get_llm_service

    data = _get_json_body(request)
    if not data or "code" not in data:
        return JsonResponse({"error": "code is required"}, status=400)

    try:
        service = get_llm_service()
        docs = service.enrich_documentation(
            code=data["code"],
            language=data.get("language", "python"),
            include_examples=data.get("include_examples", True)
        )
        return JsonResponse({"documentation": docs})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=503)


@csrf_exempt
@require_http_methods(["POST"])
def llm_review_code(request):
    """Get code review suggestions.

    POST /api/llm/review-code
    Body: {"code": "...", "context": "...", "focus_areas": ["bugs", "security"]}
    """
    from app.services.llm_service import get_llm_service

    data = _get_json_body(request)
    if not data or "code" not in data:
        return JsonResponse({"error": "code is required"}, status=400)

    try:
        service = get_llm_service()
        review = service.review_code(
            code=data["code"],
            context=data.get("context", ""),
            focus_areas=data.get("focus_areas")
        )
        return JsonResponse({"review": review})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=503)


@csrf_exempt
@require_http_methods(["POST"])
def llm_requirements(request):
    """Generate requirements from description.

    POST /api/llm/requirements
    Body: {"description": "...", "output_format": "json"}
    """
    from app.services.llm_service import get_llm_service

    data = _get_json_body(request)
    if not data or "description" not in data:
        return JsonResponse({"error": "description is required"}, status=400)

    try:
        service = get_llm_service()
        requirements = service.generate_requirements(
            description=data["description"],
            output_format=data.get("output_format", "json")
        )
        return JsonResponse({"requirements": requirements})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=503)


@csrf_exempt
@require_http_methods(["POST"])
def llm_summarize(request):
    """Summarize text.

    POST /api/llm/summarize
    Body: {"text": "...", "max_sentences": 3, "style": "concise"}
    """
    from app.services.llm_service import get_llm_service

    data = _get_json_body(request)
    if not data or "text" not in data:
        return JsonResponse({"error": "text is required"}, status=400)

    try:
        service = get_llm_service()
        summary = service.summarize(
            text=data["text"],
            max_sentences=data.get("max_sentences", 3),
            style=data.get("style", "concise")
        )
        return JsonResponse({"summary": summary})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=503)


@csrf_exempt
@require_http_methods(["POST"])
def llm_extract_json(request):
    """Extract structured JSON from text.

    POST /api/llm/extract-json
    Body: {"text": "...", "schema_hint": "..."}
    """
    from app.services.llm_service import get_llm_service

    data = _get_json_body(request)
    if not data or "text" not in data:
        return JsonResponse({"error": "text is required"}, status=400)

    try:
        service = get_llm_service()
        extracted = service.extract_json(
            text=data["text"],
            schema_hint=data.get("schema_hint")
        )
        return JsonResponse({"data": extracted})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=503)


@csrf_exempt
@require_http_methods(["POST"])
def llm_query(request):
    """Dynamic LLM query with automatic context building.

    POST /api/llm/query

    This is the main flexible endpoint for LLM queries. It automatically
    builds context from project/run/task IDs and can optionally save
    results directly to entity fields.

    Body:
    {
        "prompt": "Your query here",
        "project_id": 741,           // Optional - adds project context
        "run_id": 45,                // Optional - adds run context
        "task_id": 123,              // Optional - adds task context
        "role": "qa",                // Optional - use RoleConfig from DB (dev, qa, security, etc.)
        "session": "task_123",       // Optional - enable session-based conversation
        "system_prompt": "...",      // Optional - system instructions (combined with role if both set)
        "save_to": "project.741.description",  // Optional - flexible targeting (see formats below)
        "include_context": true,     // Optional - default true
        "temperature": 0.7,          // Optional - default 0.7
        "model": "ai/qwen3-coder",   // Optional - model to use
        "output_json": false         // Optional - parse result as JSON
    }

    Returns:
    {
        "content": "Generated text...",
        "context": {"project": {...}, "run": {...}, "task": {...}},
        "saved": true,
        "saved_to": {"entity": "project", "field": "description"},
        "model": "ai/qwen3-coder",
        "tokens_estimate": 1234,
        "parsed": {...},  // If output_json=true
        "session": {"id": 1, "name": "task_123", "message_count": 4, "resumed": true}  // If session used
    }

    Examples:
        # Summarize a project
        curl -X POST http://localhost:8000/api/llm/query -d '{
            "prompt": "Summarize this project in 3 sentences",
            "project_id": 741
        }'

        # Generate and save objectives (uses project_id from context)
        curl -X POST http://localhost:8000/api/llm/query -d '{
            "prompt": "Generate 5 project objectives as a bullet list",
            "project_id": 741,
            "save_to": "objectives"
        }'

        # Save with explicit targeting
        curl -X POST http://localhost:8000/api/llm/query -d '{
            "prompt": "Generate tech stack description",
            "save_to": "project.741.tech_stack"
        }'

        # Save with filter (finds by name)
        curl -X POST http://localhost:8000/api/llm/query -d '{
            "prompt": "Generate description",
            "save_to": "project[name=Workflow Hub].description"
        }'

        # Generate test cases for a task
        curl -X POST http://localhost:8000/api/llm/query -d '{
            "prompt": "Generate unit test cases for this task",
            "task_id": 123,
            "system_prompt": "You are a QA engineer specializing in Python testing"
        }'
    """
    from app.services.llm_service import query_llm, LLMQuery

    data = _get_json_body(request)
    if not data or "prompt" not in data:
        return JsonResponse({"error": "prompt is required"}, status=400)

    db = next(get_db())
    try:
        # Use the fluent API for more control
        query = LLMQuery(
            project_id=data.get("project_id"),
            run_id=data.get("run_id"),
            task_id=data.get("task_id"),
            db_session=db
        )

        query.prompt(data["prompt"])

        if data.get("system_prompt"):
            query.system(data["system_prompt"])

        # Flexible save targeting - supports multiple formats:
        # - "field" (uses context IDs)
        # - "table.field" (uses context ID for table)
        # - "table.123.field" (explicit ID)
        # - "table[col=val].field" (where clause - ORM parameterized, SQL-injection safe)
        if data.get("save_to"):
            query.save_to(data["save_to"])

        query.with_context(data.get("include_context", True))
        query.temperature(data.get("temperature", 0.7))

        if data.get("max_tokens"):
            query.max_tokens(data["max_tokens"])

        if data.get("model"):
            query.model(data["model"])

        # Set role if specified - uses RoleConfig from database
        if data.get("role"):
            query.role(data["role"])

        # Enable session for conversation persistence
        if data.get("session"):
            query.session(data["session"])

        # Execute with JSON parsing if requested
        if data.get("output_json"):
            result = query.execute_json(schema_hint=data.get("schema_hint"))
        else:
            result = query.execute()

        return JsonResponse(result)

    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=503)
    finally:
        db.close()


def build_agent_prompt_view(request, task_id):
    """Build a complete agent prompt with project context for a task.

    GET /api/tasks/{task_id}/agent-prompt?role=dev

    Returns a structured prompt with:
    1. PROJECT DOCUMENTATION - What the project is, how it works
    2. CODING PRINCIPLES - Standards and practices to follow
    3. CURRENT STATE - Todo list, active tasks, recent changes
    4. AVAILABLE COMMANDS - Shell and API commands
    5. TASK ASSIGNMENT - The specific task to perform

    Query params:
    - role: Agent role (dev, qa, sec, docs) - default: dev
    - include_files: Comma-separated list of files to include
    """
    import os
    from app.services.llm_service import build_agent_prompt
    from app.models import RoleConfig

    role = request.GET.get("role", "dev")
    include_files = request.GET.get("include_files")
    if include_files:
        include_files = [f.strip() for f in include_files.split(",")]

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        project = task.project
        if not project:
            return JsonResponse({"error": "Task has no project"}, status=400)

        # Fetch role configuration from database
        role_config_obj = db.query(RoleConfig).filter(
            RoleConfig.role == role,
            RoleConfig.active == True
        ).first()
        role_config = role_config_obj.to_dict() if role_config_obj else None

        # Build project context (similar to orchestrator_context)
        project_context = {
            "project": project.to_dict(),
            "commands": {
                "build": project.build_command,
                "test": project.test_command,
                "run": project.run_command,
                "deploy": project.deploy_command,
                **(project.additional_commands or {})
            },
            "files": {}
        }

        # Load key files from disk
        if project.repo_path and os.path.isdir(project.repo_path):
            priority_files = include_files or [
                "CLAUDE.md",
                "coding_principles.md",
                "todo.json",
                "_spec/BRIEF.md",
                "_spec/HANDOFF.md",
                "_spec/SESSION_CONTEXT.md"
            ]

            for filename in priority_files:
                filepath = os.path.join(project.repo_path, filename)
                if os.path.isfile(filepath):
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                            project_context["files"][filename] = {
                                "content": f.read()
                            }
                    except Exception as e:
                        project_context["files"][filename] = {"error": str(e)}

        # Fetch task history (handoffs and proofs)
        from app.models import Handoff, Proof

        # Get handoff history for this task
        handoffs = db.query(Handoff).filter(
            Handoff.task_id == task_id
        ).order_by(Handoff.created_at.desc()).limit(10).all()

        task_history = []
        for h in handoffs:
            task_history.append({
                "id": h.id,
                "from_role": h.from_role,
                "to_role": h.to_role,
                "stage": h.stage,
                "status": h.status.value if h.status else None,
                "report_status": h.report_status,
                "report_summary": h.report_summary,
                "created_at": h.created_at.isoformat() if h.created_at else None,
                "completed_at": h.completed_at.isoformat() if h.completed_at else None,
            })

        # Get proofs for this task
        proofs = db.query(Proof).filter(
            Proof.task_id == task_id
        ).order_by(Proof.created_at.desc()).limit(10).all()

        task_proofs = []
        for p in proofs:
            task_proofs.append({
                "id": p.id,
                "proof_type": p.proof_type,
                "filename": p.filename,
                "summary": p.summary,
                "stage": p.stage,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            })

        project_context["task_history"] = task_history
        project_context["task_proofs"] = task_proofs

        # Build the prompt
        prompt = build_agent_prompt(
            project_context=project_context,
            task=task.to_dict(),
            agent_role=role,
            include_files=include_files,
            role_config=role_config
        )

        return JsonResponse({
            "prompt": prompt,
            "task_id": task_id,
            "project_id": project.id,
            "role": role,
            "role_config_id": role_config_obj.id if role_config_obj else None,
            "token_estimate": len(prompt) // 4  # Rough estimate
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def project_enrich(request, project_id):
    """Enrich project documentation using LLM for agent-ready context.

    POST /api/projects/{id}/enrich

    Generates comprehensive documentation including:
    - Enhanced description
    - Project objectives
    - Success criteria
    - Agent workflow guidelines
    - Key commands and API endpoints

    Query params:
    - apply: true/false (default false) - whether to save to database
    - model: LLM model to use (optional)

    Returns enriched documentation that can be reviewed before applying.
    """
    import os
    from app.services.llm_service import get_llm_service

    apply_changes = request.GET.get("apply", "false").lower() == "true"
    model = request.GET.get("model")

    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return JsonResponse({"error": "Project not found"}, status=404)

        # Build comprehensive project context
        context_parts = []

        # --- Project Metadata ---
        context_parts.append("=== PROJECT METADATA ===")
        context_parts.append(f"Name: {project.name}")
        context_parts.append(f"Repo Path: {project.repo_path or 'Not set'}")
        context_parts.append(f"Repository URL: {project.repository_url or 'Not set'}")
        context_parts.append(f"Primary Branch: {project.primary_branch or 'main'}")
        context_parts.append(f"Entry Point: {project.entry_point or 'Not set'}")
        context_parts.append(f"Default Port: {project.default_port or 'Not set'}")
        context_parts.append("")

        # --- Tech Stack ---
        context_parts.append("=== TECH STACK ===")
        context_parts.append(f"Languages: {', '.join(project.languages or []) or 'Not specified'}")
        context_parts.append(f"Frameworks: {', '.join(project.frameworks or []) or 'Not specified'}")
        context_parts.append(f"Databases: {', '.join(project.databases or []) or 'Not specified'}")
        context_parts.append(f"Python Version: {project.python_version or 'Not specified'}")
        context_parts.append(f"Node Version: {project.node_version or 'Not specified'}")
        context_parts.append("")

        # --- Current Description ---
        context_parts.append("=== CURRENT DESCRIPTION ===")
        context_parts.append(project.description or "No description provided")
        context_parts.append("")

        # --- Commands ---
        all_commands = {
            "build": project.build_command,
            "test": project.test_command,
            "run": project.run_command,
            "deploy": project.deploy_command,
            **(project.additional_commands or {})
        }
        context_parts.append(f"=== AVAILABLE COMMANDS ({len([c for c in all_commands.values() if c])} defined) ===")
        for name, value in sorted(all_commands.items()):
            if value is None:
                continue
            if isinstance(value, dict):
                desc = value.get("description", "")
                cmd = value.get("command", "")
                context_parts.append(f"- {name}: {desc}")
                context_parts.append(f"    Command: {cmd}")
            else:
                context_parts.append(f"- {name}: {value}")
        context_parts.append("")

        # --- Key Files ---
        context_parts.append("=== KEY FILES ===")
        for f in (project.key_files or []):
            context_parts.append(f"- {f}")
        context_parts.append("")

        # --- Config Files ---
        context_parts.append("=== CONFIG FILES ===")
        for f in (project.config_files or []):
            context_parts.append(f"- {f}")
        context_parts.append("")

        # --- Read key files if available ---
        file_contents = {}
        if project.repo_path and os.path.isdir(project.repo_path):
            priority_files = ["README.md", "CLAUDE.md", "requirements.txt", "package.json", "setup.py", "pyproject.toml"]
            for filename in priority_files:
                filepath = os.path.join(project.repo_path, filename)
                if os.path.isfile(filepath):
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()
                            if len(content) < 10000:  # Only include if reasonable size
                                file_contents[filename] = content
                    except:
                        pass

            if file_contents:
                context_parts.append("=== FILE CONTENTS (for context) ===")
                for fname, content in file_contents.items():
                    context_parts.append(f"\n--- {fname} ---")
                    context_parts.append(content[:5000])  # Limit per file
                context_parts.append("")

        # --- Existing Tasks ---
        tasks = db.query(Task).filter(Task.project_id == project_id).limit(10).all()
        if tasks:
            context_parts.append(f"=== EXISTING TASKS ({len(tasks)} shown) ===")
            for t in tasks:
                context_parts.append(f"- [{t.task_id}] {t.title} ({t.status.value if t.status else 'unknown'})")
            context_parts.append("")

        project_context = "\n".join(context_parts)

        # Build the enrichment prompt
        enrichment_prompt = f"""You are a technical documentation expert preparing a project for AI agent collaboration.

Analyze this project and generate comprehensive documentation that will help AI agents understand and work on this codebase effectively.

{project_context}

=== GENERATE THE FOLLOWING ===

1. **ENHANCED DESCRIPTION** (2-3 paragraphs)
   - What the project does and its purpose
   - Architecture and key technologies
   - How agents interact with it (API, CLI, etc.)

2. **PROJECT OBJECTIVES** (5-10 bullet points)
   - Clear, measurable goals for the project
   - Both short-term and long-term objectives

3. **SUCCESS CRITERIA** (5-10 bullet points)
   - How to know if work is done correctly
   - Quality standards and requirements
   - Testing expectations

4. **AGENT WORKFLOW GUIDE**
   - Step-by-step process for agents to:
     a) Understand the codebase
     b) Pick up a task
     c) Implement changes
     d) Submit work for review
   - Include specific commands and API endpoints to use

5. **KEY COMMANDS REFERENCE**
   - Most important commands for daily development
   - Grouped by category (setup, test, deploy, etc.)

6. **GETTING STARTED CHECKLIST**
   - First steps for a new agent joining the project
   - Required setup and configuration

Format the output as structured markdown that can be stored in the project description or a separate agent guide document.
"""

        # Call LLM service
        try:
            service = get_llm_service()
            enriched_content = service.complete(
                prompt=enrichment_prompt,
                system_prompt="You are a senior technical writer creating documentation for AI coding agents. Be comprehensive, precise, and actionable. Structure your output clearly with markdown headers.",
                model=model,
                temperature=0.4,
                max_tokens=4000
            )
        except Exception as e:
            return JsonResponse({
                "error": f"LLM service error: {str(e)}",
                "hint": "Ensure Docker Model Runner is running"
            }, status=503)

        result = {
            "project_id": project_id,
            "project_name": project.name,
            "enriched_documentation": enriched_content,
            "context_used": {
                "commands_count": len([c for c in all_commands.values() if c]),
                "key_files_count": len(project.key_files or []),
                "files_read": list(file_contents.keys()),
                "tasks_count": len(tasks)
            },
            "applied": False
        }

        # Apply changes if requested
        if apply_changes:
            # Extract just the enhanced description for the description field
            # Store full enrichment in a separate field or file
            project.description = enriched_content
            db.commit()
            result["applied"] = True
            result["message"] = "Enriched documentation saved to project description"

            log_event(db, "system", "enrich", "project", project_id, {
                "action": "llm_enrichment",
                "model": model or "default"
            })

        return JsonResponse(result)
    except Exception as e:
        db.rollback()
        return JsonResponse({"error": str(e)}, status=500)
    finally:
        db.close()


# =============================================================================
# LLM Session Management
# =============================================================================

@csrf_exempt
@require_http_methods(["GET"])
def llm_sessions_list(request):
    """List LLM sessions with optional filtering.

    GET /api/llm/sessions

    Query params:
    - project_id: Filter by project
    - task_id: Filter by task
    - run_id: Filter by run
    - active: Filter by active status (true/false)
    - limit: Max results (default 50)

    Returns:
    {
        "sessions": [...],
        "count": 10
    }
    """
    from app.models import LLMSession

    project_id = request.GET.get("project_id")
    task_id = request.GET.get("task_id")
    run_id = request.GET.get("run_id")
    active = request.GET.get("active")
    limit = int(request.GET.get("limit", 50))

    db = next(get_db())
    try:
        query = db.query(LLMSession)

        if project_id:
            query = query.filter(LLMSession.project_id == int(project_id))
        if task_id:
            query = query.filter(LLMSession.task_id == int(task_id))
        if run_id:
            query = query.filter(LLMSession.run_id == int(run_id))
        if active is not None:
            query = query.filter(LLMSession.active == (active.lower() == "true"))

        sessions = query.order_by(LLMSession.updated_at.desc()).limit(limit).all()

        return JsonResponse({
            "sessions": [s.to_dict() for s in sessions],
            "count": len(sessions)
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["GET", "DELETE"])
def llm_session_detail(request, session_id):
    """Get or delete a specific LLM session.

    GET /api/llm/sessions/{id}
    DELETE /api/llm/sessions/{id}

    GET Query params:
    - messages: Include messages (true/false, default false)
    - last_n: Only include last N messages

    Returns (GET):
    {
        "session": {...},
        "messages": [...]  // If requested
    }
    """
    from app.models import LLMSession

    db = next(get_db())
    try:
        session = db.query(LLMSession).filter(LLMSession.id == session_id).first()
        if not session:
            return JsonResponse({"error": "Session not found"}, status=404)

        if request.method == "DELETE":
            db.delete(session)
            db.commit()
            return JsonResponse({"success": True, "deleted": session_id})

        # GET request
        include_messages = request.GET.get("messages", "false").lower() == "true"
        last_n = request.GET.get("last_n")

        if include_messages:
            if last_n:
                result = session.to_dict_with_messages(int(last_n))
            else:
                result = session.to_dict_with_messages()
        else:
            result = session.to_dict()

        return JsonResponse({"session": result})
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def llm_session_clear(request, session_id):
    """Clear a session's message history.

    POST /api/llm/sessions/{id}/clear

    Body:
    {
        "keep_system": true  // Optional - keep system messages (default true)
    }

    Returns:
    {
        "success": true,
        "session": {...}
    }
    """
    from app.models import LLMSession

    data = _get_json_body(request) or {}

    db = next(get_db())
    try:
        session = db.query(LLMSession).filter(LLMSession.id == session_id).first()
        if not session:
            return JsonResponse({"error": "Session not found"}, status=404)

        keep_system = data.get("keep_system", True)
        session.clear_messages(keep_system=keep_system)
        db.commit()

        return JsonResponse({
            "success": True,
            "session": session.to_dict()
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["GET"])
def llm_session_export(request, session_id):
    """Export a session in Goose-compatible JSON format.

    GET /api/llm/sessions/{id}/export

    Returns:
    {
        "id": 1,
        "name": "task_123",
        "working_dir": "/path/to/project",
        "created_at": "...",
        "total_tokens": 1234,
        "input_tokens": 567,
        "output_tokens": 678,
        "provider_name": "docker",
        "model_config": {"model_name": "ai/qwen3-coder"},
        "conversation": [...],
        "metadata": {"project_id": 1, "task_id": 123, "run_id": null}
    }
    """
    from app.models import LLMSession

    db = next(get_db())
    try:
        session = db.query(LLMSession).filter(LLMSession.id == session_id).first()
        if not session:
            return JsonResponse({"error": "Session not found"}, status=404)

        return JsonResponse(session.to_export_format())
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["GET"])
def llm_session_by_name(request, name):
    """Get a session by name.

    GET /api/llm/sessions/name/{name}

    Query params:
    - project_id: Required if multiple sessions share the same name
    - messages: Include messages (true/false)

    Returns:
    {
        "session": {...}
    }
    """
    from app.models import LLMSession

    project_id = request.GET.get("project_id")
    include_messages = request.GET.get("messages", "false").lower() == "true"

    db = next(get_db())
    try:
        query = db.query(LLMSession).filter(
            LLMSession.name == name,
            LLMSession.active == True
        )

        if project_id:
            query = query.filter(LLMSession.project_id == int(project_id))

        session = query.order_by(LLMSession.updated_at.desc()).first()
        if not session:
            return JsonResponse({"error": "Session not found"}, status=404)

        if include_messages:
            result = session.to_dict_with_messages()
        else:
            result = session.to_dict()

        return JsonResponse({"session": result})
    finally:
        db.close()
