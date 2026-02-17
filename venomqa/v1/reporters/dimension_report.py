"""Dimension coverage reporter — text heatmap per dimension axis."""

from __future__ import annotations

import sys
from typing import TextIO

from venomqa.v1.core.coverage import DimensionCoverage


class DimensionCoverageReporter:
    """Renders a ``DimensionCoverage`` report to the terminal.

    Shows per-axis coverage as an ASCII progress bar and lists which
    dimension values have been observed.

    Usage::

        from venomqa.v1.reporters.dimension_report import DimensionCoverageReporter
        from venomqa.v1.core.coverage import DimensionCoverage

        cov = DimensionCoverage.from_hypergraph(agent.hypergraph)
        DimensionCoverageReporter().report(cov)
    """

    BAR_WIDTH = 30
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    BLUE = "\033[94m"
    RESET = "\033[0m"

    def __init__(self, file: TextIO = sys.stdout, color: bool = True) -> None:
        self.file = file
        self.color = color

    def report(self, cov: DimensionCoverage) -> None:
        """Render the coverage report."""
        self._line(self._c("=== Dimension Coverage Report ===", self.BOLD))
        self._line(f"  Total states: {cov.total_states}")
        self._line(f"  Unexplored combos (top-2 dims): {cov.unexplored_combos}")
        self._line("")

        if not cov.axes:
            self._line("  No dimension data collected.")
            return

        for dim, axis in sorted(cov.axes.items()):
            pct = axis.coverage_percent
            bar = self._bar(pct)
            color = self._pct_color(pct)
            known = f"/{axis.total_possible}" if axis.total_possible > 0 else ""
            self._line(
                f"  {self._c(dim, self.BOLD):<22} "
                f"{bar} {self._c(f'{pct:5.1f}%', color)} "
                f"({axis.observed_count}{known} values)"
            )
            values_str = ", ".join(axis.observed_values_str()) or "(none)"
            self._line(f"    {'observed:':<10} {values_str}")
        self._line("")

    # ------------------------------------------------------------------
    # Markdown variant
    # ------------------------------------------------------------------

    def report_markdown(self, cov: DimensionCoverage) -> str:
        """Return the coverage report as a Markdown string."""
        lines: list[str] = [
            "## Dimension Coverage Report",
            "",
            f"- **Total states:** {cov.total_states}",
            f"- **Unexplored combos (top-2 dims):** {cov.unexplored_combos}",
            "",
            "| Dimension | Coverage | Observed | Total | Values |",
            "|-----------|----------|----------|-------|--------|",
        ]
        for dim, axis in sorted(cov.axes.items()):
            known = axis.total_possible if axis.total_possible > 0 else "?"
            values = ", ".join(axis.observed_values_str()) or "(none)"
            lines.append(
                f"| `{dim}` | {axis.coverage_percent:.1f}% | "
                f"{axis.observed_count} | {known} | {values} |"
            )
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _bar(self, pct: float) -> str:
        filled = int(round(pct / 100 * self.BAR_WIDTH))
        bar = "█" * filled + "░" * (self.BAR_WIDTH - filled)
        return f"[{bar}]"

    def _pct_color(self, pct: float) -> str:
        if pct >= 80:
            return self.GREEN
        elif pct >= 40:
            return self.YELLOW
        return self.RED

    def _c(self, text: str, code: str) -> str:
        if self.color:
            return f"{code}{text}{self.RESET}"
        return text

    def _line(self, text: str) -> None:
        print(text, file=self.file)
