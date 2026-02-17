"""Console reporter for terminal output."""

from __future__ import annotations

import sys
from typing import TextIO

from venomqa.v1.core.invariant import Severity
from venomqa.v1.core.result import ExplorationResult


class ConsoleReporter:
    """Formats ExplorationResult for terminal output."""

    # ANSI color codes
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    def __init__(self, file: TextIO = sys.stdout, color: bool = True) -> None:
        self.file = file
        self.color = color

    def _c(self, text: str, code: str) -> str:
        """Apply color if enabled."""
        if self.color:
            return f"{code}{text}{self.RESET}"
        return text

    def report(self, result: ExplorationResult) -> None:
        """Output the exploration result to console."""
        self._header("Exploration Results")
        self._newline()

        # Summary
        self._section("Summary")
        self._kv("States visited", str(result.states_visited))
        self._kv("Transitions taken", str(result.transitions_taken))
        used = result.graph.used_action_count
        total = result.actions_total
        self._kv("Actions used", f"{used}/{total} ({result.action_coverage_percent:.0f}%)")
        self._kv("Duration", f"{result.duration_ms:.0f}ms")
        if result.truncated_by_max_steps:
            self._line(
                self._c(
                    f"  ⚠ Exploration truncated at {result.transitions_taken} steps (max_steps limit)",
                    self.YELLOW,
                )
            )
        self._newline()

        # Violations
        if result.violations:
            self._section(f"Violations ({len(result.violations)})")
            for v in result.violations:
                color = self._severity_color(v.severity)
                self._line(f"  {self._c(v.severity.value.upper(), color)}: {v.invariant_name}")
                if v.message:
                    self._line(f"    {v.message}")
                if v.reproduction_path:
                    path_str = " -> ".join(t.action_name for t in v.reproduction_path)
                    self._line(f"    Path: {path_str}")
                # Show HTTP request/response payload when available
                if v.action_result is not None:
                    ar = v.action_result
                    req = ar.request
                    self._line(f"    {self._c('Request:', self.BOLD)} {req.method} {req.url}")
                    if req.body is not None:
                        self._line(f"      Body: {self._truncate(req.body)}")
                    if ar.response is not None:
                        resp = ar.response
                        ok_color = self.GREEN if resp.ok else self.RED
                        self._line(
                            f"    {self._c('Response:', self.BOLD)} "
                            f"{self._c(str(resp.status_code), ok_color)}"
                        )
                        if resp.body is not None:
                            self._line(f"      Body: {self._truncate(resp.body)}")
                    elif ar.error:
                        self._line(f"    {self._c('Error:', self.RED)} {ar.error}")
            self._newline()

        # Final status
        if result.success:
            self._line(self._c("PASSED", self.GREEN + self.BOLD))
        else:
            critical = len(result.critical_violations)
            high = len(result.high_violations)
            self._line(self._c(f"FAILED ({critical} critical, {high} high)", self.RED + self.BOLD))

    def _header(self, text: str) -> None:
        self._line(self._c(f"=== {text} ===", self.BOLD))

    def _section(self, text: str) -> None:
        self._line(self._c(f"--- {text} ---", self.BLUE))

    def _kv(self, key: str, value: str) -> None:
        self._line(f"  {key}: {value}")

    def _line(self, text: str) -> None:
        print(text, file=self.file)

    def _newline(self) -> None:
        print(file=self.file)

    def _truncate(self, body: object, max_chars: int = 200) -> str:
        """Render a response/request body, capping at max_chars."""
        text = repr(body) if not isinstance(body, str) else body
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + f"  … (+{len(text) - max_chars} chars)"

    def _severity_color(self, severity: Severity) -> str:
        if severity == Severity.CRITICAL:
            return self.RED + self.BOLD
        elif severity == Severity.HIGH:
            return self.RED
        elif severity == Severity.MEDIUM:
            return self.YELLOW
        return ""
