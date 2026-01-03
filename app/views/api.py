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
    WorkCycle, WorkCycleStatus, Proof,
    # Falsification Framework
    Claim, ClaimTest, ClaimEvidence,
    ClaimScope, ClaimStatus, ClaimCategory,
    TestType, TestStatus, EvidenceType
)
from app.models.task import TaskPipelineStage
from app.models.report import AgentRole, ReportStatus
from app.models.audit import log_event
from app.services.run_service import RunService
import shlex
import urllib.request
import socket
import subprocess as _subprocess


# Simple process tracker for local goose web instances (dev use only)
GOOSE_PROCESSES = {}  # port -> Popen


def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except Exception:
        return False


@csrf_exempt
def goose_start(request):
    """Start a local Goose web service in the given cwd on the requested port (dev convenience).

    POST body JSON: {"cwd": "/path/to/repo", "port": 8080}
    Returns JSON {running: True, url: "http://localhost:port"} on success.
    """
    data = _get_json_body(request)
    # Support form-encoded POST (fallback HTML forms) as well as JSON
    if not data:
        try:
            post = request.POST
            data = {k: post.get(k) for k in post.keys()} if post else {}
        except Exception:
            data = {}

    cwd = data.get('cwd') or os.getcwd()
    try:
        port = int(data.get('port') or os.getenv('GOOSE_WEB_PORT', 8080))
    except Exception:
        port = int(os.getenv('GOOSE_WEB_PORT', 8080))

    if port in GOOSE_PROCESSES and GOOSE_PROCESSES[port].poll() is None:
        return JsonResponse({"running": True, "url": f"http://localhost:{port}", "message": "Already running"})

    # Prefer a user-specified command, fallback to a common goose web invocation.
    cmd_template = os.getenv('GOOSE_WEB_CMD', 'goose web --port {port} --cwd "{cwd}"')
    cmd = cmd_template.format(port=port, cwd=cwd)
    args = shlex.split(cmd)

    log_dir = os.path.join(settings.BASE_DIR, 'logs')
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        log_dir = '/tmp'

    stdout_path = os.path.join(log_dir, f'goose_{port}.out')
    stderr_path = os.path.join(log_dir, f'goose_{port}.err')

    try:
        out_f = open(stdout_path, 'a')
        err_f = open(stderr_path, 'a')
        proc = _subprocess.Popen(args, cwd=cwd, stdout=out_f, stderr=err_f, start_new_session=True)
        GOOSE_PROCESSES[port] = proc
    except FileNotFoundError as e:
        return JsonResponse({"running": False, "error": f"Command not found: {args[0]}. Install goose and try again.", "cmd": args}, status=500)
    except Exception as e:
        return JsonResponse({"running": False, "error": str(e), "cmd": args}, status=500)

    # Wait briefly for port to open
    import time
    for _ in range(10):
        if _is_port_open('127.0.0.1', port):
            return JsonResponse({"running": True, "url": f"http://localhost:{port}"})
        time.sleep(0.3)

    return JsonResponse({"running": True, "url": f"http://localhost:{port}", "message": "Started but not yet responding"})


@csrf_exempt
def goose_stop(request):
    """Stop a previously started local Goose web service.

    POST body JSON: {"port": 8080}
    """
    data = _get_json_body(request)
    if not data:
        try:
            post = request.POST
            data = {k: post.get(k) for k in post.keys()} if post else {}
        except Exception:
            data = {}

    try:
        port = int(data.get('port') or os.getenv('GOOSE_WEB_PORT', 8080))
    except Exception:
        port = int(os.getenv('GOOSE_WEB_PORT', 8080))

    proc = GOOSE_PROCESSES.get(port)
    if not proc:
        return JsonResponse({"stopped": True, "message": "No managed process"})

    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    GOOSE_PROCESSES.pop(port, None)
    return JsonResponse({"stopped": True})


