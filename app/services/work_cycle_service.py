"""WorkCycle service for building agent context from DB and git.

This service generates context for each agent run by:
1. Querying DB for previous agent reports
2. Getting recent git commits
3. Building role-specific expectations
4. Optionally writing to _spec/WORK_CYCLE.md for file-based interface
"""
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.run import Run, RunState
from app.models.task import Task
from app.models.report import AgentReport, AgentRole
from app.models.project import Project


# Pipeline order for context building
PIPELINE_ORDER = ["pm", "dev", "qa", "security", "docs"]

# Role-specific deliverables
ROLE_DELIVERABLES = {
    "pm": [
        "Break down requirements into tasks",
        "Update _spec/BRIEF.md with goals",
        "Create task definitions with acceptance criteria",
        "Output JSON report with task breakdown",
    ],
    "dev": [
        "Implement code to satisfy tests",
        "Follow TDD - tests should already exist from QA",
        "COMMIT: Stage and commit ALL changes with descriptive message (git add -A && git commit -m '...')",
        "Output JSON report with files changed and commit hash",
    ],
    "qa": [
        "Write failing tests FIRST (TDD red phase)",
        "Define acceptance criteria as executable tests",
        "Do NOT implement - only write tests",
        "COMMIT: Stage and commit test files (git add tests/ && git commit -m 'Add tests for ...')",
        "Output JSON report with tests added",
    ],
    "security": [
        "Scan for OWASP Top 10 vulnerabilities",
        "Check for hardcoded secrets",
        "Review authentication/authorization",
        "If fixes needed, implement them and COMMIT",
        "Output JSON report with findings",
    ],
    "docs": [
        "VERIFY: Run tests first (pytest), ensure feature works",
        "CAPTURE: Take screenshots of working feature (Playwright)",
        "UPLOAD: Submit proofs to /api/runs/{run_id}/proofs/upload",
        "FIX: If tests fail, fix issues (second-layer debug)",
        "DOCUMENT: Update README.md and docs/ with working examples",
        "COMMIT: Stage and commit all documentation and fixes",
        "Output JSON report with tests_passed, screenshots_taken, proofs_uploaded, commit_hash",
    ],
}


