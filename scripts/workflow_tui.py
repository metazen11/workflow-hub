"""Workflow TUI - Rich terminal UI for workflow pipeline visualization.

Displays task queue, agent status, and activity log using the rich library.
"""
from datetime import datetime
from typing import List, Optional, Dict, Any

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

from app.models import Task, TaskStatus


# Status icons for task states
STATUS_ICONS = {
    TaskStatus.DONE: "\u2713",        # ✓
    TaskStatus.IN_PROGRESS: "\u22ef", # ⋯
    TaskStatus.FAILED: "\u2717",      # ✗
    TaskStatus.BACKLOG: "\u25cb",     # ○
    TaskStatus.BLOCKED: "\u25cb",     # ○
}

# Status colors for styling
STATUS_COLORS = {
    TaskStatus.DONE: "green",
    TaskStatus.IN_PROGRESS: "yellow",
    TaskStatus.FAILED: "red",
    TaskStatus.BACKLOG: "dim",
    TaskStatus.BLOCKED: "dim",
}

# Agent colors matching existing C class in workflow.py
AGENT_COLORS = {
    "PM": "magenta",
    "DEV": "green",
    "QA": "yellow",
    "SEC": "red",
}


class WorkflowTUI:
    """Rich TUI for visualizing workflow pipeline.

    Displays:
    - Header with run name and progress
    - Task queue table with status, priority, and blockers
    - Current agent status with elapsed time
    - Activity log with timestamps
    """

    def __init__(
        self,
        run_name: str,
        sandbox_path: str,
        max_log_entries: int = 20
    ):
        """Initialize the TUI.

        Args:
            run_name: Name of the workflow run
            sandbox_path: Path to the sandbox directory
            max_log_entries: Maximum log entries to display
        """
        self.run_name = run_name
        self.sandbox_path = sandbox_path
        self.max_log_entries = max_log_entries

        # State
        self.log_entries: List[Dict[str, Any]] = []
        self.current_agent: Optional[str] = None
        self.agent_start_time: Optional[datetime] = None
        self.current_task: Optional[str] = None
        self.status_summary: Dict[str, int] = {
            "done": 0,
            "in_progress": 0,
            "backlog": 0,
            "blocked": 0,
            "failed": 0,
            "total": 0
        }

        self.console = Console()
        self._live: Optional[Live] = None

    def log(self, agent: str, message: str) -> None:
        """Add an entry to the activity log.

        Args:
            agent: Agent name (PM, DEV, QA, SEC)
            message: Log message
        """
        entry = {
            "timestamp": datetime.now(),
            "agent": agent,
            "message": message
        }
        self.log_entries.append(entry)

        # Limit entries
        if len(self.log_entries) > self.max_log_entries:
            self.log_entries = self.log_entries[-self.max_log_entries:]

    def start_agent(self, agent: str, task_description: str) -> None:
        """Mark an agent as active.

        Args:
            agent: Agent name (PM, DEV, QA, SEC)
            task_description: Description of current task
        """
        self.current_agent = agent
        self.agent_start_time = datetime.now()
        self.current_task = task_description

    def stop_agent(self) -> None:
        """Clear the active agent state."""
        self.current_agent = None
        self.agent_start_time = None
        self.current_task = None

    def get_elapsed(self) -> Optional[int]:
        """Get elapsed seconds since agent started.

        Returns:
            Elapsed seconds, or None if no agent running
        """
        if self.agent_start_time is None:
            return None
        return int((datetime.now() - self.agent_start_time).total_seconds())

    def set_status_summary(self, summary: Dict[str, int]) -> None:
        """Update the status summary counts.

        Args:
            summary: Dict with done, in_progress, backlog, failed, total counts
        """
        self.status_summary = summary

    def make_task_table(self, tasks: List[Task]) -> Table:
        """Create a rich Table for displaying tasks.

        Args:
            tasks: List of Task objects to display

        Returns:
            Rich Table object
        """
        table = Table(
            title="TASK QUEUE",
            show_header=True,
            header_style="bold cyan"
        )
        table.add_column("ID", style="dim", width=8)
        table.add_column("Title", style="white", width=35)
        table.add_column("Status", justify="center", width=8)
        table.add_column("Blocked By", style="red", width=12)
        table.add_column("Pri", justify="right", width=3)

        for task in tasks:
            status = task.status or TaskStatus.BACKLOG
            icon = STATUS_ICONS.get(status, "?")
            color = STATUS_COLORS.get(status, "white")

            status_text = Text(icon, style=color)

            blockers = ", ".join(task.blocked_by) if task.blocked_by else ""

            table.add_row(
                task.task_id,
                task.title[:35] if task.title else "",
                status_text,
                blockers,
                str(task.priority or 5)
            )

        return table

    def make_agent_panel(self) -> Panel:
        """Create panel showing current agent status.

        Returns:
            Rich Panel object
        """
        if self.current_agent is None:
            content = Text("Idle", style="dim")
        else:
            color = AGENT_COLORS.get(self.current_agent, "white")
            elapsed = self.get_elapsed() or 0
            content = Text()
            content.append(f"[{self.current_agent}] ", style=f"bold {color}")
            content.append("\u28f9 ", style=color)  # Braille spinner frame
            content.append(f"Working on: {self.current_task or 'Unknown'} ", style="white")
            content.append(f"({elapsed}s)", style="dim")

        return Panel(content, title="Agent", border_style="blue")

    def make_log_panel(self) -> Panel:
        """Create panel showing activity log.

        Returns:
            Rich Panel object
        """
        log_text = Text()
        for entry in self.log_entries[-10:]:  # Show last 10
            ts = entry["timestamp"].strftime("%H:%M:%S")
            agent = entry["agent"]
            message = entry["message"]
            color = AGENT_COLORS.get(agent, "white")

            log_text.append(f"[{ts}] ", style="dim")
            log_text.append(f"{agent} ", style=f"bold {color}")
            log_text.append(f"{message}\n", style="white")

        if not log_text:
            log_text = Text("No activity yet", style="dim")

        return Panel(log_text, title="Recent Activity", border_style="green")

    def make_header(self) -> Panel:
        """Create header panel with run info and progress.

        Returns:
            Rich Panel object
        """
        done = self.status_summary.get("done", 0)
        total = self.status_summary.get("total", 0)

        header = Text()
        header.append("WORKFLOW: ", style="bold white")
        header.append(self.run_name, style="bold cyan")
        header.append(f"  [{done}/{total}]", style="bold green")
        header.append("\n")
        header.append("Sandbox: ", style="dim")
        header.append(self.sandbox_path, style="dim")

        return Panel(header, border_style="bold blue")

    def make_layout(self, tasks: List[Task]) -> Layout:
        """Create the complete TUI layout.

        Args:
            tasks: List of Task objects to display

        Returns:
            Rich Layout object
        """
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=5),
            Layout(name="body"),
            Layout(name="agent", size=3),
            Layout(name="log", size=14)
        )

        layout["header"].update(self.make_header())
        layout["body"].update(self.make_task_table(tasks))
        layout["agent"].update(self.make_agent_panel())
        layout["log"].update(self.make_log_panel())

        return layout

    def start(self) -> Live:
        """Start the live TUI display.

        Returns:
            Rich Live context manager
        """
        self._live = Live(
            self.make_layout([]),
            console=self.console,
            refresh_per_second=4,
            screen=True
        )
        return self._live

    def refresh(self, tasks: List[Task]) -> None:
        """Refresh the TUI with updated task data.

        Args:
            tasks: Current list of tasks
        """
        if self._live:
            self._live.update(self.make_layout(tasks))
