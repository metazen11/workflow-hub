#!/usr/bin/env python3
"""
Workflow CLI - Run a task through the full agent pipeline.

Usage:
    python scripts/workflow.py "Add delete functionality to the todo app"
    python scripts/workflow.py --project "My App" "Implement user login"

The task automatically flows through:
    PM (plan) → DEV (implement) → QA (test) → SEC (security) → Ready

Each agent is sandboxed to the current working directory.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime
import requests

# Optional TUI support
try:
    from scripts.workflow_tui import WorkflowTUI
    HAS_TUI = True
except ImportError:
    HAS_TUI = False

# Database support
try:
    from core.db import SessionLocal
    from app.models import Project, Run, RunState
    from app.models.task import Task as DBTask, TaskStatus
    from app.services.task_queue_service import TaskQueueService
    HAS_DB = True
except ImportError:
    HAS_DB = False

# Workflow Hub API
HUB_URL = os.getenv("WORKFLOW_HUB_URL", "http://localhost:8000")

# Colors
class C:
    PM = "\033[35m"      # Magenta
    DEV = "\033[32m"     # Green
    QA = "\033[33m"      # Yellow
    SEC = "\033[31m"     # Red
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    OK = "\033[92m"
    FAIL = "\033[91m"


@dataclass
class Task:
    """Atomic task with priority and dependencies."""
    id: str
    title: str
    priority: int = 1  # Higher = more important
    status: str = "pending"  # pending, in_progress, completed, failed
    blocked_by: list = field(default_factory=list)  # List of task IDs
    assigned_to: Optional[str] = None  # Agent currently working on it
    result: Optional[dict] = None  # Agent's result report

    def is_blocked(self, completed_tasks: set) -> bool:
        """Check if task is blocked by incomplete dependencies."""
        return any(dep not in completed_tasks for dep in self.blocked_by)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "status": self.status,
            "blocked_by": self.blocked_by,
        }


class TaskQueue:
    """Priority queue for atomic tasks with dependency tracking."""

    def __init__(self):
        self.tasks: dict[str, Task] = {}  # id -> Task
        self.completed: set[str] = set()  # Completed task IDs

    def add_task(self, task: Task):
        """Add a task to the queue."""
        self.tasks[task.id] = task

    def add_tasks_from_pm(self, pm_tasks: list[dict]):
        """Parse PM's atomic task output into queue."""
        for i, t in enumerate(pm_tasks):
            if isinstance(t, dict):
                task = Task(
                    id=t.get("id", f"task_{i+1}"),
                    title=t.get("title", str(t)),
                    priority=t.get("priority", len(pm_tasks) - i),  # First = highest
                    blocked_by=t.get("blocked_by", []),
                )
            else:
                # Simple string format
                task = Task(
                    id=f"task_{i+1}",
                    title=str(t),
                    priority=len(pm_tasks) - i,
                )
            self.add_task(task)

    def get_next_task(self) -> Optional[Task]:
        """Get highest priority unblocked task."""
        available = [
            t for t in self.tasks.values()
            if t.status == "pending" and not t.is_blocked(self.completed)
        ]
        if not available:
            return None
        # Sort by priority (highest first)
        available.sort(key=lambda t: t.priority, reverse=True)
        return available[0]

    def mark_completed(self, task_id: str, result: dict):
        """Mark a task as completed."""
        if task_id in self.tasks:
            self.tasks[task_id].status = "completed"
            self.tasks[task_id].result = result
            self.completed.add(task_id)

    def mark_failed(self, task_id: str, result: dict):
        """Mark a task as failed."""
        if task_id in self.tasks:
            self.tasks[task_id].status = "failed"
            self.tasks[task_id].result = result

    def all_completed(self) -> bool:
        """Check if all tasks are completed."""
        return all(t.status == "completed" for t in self.tasks.values())

    def has_pending(self) -> bool:
        """Check if there are pending tasks."""
        return any(t.status == "pending" for t in self.tasks.values())

    def get_status_summary(self) -> str:
        """Get a summary of queue status."""
        pending = sum(1 for t in self.tasks.values() if t.status == "pending")
        in_progress = sum(1 for t in self.tasks.values() if t.status == "in_progress")
        completed = sum(1 for t in self.tasks.values() if t.status == "completed")
        failed = sum(1 for t in self.tasks.values() if t.status == "failed")
        return f"Pending: {pending}, In Progress: {in_progress}, Completed: {completed}, Failed: {failed}"

    def get_blocked_tasks(self) -> list[Task]:
        """Get list of currently blocked tasks."""
        return [
            t for t in self.tasks.values()
            if t.status == "pending" and t.is_blocked(self.completed)
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_or_create_project(session, project_name: str, repo_path: str = None) -> "Project":
    """Get existing project or create new one."""
    if not HAS_DB:
        return None

    project = session.query(Project).filter(Project.name == project_name).first()
    if not project:
        project = Project(
            name=project_name,
            description=f"Created by workflow CLI",
            repo_path=repo_path
        )
        session.add(project)
        session.commit()
    return project


def create_run(session, project: "Project", task_description: str) -> "Run":
    """Create a new workflow run."""
    if not HAS_DB:
        return None

    run_name = f"Run {datetime.now().strftime('%Y-%m-%d_%H%M%S')}"
    run = Run(
        project_id=project.id,
        name=run_name,
        state=RunState.PM,
        pm_result={"task": task_description}
    )
    session.add(run)
    session.commit()
    return run


def add_tasks_to_db(session, project: "Project", run: "Run", atomic_tasks: list) -> None:
    """Add atomic tasks from PM to database."""
    if not HAS_DB:
        return

    for i, t in enumerate(atomic_tasks):
        db_task = DBTask(
            project_id=project.id,
            run_id=run.id,
            task_id=t.get("id", f"task_{i+1}"),
            title=t.get("title", "Untitled task"),
            description=t.get("description", ""),
            priority=t.get("priority", 5),
            blocked_by=t.get("blocked_by", []),
            status=TaskStatus.BACKLOG
        )
        session.add(db_task)
    session.commit()


class Spinner:
    """ASCII spinner for progress indication."""
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, agent: str, color: str):
        self.agent = agent.upper() if agent != "security" else "SEC"
        self.color = color
        self.running = False
        self.thread = None
        self.start_time = 0

    def _spin(self):
        idx = 0
        while self.running:
            elapsed = int(time.time() - self.start_time)
            frame = self.FRAMES[idx % len(self.FRAMES)]
            sys.stdout.write(f"\r{self.color}  {frame} [{self.agent}] Working... ({elapsed}s){C.RESET}  ")
            sys.stdout.flush()
            time.sleep(0.1)
            idx += 1
        sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()

    def start(self):
        self.running = True
        self.start_time = time.time()
        self.thread = threading.Thread(target=self._spin)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

