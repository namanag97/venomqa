"""Console reporter for terminal output."""

from __future__ import annotations

import sys
from collections import Counter
from itertools import groupby
from typing import TextIO

from venomqa.v1.core.invariant import Severity
from venomqa.v1.core.result import ExplorationResult


class ConsoleReporter:
    """Formats ExplorationResult for terminal output.

    Features:
    - Collapsible repeated actions in paths (e.g., "confirm_member ×38")
    - Clear visual hierarchy with box drawing
    - Severity-based coloring
    - Deduplication of violations by root cause
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

    def __init__(self, file: TextIO = sys.stdout, color: bool = True) -> None:
        self.file = file
        self.color = color

    def _c(self, text: str, code: str) -> str:
        """Apply color if enabled."""
        if self.color:
            return f"{code}{text}{self.RESET}"
        return text

    def _collapse_path(self, actions: list[str]) -> str:
        """Collapse repeated consecutive actions.

        Example: ['a', 'b', 'b', 'b', 'c'] -> 'a → b ×3 → c'
        """
        if not actions:
            return ""

        collapsed = []
        for action, group in groupby(actions):
            count = len(list(group))
            if count > 1:
                collapsed.append(f"{action} ×{count}")
            else:
                collapsed.append(action)

        return " → ".join(collapsed)

    def report(self, result: ExplorationResult) -> None:
        """Output the exploration result to console."""
        # ═══════════════════════════════════════════════════════════════
        # HEADER
        # ═══════════════════════════════════════════════════════════════
        self._newline()
        if result.success:
            status = self._c("PASSED", self.GREEN + self.BOLD)
            icon = self._c("✓", self.GREEN)
        else:
            critical = len(result.critical_violations)
            high = len(result.high_violations)
            status = self._c(f"FAILED ({critical} critical, {high} high)", self.RED + self.BOLD)
            icon = self._c("✗", self.RED)

        self._line(f"  {icon} VenomQA Exploration: {status}")
        self._line(self._c("  " + "─" * 60, self.DIM))
        self._newline()

        # ═══════════════════════════════════════════════════════════════
        # SUMMARY (compact)
        # ═══════════════════════════════════════════════════════════════
        used = result.graph.used_action_count
        total = result.actions_total
        coverage_pct = result.action_coverage_percent
        coverage_color = self.GREEN if coverage_pct >= 80 else (self.YELLOW if coverage_pct >= 50 else self.RED)

        summary_parts = [
            f"{result.states_visited} states",
            f"{result.transitions_taken} steps",
            self._c(f"{coverage_pct:.0f}% coverage", coverage_color),
            f"{result.duration_ms:.0f}ms",
        ]
        self._line(f"  {self._c('Summary:', self.BOLD)} {' │ '.join(summary_parts)}")

        if result.truncated_by_max_steps:
            self._line(self._c(f"  ⚠ Truncated at max_steps limit", self.YELLOW))
        self._newline()

        # ═══════════════════════════════════════════════════════════════
        # VIOLATIONS
        # ═══════════════════════════════════════════════════════════════
        if result.violations:
            unique = result.unique_violations
            total_violations = len(result.violations)
            n_unique = len(unique)

            if total_violations == n_unique:
                header = f"Violations ({total_violations})"
            else:
                header = f"Violations ({n_unique} unique, {total_violations} total)"

            self._line(f"  {self._c(header, self.BOLD)}")
            self._newline()

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
                if count > 1:
                    count_str = self._c(f" (×{count})", self.DIM)
                else:
                    count_str = ""

                # Box top
                self._line(f"  {self.BOX_TL}{self.BOX_H * 58}{self.BOX_TR}")

                # Invariant name + severity
                self._line(f"  {self.BOX_V} {sev_badge} {self._c(v.invariant_name, self.BOLD)}{count_str}")

                # Message
                if v.message:
                    self._line(f"  {self.BOX_V}")
                    # Wrap long messages
                    msg = v.message
                    if len(msg) > 54:
                        msg = msg[:51] + "..."
                    self._line(f"  {self.BOX_V}   {msg}")

                # Path (collapsed)
                if v.reproduction_path:
                    self._line(f"  {self.BOX_V}")
                    actions = [t.action_name for t in v.reproduction_path]
                    collapsed = self._collapse_path(actions)

                    # Truncate if still too long
                    if len(collapsed) > 52:
                        collapsed = collapsed[:49] + "..."

                    self._line(f"  {self.BOX_V}   {self._c('Path:', self.CYAN)} {collapsed}")

                # HTTP details (if available)
                if v.action_result is not None:
                    ar = v.action_result
                    req = ar.request
                    self._line(f"  {self.BOX_V}")
                    self._line(f"  {self.BOX_V}   {self._c(req.method, self.CYAN)} {self._truncate(req.url, 45)}")

                    if ar.response is not None:
                        resp = ar.response
                        status_color = self.GREEN if resp.ok else self.RED
                        self._line(f"  {self.BOX_V}   {self._c('→', self.DIM)} {self._c(str(resp.status_code), status_color)}")
                    elif ar.error:
                        self._line(f"  {self.BOX_V}   {self._c('→ ERROR:', self.RED)} {self._truncate(str(ar.error), 40)}")

                # Box bottom
                self._line(f"  {self.BOX_BL}{self.BOX_H * 58}{self.BOX_BR}")

                if i < len(unique) - 1:
                    self._newline()

            self._newline()

        # ═══════════════════════════════════════════════════════════════
        # FOOTER
        # ═══════════════════════════════════════════════════════════════
        self._line(self._c("  " + "─" * 60, self.DIM))
        if result.success:
            self._line(f"  {self._c('All invariants held.', self.GREEN)}")
        else:
            self._line(f"  {self._c('Fix the violations above and re-run.', self.YELLOW)}")
        self._newline()

    def _line(self, text: str) -> None:
        print(text, file=self.file)

    def _newline(self) -> None:
        print(file=self.file)

    def _truncate(self, text: str, max_chars: int = 200) -> str:
        """Truncate text to max_chars."""
        if not isinstance(text, str):
            text = str(text)
        if len(text) <= max_chars:
            return text
        return text[:max_chars - 3] + "..."

    def _severity_color(self, severity: Severity) -> str:
        if severity == Severity.CRITICAL:
            return self.RED + self.BOLD
        elif severity == Severity.HIGH:
            return self.RED
        elif severity == Severity.MEDIUM:
            return self.YELLOW
        return self.DIM
