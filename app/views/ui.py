"""UI views for Workflow Hub dashboard."""
from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from app.db import get_db
from app.models import Project, Run, Task, TaskStatus, TaskPipelineStage, AuditEvent, RunState, Credential, Environment
from app.models.bug_report import BugReport, BugReportStatus


def _get_status_class(status_value):
    """Map status to CSS class."""
    mapping = {
        # Bug statuses
        "open": "danger",
        "in_progress": "warning",
        "resolved": "success",
        "closed": "secondary",
        # Run states
        "pm": "info",
        "dev": "info",
        "qa": "warning",
        "qa_failed": "danger",
        "sec": "purple",
        "sec_failed": "danger",
        "docs": "info",
        "docs_failed": "danger",
        "ready_for_commit": "success",
        "merged": "info",
        "ready_for_deploy": "warning",
        "testing": "warning",
        "testing_failed": "danger",
        "deployed": "success",
        # Task statuses
        "backlog": "secondary",
        "blocked": "danger",
        "done": "success",
        "failed": "danger",
    }
    return mapping.get(status_value, "secondary")


def _get_pipeline_stage_class(stage_value):
    """Map pipeline stage to CSS class."""
    mapping = {
        "none": "secondary",
        "dev": "info",
        "qa": "warning",
        "sec": "purple",
        "docs": "info",
        "complete": "success",
    }
    return mapping.get(stage_value, "secondary")


def _get_open_bugs_count(db):
    """Get count of open bugs for nav badge (excludes killed)."""
    return db.query(BugReport).filter(
        BugReport.status == BugReportStatus.OPEN,
        BugReport.killed == False
    ).count()


def _format_run(r):
    """Format a run for template context."""
    return {
        'id': r.id,
        'name': r.name,
        'state': r.state.value.upper(),
        'state_class': _get_status_class(r.state.value),
        'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else ''
    }