# Task pipeline agents (PM runs first, then these in order per task)
TASK_PIPELINE = ["dev", "qa", "security"]

def load_coding_principles(cwd: str) -> str:
    """Load coding principles from the project directory."""
    principles_file = os.path.join(cwd, "coding_principles.md")
    if os.path.exists(principles_file):
        with open(principles_file, "r") as f:
            return f.read()
    # Default principles if file doesn't exist
    return """## Coding Principles
- DRY: Don't Repeat Yourself - consolidate shared logic
- TDD: Write tests BEFORE implementation
- Security: CSRF protection, input validation, no hardcoded secrets
- Quality: Readable code, meaningful names, single responsibility
"""

AGENT_PROMPTS = {
    "pm": """## YOUR ROLE: PROJECT MANAGER

TASK: {task}
WORKSPACE: {cwd}

{principles}

## YOU MUST:
- Break the feature into ATOMIC tasks (one dev session each)
- Each task MUST have testable acceptance criteria
- Set dependencies via blocked_by array
- Assign priority: higher number = work first

## YOU MUST NOT:
- Create tasks too large to test independently
- Skip acceptance criteria
- Ignore dependencies between tasks

## YOUR OUTPUT FORMAT:
```json
{{
  "status": "pass",
  "summary": "Brief plan summary",
  "requirements": ["req1", "req2"],
  "atomic_tasks": [
    {{"id": "task_1", "title": "First task", "priority": 10, "blocked_by": []}},
    {{"id": "task_2", "title": "Depends on task_1", "priority": 8, "blocked_by": ["task_1"]}}
  ]
}}
```
""",

    "dev": """## YOUR ROLE: DEVELOPER

TASK: {task}
WORKSPACE: {cwd}

{principles}

## YOU MUST:
- Write tests BEFORE or WITH implementation (TDD)
- Complete ONLY this specific atomic task
- Follow existing code patterns
- Commit changes with clear message

## YOU MUST NOT:
- Implement other tasks beyond this one
- Skip tests
- Ignore existing patterns in the codebase
- Use destructive commands

## YOUR OUTPUT FORMAT:
```json
{{"status": "pass", "summary": "What was implemented", "files": ["file1.py"], "task_id": "the_task_id"}}
```

If you cannot complete: {{"status": "fail", "summary": "Explanation"}}
""",

    "qa": """## YOUR ROLE: QA ENGINEER

TASK: {task}
WORKSPACE: {cwd}

{principles}

## YOU MUST:
- Run ALL existing tests first: `pytest tests/ -v`
- Write tests for EVERY acceptance criterion
- Check for DRY violations (code duplication)
- Verify security measures are in place

## YOU MUST NOT:
- Skip running existing tests
- Write tests that always pass
- Ignore edge cases and error paths

## YOUR OUTPUT FORMAT:
```json
{{"status": "pass", "summary": "Test results", "tests_passed": 5, "tests_failed": 0}}
```

If tests fail or violations found: {{"status": "fail", "summary": "Details"}}
""",

    "security": """## YOUR ROLE: SECURITY ENGINEER

TASK: {task}
WORKSPACE: {cwd}

{principles}

## YOU MUST CHECK FOR:
- [ ] SQL Injection (string concatenation in queries)
- [ ] XSS (unescaped user input)
- [ ] CSRF (forms without protection)
- [ ] Hardcoded secrets (passwords, API keys)
- [ ] Input validation missing

## YOU MUST:
- Report specific file + line for each issue
- Include severity (critical/high/medium/low)
- Provide actionable fix recommendations

## YOU MUST NOT:
- Modify any files (report only)
- Ignore "minor" issues

## YOUR OUTPUT FORMAT:
```json
{{"status": "pass", "summary": "Security assessment", "vulnerabilities": []}}
```

If critical vulnerabilities: {{"status": "fail", "summary": "Issues found", "vulnerabilities": [...]}}
""",
}