def goose_status(request):
    """Return status of a goose web service. Query param `port` optional."""
    port = int(request.GET.get('port') or os.getenv('GOOSE_WEB_PORT', 8080))
    running = False
    managed = False
    proc = GOOSE_PROCESSES.get(port)
    if proc and proc.poll() is None:
        running = True
        managed = True
    # Also check if something is listening on the port
    available = _is_port_open('127.0.0.1', port)
    return JsonResponse({
        "port": port,
        "running": running or available,
        "managed": managed,
        "url": f"http://localhost:{port}"
    })

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
@require_http_methods(["POST"])
def project_refresh(request, project_id):
    """Refresh project details (UI helper).

    POST /api/projects/{id}/refresh
    Returns the same payload as project_detail for UI refresh.
    """
    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return JsonResponse({"error": "Project not found"}, status=404)

        log_event(db, "human", "refresh", "project", project_id, {})
        return JsonResponse({
            "project": project.to_dict(),
            "requirements": [r.to_dict() for r in project.requirements],
            "tasks": [t.to_dict() for t in project.tasks],
            "runs": [r.to_dict() for r in project.runs],
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["GET"])
def orchestrator_context(request, project_id):
    """Return project context for orchestrator/agent use.

    GET /api/projects/{id}/context

    Query params:
    - include_files: Comma-separated list of files to include from repo_path
    """
    import os

    include_files = request.GET.get("include_files")
    if include_files:
        include_files = [f.strip() for f in include_files.split(",") if f.strip()]

    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return JsonResponse({"error": "Project not found"}, status=404)

        context = {
            "project": project.to_dict(),
            "commands": {
                "build": project.build_command,
                "test": project.test_command,
                "run": project.run_command,
                "deploy": project.deploy_command,
                **(project.additional_commands or {})
            },
            "files": {},
        }

        if project.repo_path and os.path.isdir(project.repo_path):
            priority_files = include_files or [
                "CLAUDE.md",
                "coding_principles.md",
                "todo.json",
                "_spec/BRIEF.md",
                "_spec/WORK_CYCLE.md",
                "_spec/SESSION_CONTEXT.md",
            ]
            for filename in priority_files:
                filepath = os.path.join(project.repo_path, filename)
                if os.path.isfile(filepath):
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()
                            if len(content) < 10000:
                                context["files"][filename] = content
                    except Exception:
                        continue

        return JsonResponse(context)
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
        parent_task_id: Optional parent task ID for subtasks
        inherit_requirements: If true, copy parent requirements (default true)
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

        parent_task_id = data.get("parent_task_id")
        parent_task = None
        if parent_task_id:
            parent_task = db.query(Task).filter(Task.id == parent_task_id).first()
            if not parent_task:
                return JsonResponse({"error": "parent_task_id not found"}, status=404)
            if parent_task.project_id != project_id:
                return JsonResponse({"error": "parent_task_id must belong to same project"}, status=400)

        task = Task(
            project_id=project_id,
            task_id=task_id,
            title=title,
            description=data.get("description"),
            priority=data.get("priority", 5),
            blocked_by=data.get("blocked_by", []),
            acceptance_criteria=data.get("acceptance_criteria", []),
            status=TaskStatus.BACKLOG,
            pipeline_stage=pipeline_stage,
            parent_task_id=parent_task_id
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        inherit_requirements = data.get("inherit_requirements", True)
        if parent_task and inherit_requirements and parent_task.requirements:
            task.requirements.extend(parent_task.requirements)
            db.commit()

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

        # NOTE: run_id removed from Task in refactor - skip this update
        # if "run_id" in data:
        #     task.run_id = data["run_id"]
        #     updated_fields.append("run_id")

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
        # Truncate name to fit varchar(500) in runs.name column
        run_name = f"Execute Task: {task.task_id} - {task.title}"
        if len(run_name) > 500:
            run_name = run_name[:497] + "..."
        service = RunService(db)
        run = service.create_run(project.id, run_name)

        # NOTE: task.run_id removed in refactor - runs now track via project
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
            # NOTE: run_id removed from Task - use 0 as placeholder for legacy AgentReport
            report = AgentReport(
                run_id=0,  # Legacy - run_id no longer on Task
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
        # NOTE: run_id removed from Task - use 0 as placeholder
        report = AgentReport(
            run_id=0,  # Legacy - run_id no longer on Task
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

# Global variable to track director daemon running state (not persisted - just runtime)
_director_daemon_thread = None
_director_daemon_running = False


def _get_director_settings(db=None):
    """Get Director settings from database."""
    from app.models.director_settings import DirectorSettings
    close_db = False
    if db is None:
        db = next(get_db())
        close_db = True
    try:
        settings = DirectorSettings.get_settings(db)
        return settings.to_dict()
    finally:
        if close_db:
            db.close()


def director_status(request):
    """Get Director daemon status and statistics.

    GET /api/director/status

    Uses database heartbeat to determine if daemon is running.
    """
    db = next(get_db())
    try:
        # Get settings and check daemon status from database heartbeat
        from app.models.director_settings import DirectorSettings
        settings_obj = DirectorSettings.get_settings(db)
        settings = settings_obj.to_dict()
        is_running = settings_obj.is_daemon_running()

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
            "running": is_running,
            "settings": settings,
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

    Also updates 'enabled' in database to True so Director auto-starts on restart.
    """
    global _director_daemon_thread, _director_daemon_running

    if _director_daemon_running:
        return JsonResponse({"status": "already_running", "message": "Director is already running"})

    data = _get_json_body(request) or {}
    run_id = data.get("run_id")

    # Get settings from DB
    db = next(get_db())
    try:
        from app.models.director_settings import DirectorSettings
        settings = DirectorSettings.get_settings(db)
        poll_interval = data.get("poll_interval", settings.poll_interval)

        # Update enabled flag so Director auto-starts on restart
        settings.enabled = True
        db.commit()
    finally:
        db.close()

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
    Also updates 'enabled' in database to False and clears heartbeat.
    """
    global _director_daemon_running

    db = next(get_db())
    try:
        from app.models.director_settings import DirectorSettings
        settings = DirectorSettings.get_settings(db)

        # Check if running via database heartbeat
        if not settings.is_daemon_running():
            return JsonResponse({"status": "not_running", "message": "Director is not running"})

        # Signal stop (daemon checks this and exits)
        _director_daemon_running = False

        # Update enabled flag and clear heartbeat
        settings.enabled = False
        DirectorSettings.clear_heartbeat(db)
    finally:
        db.close()

    return JsonResponse({
        "status": "stopping",
        "message": "Director will stop on next poll cycle"
    })


@csrf_exempt
@require_http_methods(["POST"])
def director_settings_update(request):
    """Update Director settings (persisted to database).

    POST /api/director/settings
    """
    data = _get_json_body(request) or {}

    db = next(get_db())
    try:
        from app.models.director_settings import DirectorSettings
        settings = DirectorSettings.get_settings(db)

        # Update provided fields
        if "enabled" in data:
            settings.enabled = bool(data["enabled"])
        if "poll_interval" in data:
            settings.poll_interval = int(data["poll_interval"])
        if "enforce_tdd" in data:
            settings.enforce_tdd = bool(data["enforce_tdd"])
        if "enforce_dry" in data:
            settings.enforce_dry = bool(data["enforce_dry"])
        if "enforce_security" in data:
            settings.enforce_security = bool(data["enforce_security"])
        if "include_images" in data:
            settings.include_images = bool(data["include_images"])
        if "vision_model" in data:
            settings.vision_model = str(data["vision_model"])

        db.commit()
        db.refresh(settings)

        return JsonResponse({
            "status": "updated",
            "settings": settings.to_dict()
        })
    finally:
        db.close()


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
# App Settings Endpoints (Admin Panel)
# =============================================================================

def app_settings_list(request):
    """Get all app settings, grouped by category.

    GET /api/settings

    Query params:
        - category: Filter by category (llm, agent, queue, ui, etc.)
    """
    from app.models.app_settings import AppSetting

    category = request.GET.get("category")

    db = next(get_db())
    try:
        settings = AppSetting.get_all(db, category=category)

        # Group by category
        grouped = {}
        for s in settings:
            cat = s.category
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(s.to_dict())

        return JsonResponse({
            "settings": grouped,
            "categories": list(grouped.keys()),
            "count": len(settings)
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def app_settings_update(request):
    """Update one or more app settings.

    POST /api/settings/update

    Body: {"settings": [{"key": "KEY", "value": "VALUE"}, ...]}

    Future: Requires admin permission.
    """
    from app.models.app_settings import AppSetting

    data = _get_json_body(request) or {}
    updates = data.get("settings", [])

    if not updates:
        return JsonResponse({"error": "No settings provided"}, status=400)

    db = next(get_db())
    try:
        updated = []
        for item in updates:
            key = item.get("key")
            value = item.get("value")
            if not key:
                continue

            # Check if setting exists and is editable
            setting = db.query(AppSetting).filter(AppSetting.key == key).first()
            if setting:
                if not setting.editable:
                    continue  # Skip read-only settings
                setting.value = value
                updated.append(setting.to_dict())
            else:
                # Create new setting
                setting = AppSetting.set(
                    db, key, value,
                    description=item.get("description"),
                    category=item.get("category", "general"),
                    is_secret=item.get("is_secret", False)
                )
                updated.append(setting.to_dict())

        db.commit()

        return JsonResponse({
            "status": "updated",
            "updated": updated,
            "count": len(updated)
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def app_settings_seed(request):
    """Seed default settings if they don't exist.

    POST /api/settings/seed

    Future: Requires admin permission.
    """
    from app.models.app_settings import AppSetting

    db = next(get_db())
    try:
        AppSetting.seed_defaults(db)
        settings = AppSetting.get_all(db)

        return JsonResponse({
            "status": "seeded",
            "count": len(settings)
        })
    finally:
        db.close()


def app_settings_get(request, key):
    """Get a single setting by key.

    GET /api/settings/{key}
    """
    from app.models.app_settings import AppSetting

    db = next(get_db())
    try:
        setting = db.query(AppSetting).filter(AppSetting.key == key).first()
        if not setting:
            return JsonResponse({"error": f"Setting '{key}' not found"}, status=404)

        return JsonResponse(setting.to_dict())
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
        - stage: Pipeline stage (required)
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
            run_id = None  # Task.run_id removed in refactor
        else:  # run
            run = db.query(Run).filter(Run.id == entity_id).first()
            run_id = entity_id
            project_id = run.project_id if run else None
            # NOTE: Task.run_id removed - no direct task-run association anymore
            task_id = None

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
# WorkCycle Endpoints (Task-Centric Agent Work Cycles)
# =============================================================================

def task_work_cycle_current(request, task_id):
    """Get the current pending/in_progress work_cycle for a task.

    GET /api/tasks/{task_id}/work_cycle

    Returns the work_cycle that an agent should work on.
    Includes full context (structured + markdown).
    """
    from app.services import work_cycle_service

    db = next(get_db())
    try:
        work_cycle = work_cycle_service.get_current_work_cycle(db, task_id)

        if not work_cycle:
            return JsonResponse({
                "task_id": task_id,
                "work_cycle": None,
                "message": "No pending work_cycle for this task"
            })

        return JsonResponse({
            "task_id": task_id,
            "work_cycle": work_cycle.to_dict()
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_work_cycle_create(request, task_id):
    """Create a new work_cycle for a task.

    POST /api/tasks/{task_id}/work_cycle/create

    Body:
        - to_role: Agent role that should pick this up (dev, qa, sec, docs, pm)
        - stage: Pipeline stage (required)
        - run_id: Optional run ID for context
        - from_role: Previous agent role (optional)
        - created_by: Who created this (default: "system")
        - write_file: Whether to write context to file (default: true)

    Returns the created work_cycle with full context.
    """
    from app.services import work_cycle_service

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

        # Check for existing pending work_cycle
        existing = work_cycle_service.get_current_work_cycle(db, task_id)
        if existing:
            return JsonResponse({
                "error": "Task already has a pending work_cycle",
                "existing_work_cycle_id": existing.id
            }, status=400)

        work_cycle = work_cycle_service.create_work_cycle(
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

        log_event(db, "system", "create_work_cycle", "task", task_id, {
            "work_cycle_id": work_cycle.id,
            "to_role": to_role,
            "stage": stage
        })

        return JsonResponse({
            "work_cycle": work_cycle.to_dict()
        }, status=201)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_work_cycle_accept(request, task_id):
    """Accept a work_cycle (agent starting work).

    POST /api/tasks/{task_id}/work_cycle/accept

    Body:
        - work_cycle_id: Optional specific work_cycle ID (uses current if not provided)

    Marks the work_cycle as IN_PROGRESS.
    """
    from app.services import work_cycle_service

    data = _get_json_body(request)
    work_cycle_id = data.get("work_cycle_id")

    db = next(get_db())
    try:
        # Get work_cycle - either specified or current
        if work_cycle_id:
            work_cycle = work_cycle_service.get_work_cycle_by_id(db, work_cycle_id)
            if not work_cycle or work_cycle.task_id != task_id:
                return JsonResponse({"error": "WorkCycle not found for this task"}, status=404)
        else:
            work_cycle = work_cycle_service.get_current_work_cycle(db, task_id)
            if not work_cycle:
                return JsonResponse({"error": "No pending work_cycle for this task"}, status=404)

        work_cycle = work_cycle_service.accept_work_cycle(db, work_cycle.id)

        log_event(db, "agent", "accept_work_cycle", "task", task_id, {
            "work_cycle_id": work_cycle.id,
            "to_role": work_cycle.to_role,
            "stage": work_cycle.stage
        })

        return JsonResponse({
            "success": True,
            "work_cycle": work_cycle.to_dict()
        })
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_work_cycle_complete(request, task_id):
    """Complete a work_cycle with the agent's report and advance task pipeline.

    POST /api/tasks/{task_id}/work_cycle/complete

    Body:
        - work_cycle_id: Optional specific work_cycle ID (uses current if not provided)
        - report_status: "pass" or "fail" (required)
        - report_summary: Summary of what agent did (required)
        - report_details: Full report details as JSON (optional)
        - agent_report_id: Link to AgentReport record (optional)
        - auto_advance: Whether to auto-advance pipeline stage (default: true)

    Marks the work_cycle as COMPLETED with the report.
    If report_status is "pass" and auto_advance is true, advances task to next pipeline stage.
    If report_status is "fail", loops task back to DEV stage.
    """
    from app.services import work_cycle_service
    from app.services.director_service import DirectorService
    from app.services.webhook_service import dispatch_webhook, EVENT_STATE_CHANGE
    from app.models.report import AgentReport, ReportStatus
    from app.models.task import Task

    data = _get_json_body(request)
    if not data:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    report_status = data.get("report_status")
    if not report_status:
        return JsonResponse({"error": "report_status is required"}, status=400)
    if report_status not in ("pass", "fail"):
        return JsonResponse({"error": "report_status must be 'pass' or 'fail'"}, status=400)

    work_cycle_id = data.get("work_cycle_id")
    auto_advance = data.get("auto_advance", True)

    db = next(get_db())
    try:
        # Get task first
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        # Get work_cycle - either specified or current in_progress
        if work_cycle_id:
            work_cycle = work_cycle_service.get_work_cycle_by_id(db, work_cycle_id)
            if not work_cycle or work_cycle.task_id != task_id:
                return JsonResponse({"error": "WorkCycle not found for this task"}, status=404)
        else:
            work_cycle = work_cycle_service.get_current_work_cycle(db, task_id)
            if not work_cycle:
                return JsonResponse({"error": "No in-progress work_cycle for this task"}, status=404)

        old_stage = task.pipeline_stage.value if task.pipeline_stage else "none"

        work_cycle = work_cycle_service.complete_work_cycle(
            db=db,
            work_cycle_id=work_cycle.id,
            report_status=report_status,
            report_summary=data.get("report_summary"),
            report_details=data.get("report_details"),
            agent_report_id=data.get("agent_report_id")
        )

        log_event(db, "agent", "complete_work_cycle", "task", task_id, {
            "work_cycle_id": work_cycle.id,
            "to_role": work_cycle.to_role,
            "stage": work_cycle.stage,
            "report_status": report_status
        })

        # Advance task pipeline if auto_advance is enabled
        advance_result = None
        if auto_advance:
            director = DirectorService(db)

            # Create a minimal report-like object for the director to check status
            # Using a simple object since AgentReport is run-centric, not task-centric
            class TaskReport:
                def __init__(self, status):
                    self.status = status

            temp_report = TaskReport(
                status=ReportStatus.PASS if report_status == "pass" else ReportStatus.FAIL
            )

            success, message = director.advance_task(task, temp_report)
            advance_result = {"success": success, "message": message}

            new_stage = task.pipeline_stage.value if task.pipeline_stage else "none"

            # Dispatch webhook for state change to trigger next agent
            if success:
                # Determine next agent based on new stage
                stage_to_agent = {
                    "dev": "dev",
                    "qa": "qa",
                    "sec": "sec",
                    "docs": "docs",
                    "complete": None
                }
                next_agent = stage_to_agent.get(new_stage)

                dispatch_webhook(EVENT_STATE_CHANGE, {
                    "task_id": task_id,
                    "project_id": task.project_id,
                    "run_id": work_cycle.run_id,
                    "from_stage": old_stage,
                    "to_stage": new_stage,
                    "next_agent": next_agent,
                    "report_status": report_status
                })

        return JsonResponse({
            "success": True,
            "work_cycle": work_cycle.to_dict(),
            "task": task.to_dict() if hasattr(task, 'to_dict') else {"id": task.id, "pipeline_stage": task.pipeline_stage.value if task.pipeline_stage else None},
            "advance_result": advance_result
        })
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def task_work_cycle_fail(request, task_id):
    """Mark a work_cycle as failed (timeout, error, etc.).

    POST /api/tasks/{task_id}/work_cycle/fail

    Body:
        - work_cycle_id: Optional specific work_cycle ID (uses current if not provided)
        - reason: Reason for failure (optional)

    Marks the work_cycle as FAILED.
    """
    from app.services import work_cycle_service

    data = _get_json_body(request) or {}
    work_cycle_id = data.get("work_cycle_id")
    reason = data.get("reason")

    db = next(get_db())
    try:
        # Get work_cycle - either specified or current
        if work_cycle_id:
            work_cycle = work_cycle_service.get_work_cycle_by_id(db, work_cycle_id)
            if not work_cycle or work_cycle.task_id != task_id:
                return JsonResponse({"error": "WorkCycle not found for this task"}, status=404)
        else:
            work_cycle = work_cycle_service.get_current_work_cycle(db, task_id)
            if not work_cycle:
                return JsonResponse({"error": "No active work_cycle for this task"}, status=404)

        work_cycle = work_cycle_service.fail_work_cycle(db, work_cycle.id, reason)

        log_event(db, "system", "fail_work_cycle", "task", task_id, {
            "work_cycle_id": work_cycle.id,
            "reason": reason
        })

        return JsonResponse({
            "success": True,
            "work_cycle": work_cycle.to_dict()
        })
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    finally:
        db.close()


# =============================================================================
# WorkCycle Maintenance
# =============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def work_cycles_cleanup_stale(request):
    """Mark stale work_cycles as completed when their tasks are DONE.

    POST /api/work_cycles/cleanup-stale
    Body: {"limit": 100}
    """
    from app.services import work_cycle_service

    data = _get_json_body(request) or {}
    limit = data.get("limit", 100)

    db = next(get_db())
    try:
        updated = work_cycle_service.cleanup_stale_work_cycles(db, limit=limit)
        for work_cycle in updated:
            log_event(db, "system", "cleanup_stale_work_cycle", "task", work_cycle.task_id, {
                "work_cycle_id": work_cycle.id,
                "status": work_cycle.status.value if work_cycle.status else None
            })
        return JsonResponse({
            "updated_count": len(updated),
            "work_cycle_ids": [w.id for w in updated]
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def work_cycle_delete(request, work_cycle_id):
    """Delete a work_cycle record.

    POST /api/work_cycles/{work_cycle_id}/delete
    """
    from app.models.work_cycle import WorkCycle

    db = next(get_db())
    try:
        work_cycle = db.query(WorkCycle).filter(WorkCycle.id == work_cycle_id).first()
        if not work_cycle:
            return JsonResponse({"error": "WorkCycle not found"}, status=404)

        task_id = work_cycle.task_id
        db.delete(work_cycle)
        db.commit()

        log_event(db, "human", "delete_work_cycle", "task", task_id, {
            "work_cycle_id": work_cycle_id
        })

        return JsonResponse({"success": True, "work_cycle_id": work_cycle_id})
    finally:
        db.close()


# =============================================================================
# Task Maintenance
# =============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def tasks_auto_assign_dev(request):
    """Assign DEV pipeline stage to tasks with no stage or NONE.

    POST /api/tasks/auto-assign-dev
    Body: {"project_id": 123}
    """
    data = _get_json_body(request) or {}
    project_id = data.get("project_id")

    db = next(get_db())
    try:
        query = db.query(Task)
        if project_id:
            query = query.filter(Task.project_id == project_id)

        tasks = query.filter(
            Task.pipeline_stage.in_([None, TaskPipelineStage.NONE])
        ).all()

        updated_ids = []
        for task in tasks:
            task.pipeline_stage = TaskPipelineStage.DEV
            updated_ids.append(task.id)
            log_event(db, "system", "auto_assign_dev", "task", task.id, {
                "task_id": task.task_id
            })

        if updated_ids:
            db.commit()

        return JsonResponse({
            "updated_count": len(updated_ids),
            "task_ids": updated_ids
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
            "project": project.to_dict(include_children=True),
            "commands": {
                "build": project.build_command,
                "test": project.test_command,
                "run": project.run_command,
                "deploy": project.deploy_command,
                **(project.additional_commands or {})
            },
            "files": {},
        }

        # Load key files from disk
        if project.repo_path and os.path.isdir(project.repo_path):
            priority_files = include_files or [
                "README.md",
                "CLAUDE.md",
                "todo.json",
                "pyproject.toml",
                "requirements.txt"
            ]
            for filename in priority_files:
                filepath = os.path.join(project.repo_path, filename)
                if os.path.isfile(filepath):
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read(20000)
                            project_context["files"][filename] = content
                    except Exception:
                        project_context["files"][filename] = None

        # Fetch task history (work_cycles and proofs)
        from app.models import WorkCycle, Proof

        # Get work_cycle history for this task
        work_cycles = db.query(WorkCycle).filter(
            WorkCycle.task_id == task_id
        ).order_by(WorkCycle.created_at.desc()).limit(10).all()

        task_history = []
        for h in work_cycles:
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
            priority_files = ["README.md", "CLAUDE.md", "todo.json", "pyproject.toml", "requirements.txt"]
            for filename in priority_files:
                filepath = os.path.join(project.repo_path, filename)
                if os.path.isfile(filepath):
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read(20000)
                            file_contents[filename] = content
                    except Exception:
                        file_contents[filename] = None

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


def task_context(request, task_id):
    """Return task-level context for agents/UI.

    GET /api/tasks/{task_id}/context

    Returns task, its project, recent work_cycles, recent proofs, and a small selection
    of key files from the repo (if available).
    """
    import os

    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return JsonResponse({"error": "Task not found"}, status=404)

        project = task.project

        # Recent work_cycles (agent work units)
        try:
            work_cycles = db.query(WorkCycle).filter(WorkCycle.task_id == task_id).order_by(WorkCycle.created_at.desc()).limit(10).all()
        except Exception:
            work_cycles = []

        # Recent proofs (artifacts)
        try:
            proofs = db.query(Proof).filter(Proof.task_id == task_id).order_by(Proof.created_at.desc()).limit(10).all()
        except Exception:
            proofs = []

        # Small selection of repository files for context (if project repo available)
        files_content = {}
        if project and project.repo_path and os.path.isdir(project.repo_path):
            priority_files = ["README.md", "CLAUDE.md", "todo.json", "pyproject.toml", "requirements.txt"]
            for fname in priority_files:
                fp = os.path.join(project.repo_path, fname)
                if os.path.isfile(fp):
                    try:
                        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read(20000)
                            files_content[fname] = content
                    except Exception:
                        files_content[fname] = None

        return JsonResponse({
            "task": task.to_dict(),
            "project": project.to_dict() if project else None,
            "work_cycles": [w.to_dict() for w in work_cycles],
            "proofs": [p.to_dict() for p in proofs],
            "files": files_content
        })
    finally:
        db.close()


@csrf_exempt
@require_http_methods(["POST"])
def run_kill(request, run_id):
    """Soft-kill a run (mark as killed).

    POST /api/runs/{run_id}/kill

    This sets the run.killed flag and killed_at timestamp. It's intended as a safe
    way for humans to stop runs that were started or to mark them as cancelled.
    """
    from datetime import datetime

    db = next(get_db())
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return JsonResponse({"error": "Run not found"}, status=404)

        # Mark as killed (soft flag) and record time
        run.killed = True
        run.killed_at = datetime.utcnow()
        db.commit()

        log_event(db, "human", "kill", "run", run_id, {"run_id": run_id})

        return JsonResponse({"success": True, "killed": True, "run_id": run_id})
    finally:
        db.close()


# -----------------------------------------------------------------------------
# Job Queue API
# -----------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["GET"])
def queue_status(request):
    """Get current job queue status including pending/running jobs and worker info.

    Returns aggregated queue status, worker states, DMR health, and director status.
    """
    from app.services.job_queue_service import JobQueueService
    from app.models.director_settings import DirectorSettings
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        # Get queue stats from JobQueueService
        queue_service = JobQueueService(db)
        queue_stats = queue_service.get_queue_status()

        # Get worker status
        workers_status = {"started": False, "workers": []}
        try:
            from app.services.job_worker import get_workers_status
            workers_status = get_workers_status()
        except Exception:
            pass

        # Get DMR health (Docker Model Runner for local LLM)
        dmr_healthy = False
        dmr_error = None
        try:
            import socket
            with socket.create_connection(("localhost", 12434), timeout=1):
                dmr_healthy = True
        except Exception as e:
            dmr_error = str(e)

        # Get director status (use global flag and database heartbeat)
        try:
            director_settings = db.query(DirectorSettings).first()
            # Check running via global flag or database heartbeat
            is_running = _director_daemon_running
            if not is_running and director_settings:
                is_running = director_settings.is_daemon_running()
            director_status = {
                "running": is_running,
                "enabled": getattr(director_settings, 'enabled', False) if director_settings else False,
                "poll_interval": getattr(director_settings, 'poll_interval', 30) if director_settings else 30
            }
        except Exception:
            director_status = {"running": False, "enabled": False, "poll_interval": 30}

        return JsonResponse({
            "queue": queue_stats,
            "workers": workers_status,
            "dmr": {"healthy": dmr_healthy, "error": dmr_error},
            "director": director_status
        })
    finally:
        db.close()


# -----------------------------------------------------------------------------
# Lightweight stubs for endpoints not yet implemented (prevent import errors)
# -----------------------------------------------------------------------------

_STUB_NAMES = [
    'activity_feed', 'audit_log', 'bug_create', 'bug_detail', 'bug_kill', 'bug_list', 'bug_update_status',
    'claim_detail', 'claim_evidence', 'claim_tests',
    'credential_create', 'credential_delete', 'credential_detail', 'credential_update', 'credentials_list',
    'environment_create', 'environment_delete', 'environment_detail', 'environment_update', 'environments_list',
    'llm_activity', 'llm_activity_full', 'llm_session_by_name', 'llm_session_clear', 'llm_session_detail',
    'llm_session_export', 'llm_sessions_list', 'project_audit_log', 'project_claims', 'project_work_cycle_history',
    'queue_check_timeouts', 'queue_cleanup', 'queue_enqueue', 'queue_job_cancel', 'queue_job_kill',
    'queue_job_status', 'queue_job_wait', 'queue_kill_all',
    'run_claim_tests', 'run_claims_summary', 'run_claims_validate', 'run_task_progress',
    'task_advance_stage', 'task_claims', 'task_director_prepare', 'task_enhance', 'task_job_status',
    'task_queue', 'task_set_stage', 'task_simplify', 'task_start_work', 'task_work_cycle_history', 'test_run',
    'threat_intel_create', 'threat_intel_list', 'webhook_create', 'webhook_delete', 'webhook_detail', 'webhook_update', 'webhooks_list'
]

for _name in _STUB_NAMES:
    exec(f"@csrf_exempt\ndef {_name}(request, *args, **kwargs):\n    '''Stub placeholder for { _name }'''\n    return JsonResponse({{'error': 'Not implemented', 'endpoint': '{_name}'}}, status=501)\n")


