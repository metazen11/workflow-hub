"""UI views for Workflow Hub dashboard."""
from django.http import HttpResponse
from app.db import get_db
from app.models import Project, Run, Task, TaskStatus, AuditEvent


def _state_color(state_value):
    """Get color for run state."""
    colors = {
        "pm": "#6366f1",
        "dev": "#8b5cf6",
        "qa": "#3b82f6",
        "qa_failed": "#ef4444",
        "sec": "#f59e0b",
        "sec_failed": "#ef4444",
        "ready_for_commit": "#10b981",
        "merged": "#06b6d4",
        "ready_for_deploy": "#84cc16",
        "deployed": "#22c55e",
    }
    return colors.get(state_value, "#6b7280")


def _status_color(status_value):
    """Get color for task status."""
    colors = {
        "backlog": "#6b7280",
        "in_progress": "#3b82f6",
        "blocked": "#ef4444",
        "done": "#22c55e",
    }
    return colors.get(status_value, "#6b7280")


def dashboard(request):
    """Main dashboard view."""
    db = next(get_db())
    try:
        projects = db.query(Project).order_by(Project.created_at.desc()).all()
        recent_runs = db.query(Run).order_by(Run.created_at.desc()).limit(10).all()
        recent_events = db.query(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(10).all()

        projects_html = ""
        for p in projects:
            run_count = len(p.runs)
            task_count = len(p.tasks)
            projects_html += f'''
            <div class="card">
                <h3><a href="/ui/project/{p.id}">{p.name}</a></h3>
                <p class="muted">{p.description or 'No description'}</p>
                <div class="stats">
                    <span>{task_count} tasks</span>
                    <span>{run_count} runs</span>
                </div>
                <div class="tags">
                    {''.join(f'<span class="tag">{t}</span>' for t in (p.stack_tags or []))}
                </div>
            </div>
            '''

        runs_html = ""
        for r in recent_runs:
            color = _state_color(r.state.value)
            runs_html += f'''
            <tr>
                <td><a href="/ui/run/{r.id}">{r.name}</a></td>
                <td><span class="badge" style="background:{color}">{r.state.value.upper()}</span></td>
                <td>{r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else ''}</td>
            </tr>
            '''

        events_html = ""
        for e in recent_events:
            events_html += f'''
            <tr>
                <td>{e.timestamp.strftime('%H:%M:%S') if e.timestamp else ''}</td>
                <td>{e.actor}</td>
                <td>{e.action}</td>
                <td>{e.entity_type} #{e.entity_id or ''}</td>
            </tr>
            '''

        html = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Workflow Hub</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    background: #0f172a;
                    color: #e2e8f0;
                    line-height: 1.6;
                }}
                .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
                header {{
                    background: #1e293b;
                    padding: 20px;
                    margin-bottom: 30px;
                    border-bottom: 1px solid #334155;
                }}
                header h1 {{ color: #38bdf8; font-size: 1.8rem; }}
                header nav {{ margin-top: 10px; }}
                header nav a {{
                    color: #94a3b8;
                    text-decoration: none;
                    margin-right: 20px;
                }}
                header nav a:hover {{ color: #38bdf8; }}
                .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }}
                .card {{
                    background: #1e293b;
                    border-radius: 8px;
                    padding: 20px;
                    border: 1px solid #334155;
                }}
                .card h3 {{ color: #f1f5f9; margin-bottom: 10px; }}
                .card h3 a {{ color: inherit; text-decoration: none; }}
                .card h3 a:hover {{ color: #38bdf8; }}
                .muted {{ color: #64748b; font-size: 0.9rem; }}
                .stats {{ margin-top: 15px; color: #94a3b8; font-size: 0.85rem; }}
                .stats span {{ margin-right: 15px; }}
                .tags {{ margin-top: 10px; }}
                .tag {{
                    display: inline-block;
                    background: #334155;
                    color: #94a3b8;
                    padding: 2px 8px;
                    border-radius: 4px;
                    font-size: 0.75rem;
                    margin-right: 5px;
                }}
                h2 {{
                    color: #f1f5f9;
                    margin: 30px 0 15px;
                    font-size: 1.3rem;
                }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{
                    text-align: left;
                    padding: 12px;
                    border-bottom: 1px solid #334155;
                }}
                th {{ color: #94a3b8; font-weight: 500; }}
                td a {{ color: #38bdf8; text-decoration: none; }}
                td a:hover {{ text-decoration: underline; }}
                .badge {{
                    display: inline-block;
                    padding: 3px 10px;
                    border-radius: 4px;
                    font-size: 0.75rem;
                    font-weight: 600;
                    color: white;
                }}
                .section {{ background: #1e293b; border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <header>
                <div class="container">
                    <h1>Workflow Hub</h1>
                    <nav>
                        <a href="/ui/">Dashboard</a>
                        <a href="/api/status">API Status</a>
                        <a href="/api/audit">Audit Log</a>
                    </nav>
                </div>
            </header>
            <div class="container">
                <h2>Projects</h2>
                <div class="grid">
                    {projects_html or '<div class="card"><p class="muted">No projects yet. Create one via API.</p></div>'}
                </div>

                <h2>Recent Runs</h2>
                <div class="section">
                    <table>
                        <thead><tr><th>Run</th><th>State</th><th>Created</th></tr></thead>
                        <tbody>{runs_html or '<tr><td colspan="3" class="muted">No runs yet</td></tr>'}</tbody>
                    </table>
                </div>

                <h2>Recent Activity</h2>
                <div class="section">
                    <table>
                        <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Entity</th></tr></thead>
                        <tbody>{events_html or '<tr><td colspan="4" class="muted">No activity yet</td></tr>'}</tbody>
                    </table>
                </div>
            </div>
        </body>
        </html>
        '''
        return HttpResponse(html)
    finally:
        db.close()


def project_view(request, project_id):
    """Project detail view."""
    db = next(get_db())
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return HttpResponse("Project not found", status=404)

        # Requirements
        reqs_html = ""
        for r in project.requirements:
            reqs_html += f'''
            <tr>
                <td><strong>{r.req_id}</strong></td>
                <td>{r.title}</td>
                <td class="muted">{(r.acceptance_criteria or '')[:100]}...</td>
            </tr>
            '''

        # Tasks
        tasks_html = ""
        for t in project.tasks:
            color = _status_color(t.status.value)
            reqs = ', '.join(r.req_id for r in t.requirements) or '-'
            tasks_html += f'''
            <tr>
                <td><strong>{t.task_id}</strong></td>
                <td>{t.title}</td>
                <td><span class="badge" style="background:{color}">{t.status.value.upper()}</span></td>
                <td>{reqs}</td>
            </tr>
            '''

        # Runs
        runs_html = ""
        for r in project.runs:
            color = _state_color(r.state.value)
            runs_html += f'''
            <tr>
                <td><a href="/ui/run/{r.id}">{r.name}</a></td>
                <td><span class="badge" style="background:{color}">{r.state.value.upper()}</span></td>
                <td>{r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else ''}</td>
            </tr>
            '''

        html = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>{project.name} - Workflow Hub</title>
            <meta charset="utf-8">
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    background: #0f172a;
                    color: #e2e8f0;
                    line-height: 1.6;
                }}
                .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
                header {{
                    background: #1e293b;
                    padding: 20px;
                    margin-bottom: 30px;
                    border-bottom: 1px solid #334155;
                }}
                header h1 {{ color: #38bdf8; font-size: 1.8rem; }}
                header nav {{ margin-top: 10px; }}
                header nav a {{ color: #94a3b8; text-decoration: none; margin-right: 20px; }}
                header nav a:hover {{ color: #38bdf8; }}
                .muted {{ color: #64748b; }}
                h2 {{ color: #f1f5f9; margin: 30px 0 15px; font-size: 1.3rem; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ text-align: left; padding: 12px; border-bottom: 1px solid #334155; }}
                th {{ color: #94a3b8; font-weight: 500; }}
                td a {{ color: #38bdf8; text-decoration: none; }}
                .badge {{
                    display: inline-block;
                    padding: 3px 10px;
                    border-radius: 4px;
                    font-size: 0.75rem;
                    font-weight: 600;
                    color: white;
                }}
                .section {{ background: #1e293b; border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
                .tags {{ margin-top: 10px; }}
                .tag {{
                    display: inline-block;
                    background: #334155;
                    color: #94a3b8;
                    padding: 4px 12px;
                    border-radius: 4px;
                    font-size: 0.85rem;
                    margin-right: 8px;
                }}
            </style>
        </head>
        <body>
            <header>
                <div class="container">
                    <h1>{project.name}</h1>
                    <nav>
                        <a href="/ui/">← Dashboard</a>
                        <a href="/api/projects/{project.id}">API</a>
                    </nav>
                </div>
            </header>
            <div class="container">
                <div class="section">
                    <p>{project.description or 'No description'}</p>
                    <p class="muted" style="margin-top:10px">Path: {project.repo_path or 'Not set'}</p>
                    <div class="tags" style="margin-top:15px">
                        {''.join(f'<span class="tag">{t}</span>' for t in (project.stack_tags or []))}
                    </div>
                </div>

                <h2>Requirements</h2>
                <div class="section">
                    <table>
                        <thead><tr><th>ID</th><th>Title</th><th>Acceptance Criteria</th></tr></thead>
                        <tbody>{reqs_html or '<tr><td colspan="3" class="muted">No requirements</td></tr>'}</tbody>
                    </table>
                </div>

                <h2>Tasks</h2>
                <div class="section">
                    <table>
                        <thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Requirements</th></tr></thead>
                        <tbody>{tasks_html or '<tr><td colspan="4" class="muted">No tasks</td></tr>'}</tbody>
                    </table>
                </div>

                <h2>Runs</h2>
                <div class="section">
                    <table>
                        <thead><tr><th>Run</th><th>State</th><th>Created</th></tr></thead>
                        <tbody>{runs_html or '<tr><td colspan="3" class="muted">No runs</td></tr>'}</tbody>
                    </table>
                </div>
            </div>
        </body>
        </html>
        '''
        return HttpResponse(html)
    finally:
        db.close()


def run_view(request, run_id):
    """Run detail view with state machine visualization."""
    db = next(get_db())
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            return HttpResponse("Run not found", status=404)

        # State machine visualization
        states = ["pm", "dev", "qa", "sec", "ready_for_commit", "merged", "ready_for_deploy", "deployed"]
        current_idx = states.index(run.state.value) if run.state.value in states else -1

        state_html = ""
        for i, s in enumerate(states):
            if i < current_idx:
                cls = "completed"
            elif i == current_idx:
                cls = "current"
            else:
                cls = "pending"
            state_html += f'<div class="state {cls}">{s.upper()}</div>'
            if i < len(states) - 1:
                state_html += '<div class="arrow">→</div>'

        # Reports
        reports_html = ""
        for report in run.reports:
            status_color = "#22c55e" if report.status.value == "pass" else "#ef4444" if report.status.value == "fail" else "#f59e0b"
            reports_html += f'''
            <div class="report">
                <div class="report-header">
                    <strong>{report.role.value.upper()}</strong>
                    <span class="badge" style="background:{status_color}">{report.status.value.upper()}</span>
                </div>
                <p>{report.summary or 'No summary'}</p>
                <pre>{str(report.details) if report.details else ''}</pre>
            </div>
            '''

        html = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>{run.name} - Workflow Hub</title>
            <meta charset="utf-8">
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    background: #0f172a;
                    color: #e2e8f0;
                    line-height: 1.6;
                }}
                .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
                header {{
                    background: #1e293b;
                    padding: 20px;
                    margin-bottom: 30px;
                }}
                header h1 {{ color: #38bdf8; font-size: 1.8rem; }}
                header nav {{ margin-top: 10px; }}
                header nav a {{ color: #94a3b8; text-decoration: none; margin-right: 20px; }}
                .section {{ background: #1e293b; border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
                h2 {{ color: #f1f5f9; margin: 30px 0 15px; font-size: 1.3rem; }}
                .pipeline {{
                    display: flex;
                    align-items: center;
                    flex-wrap: wrap;
                    gap: 5px;
                    padding: 20px;
                }}
                .state {{
                    padding: 10px 15px;
                    border-radius: 6px;
                    font-size: 0.8rem;
                    font-weight: 600;
                }}
                .state.completed {{ background: #22c55e; color: white; }}
                .state.current {{ background: #3b82f6; color: white; animation: pulse 2s infinite; }}
                .state.pending {{ background: #334155; color: #64748b; }}
                .arrow {{ color: #64748b; font-size: 1.2rem; }}
                @keyframes pulse {{
                    0%, 100% {{ opacity: 1; }}
                    50% {{ opacity: 0.7; }}
                }}
                .badge {{
                    display: inline-block;
                    padding: 3px 10px;
                    border-radius: 4px;
                    font-size: 0.75rem;
                    font-weight: 600;
                    color: white;
                }}
                .report {{
                    background: #0f172a;
                    border-radius: 6px;
                    padding: 15px;
                    margin-bottom: 15px;
                }}
                .report-header {{
                    display: flex;
                    justify-content: space-between;
                    margin-bottom: 10px;
                }}
                .report pre {{
                    background: #1e293b;
                    padding: 10px;
                    border-radius: 4px;
                    font-size: 0.8rem;
                    overflow-x: auto;
                    margin-top: 10px;
                }}
                .actions {{ margin-top: 20px; }}
                .btn {{
                    display: inline-block;
                    padding: 10px 20px;
                    background: #3b82f6;
                    color: white;
                    text-decoration: none;
                    border-radius: 6px;
                    font-weight: 500;
                    margin-right: 10px;
                    border: none;
                    cursor: pointer;
                }}
                .btn:hover {{ background: #2563eb; }}
                .btn.approve {{ background: #22c55e; }}
                .btn.approve:hover {{ background: #16a34a; }}
            </style>
        </head>
        <body>
            <header>
                <div class="container">
                    <h1>{run.name}</h1>
                    <nav>
                        <a href="/ui/">← Dashboard</a>
                        <a href="/api/runs/{run.id}">API</a>
                    </nav>
                </div>
            </header>
            <div class="container">
                <h2>Pipeline Status</h2>
                <div class="section">
                    <div class="pipeline">
                        {state_html}
                    </div>
                    <div class="actions">
                        <p style="color:#64748b;margin-bottom:10px">Current state: <strong>{run.state.value.upper()}</strong></p>
                        {'<p style="color:#84cc16">Ready for human approval to deploy!</p>' if run.state.value == 'ready_for_deploy' else ''}
                    </div>
                </div>

                <h2>Agent Reports</h2>
                <div class="section">
                    {reports_html or '<p style="color:#64748b">No reports submitted yet</p>'}
                </div>

                <h2>Artifacts</h2>
                <div class="section">
                    <p><strong>PM Result:</strong> {str(run.pm_result) if run.pm_result else 'None'}</p>
                    <p><strong>Dev Result:</strong> {str(run.dev_result) if run.dev_result else 'None'}</p>
                    <p><strong>QA Result:</strong> {str(run.qa_result) if run.qa_result else 'None'}</p>
                    <p><strong>Security Result:</strong> {str(run.sec_result) if run.sec_result else 'None'}</p>
                </div>
            </div>
        </body>
        </html>
        '''
        return HttpResponse(html)
    finally:
        db.close()
