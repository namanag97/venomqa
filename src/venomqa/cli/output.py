"""Rich CLI output for VenomQA with real-time progress and visualization.

This module provides a professional CLI output system using the Rich library,
featuring real-time progress indicators, checkpoint visualization, timing
breakdowns, and interactive journey tree views.

Example:
    >>> from venomqa.cli.output import CLIOutput, ProgressConfig
    >>> output = CLIOutput(ProgressConfig(show_timing=True))
    >>> output.journey_start("login_flow", total_steps=5)
    >>> output.step_start("login", step_num=1)
    >>> output.step_pass("login", duration_ms=150)
    >>> output.journey_summary("login_flow", success=True, ...)
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text
from rich.tree import Tree


class OutputStyle(Enum):
    """Output style options."""
    PLAIN = "plain"
    RICH = "rich"
    MINIMAL = "minimal"
    VERBOSE = "verbose"


class StepStatus(Enum):
    """Step execution status."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepInfo:
    """Information about a step execution."""
    name: str
    status: StepStatus = StepStatus.PENDING
    duration_ms: float = 0.0
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class PathInfo:
    """Information about a path execution."""
    name: str
    checkpoint: str
    steps: list[StepInfo] = field(default_factory=list)
    success: bool = True
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class ProgressConfig:
    """Configuration for CLI output."""
    show_progress: bool = True
    show_checkpoints: bool = True
    show_paths: bool = True
    show_timing: bool = True
    show_step_details: bool = True
    show_request_response: bool = False
    use_colors: bool = True
    use_unicode: bool = True
    live_update: bool = True
    verbose: bool = False


class DurationColumn(ProgressColumn):
    """Custom column showing step duration."""

    def render(self, task: Task) -> Text:
        """Render the duration column."""
        duration = task.fields.get("duration", 0)
        if duration > 0:
            return Text(f"{duration:.0f}ms", style="cyan")
        return Text("")


