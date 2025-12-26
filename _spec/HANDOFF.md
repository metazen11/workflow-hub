# Handoff

## What changed
- MVP Workflow Hub is complete and functional
- All SQLAlchemy models implemented (Project, Requirement, Task, Run, AgentReport, ThreatIntel, AuditEvent)
- Run state machine with gate enforcement (QA/Security gates)
- Human approval required for deployment
- Full audit logging
- 99 tests passing (workflow hub + TUI)
- Dashboard UI at `/ui/`
- Complete REST API

### Rich TUI for Workflow Visualization (NEW)
- **WorkflowTUI class** (`scripts/workflow_tui.py`) - Real-time terminal UI using Rich library
- **Task Queue Table** - Shows all tasks with status icons (✓⋯✗○), priority, and blockers
- **Agent Activity Panel** - Current agent work with elapsed time and color coding
- **Activity Log** - Timestamped entries for task progress and agent output
- **Usage**: `python scripts/workflow.py --tui "task description"`

#### TUI Architecture

The TUI uses the [Rich](https://rich.readthedocs.io/) library for terminal rendering with a four-panel layout:

```
┌─────────────────────────────────────────────────────────┐
│ WORKFLOW: Run-2025-01-01  [3/8]                         │
│ Sandbox: /tmp/sandbox-abc123                            │
├─────────────────────────────────────────────────────────┤
│ TASK QUEUE                                              │
│ ID       │ Title                    │ Status │ Pri      │
│ T001     │ Parse requirements       │   ✓    │  1       │
│ T002     │ Design database schema   │   ⋯    │  2       │
│ T003     │ Implement API endpoints  │   ○    │  3       │
├─────────────────────────────────────────────────────────┤
│ Agent: [DEV] ⣹ Working on: T002 (45s)                   │
├─────────────────────────────────────────────────────────┤
│ Recent Activity                                         │
│ [14:23:45] PM  Analyzed requirements                    │
│ [14:23:50] DEV Starting database design                 │
└─────────────────────────────────────────────────────────┘
```

#### TUI API Reference

```python
from scripts.workflow_tui import WorkflowTUI
from app.models import Task, TaskStatus

# Initialize TUI
tui = WorkflowTUI(
    run_name="Feature-XYZ",
    sandbox_path="/tmp/sandbox-abc123",
    max_log_entries=20  # Optional, default 20
)

# Start live display (context manager)
with tui.start() as live:
    # Update agent status
    tui.start_agent("DEV", "Implementing feature")

    # Add log entries
    tui.log("DEV", "Starting implementation...")

    # Update task counts
    tui.set_status_summary({
        "done": 2,
        "in_progress": 1,
        "backlog": 5,
        "blocked": 0,
        "failed": 0,
        "total": 8
    })

    # Refresh display with current tasks
    tasks = get_tasks_from_db()  # Your task fetching logic
    tui.refresh(tasks)

    # Clear agent when done
    tui.stop_agent()
```

#### Status Icons & Colors

| Status      | Icon | Color   |
|------------|------|---------|
| DONE       | ✓    | green   |
| IN_PROGRESS| ⋯    | yellow  |
| FAILED     | ✗    | red     |
| BACKLOG    | ○    | dim     |
| BLOCKED    | ○    | dim     |

#### Agent Colors

| Agent | Color   |
|-------|---------|
| PM    | magenta |
| DEV   | green   |
| QA    | yellow  |
| SEC   | red     |

### Bug Report Widget (NEW)
- **JavaScript Widget** (`app/static/bug-widget.js`) - Embeddable bug reporting
- **Features**: Auto-capture screenshots (html2canvas), file upload, CORS support
- **API**: POST `/api/bugs/create`, GET `/api/bugs`, PATCH `/api/bugs/<id>/status`
- **Dashboard**: `/ui/bugs/` - View and manage bug reports
- **Usage in any app**:
  ```html
  <script>
    window.BUG_REPORT_API = 'http://localhost:8000/api/bugs/create';
    window.BUG_REPORT_APP = 'My App Name';
  </script>
  <script src="http://localhost:8000/static/bug-widget.js"></script>
  ```

### Task Model Extensions (NEW)
- `priority` (Integer 1-10) - Task priority for queue ordering
- `blocked_by` (JSON array) - Dependency task IDs that block this task
- `run_id` (ForeignKey) - Link to workflow run
- `completed` (Boolean) - Task completion flag
- `completed_at` (DateTime) - Auto-set via PostgreSQL trigger
- `is_blocked(session)` method - Check if dependencies are satisfied
- `TaskStatus.FAILED` - New enum value for failed tasks

### TaskQueueService (NEW)
- `app/services/task_queue_service.py` - DB-backed priority queue
- `get_next_task()` - Returns highest priority unblocked task
- `mark_completed()`, `mark_failed()`, `mark_in_progress()`
- `get_status_summary()` - Returns counts by status
- `get_all_tasks()` - Returns all tasks for current run

### Test Projects
- **Todo App** (`projects/todo-app/todo-app/`) - Flask todo app on port 5050
  - 22 tests passing
  - CSRF protection with Flask-WTF
  - Kanban board with status movement

## What to do next
1. Add more UI features (forms for creating projects/runs)
2. Integrate with actual agent runners (Claude Code hooks)
3. Add authentication for the dashboard
4. Consider adding WebSocket for real-time updates
5. Integrate TUI with web dashboard for dual-mode visualization

## Commands
```bash
# Start everything
docker compose -f docker/docker-compose.yml up -d
source venv/bin/activate
python manage.py runserver 0.0.0.0:8000

# Run workflow with TUI
python scripts/workflow.py --tui "Add feature X to project Y"

# Run workflow without TUI (spinner mode)
python scripts/workflow.py "Add feature X to project Y"

# Run tests
pytest tests/ -v

# Run todo app tests
venv/bin/python -m pytest projects/todo-app/todo-app/tests/ -v

# Create migration after model changes
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Current state
- Server runs on http://localhost:8000
- Dashboard at http://localhost:8000/ui/
- Bug Reports at http://localhost:8000/ui/bugs/
- API at http://localhost:8000/api/
- PostgreSQL on localhost:5432 (credentials in .env)
- Todo App at http://localhost:5050 (with bug widget integrated)