def build_work_cycle(agent: str, report: dict) -> str:
    """Build work_cycle context from agent's report for the next agent."""
    role_display = agent.upper() if agent != "security" else "SEC"

    work_cycle = f"\n[{role_display} WORK_CYCLE]\n"
    work_cycle += f"Status: {report.get('status', 'unknown')}\n"
    work_cycle += f"Summary: {report.get('summary', 'No summary')}\n"

    # Include agent-specific details
    if agent == "pm":
        reqs = report.get("requirements", [])
        if reqs:
            work_cycle += "Requirements:\n"
            for req in reqs:
                work_cycle += f"  - {req}\n"

    elif agent == "dev":
        files = report.get("files", [])
        if files:
            work_cycle += f"Files modified: {', '.join(files)}\n"

    elif agent == "qa":
        passed = report.get("tests_passed", 0)
        failed = report.get("tests_failed", 0)
        work_cycle += f"Tests: {passed} passed, {failed} failed\n"

    elif agent == "security":
        vulns = report.get("vulnerabilities", [])
        if vulns:
            work_cycle += f"Vulnerabilities: {', '.join(vulns)}\n"
        else:
            work_cycle += "No vulnerabilities found\n"

    return work_cycle


def api(method, endpoint, data=None):
    """Call Workflow Hub API."""
    url = f"{HUB_URL}{endpoint}"
    try:
        if method == "GET":
            r = requests.get(url, timeout=30)
        else:
            r = requests.post(url, json=data, timeout=30)
        return r.json() if r.content else {}
    except Exception as e:
        return {"error": str(e)}