class CLIOutput:
    """Rich CLI output handler for VenomQA with real-time visualization.

    Provides a comprehensive output system for journey execution including:
    - Real-time progress bars with step details
    - Checkpoint and rollback visualization
    - Branch path tree view
    - Timing breakdowns and performance metrics
    - Color-coded status indicators

    Attributes:
        config: ProgressConfig controlling output behavior.
        console: Rich Console instance for output.

    Example:
        >>> output = CLIOutput()
        >>> output.journey_start("checkout", total_steps=10)
        >>> output.step_start("add_to_cart", step_num=1)
        >>> output.step_pass("add_to_cart", duration_ms=45)
    """

    COLORS = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "cyan": "\033[96m",
        "dim": "\033[90m",
        "magenta": "\033[95m",
    }

    SYMBOLS = {
        "check": "✓",
        "cross": "✗",
        "arrow": "→",
        "branch": "├─",
        "corner": "└─",
        "pipe": "│",
        "checkpoint": "◉",
        "rollback": "↩",
        "clock": "⏱",
        "gear": "⚙",
        "running": "●",
        "pending": "○",
        "warning": "⚠",
        "info": "ℹ",
        "bullet": "•",
        "dash": "─",
        "double_arrow": "»",
    }

    ASCII_SYMBOLS = {
        "check": "[OK]",
        "cross": "[FAIL]",
        "arrow": "->",
        "branch": "|--",
        "corner": "`--",
        "pipe": "|",
        "checkpoint": "[*]",
        "rollback": "<-",
        "clock": "[time]",
        "gear": "[*]",
        "running": "[.]",
        "pending": "[ ]",
        "warning": "[!]",
        "info": "[i]",
        "bullet": "*",
        "dash": "-",
        "double_arrow": ">>",
    }

    def __init__(self, config: ProgressConfig | dict[str, Any] | None = None) -> None:
        """Initialize the CLI output handler.

        Args:
            config: ProgressConfig or dict with configuration options.
        """
        if isinstance(config, dict):
            self.config = ProgressConfig(
                show_progress=config.get("show_progress", True),
                show_checkpoints=config.get("show_checkpoints", True),
                show_paths=config.get("show_paths", True),
                show_timing=config.get("show_timing", True),
                show_step_details=config.get("show_step_details", True),
                show_request_response=config.get("show_request_response", False),
                use_colors=config.get("use_colors", True),
                use_unicode=config.get("use_unicode", True),
                live_update=config.get("live_update", True),
                verbose=config.get("verbose", False),
            )
        else:
            self.config = config or ProgressConfig()

        self._use_colors = self.config.use_colors and self._supports_color()
        self._use_unicode = self.config.use_unicode and self._supports_unicode()

        # Rich components
        self.console = Console(force_terminal=True if self._use_colors else None)
        self.progress: Progress | None = None
        self.live: Live | None = None
        self.current_task: TaskID | None = None

        # Journey state
        self.journey_name = ""
        self.total_steps = 0
        self.completed_steps = 0
        self.start_time = 0.0
        self.step_timings: list[tuple[str, float, bool]] = []  # (name, duration, success)
        self.steps: list[StepInfo] = []
        self.paths: list[PathInfo] = []
        self.checkpoints: list[str] = []
        self.current_path: PathInfo | None = None

        # Visual tree
        self.tree: Tree | None = None
        self.current_branch_node: Tree | None = None

    def _supports_color(self) -> bool:
        """Check if terminal supports colors."""
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    def _supports_unicode(self) -> bool:
        """Check if terminal supports unicode."""
        try:
            encoding = sys.stdout.encoding
            return encoding is not None and "utf" in encoding.lower()
        except Exception:
            return False

    def _color(self, text: str, color: str) -> str:
        """Apply ANSI color to text."""
        if not self._use_colors:
            return text
        return f"{self.COLORS.get(color, '')}{text}{self.COLORS['reset']}"

    def _symbol(self, name: str) -> str:
        """Get symbol based on unicode support."""
        symbols = self.SYMBOLS if self._use_unicode else self.ASCII_SYMBOLS
        return symbols.get(name, name)

    def _format_duration(self, duration_ms: float) -> str:
        """Format duration for display."""
        if duration_ms < 1000:
            return f"{duration_ms:.0f}ms"
        elif duration_ms < 60000:
            return f"{duration_ms / 1000:.2f}s"
        else:
            minutes = int(duration_ms / 60000)
            seconds = (duration_ms % 60000) / 1000
            return f"{minutes}m {seconds:.1f}s"

    def _create_progress_display(self) -> Group:
        """Create the progress display group."""
        elements = []

        # Progress bar
        if self.progress:
            elements.append(self.progress)

        # Current steps table
        if self.config.show_step_details and self.steps:
            steps_table = self._create_steps_table()
            elements.append(Padding(steps_table, (1, 0, 0, 0)))

        return Group(*elements)

    def _create_steps_table(self) -> Table:
        """Create a table showing recent step results."""
        table = Table(
            show_header=True,
            header_style="bold dim",
            box=None,
            padding=(0, 1),
            expand=False,
        )
        table.add_column("Status", width=3, justify="center")
        table.add_column("Step", min_width=30)
        table.add_column("Duration", width=10, justify="right")

        # Show last 5 steps
        recent_steps = self.steps[-5:]
        for step in recent_steps:
            status_symbol, status_style = self._get_status_display(step.status)
            duration_text = self._format_duration(step.duration_ms) if step.duration_ms > 0 else "-"

            table.add_row(
                Text(status_symbol, style=status_style),
                Text(step.name, style="bold" if step.status == StepStatus.RUNNING else ""),
                Text(duration_text, style="cyan"),
            )

        return table

    def _get_status_display(self, status: StepStatus) -> tuple[str, str]:
        """Get display symbol and style for a status."""
        if status == StepStatus.PASSED:
            return self._symbol("check"), "green"
        elif status == StepStatus.FAILED:
            return self._symbol("cross"), "red"
        elif status == StepStatus.RUNNING:
            return self._symbol("running"), "yellow"
        elif status == StepStatus.SKIPPED:
            return self._symbol("dash"), "dim"
        else:
            return self._symbol("pending"), "dim"

    def header(self, text: str) -> None:
        """Display a section header."""
        self.console.print()
        self.console.rule(f"[bold]{text}[/bold]", style="blue")
        self.console.print()

    def info(self, message: str) -> None:
        """Display an info message."""
        self.console.print(f"[blue]{self._symbol('info')}[/blue] {message}")

    def warning(self, message: str) -> None:
        """Display a warning message."""
        self.console.print(f"[yellow]{self._symbol('warning')}[/yellow] {message}")

    def error(self, message: str) -> None:
        """Display an error message."""
        self.console.print(f"[red]{self._symbol('cross')}[/red] {message}")

    def success(self, message: str) -> None:
        """Display a success message."""
        self.console.print(f"[green]{self._symbol('check')}[/green] {message}")

    def journey_start(
        self,
        name: str,
        description: str = "",
        total_steps: int = 0,
        tags: list[str] | None = None,
    ) -> None:
        """Signal the start of a journey execution.

        Args:
            name: Journey name.
            description: Journey description.
            total_steps: Total number of steps to execute.
            tags: Optional list of journey tags.
        """
        self.journey_name = name
        self.total_steps = total_steps
        self.completed_steps = 0
        self.start_time = time.time()
        self.step_timings = []
        self.steps = []
        self.paths = []
        self.checkpoints = []
        self.current_path = None

        # Create visual tree
        self.tree = Tree(
            f"[bold cyan]{self._symbol('gear')} {name}[/bold cyan]",
            guide_style="dim",
        )
        if description:
            self.tree.add(f"[dim]{description}[/dim]")
        if tags:
            tag_text = " ".join(f"[dim cyan]#{tag}[/dim cyan]" for tag in tags)
            self.tree.add(tag_text)

        # Display journey header
        self.console.print()

        header_content = Table.grid(padding=0)
        header_content.add_column()
        header_content.add_row(
            f"[bold cyan]{self._symbol('gear')} Journey: {name}[/bold cyan]"
        )
        if description:
            header_content.add_row(f"[dim]{description}[/dim]")
        if tags:
            tag_text = " ".join(f"[dim cyan]#{tag}[/dim cyan]" for tag in tags)
            header_content.add_row(tag_text)

        header_panel = Panel(
            header_content,
            border_style="blue",
            padding=(0, 1),
        )
        self.console.print(header_panel)
        self.console.print()

        # Create progress bar
        if self.config.show_progress and total_steps > 0:
            self.progress = Progress(
                SpinnerColumn(spinner_name="dots"),
                TextColumn("[bold blue]{task.description}[/bold blue]"),
                BarColumn(bar_width=40, complete_style="green", finished_style="green"),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("[dim]|[/dim]"),
                MofNCompleteColumn(),
                TextColumn("[dim]|[/dim]"),
                TimeElapsedColumn(),
                TextColumn("[dim]|[/dim]"),
                TimeRemainingColumn(),
                console=self.console,
                expand=False,
            )

            self.current_task = self.progress.add_task(
                f"Running {name}",
                total=total_steps,
                completed=0,
            )

            if self.config.live_update:
                self.live = Live(
                    self._create_progress_display(),
                    console=self.console,
                    refresh_per_second=10,
                    transient=False,
                )
                self.live.start()

    def step_start(
        self,
        name: str,
        step_num: int = 0,
        description: str = "",
    ) -> None:
        """Signal the start of a step execution.

        Args:
            name: Step name.
            step_num: Step number in sequence.
            description: Step description.
        """
        step_info = StepInfo(
            name=name,
            status=StepStatus.RUNNING,
            started_at=datetime.now(),
        )
        self.steps.append(step_info)

        if not self.config.show_progress:
            return

        step_label = f"Step {step_num}/{self.total_steps}: {name}" if step_num > 0 else name

        if self.progress and self.current_task is not None:
            self.progress.update(
                self.current_task,
                description=f"[bold blue]{self._symbol('arrow')} {step_label}[/bold blue]",
            )

        if self.live and self.config.live_update:
            self.live.update(self._create_progress_display())

    def step_pass(
        self,
        name: str = "",
        duration_ms: float | None = None,
        response_summary: str | None = None,
    ) -> None:
        """Signal successful step completion.

        Args:
            name: Step name.
            duration_ms: Step duration in milliseconds.
            response_summary: Optional response summary to display.
        """
        self.completed_steps += 1
        duration = duration_ms or 0.0

        # Update step info
        if self.steps:
            self.steps[-1].status = StepStatus.PASSED
            self.steps[-1].duration_ms = duration
            self.steps[-1].finished_at = datetime.now()

        self.step_timings.append((name, duration, True))

        if self.progress and self.current_task is not None:
            self.progress.update(self.current_task, advance=1)

        if self.live and self.config.live_update:
            self.live.update(self._create_progress_display())

        # Verbose output
        if self.config.verbose and not self.live:
            self.console.print(
                f"  [green]{self._symbol('check')}[/green] {name} "
                f"[dim]({self._format_duration(duration)})[/dim]"
            )

    def step_fail(
        self,
        name: str = "",
        error: str = "",
        duration_ms: float | None = None,
    ) -> None:
        """Signal step failure.

        Args:
            name: Step name.
            error: Error message.
            duration_ms: Step duration in milliseconds.
        """
        self.completed_steps += 1
        duration = duration_ms or 0.0

        # Update step info
        if self.steps:
            self.steps[-1].status = StepStatus.FAILED
            self.steps[-1].duration_ms = duration
            self.steps[-1].error = error
            self.steps[-1].finished_at = datetime.now()

        self.step_timings.append((name, duration, False))

        if self.progress and self.current_task is not None:
            self.progress.update(self.current_task, advance=1)

        if self.live and self.config.live_update:
            self.live.update(self._create_progress_display())

        # Always show failures prominently
        if not self.live:
            self.console.print(
                f"  [red]{self._symbol('cross')}[/red] {name} "
                f"[dim]({self._format_duration(duration)})[/dim]"
            )
            if error and self.config.verbose:
                self.console.print(f"    [red dim]{error}[/red dim]")

    def step_skip(self, name: str = "", reason: str = "") -> None:
        """Signal step was skipped.

        Args:
            name: Step name.
            reason: Reason for skipping.
        """
        step_info = StepInfo(
            name=name,
            status=StepStatus.SKIPPED,
        )
        self.steps.append(step_info)

        if self.progress and self.current_task is not None:
            self.progress.update(self.current_task, advance=1)

        if self.live and self.config.live_update:
            self.live.update(self._create_progress_display())

    def checkpoint(self, name: str) -> None:
        """Signal a checkpoint was created.

        Args:
            name: Checkpoint name.
        """
        self.checkpoints.append(name)

        if not self.config.show_checkpoints:
            return

        # Pause live display to show checkpoint
        if self.live:
            self.live.stop()

        checkpoint_text = (
            f"  [yellow]{self._symbol('checkpoint')} Checkpoint: [bold]{name}[/bold][/yellow]"
        )
        self.console.print(checkpoint_text)

        # Add to tree
        if self.tree:
            self.tree.add(f"[yellow]{self._symbol('checkpoint')} {name}[/yellow]")

        # Restart live display
        if self.live and self.progress and self.current_task is not None:
            self.live.start()

    def rollback(self, checkpoint_name: str) -> None:
        """Signal rollback to a checkpoint.

        Args:
            checkpoint_name: Name of checkpoint to rollback to.
        """
        if not self.config.show_checkpoints:
            return

        # Pause live display
        if self.live:
            self.live.stop()

        rollback_text = (
            f"  [cyan]{self._symbol('rollback')} Rollback to: [bold]{checkpoint_name}[/bold][/cyan]"
        )
        self.console.print(rollback_text)

        # Restart live display
        if self.live and self.progress and self.current_task is not None:
            self.live.start()

    def branch_start(self, checkpoint_name: str, path_count: int) -> None:
        """Signal the start of a branch execution.

        Args:
            checkpoint_name: Name of the checkpoint this branch starts from.
            path_count: Number of paths in this branch.
        """
        if not self.config.show_paths:
            return

        # Pause live display
        if self.live:
            self.live.stop()

        self.console.print()
        branch_text = (
            f"[bold blue]{self._symbol('branch')} Branch: {checkpoint_name}[/bold blue] "
            f"[dim]({path_count} paths)[/dim]"
        )
        self.console.print(branch_text)

        # Add to tree
        if self.tree:
            self.current_branch_node = self.tree.add(
                f"[blue]{self._symbol('branch')} Branch: {checkpoint_name}[/blue]"
            )

        # Restart live display
        if self.live and self.progress and self.current_task is not None:
            self.live.start()

    def path_start(self, name: str, checkpoint: str = "") -> None:
        """Signal the start of a path execution.

        Args:
            name: Path name.
            checkpoint: Associated checkpoint name.
        """
        self.current_path = PathInfo(
            name=name,
            checkpoint=checkpoint,
            started_at=datetime.now(),
        )
        self.paths.append(self.current_path)

        if not self.config.show_paths:
            return

        # Pause live display
        if self.live:
            self.live.stop()

        path_text = f"  [cyan]{self._symbol('pipe')} {self._symbol('branch')} Path: {name}[/cyan]"
        self.console.print(path_text)

        # Restart live display
        if self.live and self.progress and self.current_task is not None:
            self.live.start()

    def path_result(
        self,
        name: str,
        success: bool,
        step_count: int,
        duration_ms: float = 0.0,
    ) -> None:
        """Signal path completion with result.

        Args:
            name: Path name.
            success: Whether path passed.
            step_count: Number of steps in path.
            duration_ms: Path duration in milliseconds.
        """
        if self.current_path:
            self.current_path.success = success
            self.current_path.finished_at = datetime.now()

        if not self.config.show_paths:
            return

        # Pause live display
        if self.live:
            self.live.stop()

        symbol = self._symbol("check") if success else self._symbol("cross")
        color = "green" if success else "red"

        duration_text = f" [{self._format_duration(duration_ms)}]" if duration_ms > 0 else ""
        result_text = (
            f"  [{color}]{self._symbol('pipe')} {self._symbol('corner')} "
            f"{symbol} {name}[/{color}] [dim]({step_count} steps){duration_text}[/dim]"
        )
        self.console.print(result_text)

        # Add to tree
        if self.current_branch_node:
            self.current_branch_node.add(
                f"[{color}]{symbol} {name}[/{color}] [dim]({step_count} steps)[/dim]"
            )

        # Restart live display
        if self.live and self.progress and self.current_task is not None:
            self.live.start()

    def invariant_check(self, name: str, passed: bool, message: str = "") -> None:
        """Display an invariant check result.

        Args:
            name: Invariant name.
            passed: Whether invariant passed.
            message: Optional message.
        """
        symbol = self._symbol("check") if passed else self._symbol("cross")
        color = "green" if passed else "red"

        inv_text = f"[{color}]{symbol} Invariant: {name}[/{color}]"
        if message:
            inv_text += f" [dim]{message}[/dim]"

        if self.tree:
            self.tree.add(inv_text)

        if not self.live:
            self.console.print(f"  {inv_text}")

    def journey_summary(
        self,
        name: str,
        success: bool,
        step_count: int,
        passed_steps: int,
        duration_ms: float,
        issues: list[Any] | None = None,
        paths_passed: int = 0,
        paths_total: int = 0,
    ) -> None:
        """Display journey completion summary.

        Args:
            name: Journey name.
            success: Whether journey passed.
            step_count: Total steps executed.
            passed_steps: Number of passed steps.
            duration_ms: Total duration in milliseconds.
            issues: List of issues captured.
            paths_passed: Number of passed paths.
            paths_total: Total paths.
        """
        # Stop live display
        if self.live:
            self.live.stop()
            self.live = None

        self.console.print()

        # Status
        status_symbol = self._symbol("check") if success else self._symbol("cross")
        status_color = "green" if success else "red"
        status_text = "PASSED" if success else "FAILED"

        # Create summary table
        summary_table = Table.grid(padding=(0, 2))
        summary_table.add_column(style="bold", width=15)
        summary_table.add_column()

        summary_table.add_row(
            "Status:",
            f"[{status_color} bold]{status_symbol} {status_text}[/{status_color} bold]"
        )
        summary_table.add_row("Duration:", f"[cyan]{self._format_duration(duration_ms)}[/cyan]")
        summary_table.add_row(
            "Steps:",
            f"[green]{passed_steps}[/green]/[cyan]{step_count}[/cyan] passed"
        )

        if paths_total > 0:
            summary_table.add_row(
                "Paths:",
                f"[green]{paths_passed}[/green]/[cyan]{paths_total}[/cyan] passed"
            )

        if self.checkpoints:
            summary_table.add_row(
                "Checkpoints:",
                f"[yellow]{len(self.checkpoints)}[/yellow]"
            )

        # Add timing breakdown
        if self.config.show_timing and self.step_timings:
            summary_table.add_row("", "")
            summary_table.add_row("[bold]Step Timings:[/bold]", "")

            # Sort by duration descending
            sorted_timings = sorted(self.step_timings, key=lambda x: x[1], reverse=True)

            for step_name, step_duration, step_success in sorted_timings[:8]:
                symbol = self._symbol("check") if step_success else self._symbol("cross")
                color = "green" if step_success else "red"
                summary_table.add_row(
                    f"  [{color}]{symbol}[/{color}] {step_name}",
                    f"[cyan]{self._format_duration(step_duration)}[/cyan]"
                )

            if len(self.step_timings) > 8:
                remaining = len(self.step_timings) - 8
                summary_table.add_row(f"  [dim]... and {remaining} more[/dim]", "")

        # Create panel
        panel = Panel(
            summary_table,
            title=f"[bold]{status_symbol} JOURNEY COMPLETE: {name}[/bold]",
            border_style=status_color,
            padding=(1, 2),
        )
        self.console.print(panel)

        # Show issues if any
        if issues:
            self.console.print()
            issues_table = Table(
                title=f"[bold red]{self._symbol('cross')} Issues ({len(issues)})[/bold red]",
                show_header=True,
                header_style="bold",
                box=None,
            )
            issues_table.add_column("Severity", width=10)
            issues_table.add_column("Step", width=25)
            issues_table.add_column("Error")

            for issue in issues[:10]:
                if isinstance(issue, dict):
                    severity = issue.get("severity", "high")
                    step = issue.get("step", "unknown")
                    error = issue.get("error", "unknown error")
                else:
                    severity = getattr(issue, "severity", "high")
                    if hasattr(severity, "value"):
                        severity = severity.value
                    step = getattr(issue, "step", "unknown")
                    error = getattr(issue, "error", "unknown error")

                severity_color = {
                    "critical": "red bold",
                    "high": "red",
                    "medium": "yellow",
                    "low": "blue",
                    "info": "dim",
                }.get(str(severity).lower(), "red")

                issues_table.add_row(
                    f"[{severity_color}]{severity.upper()}[/{severity_color}]",
                    step,
                    error[:60] + "..." if len(error) > 60 else error,
                )

            if len(issues) > 10:
                self.console.print(f"  [dim]... and {len(issues) - 10} more[/dim]")

            self.console.print(issues_table)

    def overall_summary(
        self,
        total: int,
        passed: int,
        failed: int,
        total_duration_ms: float,
        issues_by_severity: dict[str, int] | None = None,
    ) -> None:
        """Display overall test run summary.

        Args:
            total: Total journeys.
            passed: Passed journeys.
            failed: Failed journeys.
            total_duration_ms: Total duration.
            issues_by_severity: Issue counts by severity level.
        """
        self.console.print()

        # Create summary table
        summary_table = Table.grid(padding=(0, 3))
        summary_table.add_column(style="bold", width=15)
        summary_table.add_column(width=15)

        # Pass rate
        pass_rate = (passed / total * 100) if total > 0 else 100
        rate_color = "green" if pass_rate >= 90 else "yellow" if pass_rate >= 70 else "red"

        summary_table.add_row("Total Journeys:", f"[cyan]{total}[/cyan]")
        summary_table.add_row("Passed:", f"[green]{passed}[/green]")
        summary_table.add_row("Failed:", f"[red]{failed}[/red]")
        summary_table.add_row("Pass Rate:", f"[{rate_color}]{pass_rate:.1f}%[/{rate_color}]")
        summary_table.add_row("Duration:", f"[cyan]{self._format_duration(total_duration_ms)}[/cyan]")

        # Issue breakdown
        if issues_by_severity:
            summary_table.add_row("", "")
            summary_table.add_row("[bold]Issues:[/bold]", "")
            for severity, count in issues_by_severity.items():
                if count > 0:
                    severity_color = {
                        "critical": "red bold",
                        "high": "red",
                        "medium": "yellow",
                        "low": "blue",
                        "info": "dim",
                    }.get(severity.lower(), "white")
                    summary_table.add_row(
                        f"  {severity.capitalize()}:",
                        f"[{severity_color}]{count}[/{severity_color}]"
                    )

        # Status
        status_color = "green" if failed == 0 else "red"
        status_text = "ALL JOURNEYS PASSED" if failed == 0 else "SOME JOURNEYS FAILED"
        status_symbol = self._symbol("check") if failed == 0 else self._symbol("cross")

        panel = Panel(
            summary_table,
            title=f"[bold]{status_symbol} SUMMARY: {status_text}[/bold]",
            border_style=status_color,
            padding=(1, 2),
        )

        self.console.print(panel)

    def show_dashboard(
        self,
        stats: dict[str, Any],
        trend_data: list[dict[str, Any]] | None = None,
    ) -> None:
        """Display a dashboard summary.

        Args:
            stats: Dashboard statistics dictionary.
            trend_data: Optional trend data for visualization.
        """
        self.console.print()
        self.console.rule("[bold blue]VenomQA Dashboard[/bold blue]")
        self.console.print()

        # Create layout
        layout = Layout()
        layout.split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1),
        )

        # Stats cards
        stats_table = Table.grid(padding=(0, 2))
        stats_table.add_column(width=20)
        stats_table.add_column(width=15)

        pass_rate = stats.get("pass_rate", 0)
        rate_color = "green" if pass_rate >= 90 else "yellow" if pass_rate >= 70 else "red"

        stats_table.add_row("Total Runs:", f"[cyan]{stats.get('total_runs', 0)}[/cyan]")
        stats_table.add_row("Passed:", f"[green]{stats.get('total_passed', 0)}[/green]")
        stats_table.add_row("Failed:", f"[red]{stats.get('total_failed', 0)}[/red]")
        stats_table.add_row("Pass Rate:", f"[{rate_color}]{pass_rate:.1f}%[/{rate_color}]")
        stats_table.add_row(
            "Avg Duration:",
            f"[cyan]{self._format_duration(stats.get('avg_duration_ms', 0))}[/cyan]"
        )

        stats_panel = Panel(
            stats_table,
            title="[bold]Statistics[/bold]",
            border_style="blue",
        )
        self.console.print(stats_panel)

        # Top failing journeys
        if stats.get("top_failing_journeys"):
            self.console.print()
            failing_table = Table(
                title="[bold red]Top Failing Journeys[/bold red]",
                show_header=True,
                header_style="bold",
            )
            failing_table.add_column("Journey", min_width=30)
            failing_table.add_column("Failures", width=10, justify="right")

            for journey_name, fail_count in stats["top_failing_journeys"][:5]:
                failing_table.add_row(journey_name, f"[red]{fail_count}[/red]")

            self.console.print(failing_table)

        # Slowest journeys
        if stats.get("slowest_journeys"):
            self.console.print()
            slow_table = Table(
                title="[bold yellow]Slowest Journeys[/bold yellow]",
                show_header=True,
                header_style="bold",
            )
            slow_table.add_column("Journey", min_width=30)
            slow_table.add_column("Avg Duration", width=15, justify="right")

            for journey_name, avg_duration in stats["slowest_journeys"][:5]:
                slow_table.add_row(
                    journey_name,
                    f"[yellow]{self._format_duration(avg_duration)}[/yellow]"
                )

            self.console.print(slow_table)

        # Trend visualization (simple ASCII)
        if trend_data and len(trend_data) > 1:
            self.console.print()
            self._render_trend_chart(trend_data)

    def _render_trend_chart(
        self,
        trend_data: list[dict[str, Any]],
        width: int = 60,
        height: int = 10,
    ) -> None:
        """Render a simple ASCII trend chart.

        Args:
            trend_data: List of trend data points.
            width: Chart width in characters.
            height: Chart height in lines.
        """
        if not trend_data:
            return

        self.console.print("[bold]Pass Rate Trend[/bold]")
        self.console.print()

        # Extract pass rates
        pass_rates = [d.get("pass_rate", 0) for d in trend_data]
        max_rate = max(pass_rates) if pass_rates else 100
        min_rate = min(pass_rates) if pass_rates else 0

        # Normalize to height
        range_val = max(max_rate - min_rate, 1)

        # Create chart
        for row in range(height, -1, -1):
            threshold = min_rate + (range_val * row / height)
            line = ""

            for rate in pass_rates:
                if rate >= threshold:
                    line += "[green]█[/green]"
                else:
                    line += " "

            # Y-axis label
            if row == height:
                label = f"{max_rate:5.1f}%"
            elif row == 0:
                label = f"{min_rate:5.1f}%"
            elif row == height // 2:
                mid = (max_rate + min_rate) / 2
                label = f"{mid:5.1f}%"
            else:
                label = "      "

            self.console.print(f"  {label} │{line}")

        # X-axis
        self.console.print(f"        └{'─' * len(pass_rates)}")

        # Date labels (first and last)
        if trend_data:
            first_date = trend_data[0].get("date", "")
            last_date = trend_data[-1].get("date", "")
            padding = len(pass_rates) - len(first_date) - len(last_date)
            if padding > 0:
                self.console.print(f"         {first_date}{' ' * padding}{last_date}")


    def show_enhanced_error(
        self,
        step_name: str,
        journey_name: str,
        error: str,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        suggestions: list[str] | None = None,
        stack_trace: str | None = None,
    ) -> None:
        """Display an enhanced error with full context and troubleshooting suggestions.

        Args:
            step_name: Name of the failed step.
            journey_name: Name of the journey.
            error: Error message.
            request: Full request data.
            response: Full response data.
            suggestions: Troubleshooting suggestions.
            stack_trace: Filtered stack trace.
        """
        # Stop live display to show error
        if self.live:
            self.live.stop()

        self.console.print()

        # Error header
        error_panel = Panel(
            f"[red bold]Step Failed: {step_name}[/red bold]\n"
            f"[dim]Journey: {journey_name}[/dim]",
            title="[red]ERROR[/red]",
            border_style="red",
            padding=(0, 2),
        )
        self.console.print(error_panel)

        # Error message
        self.console.print("\n[bold]Error Message:[/bold]")
        self.console.print(f"  [red]{error}[/red]")

        # Request details
        if request and self.config.show_request_response:
            self.console.print("\n[bold]Request:[/bold]")
            method = request.get("method", "?")
            url = request.get("url", "?")
            self.console.print(f"  [cyan]{method}[/cyan] {url}")
            if request.get("body"):
                self.console.print(f"  Body: {str(request['body'])[:200]}")

        # Response details
        if response and self.config.show_request_response:
            self.console.print("\n[bold]Response:[/bold]")
            status = response.get("status_code", "?")
            status_color = "green" if 200 <= int(status or 0) < 300 else "red"
            self.console.print(f"  Status: [{status_color}]{status}[/{status_color}]")
            if response.get("body"):
                body_str = str(response["body"])
                if len(body_str) > 300:
                    body_str = body_str[:300] + "..."
                self.console.print(f"  Body: {body_str}")

        # Stack trace (filtered)
        if stack_trace:
            self.console.print("\n[bold]Stack Trace (user code):[/bold]")
            for line in stack_trace.split("\n")[:15]:
                if line.strip():
                    if ">>>" in line:
                        self.console.print(f"  [cyan]{line}[/cyan]")
                    else:
                        self.console.print(f"  [dim]{line}[/dim]")

        # Troubleshooting suggestions
        if suggestions:
            self.console.print("\n[bold]Troubleshooting Suggestions:[/bold]")
            for suggestion in suggestions:
                self.console.print(f"  [green]{self._symbol('bullet')}[/green] {suggestion}")

        self.console.print()

        # Restart live display
        if self.live and self.progress and self.current_task is not None:
            self.live.start()


def create_output(config: ProgressConfig | dict[str, Any] | None = None) -> CLIOutput:
    """Create a CLI output handler.

    Args:
        config: Optional configuration.

    Returns:
        Configured CLIOutput instance.
    """
    return CLIOutput(config)
