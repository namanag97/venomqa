"""Console reporter for terminal output."""

from __future__ import annotations

import io
import sys
from collections import Counter
from itertools import groupby
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from venomqa.exploration import ExplorationResult
    from venomqa.v1.core.invariant import Severity


class ConsoleReporter:
    """Formats ExplorationResult for terminal output.

    Features:
    - Collapsible repeated actions in paths (e.g., "confirm_member x38")
    - Clear visual hierarchy with box drawing
    - Severity-based coloring
    - Deduplication of violations by root cause

    Example::

        reporter = ConsoleReporter()

        # Get report as string
        output = reporter.report(result)

        # Or print directly
        reporter.print_report(result)

        # Disable colors for file output
        reporter = ConsoleReporter(color=False)
        with open("report.txt", "w") as f:
            f.write(reporter.report(result))
    """

    # ANSI color codes
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    # Box drawing characters
    BOX_TL = "┌"
    BOX_TR = "┐"
    BOX_BL = "└"
    BOX_BR = "┘"
    BOX_H = "─"
    BOX_V = "│"

    def __init__(self, file: TextIO | None = None, color: bool = True) -> None:
        """Initialize the console reporter.

        Args:
            file: Output file (default: stdout). Only used by print_report().
            color: Whether to use ANSI colors (default: True).
        """
        self.file = file or sys.stdout
        self.color = color

    def _c(self, text: str, code: str) -> str:
        """Apply color if enabled."""
        if self.color:
            return f"{code}{text}{self.RESET}"
        return text

    def _collapse_path(self, actions: list[str]) -> str:
        """Collapse repeated consecutive actions.

        Example: ['a', 'b', 'b', 'b', 'c'] -> 'a -> b x3 -> c'
        """
        if not actions:
            return ""

        collapsed = []
        for action, group in groupby(actions):
            count = len(list(group))
            if count > 1:
                collapsed.append(f"{action} x{count}")
            else:
                collapsed.append(action)

        return " -> ".join(collapsed)

    def report(self, result: ExplorationResult) -> str:
        """Format the exploration result as a string.

        For backward compatibility, if a file was provided in __init__,
        the output is also written to that file.

        Args:
            result: The exploration result to format.

        Returns:
            Formatted string with ANSI colors (if enabled).
        """
        # Use StringIO to build the output
        buffer = io.StringIO()

        # Build the report into the buffer
        self._write_report(result, buffer)

        output = buffer.getvalue()

        # Backward compatibility: also write to file if provided
        # (old code expected report() to write to file)
        if self.file is not sys.stdout:
            self.file.write(output)

        return output

    def print_report(self, result: ExplorationResult) -> None:
        """Print the exploration result to stdout.

        Args:
            result: The exploration result to print.
        """
        output = self.report(result)
        if self.file is sys.stdout:
            # Already handled by report() for non-stdout files
            print(output, end="")

    def _write_report(self, result: ExplorationResult, buffer: io.StringIO) -> None:
        """Write the report to a buffer."""
        from venomqa.v1.core.invariant import Severity

        def line(text: str = "") -> None:
            buffer.write(text + "\n")

        # Header
        line()
        if result.success:
            status = self._c("PASSED", self.GREEN + self.BOLD)
            icon = self._c("✓", self.GREEN)
        else:
            critical = len(result.critical_violations)
            high = len(result.high_violations)
            status = self._c(f"FAILED ({critical} critical, {high} high)", self.RED + self.BOLD)
            icon = self._c("✗", self.RED)

        line(f"  {icon} VenomQA Exploration: {status}")
        line(self._c("  " + "─" * 60, self.DIM))
        line()

        # Summary
        coverage_pct = result.action_coverage_percent
        coverage_color = self.GREEN if coverage_pct >= 80 else (self.YELLOW if coverage_pct >= 50 else self.RED)

        summary_parts = [
            f"{result.states_visited} states",
            f"{result.transitions_taken} steps",
            self._c(f"{coverage_pct:.0f}% coverage", coverage_color),
            f"{result.duration_ms:.0f}ms",
        ]
        line(f"  {self._c('Summary:', self.BOLD)} {' | '.join(summary_parts)}")

        if result.truncated_by_max_steps:
            line(self._c("  Warning: Truncated at max_steps limit", self.YELLOW))
        line()

        # Violations
        if result.violations:
            unique = result.unique_violations
            total_violations = len(result.violations)
            n_unique = len(unique)

            if total_violations == n_unique:
                header = f"Violations ({total_violations})"
            else:
                header = f"Violations ({n_unique} unique, {total_violations} total)"

            line(f"  {self._c(header, self.BOLD)}")
            line()

            # Count occurrences per root cause
            cause_counts: Counter[tuple[str, str | None]] = Counter()
            for v in result.violations:
                cause_counts[(v.invariant_name, v.action.name if v.action else None)] += 1

            for i, v in enumerate(unique):
                key = (v.invariant_name, v.action.name if v.action else None)
                count = cause_counts[key]

                # Severity badge
                sev_color = self._severity_color(v.severity)
                sev_badge = self._c(f"[{v.severity.value.upper()}]", sev_color)

                # Occurrence count
                count_str = self._c(f" (x{count})", self.DIM) if count > 1 else ""

                # Box top
                line(f"  {self.BOX_TL}{self.BOX_H * 58}{self.BOX_TR}")

                # Invariant name + severity
                line(f"  {self.BOX_V} {sev_badge} {self._c(v.invariant_name, self.BOLD)}{count_str}")

                # Message
                if v.message:
                    line(f"  {self.BOX_V}")
                    msg = v.message[:51] + "..." if len(v.message) > 54 else v.message
                    line(f"  {self.BOX_V}   {msg}")

                # Path
                if v.reproduction_path:
                    line(f"  {self.BOX_V}")
                    actions = [t.action_name for t in v.reproduction_path]
                    collapsed = self._collapse_path(actions)
                    if len(collapsed) > 52:
                        collapsed = collapsed[:49] + "..."
                    line(f"  {self.BOX_V}   {self._c('Path:', self.CYAN)} {collapsed}")

                # HTTP details
                if v.action_result is not None:
                    ar = v.action_result
                    req = ar.request
                    line(f"  {self.BOX_V}")
                    line(f"  {self.BOX_V}   {self._c(req.method, self.CYAN)} {self._truncate(req.url, 45)}")

                    if ar.response is not None:
                        resp = ar.response
                        status_color = self.GREEN if resp.ok else self.RED
                        line(f"  {self.BOX_V}   {self._c('->', self.DIM)} {self._c(str(resp.status_code), status_color)}")
                    elif ar.error:
                        line(f"  {self.BOX_V}   {self._c('-> ERROR:', self.RED)} {self._truncate(str(ar.error), 40)}")

                # Box bottom
                line(f"  {self.BOX_BL}{self.BOX_H * 58}{self.BOX_BR}")

                if i < len(unique) - 1:
                    line()

            line()

        # Footer
        line(self._c("  " + "─" * 60, self.DIM))
        if result.success:
            line(f"  {self._c('All invariants held.', self.GREEN)}")
        else:
            line(f"  {self._c('Fix the violations above and re-run.', self.YELLOW)}")
        line()

    def _truncate(self, text: str, max_chars: int = 200) -> str:
        """Truncate text to max_chars."""
        if not isinstance(text, str):
            text = str(text)
        return text[:max_chars - 3] + "..." if len(text) > max_chars else text

    def _severity_color(self, severity: Severity) -> str:
        from venomqa.v1.core.invariant import Severity

        if severity == Severity.CRITICAL:
            return self.RED + self.BOLD
        elif severity == Severity.HIGH:
            return self.RED
        elif severity == Severity.MEDIUM:
            return self.YELLOW
        return self.DIM


__all__ = ["ConsoleReporter"]