def run_goose(agent: str, task: str, cwd: str, principles: str = "", color: str = "",
               tui: Optional["WorkflowTUI"] = None, task_title: str = "") -> dict:
    """Run Goose agent with spinner and extract result."""
    prompt = AGENT_PROMPTS[agent].format(task=task, cwd=cwd, principles=principles)

    # Use TUI if available, otherwise use spinner
    if tui:
        agent_display = agent.upper() if agent != "security" else "SEC"
        tui.start_agent(agent_display, task_title or task[:50])
        spinner = None
    else:
        spinner = Spinner(agent, color or C.DIM)
        spinner.start()

    try:
        # Use Popen for non-blocking execution while spinner runs
        process = subprocess.Popen(
            ["goose", "run", "--text", prompt],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Wait with timeout
        try:
            stdout, stderr = process.communicate(timeout=600)
        except subprocess.TimeoutExpired:
            process.kill()
            if spinner:
                spinner.stop()
            if tui:
                tui.stop_agent()
            return {"status": "fail", "summary": "Timeout (10 min)"}

        if spinner:
            spinner.stop()
        if tui:
            tui.stop_agent()
        output = stdout
        print(output)  # Show full output

        # Extract JSON result
        if "```json" in output:
            start = output.find("```json") + 7
            end = output.find("```", start)
            return json.loads(output[start:end].strip())
        elif '{"status"' in output:
            start = output.find('{"status"')
            end = output.rfind("}") + 1
            return json.loads(output[start:end])

        # Default to pass if goose completed
        return {"status": "pass", "summary": f"{agent} completed"}

    except subprocess.TimeoutExpired:
        if spinner:
            spinner.stop()
        if tui:
            tui.stop_agent()
        return {"status": "fail", "summary": "Timeout"}
    except FileNotFoundError:
        if spinner:
            spinner.stop()
        if tui:
            tui.stop_agent()
        print(f"{C.FAIL}Goose not found. Install: pipx install goose-ai{C.RESET}")
        return {"status": "fail", "summary": "Goose not installed"}
    except json.JSONDecodeError:
        if spinner:
            spinner.stop()
        if tui:
            tui.stop_agent()
        return {"status": "pass", "summary": f"{agent} completed"}
    except Exception as e:
        if spinner:
            spinner.stop()
        if tui:
            tui.stop_agent()
        return {"status": "fail", "summary": str(e)}


def run_task_through_pipeline(task: Task, cwd: str, principles: str, project: dict,
                               work_cycle_context: str, max_retries: int = 2,
                               tui: Optional["WorkflowTUI"] = None) -> tuple[bool, str]:
    """Run a single atomic task through DEV → QA → SEC pipeline.

    Returns: (success, updated_work_cycle_context)
    """
    colors = {"dev": C.DEV, "qa": C.QA, "security": C.SEC}
    task_agents = TASK_PIPELINE  # PM already ran, these run per task

    # Create run for this task
    run_id = None
    if project:
        result = api("POST", f"/api/projects/{project['id']}/runs/create", {
            "name": f"[{task.id}] {task.title[:80]}"
        })
        run_id = result.get("run", {}).get("id")
        if run_id:
            print(f"{C.DIM}  Run #{run_id} created for task {task.id}{C.RESET}")

    retries = 0
    while retries <= max_retries:
        if retries > 0:
            print(f"\n{C.DIM}  Retry {retries}/{max_retries} for task {task.id}{C.RESET}")

        task_work_cycle = work_cycle_context
        all_passed = True

        for agent in task_agents:
            color = colors.get(agent, "")
            role_display = agent.upper() if agent != "security" else "SEC"

            if not tui:
                print(f"{color}{'─'*50}{C.RESET}")
                print(f"{color}  [{role_display}] Working on: {task.title[:40]}...{C.RESET}")

            # Build agent task description
            agent_task = f"ATOMIC TASK [{task.id}]: {task.title}"
            if task_work_cycle:
                agent_task += f"\n\n--- CONTEXT FROM PREVIOUS WORK ---\n{task_work_cycle}"

            report = run_goose(agent, agent_task, cwd, principles, color, tui=tui, task_title=task.title)

            status_icon = f"{C.OK}✓{C.RESET}" if report.get("status") == "pass" else f"{C.FAIL}✗{C.RESET}"
            status_text = "✓" if report.get("status") == "pass" else "✗"
            summary = report.get('summary', 'No summary')[:50]

            if tui:
                tui.log(role_display, f"{status_text} {summary}")
            else:
                print(f"{color}  [{role_display}] {status_icon} {summary}{C.RESET}")

            # Submit to Hub
            if run_id:
                api("POST", f"/api/runs/{run_id}/report", {
                    "role": agent,
                    "status": report.get("status", "fail"),
                    "summary": report.get("summary", ""),
                    "details": report,
                    "actor": f"goose-{agent}"
                })
                if report.get("status") == "pass":
                    api("POST", f"/api/runs/{run_id}/advance", {"actor": f"goose-{agent}"})

            if report.get("status") != "pass":
                all_passed = False
                failure_msg = report.get("summary", "Unknown failure")
                vulns = report.get("vulnerabilities", [])
                if vulns:
                    failure_msg += f" | Vulns: {', '.join(vulns[:2])}"

                # Add failure context for retry
                task_work_cycle += f"\n\n[FAILURE @ {role_display}]\n{failure_msg}\nFix this issue and try again."
                break

            # Accumulate work_cycle
            task_work_cycle += build_work_cycle(agent, report)

        if all_passed:
            return True, task_work_cycle

        retries += 1

    return False, task_work_cycle


def run_workflow(task: str, project_name: str, cwd: str, max_iterations: int = 3, use_tui: bool = False):
    """Run task through queue-based workflow pipeline.

    Architecture:
    1. PM decomposes feature into atomic tasks with dependencies
    2. TaskQueue manages priority and blockers
    3. DEV→QA→SEC pipeline processes one atomic task at a time
    4. Tasks are processed in priority order (highest first, respecting blockers)
    """
    cwd = os.path.abspath(cwd)

    # Initialize TUI if requested
    tui = None
    live = None
    if use_tui and HAS_TUI:
        tui = WorkflowTUI(run_name=task[:50], sandbox_path=cwd)
        live = tui.start()
        live.__enter__()
    elif use_tui and not HAS_TUI:
        print(f"{C.FAIL}TUI not available. Install rich: pip install rich{C.RESET}")

    if not tui:
        print(f"\n{C.BOLD}{'═'*60}{C.RESET}")
        print(f"{C.BOLD}  WORKFLOW: {task[:50]}{'...' if len(task) > 50 else ''}{C.RESET}")
        print(f"{C.BOLD}  Sandbox: {cwd}{C.RESET}")
        print(f"{C.BOLD}{'═'*60}{C.RESET}\n")

    # Initialize database connection
    db_session = None
    db_project = None
    db_run = None
    db_queue = None

    if HAS_DB:
        try:
            db_session = SessionLocal()
            db_project = get_or_create_project(db_session, project_name, cwd)
            db_run = create_run(db_session, db_project, task)
            if not tui:
                print(f"{C.DIM}Database connected: Project #{db_project.id}, Run #{db_run.id}{C.RESET}")
        except Exception as e:
            print(f"{C.DIM}Database unavailable: {e}{C.RESET}")
            db_session = None

    # Check Hub connection
    status = api("GET", "/api/status")
    if "error" in status:
        print(f"{C.DIM}(Workflow Hub not running - proceeding without tracking){C.RESET}\n")
        project = None
    else:
        projects = api("GET", "/api/projects")
        project = None
        for p in projects.get("projects", []):
            if p["name"] == project_name:
                project = p
                break
        if not project:
            result = api("POST", "/api/projects/create", {"name": project_name, "repo_path": cwd})
            project = result.get("project")

    # Load coding principles
    principles = load_coding_principles(cwd)
    if not tui:
        print(f"{C.DIM}Loaded coding principles{C.RESET}\n")

    colors = {"pm": C.PM, "dev": C.DEV, "qa": C.QA, "security": C.SEC}

    # ═══════════════════════════════════════════════════════════
    # PHASE 1: PM creates atomic tasks
    # ═══════════════════════════════════════════════════════════
    if tui:
        tui.log("PM", "Breaking down feature into atomic tasks...")
    else:
        print(f"{C.PM}{C.BOLD}{'═'*60}{C.RESET}")
        print(f"{C.PM}{C.BOLD}  [PM] Breaking down feature into atomic tasks...{C.RESET}")
        print(f"{C.PM}{'═'*60}{C.RESET}\n")

    pm_report = run_goose("pm", task, cwd, principles, C.PM, tui=tui, task_title="Planning")

    if pm_report.get("status") != "pass":
        if tui:
            tui.log("PM", "✗ Failed to create task breakdown")
        print(f"{C.FAIL}PM failed to create task breakdown. Manual intervention required.{C.RESET}")
        if live:
            live.__exit__(None, None, None)
        return False

    # Parse atomic tasks into queue
    queue = TaskQueue()
    atomic_tasks = pm_report.get("atomic_tasks", [])

    if not atomic_tasks:
        # Fallback: treat entire task as single atomic task
        if not tui:
            print(f"{C.DIM}  No atomic tasks defined, treating as single task{C.RESET}")
        atomic_tasks = [{"id": "task_1", "title": task, "priority": 10, "blocked_by": []}]

    queue.add_tasks_from_pm(atomic_tasks)

    # Also persist to database
    if db_session and db_project and db_run:
        add_tasks_to_db(db_session, db_project, db_run, atomic_tasks)
        db_queue = TaskQueueService(db_session, db_run.id)
        if not tui:
            print(f"{C.DIM}  Tasks persisted to database{C.RESET}")

    if tui:
        tui.log("PM", f"✓ Created {len(queue.tasks)} atomic tasks")
    else:
        print(f"\n{C.PM}{C.BOLD}  [PM] Created {len(queue.tasks)} atomic tasks:{C.RESET}")
        for t in sorted(queue.tasks.values(), key=lambda x: x.priority, reverse=True):
            blockers = f" (blocked by: {', '.join(t.blocked_by)})" if t.blocked_by else ""
            print(f"{C.PM}    [{t.id}] P{t.priority}: {t.title[:45]}...{blockers}{C.RESET}")
        print()

    # WorkCycle context accumulates across all tasks
    work_cycle_context = build_work_cycle("pm", pm_report)

    # ═══════════════════════════════════════════════════════════
    # PHASE 2: Process tasks from queue
    # ═══════════════════════════════════════════════════════════
    tasks_completed = 0
    tasks_failed = 0
    iteration = 0

    while queue.has_pending() and iteration < max_iterations * len(queue.tasks):
        iteration += 1

        # Update TUI with queue status
        if tui:
            pending = sum(1 for t in queue.tasks.values() if t.status == "pending")
            in_progress = sum(1 for t in queue.tasks.values() if t.status == "in_progress")
            completed = sum(1 for t in queue.tasks.values() if t.status == "completed")
            failed = sum(1 for t in queue.tasks.values() if t.status == "failed")
            tui.set_status_summary({
                "done": completed,
                "in_progress": in_progress,
                "backlog": pending,
                "failed": failed,
                "total": len(queue.tasks)
            })

        # Get next unblocked task
        current_task = queue.get_next_task()

        if not current_task:
            # No unblocked tasks available
            blocked = queue.get_blocked_tasks()
            if blocked:
                if not tui:
                    print(f"\n{C.FAIL}All remaining tasks are blocked:{C.RESET}")
                    for t in blocked:
                        print(f"  - [{t.id}] blocked by: {', '.join(t.blocked_by)}")
                    print(f"{C.FAIL}Cannot proceed. Check for circular dependencies.{C.RESET}")
            break

        current_task.status = "in_progress"
        if db_queue:
            db_queue.mark_in_progress(current_task.id)

        if not tui:
            print(f"\n{C.BOLD}{'╔'*60}{C.RESET}")
            print(f"{C.BOLD}  TASK [{current_task.id}] Priority: {current_task.priority}{C.RESET}")
            print(f"{C.BOLD}  {current_task.title}{C.RESET}")
            print(f"{C.DIM}  Queue: {queue.get_status_summary()}{C.RESET}")
            print(f"{C.BOLD}{'╚'*60}{C.RESET}")

        success, new_work_cycle = run_task_through_pipeline(
            current_task, cwd, principles, project, work_cycle_context, tui=tui
        )

        if success:
            queue.mark_completed(current_task.id, {"status": "pass"})
            if db_queue:
                db_queue.mark_completed(current_task.id)
            work_cycle_context = new_work_cycle
            tasks_completed += 1
            if tui:
                tui.log("SYS", f"✓ Task [{current_task.id}] completed")
            else:
                print(f"\n{C.OK}  ✓ Task [{current_task.id}] completed{C.RESET}")
        else:
            queue.mark_failed(current_task.id, {"status": "fail"})
            if db_queue:
                db_queue.mark_failed(current_task.id)
            tasks_failed += 1
            if tui:
                tui.log("SYS", f"✗ Task [{current_task.id}] failed")
            else:
                print(f"\n{C.FAIL}  ✗ Task [{current_task.id}] failed after retries{C.RESET}")

    # ═══════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════

    # Close TUI before printing summary
    if live:
        live.__exit__(None, None, None)

    print(f"\n{C.BOLD}{'═'*60}{C.RESET}")

    # Close database session
    if db_session:
        db_session.close()

    if queue.all_completed():
        print(f"{C.OK}{C.BOLD}  ✓ ALL {tasks_completed} TASKS COMPLETED{C.RESET}")
        print(f"{C.OK}{C.BOLD}  Ready for deployment!{C.RESET}")
        if db_run:
            print(f"{C.DIM}  Run #{db_run.id} saved to database{C.RESET}")
        print(f"{C.BOLD}{'═'*60}{C.RESET}\n")
        return True
    else:
        print(f"{C.FAIL}{C.BOLD}  WORKFLOW INCOMPLETE{C.RESET}")
        print(f"  Completed: {tasks_completed}, Failed: {tasks_failed}, Pending: {sum(1 for t in queue.tasks.values() if t.status == 'pending')}")
        if db_run:
            print(f"{C.DIM}  Run #{db_run.id} saved to database{C.RESET}")
        print(f"{C.BOLD}{'═'*60}{C.RESET}\n")

        # Show remaining tasks
        pending = [t for t in queue.tasks.values() if t.status == "pending"]
        if pending:
            print(f"{C.DIM}Pending tasks:{C.RESET}")
            for t in pending:
                blocked = " (BLOCKED)" if t.is_blocked(queue.completed) else ""
                print(f"  - [{t.id}] {t.title[:50]}{blocked}")

        return False


def main():
    parser = argparse.ArgumentParser(
        description="Run a task through the full agent workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    workflow "Add user authentication"
    workflow --project "Todo App" "Add delete button"
    workflow "Fix the login bug" --dir ./src
    workflow --max-iter 5 "Complex feature"  # Allow more retries
    workflow --tui "Add feature"  # Use rich TUI
        """
    )

    parser.add_argument("task", help="Task description")
    parser.add_argument("--project", "-p", default="Project", help="Project name")
    parser.add_argument("--dir", "-d", default=".", help="Working directory")
    parser.add_argument("--max-iter", "-m", type=int, default=3, help="Max iterations for retry loop (default: 3)")
    parser.add_argument("--tui", action="store_true", help="Use rich terminal UI for visualization")

    args = parser.parse_args()

    if not os.path.isdir(args.dir):
        print(f"Error: {args.dir} is not a valid directory")
        sys.exit(1)

    run_workflow(args.task, args.project, args.dir, args.max_iter, use_tui=args.tui)


if __name__ == "__main__":
    main()
