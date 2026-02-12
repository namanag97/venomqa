"""Rich CLI output for VenomQA with progress indicators and visualization."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any


class OutputStyle(Enum):
    PLAIN = "plain"
    RICH = "rich"


@dataclass
class ProgressConfig:
    show_progress: bool = True
    show_checkpoints: bool = True
    show_paths: bool = True
    show_timing: bool = True
    use_colors: bool = True
    use_unicode: bool = True


class CLIOutput:
    """Rich CLI output handler for VenomQA."""

    COLORS = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "cyan": "\033[96m",
        "dim": "\033[90m",
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
    }

    def __init__(self, config: ProgressConfig | None = None) -> None:
        self.config = config or ProgressConfig()
        self._use_colors = self.config.use_colors and self._supports_color()
        self._use_unicode = self.config.use_unicode and self._supports_unicode()

    def _supports_color(self) -> bool:
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    def _supports_unicode(self) -> bool:
        try:
            return sys.stdout.encoding and "utf" in sys.stdout.encoding.lower()
        except Exception:
            return False

    def _color(self, text: str, color: str) -> str:
        if not self._use_colors:
            return text
        return f"{self.COLORS.get(color, '')}{text}{self.COLORS['reset']}"

    def _symbol(self, name: str) -> str:
        symbols = self.SYMBOLS if self._use_unicode else self.ASCII_SYMBOLS
        return symbols.get(name, name)

    def header(self, text: str) -> None:
        print(f"\n{self._color(text, 'bold')}")
        print(self._color("=" * len(text), "dim"))

    def journey_start(self, name: str, description: str = "") -> None:
        msg = f"\n{self._symbol('gear')} Journey: {self._color(name, 'cyan')}"
        if description:
            msg += f"\n   {self._color(description, 'dim')}"
        print(msg)

    def step_start(self, name: str, description: str = "") -> None:
        if not self.config.show_progress:
            return
        msg = f"  {self._symbol('arrow')} {name}"
        if description:
            msg += f" {self._color(description, 'dim')}"
        print(msg, end="", flush=True)

    def step_pass(self, duration_ms: float | None = None) -> None:
        msg = f" {self._color(self._symbol('check'), 'green')}"
        if self.config.show_timing and duration_ms is not None:
            msg += f" {self._color(f'({duration_ms:.0f}ms)', 'dim')}"
        print(msg)

    def step_fail(self, error: str, duration_ms: float | None = None) -> None:
        msg = f" {self._color(self._symbol('cross'), 'red')}"
        if self.config.show_timing and duration_ms is not None:
            msg += f" {self._color(f'({duration_ms:.0f}ms)', 'dim')}"
        print(msg)
        print(f"    {self._color(f'Error: {error}', 'red')}")

    def checkpoint(self, name: str) -> None:
        if not self.config.show_checkpoints:
            return
        print(f"  {self._color(self._symbol('checkpoint'), 'yellow')} Checkpoint: {name}")

    def rollback(self, checkpoint_name: str) -> None:
        if not self.config.show_checkpoints:
            return
        print(f"  {self._color(self._symbol('rollback'), 'cyan')} Rollback to: {checkpoint_name}")

    def branch_start(self, checkpoint_name: str, path_count: int) -> None:
        if not self.config.show_paths:
            return
        print(f"\n  {self._color('Branch', 'blue')} from {checkpoint_name} ({path_count} paths)")

    def path_start(self, name: str) -> None:
        if not self.config.show_paths:
            return
        print(f"    {self._symbol('branch')} Path: {self._color(name, 'cyan')}")

    def path_result(self, name: str, success: bool, step_count: int) -> None:
        if not self.config.show_paths:
            return
        symbol = self._symbol("check") if success else self._symbol("cross")
        color = "green" if success else "red"
        print(
            f"    {self._symbol('corner')} {self._color(symbol, color)} {name} ({step_count} steps)"
        )

    def invariant_check(self, name: str, passed: bool, message: str = "") -> None:
        symbol = self._symbol("check") if passed else self._symbol("cross")
        color = "green" if passed else "red"
        msg = f"  {self._color(symbol, color)} Invariant: {name}"
        if message:
            msg += f" {self._color(message, 'dim')}"
        print(msg)

    def journey_summary(
        self,
        name: str,
        success: bool,
        step_count: int,
        passed_steps: int,
        duration_ms: float,
        issues: list[Any] | None = None,
    ) -> None:
        symbol = self._symbol("check") if success else self._symbol("cross")
        color = "green" if success else "red"
        status = "PASSED" if success else "FAILED"

        print(f"\n{self._color(symbol, color)} {name}: {self._color(status, color)}")
        print(f"  Steps: {passed_steps}/{step_count} | Duration: {duration_ms:.0f}ms")

        if issues:
            print(f"\n  {self._color('Issues:', 'red')}")
            for issue in issues[:5]:
                step = issue.get("step", "unknown")
                error = issue.get("error", "unknown error")
                print(f"    {self._symbol('cross')} {step}: {error}")
            if len(issues) > 5:
                print(f"    {self._color(f'... and {len(issues) - 5} more', 'dim')}")

    def overall_summary(
        self,
        total: int,
        passed: int,
        failed: int,
        total_duration_ms: float,
    ) -> None:
        print(f"\n{'=' * 50}")
        print(f"{self._color('Summary', 'bold')}")
        passed_str = self._color(f"Passed: {passed}", "green")
        failed_str = self._color(f"Failed: {failed}", "red")
        print(f"  Total: {total} | {passed_str} | {failed_str}")
        print(f"  Duration: {total_duration_ms / 1000:.2f}s")

        if failed == 0:
            print(f"\n{self._color('All journeys passed!', 'green')}")


def create_output(config: ProgressConfig | None = None) -> CLIOutput:
    return CLIOutput(config)