def get_recent_commits(repo_path: str, limit: int = 5) -> List[Dict]:
    """Get recent git commits from the repository."""
    commits = []
    try:
        result = subprocess.run(
            ["git", "log", f"-{limit}", "--format=%H|%s|%an|%ai"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line and "|" in line:
                    parts = line.split("|", 3)
                    if len(parts) >= 4:
                        commits.append({
                            "sha": parts[0][:8],
                            "message": parts[1],
                            "author": parts[2],
                            "date": parts[3]
                        })
    except Exception:
        pass
    return commits


def get_git_diff_summary(repo_path: str) -> str:
    """Get summary of uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def build_work_cycle_context(
    db: Session,
    run_id: int,
    role: str,
    task_id: Optional[str] = None,
    include_raw_output: bool = False,
    max_report_chars: int = 2000
) -> str:
    """Build comprehensive work_cycle context from DB and git.

    Args:
        db: SQLAlchemy session
        run_id: Current run ID
        role: Agent role about to execute
        task_id: Optional specific task ID for task-focused context
        include_raw_output: Include full raw output from previous agents
        max_report_chars: Max chars per report summary

    Returns:
        Formatted context string for agent prompt
    """
    # Get run and project
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        return f"# WorkCycle Context\nRun {run_id} not found."

    project = db.query(Project).filter(Project.id == run.project_id).first()
    if not project:
        return f"# WorkCycle Context\nProject not found for run {run_id}."

    # Get specific task or all tasks for this run's project
    # NOTE: Task.run_id removed in refactor - get tasks from project
    if task_id:
        task = db.query(Task).filter(
            Task.project_id == run.project_id,
            Task.task_id == task_id
        ).first()
        tasks = [task] if task else []
    else:
        # Get in-progress tasks for this project
        from app.models.task import TaskStatus
        tasks = db.query(Task).filter(
            Task.project_id == run.project_id,
            Task.status == TaskStatus.IN_PROGRESS
        ).all()

    # Get all agent reports for this run, ordered by creation
    reports = db.query(AgentReport).filter(
        AgentReport.run_id == run_id
    ).order_by(AgentReport.created_at.asc()).all()

    # Get recent git commits
    repo_path = project.repo_path or "."
    commits = get_recent_commits(repo_path)
    diff_summary = get_git_diff_summary(repo_path)

    # Build context sections
    sections = []

    # Check for loopback situation (QA/SEC failure that looped back to DEV)
    is_loopback = False
    failed_report = None
    loopback_stage = None

    for report in reports:
        if report.status and report.status.value == "fail":
            if report.role == AgentRole.QA:
                is_loopback = True
                failed_report = report
                loopback_stage = "QA"
            elif report.role == AgentRole.SECURITY:
                is_loopback = True
                failed_report = report
                loopback_stage = "SECURITY"

    # Header
    task_label = f" | Task: {task_id}" if task_id else ""
    sections.append(f"""# WorkCycle Context
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Run ID: {run_id} | Project: {project.name}{task_label}
""")

    # PROMINENT LOOPBACK WARNING for DEV agent
    if is_loopback and role == "dev" and failed_report:
        sections.append(f"""
## ⚠️ LOOPBACK - FIX REQUIRED ⚠️

**{loopback_stage} AGENT FOUND ISSUES THAT MUST BE FIXED**

This is NOT a fresh implementation. The code has already been through the pipeline
and {loopback_stage} found problems. Your job is to FIX these specific issues.

### {loopback_stage} Failure Report
**Status**: FAILED
**Summary**: {failed_report.summary or 'No summary provided'}
""")
        # Show full details of what failed
        if failed_report.details:
            sections.append("### Issues to Fix:")
            details = failed_report.details

            # Handle different report formats
            if isinstance(details, dict):
                # Look for common keys
                for key in ['failing_tests', 'failures', 'errors', 'issues',
                           'vulnerabilities', 'findings', 'bugs']:
                    if key in details and details[key]:
                        items = details[key]
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    # Format dict items nicely
                                    title = item.get('title') or item.get('name') or item.get('issue') or str(item)
                                    desc = item.get('description') or item.get('details') or item.get('recommendation') or ''
                                    sections.append(f"- **{title}**")
                                    if desc:
                                        sections.append(f"  {desc}")
                                else:
                                    sections.append(f"- {item}")
                        else:
                            sections.append(f"- {key}: {items}")

                # Show any other details
                for key, value in details.items():
                    if key not in ['failing_tests', 'failures', 'errors', 'issues',
                                  'vulnerabilities', 'findings', 'bugs', 'status', 'summary']:
                        if value:
                            sections.append(f"- **{key}**: {value}")
            else:
                sections.append(f"```\n{details}\n```")

        # Show fix tasks created from findings
        fix_tasks = [t for t in tasks if t.title and ('fix' in t.title.lower() or 'vulnerability' in t.title.lower() or 'security' in t.title.lower())]
        if fix_tasks:
            sections.append("\n### Fix Tasks Created:")
            for t in fix_tasks:
                status = t.status.value if t.status else "unknown"
                sections.append(f"- [{status}] **{t.title}**: {t.description or 'No description'}")

        sections.append("""
### Your Task
1. Read the failure details above carefully
2. Find and fix each issue mentioned
3. Run tests to verify fixes
4. Commit your fixes with a descriptive message
5. Do NOT introduce new features - only fix the reported issues

---
""")

    # Extract goal from pm_result if available
    goal = "No goal specified"
    if run.pm_result and isinstance(run.pm_result, dict):
        goal = run.pm_result.get("goal") or run.pm_result.get("summary") or goal

    # Pipeline position
    sections.append(f"""## Pipeline Position
- **Current State**: {run.state.value if run.state else 'unknown'}
- **Your Role**: {role.upper()}
- **Run**: {run.name}
- **Goal**: {goal}
""")

    # Tasks section - detailed for specific task, summary for all
    if tasks:
        if task_id and len(tasks) == 1:
            # Detailed view for specific task
            task = tasks[0]
            status = task.status.value if task.status else "unknown"
            stage = task.pipeline_stage.value if task.pipeline_stage else "none"
            sections.append(f"""## Current Task: {task.task_id}
**Title**: {task.title}
**Status**: {status}
**Pipeline Stage**: {stage}
**Priority**: {task.priority or 'Not set'}

### Description
{task.description or 'No description provided.'}

### Acceptance Criteria""")
            if task.acceptance_criteria:
                for i, criteria in enumerate(task.acceptance_criteria, 1):
                    sections.append(f"{i}. {criteria}")
            else:
                sections.append("No acceptance criteria defined.")

            # Show blocking dependencies
            if task.blocked_by:
                sections.append(f"\n**Blocked By**: {', '.join(task.blocked_by)}")
            sections.append("")
        else:
            # Summary view for multiple tasks
            sections.append("## Tasks in This Run")
            for task in tasks:
                status = task.status.value if task.status else "unknown"
                stage = task.pipeline_stage.value if task.pipeline_stage else "none"
                sections.append(f"- **{task.task_id}**: {task.title} [{status}] (stage: {stage})")
            sections.append("")

    # Previous agent reports - the key work_cycle data
    if reports:
        sections.append("## Previous Agent Work")
        for report in reports:
            role_name = report.role.value.upper() if report.role else "UNKNOWN"
            status = report.status.value if report.status else "unknown"
            created = report.created_at.strftime('%m-%d %H:%M') if report.created_at else ""

            sections.append(f"""### {role_name} Agent ({created})
**Status**: {status}
**Summary**: {report.summary or 'No summary'}
""")
            # Include details if available
            if report.details:
                details_str = _format_details(report.details)
                if details_str:
                    sections.append(f"**Details**:\n{details_str}")

            # Include raw output if requested (for deep context)
            if include_raw_output and report.raw_output:
                output = report.raw_output
                if len(output) > max_report_chars:
                    output = f"[...truncated...]\n{output[-max_report_chars:]}"
                sections.append(f"```\n{output}\n```")

            sections.append("---")
    else:
        sections.append("## Previous Agent Work\nNo previous reports. You are the first agent on this run.\n")

    # Recent commits
    if commits:
        sections.append("## Recent Git Commits")
        for commit in commits:
            sections.append(f"- `{commit['sha']}` {commit['message']} ({commit['author']})")
        sections.append("")

    # Uncommitted changes
    if diff_summary:
        sections.append(f"## Uncommitted Changes\n```\n{diff_summary}\n```\n")

    # Role-specific deliverables
    deliverables = ROLE_DELIVERABLES.get(role, ["Complete your role's responsibilities"])
    sections.append("## Your Deliverables")
    for d in deliverables:
        sections.append(f"- {d}")
    sections.append("")

    # Important reminders
    sections.append(f"""## Important
- Stay within workspace: {repo_path}
- Output a JSON status report when done
- Do NOT modify files outside the project
""")

    return "\n".join(sections)


def _format_details(details: dict) -> str:
    """Format details dict into readable string."""
    if not details:
        return ""

    lines = []
    for key, value in details.items():
        if isinstance(value, list):
            if value:
                lines.append(f"  - {key}: {', '.join(str(v) for v in value[:5])}")
                if len(value) > 5:
                    lines.append(f"    ... and {len(value) - 5} more")
        elif isinstance(value, dict):
            lines.append(f"  - {key}: {len(value)} items")
        else:
            lines.append(f"  - {key}: {value}")
    return "\n".join(lines)


def write_work_cycle_file(
    db: Session,
    run_id: int,
    role: str,
    project_path: str,
    task_id: Optional[str] = None,
    include_raw_output: bool = False
) -> str:
    """Write work_cycle context to task-specific file (READ-ONLY for agents).

    Creates: _spec/WORK_CYCLE_{run_id}_{task_id}.md
    This file is generated fresh before each agent run and should NOT
    be modified by agents. Agents output via the report API instead.

    Args:
        db: SQLAlchemy session
        run_id: Current run ID
        role: Agent role about to execute
        project_path: Path to project repository
        task_id: Optional task ID for task-specific work_cycle
        include_raw_output: Include full raw output

    Returns:
        Path to written file
    """
    context = build_work_cycle_context(db, run_id, role, task_id=task_id, include_raw_output=include_raw_output)

    spec_dir = Path(project_path) / "_spec"
    spec_dir.mkdir(exist_ok=True)

    # Task-specific filename to avoid conflicts
    if task_id:
        filename = f"WORK_CYCLE_{run_id}_{task_id}.md"
    else:
        filename = f"WORK_CYCLE_{run_id}.md"

    work_cycle_path = spec_dir / filename
    work_cycle_path.write_text(context)

    return str(work_cycle_path)


def get_work_cycle_for_prompt(
    db: Session,
    run_id: int,
    role: str,
    project_path: str,
    task_id: Optional[str] = None,
    write_file: bool = True,
    include_images: bool = None
) -> str:
    """Get work_cycle context and optionally write to task-specific file.

    This is the main entry point for agent_runner integration.
    Creates READ-ONLY work_cycle files that agents should not modify.

    Args:
        db: SQLAlchemy session
        run_id: Current run ID
        role: Agent role about to execute
        project_path: Path to project
        task_id: Optional task ID for task-specific context
        write_file: Whether to write work_cycle file
        include_images: Whether to enrich with image descriptions (None = check settings)

    Returns:
        Context string for agent prompt
    """
    context = build_work_cycle_context(db, run_id, role, task_id=task_id, include_raw_output=False)

    # Enrich with image descriptions if enabled
    if include_images is None:
        # Check director settings for include_images flag
        try:
            from app.views.api import _director_settings
            include_images = _director_settings.get("include_images", False)
        except ImportError:
            include_images = False

    if include_images:
        try:
            from app.services.llm_service import enrich_text_with_image_descriptions
            context = enrich_text_with_image_descriptions(context)
        except Exception as e:
            print(f"Warning: Could not enrich with image descriptions: {e}")

    if write_file:
        try:
            filepath = write_work_cycle_file(
                db, run_id, role, project_path,
                task_id=task_id, include_raw_output=True
            )
            print(f"Wrote work_cycle file: {filepath}")
        except Exception as e:
            print(f"Warning: Could not write work_cycle file: {e}")

    return context


# =============================================================================
# WorkCycle CRUD Operations (Database-backed)
# =============================================================================

def create_work_cycle(
    db: Session,
    task_id: int,
    to_role: str,
    stage: str,
    project_id: int = None,
    run_id: int = None,
    from_role: str = None,
    created_by: str = "system",
    write_file: bool = True
) -> "WorkCycle":
    """Create a new work_cycle for a task.

    Builds context from previous work_cycles, reports, and proofs,
    then stores in DB and optionally writes to file.

    Args:
        db: SQLAlchemy session
        task_id: Task to create work_cycle for
        to_role: Agent role that should pick this up
        stage: Pipeline stage (dev, qa, sec, docs, pm)
        project_id: Project ID (auto-detected from task if not provided)
        run_id: Optional run ID for context
        from_role: Previous agent role (null if first work_cycle)
        created_by: Who created this (system, human, auto-trigger)
        write_file: Whether to write context to file

    Returns:
        Created WorkCycle record
    """
    from app.models.work_cycle import WorkCycle, WorkCycleStatus
    from app.models.task import Task

    # Get task to auto-fill project_id if needed
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise ValueError(f"Task {task_id} not found")

    if project_id is None:
        project_id = task.project_id

    # Build context markdown using existing function
    context_markdown = build_work_cycle_context(
        db=db,
        run_id=run_id or 0,  # Use 0 if no run, will still get task context
        role=to_role,
        task_id=task.task_id,
        include_raw_output=True
    )

    # Build structured context for JSON
    context = {
        "task_id": task_id,
        "task_title": task.title,
        "stage": stage,
        "to_role": to_role,
        "from_role": from_role,
        "project_id": project_id,
        "run_id": run_id,
    }

    # Optionally write to file
    context_file = None
    if write_file and task.project and task.project.repo_path:
        try:
            context_file = write_work_cycle_file(
                db=db,
                run_id=run_id or 0,
                role=to_role,
                project_path=task.project.repo_path,
                task_id=task.task_id,
                include_raw_output=True
            )
        except Exception as e:
            print(f"Warning: Could not write work_cycle file: {e}")

    # Create work_cycle record
    work_cycle = WorkCycle(
        project_id=project_id,
        task_id=task_id,
        run_id=run_id,
        from_role=from_role,
        to_role=to_role,
        stage=stage,
        status=WorkCycleStatus.PENDING,
        context=context,
        context_markdown=context_markdown,
        context_file=context_file,
        created_by=created_by
    )

    db.add(work_cycle)
    db.commit()
    db.refresh(work_cycle)

    return work_cycle


def get_current_work_cycle(db: Session, task_id: int) -> "WorkCycle":
    """Get the current pending/in_progress work_cycle for a task.

    Returns the most recent work_cycle that is not yet completed.
    """
    from app.models.work_cycle import WorkCycle, WorkCycleStatus

    return db.query(WorkCycle).filter(
        WorkCycle.task_id == task_id,
        WorkCycle.status.in_([WorkCycleStatus.PENDING, WorkCycleStatus.IN_PROGRESS])
    ).order_by(WorkCycle.created_at.desc()).first()


def get_work_cycle_by_id(db: Session, work_cycle_id: int) -> "WorkCycle":
    """Get a specific work_cycle by ID."""
    from app.models.work_cycle import WorkCycle
    return db.query(WorkCycle).filter(WorkCycle.id == work_cycle_id).first()


def accept_work_cycle(db: Session, work_cycle_id: int) -> "WorkCycle":
    """Mark a work_cycle as accepted (agent starting work).

    Args:
        db: SQLAlchemy session
        work_cycle_id: WorkCycle to accept

    Returns:
        Updated WorkCycle record

    Raises:
        ValueError: If work_cycle not found or not in PENDING state
    """
    from app.models.work_cycle import WorkCycle, WorkCycleStatus
    from datetime import datetime

    work_cycle = db.query(WorkCycle).filter(WorkCycle.id == work_cycle_id).first()
    if not work_cycle:
        raise ValueError(f"WorkCycle {work_cycle_id} not found")

    if work_cycle.status != WorkCycleStatus.PENDING:
        raise ValueError(f"WorkCycle {work_cycle_id} is not pending (status: {work_cycle.status.value})")

    work_cycle.status = WorkCycleStatus.IN_PROGRESS
    work_cycle.accepted_at = datetime.utcnow()
    db.commit()
    db.refresh(work_cycle)

    return work_cycle


def complete_work_cycle(
    db: Session,
    work_cycle_id: int,
    report_status: str,
    report_summary: str = None,
    report_details: dict = None,
    agent_report_id: int = None
) -> "WorkCycle":
    """Complete a work_cycle with the agent's report.

    Args:
        db: SQLAlchemy session
        work_cycle_id: WorkCycle to complete
        report_status: "pass" or "fail"
        report_summary: Summary of what agent did
        report_details: Full report details (JSON)
        agent_report_id: Optional link to AgentReport record

    Returns:
        Updated WorkCycle record

    Raises:
        ValueError: If work_cycle not found or not in IN_PROGRESS state
    """
    from app.models.work_cycle import WorkCycle, WorkCycleStatus
    from datetime import datetime

    work_cycle = db.query(WorkCycle).filter(WorkCycle.id == work_cycle_id).first()
    if not work_cycle:
        raise ValueError(f"WorkCycle {work_cycle_id} not found")

    if work_cycle.status != WorkCycleStatus.IN_PROGRESS:
        raise ValueError(f"WorkCycle {work_cycle_id} is not in progress (status: {work_cycle.status.value})")

    work_cycle.status = WorkCycleStatus.COMPLETED
    work_cycle.completed_at = datetime.utcnow()
    work_cycle.report_status = report_status
    work_cycle.report_summary = report_summary
    work_cycle.report = report_details
    work_cycle.agent_report_id = agent_report_id

    db.commit()
    db.refresh(work_cycle)

    return work_cycle


def fail_work_cycle(db: Session, work_cycle_id: int, reason: str = None) -> "WorkCycle":
    """Mark a work_cycle as failed (timeout, error, etc.).

    Args:
        db: SQLAlchemy session
        work_cycle_id: WorkCycle to fail
        reason: Optional reason for failure

    Returns:
        Updated WorkCycle record
    """
    from app.models.work_cycle import WorkCycle, WorkCycleStatus
    from datetime import datetime

    work_cycle = db.query(WorkCycle).filter(WorkCycle.id == work_cycle_id).first()
    if not work_cycle:
        raise ValueError(f"WorkCycle {work_cycle_id} not found")

    work_cycle.status = WorkCycleStatus.FAILED
    work_cycle.completed_at = datetime.utcnow()
    work_cycle.report_status = "fail"
    work_cycle.report_summary = reason or "WorkCycle failed"

    db.commit()
    db.refresh(work_cycle)

    return work_cycle


def get_work_cycle_history(
    db: Session,
    task_id: int = None,
    project_id: int = None,
    stage: str = None,
    limit: int = 50
) -> list:
    """Get work_cycle history for a task or project.

    Args:
        db: SQLAlchemy session
        task_id: Filter by task
        project_id: Filter by project
        stage: Filter by pipeline stage
        limit: Max results

    Returns:
        List of WorkCycle records
    """
    from app.models.work_cycle import WorkCycle

    query = db.query(WorkCycle)

    if task_id:
        query = query.filter(WorkCycle.task_id == task_id)
    if project_id:
        query = query.filter(WorkCycle.project_id == project_id)
    if stage:
        query = query.filter(WorkCycle.stage == stage)

    return query.order_by(WorkCycle.created_at.desc()).limit(limit).all()
