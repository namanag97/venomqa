"""Reporter protocol - Interface for formatting exploration results."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from venomqa.exploration import ExplorationResult


@runtime_checkable
class Reporter(Protocol):
    """Protocol for formatting exploration results.

    All reporters implement this protocol, allowing them to be used
    interchangeably. The report method returns a string that can be
    printed, saved to a file, or sent to an external service.

    Example::

        class MyReporter:
            def report(self, result: ExplorationResult) -> str:
                return f"Visited {result.states_visited} states"

        reporter = MyReporter()
        output = reporter.report(result)
        print(output)
        # or
        with open("report.txt", "w") as f:
            f.write(output)

    Built-in reporters:
    - ConsoleReporter: Terminal output with ANSI colors
    - JSONReporter: Machine-readable JSON
    - HTMLTraceReporter: Interactive HTML visualization
    - JUnitReporter: CI-compatible XML
    - MarkdownReporter: Human-readable markdown
    """

    def report(self, result: ExplorationResult) -> str:
        """Format the exploration result as a string.

        Args:
            result: The exploration result to format.

        Returns:
            Formatted string representation of the result.
        """
        ...


__all__ = ["Reporter"]