def dashboard(request):
    """Main dashboard view."""
    db = next(get_db())
    try:
        # Stats (exclude killed items)
        open_bugs = db.query(BugReport).filter(
            BugReport.status == BugReportStatus.OPEN,
            BugReport.killed == False
        ).count()
        active_runs = db.query(Run).filter(
            Run.state.notin_([RunState.DEPLOYED]),
            Run.killed == False
        ).count()
        total_tasks = db.query(Task).count()
        total_projects = db.query(Project).count()

        # All runs for kanban board (exclude killed)
        all_runs = db.query(Run).filter(Run.killed == False).order_by(Run.created_at.desc()).all()

        # Group runs by pipeline stage
        kanban = {
            'pm': [],
            'dev': [],
            'qa': [],
            'failed': [],
            'sec': [],
            'docs': [],
            'deploy': [],
            'testing': []
        }

        for r in all_runs:
            run_data = _format_run(r)
            state = r.state

            if state == RunState.PM:
                kanban['pm'].append(run_data)
            elif state == RunState.DEV:
                kanban['dev'].append(run_data)
            elif state == RunState.QA:
                kanban['qa'].append(run_data)
            elif state in (RunState.QA_FAILED, RunState.SEC_FAILED, RunState.DOCS_FAILED, RunState.TESTING_FAILED):
                kanban['failed'].append(run_data)
            elif state == RunState.SEC:
                kanban['sec'].append(run_data)
            elif state == RunState.DOCS:
                kanban['docs'].append(run_data)
            elif state in (RunState.READY_FOR_COMMIT, RunState.MERGED, RunState.READY_FOR_DEPLOY):
                kanban['deploy'].append(run_data)
            elif state == RunState.TESTING:
                kanban['testing'].append(run_data)
            elif state == RunState.DEPLOYED:
                kanban['deploy'].append(run_data)  # Show deployed in deploy column

        # Projects
        projects_list = db.query(Project).order_by(Project.created_at.desc()).all()
        projects = db.query(Project).filter(Project.is_archived == False).all()
        for p in projects:
            p.task_count = db.query(Task).filter(Task.project_id == p.id).count()
            p.run_count = db.query(Run).filter(Run.project_id == p.id).count()

        # Active Tasks - Group by Pipeline Stage for Kanban
        task_kanban = {
            'backlog': [],
            'dev': [],
            'qa': [],
            'sec': [],
            'docs': [],
            'complete': []
        }
        
        # Fetch all non-archived tasks
        all_active_tasks = db.query(Task).filter(
            Task.status != TaskStatus.DONE
        ).order_by(Task.priority.desc(), Task.created_at.desc()).all()

        for t in all_active_tasks:
            # Map stage to key (lowercase for kanban dict keys)
            stage_key = 'backlog'
            if t.pipeline_stage:
                val = t.pipeline_stage.value.lower()  # Lowercase to match dict keys
                if val == 'none':
                    stage_key = 'backlog'
                else:
                    stage_key = val

            if stage_key in task_kanban:
                task_kanban[stage_key].append({
                    'id': t.id,
                    'title': t.title,
                    'project_name': t.project.name if t.project else '',
                    'priority': t.priority,
                    'status_class': _get_status_class(t.status.value),
                    'run_id': t.run_id
                })

        # Recent activity (mix of bugs, runs, and recently completed tasks)
        recent_events = db.query(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(10).all()
        recent_tasks = db.query(Task).order_by(Task.created_at.desc()).limit(5).all()
        
        activity = []
        
        # 1. Recent bugs
        recent_bugs = db.query(BugReport).order_by(BugReport.created_at.desc()).limit(5).all()
        for b in recent_bugs:
            activity.append({
                'type': 'bug',
                'title': f"Bug: {b.title}",
                'description': b.description[:50] + "...",
                'time': b.created_at.strftime('%Y-%m-%d %H:%M'),
                'url': f"/ui/bugs/{b.id}/",
                'created_at': b.created_at
            })
        for t in recent_tasks:
            activity.append({
                'type': 'task',
                'title': f'Task: {t.title}',
                'description': f'{t.status.value if t.status else "backlog"} - {t.project.name if t.project else "No project"}',
                'time': t.created_at.strftime('%H:%M') if t.created_at else '',
                'timestamp': t.created_at,
                'url': f'/ui/task/{t.id}/'
            })
        for e in recent_events:
            activity.append({
                'type': 'human' if e.actor == 'human' else 'event',
                'title': f'{e.action.title()} {e.entity_type}',
                'description': f'by {e.actor}',
                'time': e.timestamp.strftime('%H:%M') if e.timestamp else '',
                'timestamp': e.timestamp,
                'url': None
            })

        # Sort by timestamp and take most recent
        activity.sort(key=lambda x: x['timestamp'] or '', reverse=True)
        activity = activity[:10]

        context = {
            'active_page': 'dashboard',
            'stats': {
                'open_bugs': open_bugs,
                'active_runs': active_runs,
                'total_tasks': total_tasks,
                'total_projects': total_projects
            },
            'kanban': kanban,
            'task_kanban': task_kanban,
            'activity': activity,
            'projects': projects,
            'active_tasks': [], # Legacy support if needed, empty now
            'open_bugs_count': open_bugs if open_bugs > 0 else None
        }

        return render(request, 'dashboard.html', context)
    finally:
        db.close()


def bugs_list(request):
    """Bug reports list view."""
    db = next(get_db())
    try:
        # Exclude killed bugs from main list
        all_bugs = db.query(BugReport).filter(BugReport.killed == False).order_by(BugReport.created_at.desc()).all()

        # Stats
        stats = {
            'total': len(all_bugs),
            'open': sum(1 for b in all_bugs if b.status == BugReportStatus.OPEN),
            'in_progress': sum(1 for b in all_bugs if b.status == BugReportStatus.IN_PROGRESS),
            'resolved': sum(1 for b in all_bugs if b.status == BugReportStatus.RESOLVED)
        }

        bugs = [{
            'id': b.id,
            'title': b.title,
            'app_name': b.app_name,
            'status': b.status.value.upper(),
            'status_class': _get_status_class(b.status.value),
            'screenshot': b.screenshot,
            'created_at': b.created_at.strftime('%Y-%m-%d %H:%M') if b.created_at else ''
        } for b in all_bugs]

        context = {
            'active_page': 'bugs',
            'open_bugs_count': stats['open'] if stats['open'] > 0 else None,
            'stats': stats,
            'bugs': bugs
        }

        return render(request, 'bugs.html', context)
    finally:
        db.close()


def bug_detail_view(request, bug_id):
    """Bug report detail view."""
    db = next(get_db())
    try:
        bug = db.query(BugReport).filter(BugReport.id == bug_id).first()
        if not bug:
            return HttpResponse("Bug not found", status=404)

        open_bugs = _get_open_bugs_count(db)

        context = {
            'active_page': 'bugs',
            'open_bugs_count': open_bugs if open_bugs > 0 else None,
            'bug': {
                'id': bug.id,
                'title': bug.title,
                'description': bug.description,
                'screenshot': bug.screenshot,
                'url': bug.url,
                'user_agent': bug.user_agent,
                'app_name': bug.app_name,
                'status': bug.status.value,
                'status_class': _get_status_class(bug.status.value),
                'created_at': bug.created_at.strftime('%Y-%m-%d %H:%M') if bug.created_at else '',
                'resolved_at': bug.resolved_at.strftime('%Y-%m-%d %H:%M') if bug.resolved_at else None
            }
        }

        return render(request, 'bug_detail.html', context)
    finally:
        db.close()


def runs_list(request):
    """All runs list view."""
    db = next(get_db())
    try:
        # Exclude killed runs
        all_runs = db.query(Run).filter(Run.killed == False).order_by(Run.created_at.desc()).all()
        all_projects = db.query(Project).order_by(Project.name).all()
        open_bugs = _get_open_bugs_count(db)

        # Stats
        stats = {
            'total': len(all_runs),
            'active': sum(1 for r in all_runs if r.state not in [RunState.DEPLOYED, RunState.QA_FAILED, RunState.SEC_FAILED]),
            'completed': sum(1 for r in all_runs if r.state == RunState.DEPLOYED),
            'failed': sum(1 for r in all_runs if r.state in [RunState.QA_FAILED, RunState.SEC_FAILED])
        }

        runs = [{
            'id': r.id,
            'name': r.name,
            'project_name': r.project.name if r.project else 'Unknown',
            'project_id': r.project_id,
            'state': r.state.value.upper().replace('_', ' '),
            'state_raw': r.state.value,
            'state_class': _get_status_class(r.state.value),
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else '',
        } for r in all_runs]

        projects = [{'id': p.id, 'name': p.name} for p in all_projects]

        context = {
            'active_page': 'runs',
            'stats': stats,
            'runs': runs,
            'projects': projects,
            'open_bugs_count': open_bugs
        }

        return render(request, 'runs_list.html', context)
    finally:
        db.close()


def projects_list(request):
    """Projects list view."""
    db = next(get_db())
    try:
        all_projects = db.query(Project).order_by(Project.created_at.desc()).all()
        open_bugs = _get_open_bugs_count(db)

        # Stats
        stats = {
            'total': len(all_projects),
            'active': sum(1 for p in all_projects if p.is_active is not False),
            'with_tasks': sum(1 for p in all_projects if len(p.tasks) > 0)
        }

        projects = [{
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'repo_path': p.repo_path,
            'task_count': len(p.tasks),
            'run_count': len(p.runs),
            'is_active': p.is_active is not False,
            'is_archived': p.is_archived or False
        } for p in all_projects]

        context = {
            'active_page': 'projects',
            'open_bugs_count': open_bugs if open_bugs > 0 else None,
            'stats': stats,
            'projects': projects
        }

        return render(request, 'projects.html', context)
    finally:
        db.close()


@ensure_csrf_cookie
def project_view(request, project_id):
    """Project detail view with credentials and environments."""
    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return HttpResponse("Project not found", status=404)

        open_bugs = _get_open_bugs_count(db)

        # Get credentials
        credentials = db.query(Credential).filter(Credential.project_id == project_id).all()
        credentials_data = [{
            'id': c.id,
            'name': c.name,
            'credential_type': c.credential_type.value if c.credential_type else 'other',
            'service': c.service,
            'environment': c.environment,
            'is_active': c.is_active if c.is_active is not None else True
        } for c in credentials]

        # Get environments
        environments = db.query(Environment).filter(Environment.project_id == project_id).all()
        environments_data = [{
            'id': e.id,
            'name': e.name,
            'env_type': e.env_type.value if e.env_type else 'other',
            'url': e.url,
            'ssh_host': e.ssh_host,
            'ssh_port': e.ssh_port,
            'ssh_user': e.ssh_user,
            'path': e.path,
            'is_healthy': e.is_healthy,
            'is_active': e.is_active if e.is_active is not None else True
        } for e in environments]

        # Get tasks
        tasks = [{
            'id': t.id,
            'task_id': t.task_id,
            'title': t.title,
            'status': t.status.value if t.status else 'backlog',
            'status_class': _get_status_class(t.status.value if t.status else 'backlog'),
            'priority': t.priority
        } for t in project.tasks]

        context = {
            'active_page': 'projects',
            'open_bugs_count': open_bugs if open_bugs > 0 else None,
            'project': {
                'id': project.id,
                'name': project.name,
                'description': project.description,
                'repo_path': project.repo_path,
                'repository_url': project.repository_url,
                'repository_ssh_url': project.repository_ssh_url,
                'primary_branch': project.primary_branch,
                'documentation_url': project.documentation_url,
                'entry_point': project.entry_point,
                'languages': project.languages or [],
                'frameworks': project.frameworks or [],
                'databases': project.databases or [],
                'key_files': project.key_files or [],
                'config_files': project.config_files or [],
                'build_command': project.build_command,
                'test_command': project.test_command,
                'run_command': project.run_command,
                'deploy_command': project.deploy_command,
                'additional_commands': project.additional_commands or {},
                'default_port': project.default_port,
                'python_version': project.python_version,
                'node_version': project.node_version,
                'is_active': project.is_active,
                'is_archived': project.is_archived
            },
            'credentials': credentials_data,
            'environments': environments_data,
            'tasks': tasks
        }

        return render(request, 'project_detail.html', context)
    finally:
        db.close()


def run_view(request, run_id):
    """Run detail view with controls."""
    db = next(get_db())
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return HttpResponse("Run not found", status=404)

        project = db.query(Project).filter(Project.id == run.project_id).first()
        open_bugs = _get_open_bugs_count(db)

        # Get tasks for this run (directly linked)
        run_tasks = db.query(Task).filter(Task.run_id == run_id).order_by(Task.priority.desc()).all()

        # Get ALL tasks for the project (may or may not have run_id set)
        project_tasks = db.query(Task).filter(Task.project_id == run.project_id).order_by(Task.priority.desc()).all()

        # Combine: show project tasks (which includes run tasks)
        tasks = project_tasks

        # Get audit events for this run
        audit_events = db.query(AuditEvent).filter(
            AuditEvent.entity_type == "run",
            AuditEvent.entity_id == run_id
        ).order_by(AuditEvent.timestamp.desc()).limit(20).all()

        # Build pipeline stages
        all_states = ["pm", "dev", "qa", "sec", "docs", "ready_for_commit", "merged", "ready_for_deploy", "testing", "deployed"]
        failed_states = ["qa_failed", "sec_failed", "docs_failed", "testing_failed"]
        current_state = run.state.value

        pipeline_stages = []
        current_found = False
        for state in all_states:
            stage = {
                "name": state,
                "label": state.upper().replace("_", " "),
                "completed": False,
                "failed": False
            }
            if state == current_state:
                current_found = True
            elif not current_found:
                stage["completed"] = True
            pipeline_stages.append(stage)

        # Check for failed states
        if current_state in failed_states:
            base_state = current_state.replace("_failed", "")
            for stage in pipeline_stages:
                if stage["name"] == base_state:
                    stage["failed"] = True

        # Build results dict
        results = {
            "pm": run.pm_result,
            "dev": run.dev_result,
            "qa": run.qa_result,
            "sec": run.sec_result,
            "docs": run.docs_result if hasattr(run, 'docs_result') else None,
            "testing": run.testing_result if hasattr(run, 'testing_result') else None,
        }

        # State flags for template
        is_failed = current_state in ['qa_failed', 'sec_failed', 'docs_failed', 'testing_failed']
        is_ready_for_deploy = current_state == 'ready_for_deploy'
        can_deploy = current_state in ['ready_for_deploy', 'testing']
        can_rollback = current_state in ['deployed', 'testing', 'testing_failed']

        context = {
            'active_page': 'runs',
            'open_bugs_count': open_bugs if open_bugs > 0 else None,
            'run': {
                'id': run.id,
                'name': run.name,
                'state': current_state,
                'state_class': _get_status_class(current_state),
                'project_id': run.project_id,
                'project_name': project.name if project else 'Unknown',
                'killed': run.killed,
                'is_failed': is_failed,
                'is_ready_for_deploy': is_ready_for_deploy,
                'can_deploy': can_deploy,
                'can_rollback': can_rollback,
                'created_at': run.created_at.strftime('%Y-%m-%d %H:%M') if run.created_at else '',
                'results': results,
            },
            'pipeline_stages': pipeline_stages,
            'all_states': all_states + failed_states,
            'tasks': [{
                'id': t.id,
                'task_id': t.task_id,
                'title': t.title,
                'description': t.description or '',
                'status': t.status.value if t.status else 'backlog',
                'status_class': _get_status_class(t.status.value if t.status else 'backlog'),
                'pipeline_stage': t.pipeline_stage.value if t.pipeline_stage else 'none',
                'pipeline_stage_class': _get_pipeline_stage_class(t.pipeline_stage.value if t.pipeline_stage else 'none'),
                'priority': t.priority or 5,
                'blocked_by': ','.join(t.blocked_by) if t.blocked_by else '',
                'acceptance_criteria': '\n'.join(t.acceptance_criteria) if t.acceptance_criteria else '',
                'run_id': t.run_id,
                'linked_to_run': t.run_id == run_id,
            } for t in tasks],
            'run_task_count': len(run_tasks),
            'project_task_count': len(project_tasks),
            'audit_events': [{
                'timestamp': e.timestamp.strftime('%H:%M:%S') if e.timestamp else '',
                'actor': e.actor,
                'action': e.action,
                'details': str(e.details) if e.details else '',
            } for e in audit_events],
        }

        return render(request, 'run_detail.html', context)
    finally:
        db.close()


@ensure_csrf_cookie
def task_view(request, task_id):
    """Task detail view with attachments."""
    db = next(get_db())
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return HttpResponse("Task not found", status=404)

        open_bugs = _get_open_bugs_count(db)

        # Get attachments
        from app.models import TaskAttachment
        attachments = db.query(TaskAttachment).filter(TaskAttachment.task_id == task_id).all()

        # Build pipeline stages from enum for dynamic dropdown
        # Labels come from TaskPipelineStage.label property
        pipeline_stages = [
            {'value': stage.value, 'label': stage.label}
            for stage in TaskPipelineStage
        ]

        context = {
            'active_page': 'tasks',
            'open_bugs_count': open_bugs if open_bugs > 0 else None,
            'task': {
                'id': task.id,
                'task_id': task.task_id,
                'title': task.title,
                'description': task.description,
                'status': task.status.value if task.status else 'backlog',
                'status_class': _get_status_class(task.status.value if task.status else 'backlog'),
                'priority': task.priority,
                'blocked_by': task.blocked_by or [],
                'project_id': task.project_id,
                'project_name': task.project.name if task.project else 'Unknown',
                'run_id': task.run_id,
                'created_at': task.created_at.strftime('%Y-%m-%d %H:%M') if task.created_at else '',
                'pipeline_stage': task.pipeline_stage.value if task.pipeline_stage else 'none',
            },
            'attachments': [a.to_dict() for a in attachments],
            'pipeline_stages': pipeline_stages,
        }

        return render(request, 'task_detail.html', context)
    finally:
        db.close()

def task_board_view(request, project_id):
    """Kanban board view for a project."""
    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return HttpResponse("Project not found", status=404)

        open_bugs = _get_open_bugs_count(db)

        # Categorize tasks by pipeline stage
        board = {
            'none': [],
            'dev': [],
            'qa': [],
            'sec': [],
            'docs': [],
            'complete': []
        }

        # Fetch all tasks for the project
        tasks = project.tasks
        
        for task in tasks:
            stage = task.pipeline_stage.value if task.pipeline_stage else 'none'
            if stage in board:
                board[stage].append(task)
            else:
                 # Fallback for unknown stages
                board['none'].append(task)
        
        # Sort each column by priority (descending)
        for stage in board:
            board[stage].sort(key=lambda t: t.priority or 0, reverse=True)

        context = {
            'active_page': 'projects',
            'open_bugs_count': open_bugs if open_bugs > 0 else None,
            'project': project,
            'board': board
        }

        return render(request, 'task_board.html', context)
    finally:
        db.close()
