"""Markdown reporter for documentation output."""

from __future__ import annotations

from io import StringIO

from venomqa.v1.core.result import ExplorationResult
from venomqa.v1.core.invariant import Severity


class MarkdownReporter:
    """Formats ExplorationResult as Markdown."""

    def report(self, result: ExplorationResult) -> str:
        """Generate Markdown report."""
        out = StringIO()

        out.write("# Exploration Report\n\n")

        # Summary table
        out.write("## Summary\n\n")
        out.write("| Metric | Value |\n")
        out.write("|--------|-------|\n")
        out.write(f"| States visited | {result.states_visited} |\n")
        out.write(f"| Transitions taken | {result.transitions_taken} |\n")
        out.write(f"| Actions available | {result.actions_total} |\n")
        out.write(f"| Coverage | {result.coverage_percent:.1f}% |\n")
        out.write(f"| Duration | {result.duration_ms:.0f}ms |\n")
        out.write(f"| Status | {'PASSED' if result.success else 'FAILED'} |\n")
        out.write("\n")

        # Violations
        if result.violations:
            out.write("## Violations\n\n")
            out.write("| Severity | Invariant | Message |\n")
            out.write("|----------|-----------|----------|\n")
            for v in result.violations:
                out.write(f"| {self._severity_badge(v.severity)} | {v.invariant_name} | {v.message} |\n")
            out.write("\n")

            # Reproduction paths
            out.write("### Reproduction Paths\n\n")
            for i, v in enumerate(result.violations, 1):
                if v.reproduction_path:
                    out.write(f"**Violation {i}: {v.invariant_name}**\n\n")
                    out.write("```\n")
                    for t in v.reproduction_path:
                        out.write(f"{t.action_name}\n")
                    out.write("```\n\n")

        # State graph (Mermaid)
        out.write("## State Graph\n\n")
        out.write("```mermaid\n")
        out.write("stateDiagram-v2\n")
        for t in result.graph.transitions[:50]:  # Limit for readability
            from_label = t.from_state_id[:8]
            to_label = t.to_state_id[:8]
            out.write(f"    {from_label} --> {to_label}: {t.action_name}\n")
        if result.graph.transition_count > 50:
            out.write(f"    note: ... and {result.graph.transition_count - 50} more transitions\n")
        out.write("```\n")

        return out.getvalue()

    def _severity_badge(self, severity: Severity) -> str:
        if severity == Severity.CRITICAL:
            return "**CRITICAL**"
        elif severity == Severity.HIGH:
            return "**HIGH**"
        elif severity == Severity.MEDIUM:
            return "MEDIUM"
        return "LOW"
