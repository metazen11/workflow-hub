from django.http import HttpResponse
from django.shortcuts import render
import json

# Minimal UI view stubs used during development/startup.
# These are simple placeholders so URL routing can import the handlers.
# They can be expanded later to render full templates and context.

def dashboard(request):
    return HttpResponse("<h1>Workflow Hub Dashboard (placeholder)</h1>")


def global_board_view(request):
    return HttpResponse("<h1>Global Board (placeholder)</h1>")


def projects_list(request):
    return HttpResponse("<h1>Projects List (placeholder)</h1>")


def task_board_view(request, project_id):
    return HttpResponse(f"<h1>Task Board for project {project_id} (placeholder)</h1>")


def project_view(request, project_id):
    return HttpResponse(f"<h1>Project {project_id} (placeholder)</h1>")


def runs_list(request):
    return HttpResponse("<h1>Runs List (placeholder)</h1>")


def run_view(request, run_id):
    return HttpResponse(f"<h1>Run {run_id} (placeholder)</h1>")


def task_view(request, task_id):
    """Show a single task. Returns 404 if the task doesn't exist.

    Tries to render the existing `task_detail.html` template (found in repo).
    If that template isn't available or rendering fails, falls back to `task.html`
    and finally a simple HTML/JSON dump.
    """
    from django.http import HttpResponseNotFound
    from app.db import get_db
    from app.models import Task as TaskModel

    db = next(get_db())
    try:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            return HttpResponseNotFound(f"Task {task_id} not found")

        # Prefer the canonical task_detail.html if available
        for tpl in ("task_detail.html", "task.html"):
            try:
                context = {"task": task.to_dict()}
                return render(request, tpl, context)
            except Exception:
                # Try next template or fallback to simple HTML
                continue

        # Final fallback - simple HTML + JSON
        data = task.to_dict()
        html = f"<h1>{data.get('task_id','T')}: {data.get('title','No title')}</h1>"
        if data.get('description'):
            html += f"<p>{data.get('description')}</p>"
        html += f"<pre>{json.dumps(data, indent=2)}</pre>"
        return HttpResponse(html)
    finally:
        db.close()


def tasks_list(request):
    return HttpResponse("<h1>Tasks List (placeholder)</h1>")


def bugs_list(request):
    return HttpResponse("<h1>Bugs List (placeholder)</h1>")


def bug_detail_view(request, bug_id):
    return HttpResponse(f"<h1>Bug {bug_id} (placeholder)</h1>")


def ledger_view(request):
    return HttpResponse("<h1>Ledger (placeholder)</h1>")


def ledger_entry_view(request, entry_id):
    return HttpResponse(f"<h1>Ledger Entry {entry_id} (placeholder)</h1>")


def settings_view(request):
    return HttpResponse("<h1>Settings (placeholder)</h1>")


# Helper to get open bugs count (safe - returns 0 on error)
def _get_open_bugs_count(db):
    try:
        from app.models import BugReport, BugReportStatus
        return db.query(BugReport).filter(BugReport.status != BugReportStatus.CLOSED).count()
    except Exception:
        return 0


def activity_view(request):
    """Activity log page showing LLM and agent activity.

    GET /ui/activity/
    """
    from app.db import get_db

    db = next(get_db())
    try:
        open_bugs = _get_open_bugs_count(db)

        context = {
            'active_page': 'activity',
            'open_bugs_count': open_bugs if open_bugs > 0 else None,
        }

        return render(request, 'activity.html', context)
    finally:
        db.close()


def goose_view(request):
    """Goose AI assistant integration view."""
    from app.db import get_db

    db = next(get_db())
    try:
        open_bugs = _get_open_bugs_count(db)

        # Get current working directory for context
        import os
        current_dir = os.getcwd()
        
        # Try to get the repository root if we're in a git repo
        try:
            import subprocess
            repo_root = subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], 
                                               cwd=current_dir, stderr=subprocess.DEVNULL, 
                                               universal_newlines=True).strip()
        except:
            repo_root = current_dir

        context = {
            'active_page': 'goose',
            'open_bugs_count': open_bugs if open_bugs > 0 else None,
            'repo_root': repo_root,
            'current_dir': current_dir,
        }

        return render(request, 'goose.html', context)
    finally:
        db.close()
