"""Handoff service for building agent context from DB and git.

This service generates context for each agent run by:
1. Querying DB for previous agent reports
2. Getting recent git commits
3. Building role-specific expectations
4. Optionally writing to _spec/HANDOFF.md for file-based interface
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
        "Commit working code with clear messages",
        "Output JSON report with files changed",
    ],
    "qa": [
        "Write failing tests FIRST (TDD red phase)",
        "Define acceptance criteria as executable tests",
        "Do NOT implement - only write tests",
        "Output JSON report with tests added",
    ],
    "security": [
        "Scan for OWASP Top 10 vulnerabilities",
        "Check for hardcoded secrets",
        "Review authentication/authorization",
        "Output JSON report with findings",
    ],
    "docs": [
        "Update README.md if needed",
        "Add/update API documentation",
        "Document new features or changes",
        "Output JSON report with docs updated",
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


def build_handoff_context(
    db: Session,
    run_id: int,
    role: str,
    include_raw_output: bool = False,
    max_report_chars: int = 2000
) -> str:
    """Build comprehensive handoff context from DB and git.

    Args:
        db: SQLAlchemy session
        run_id: Current run ID
        role: Agent role about to execute
        include_raw_output: Include full raw output from previous agents
        max_report_chars: Max chars per report summary

    Returns:
        Formatted context string for agent prompt
    """
    # Get run and project
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        return f"# Handoff Context\nRun {run_id} not found."

    project = db.query(Project).filter(Project.id == run.project_id).first()
    if not project:
        return f"# Handoff Context\nProject not found for run {run_id}."

    # Get tasks for this run
    tasks = db.query(Task).filter(Task.run_id == run_id).all()

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

    # Header
    sections.append(f"""# Handoff Context
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Run ID: {run_id} | Project: {project.name}
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

    # Tasks section
    if tasks:
        sections.append("## Tasks in This Run")
        for task in tasks:
            status = task.status.value if task.status else "unknown"
            stage = task.pipeline_stage.value if task.pipeline_stage else "none"
            sections.append(f"- **{task.task_id}**: {task.title} [{status}] (stage: {stage})")
        sections.append("")

    # Previous agent reports - the key handoff data
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


def write_handoff_file(
    db: Session,
    run_id: int,
    role: str,
    project_path: str,
    include_raw_output: bool = False
) -> str:
    """Write handoff context to _spec/HANDOFF.md file.

    Args:
        db: SQLAlchemy session
        run_id: Current run ID
        role: Agent role about to execute
        project_path: Path to project repository
        include_raw_output: Include full raw output

    Returns:
        Path to written file
    """
    context = build_handoff_context(db, run_id, role, include_raw_output)

    spec_dir = Path(project_path) / "_spec"
    spec_dir.mkdir(exist_ok=True)

    handoff_path = spec_dir / "HANDOFF.md"
    handoff_path.write_text(context)

    return str(handoff_path)


def get_handoff_for_prompt(
    db: Session,
    run_id: int,
    role: str,
    project_path: str,
    write_file: bool = True
) -> str:
    """Get handoff context and optionally write to file.

    This is the main entry point for agent_runner integration.

    Args:
        db: SQLAlchemy session
        run_id: Current run ID
        role: Agent role about to execute
        project_path: Path to project
        write_file: Whether to write HANDOFF.md

    Returns:
        Context string for agent prompt
    """
    context = build_handoff_context(db, run_id, role, include_raw_output=False)

    if write_file:
        try:
            write_handoff_file(db, run_id, role, project_path, include_raw_output=True)
        except Exception as e:
            print(f"Warning: Could not write HANDOFF.md: {e}")

    return context
