"""Abstract base reporter class for VenomQA.

This module provides the base class that all reporters must inherit from.
Reporters are responsible for converting JourneyResult objects into various
output formats like Markdown, JSON, JUnit XML, HTML, etc.

Design Pattern:
    The reporters follow the Strategy pattern, allowing different output
    formats to be selected at runtime without changing the core test logic.

Example:
    >>> class CustomReporter(BaseReporter):
    ...     @property
    ...     def file_extension(self) -> str:
    ...         return ".custom"
    ...
    ...     def generate(self, results: list[JourneyResult]) -> str:
    ...         return "custom format output"
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.core.models import JourneyResult


class BaseReporter(ABC):
    """Abstract base class for all VenomQA reporters.

    All reporters must inherit from this class and implement the required
    abstract methods and properties. Reporters convert JourneyResult objects
    into various output formats for different consumers (CI systems, humans,
    monitoring tools, etc.).

    The base class provides:
        - Common interface for all reporters
        - File saving functionality with directory creation
        - Support for both text and binary output formats

    Attributes:
        output_path: Optional default path for saving reports.

    Example:
        >>> reporter = MarkdownReporter()
        >>> report = reporter.generate(journey_results)
        >>> reporter.save(journey_results, path="report.md")
        PosixPath('report.md')

    See Also:
        - MarkdownReporter: Human-readable Markdown reports
        - JSONReporter: Structured JSON output
        - JUnitReporter: JUnit XML for CI/CD integration
        - HTMLReporter: Beautiful HTML reports with charts
    """

    def __init__(self, output_path: str | Path | None = None) -> None:
        """Initialize the reporter with an optional output path.

        Args:
            output_path: Default path where reports will be saved.
                         Can be overridden when calling save().
                         Accepts both string paths and Path objects.

        Example:
            >>> reporter = MarkdownReporter(output_path="reports/test.md")
            >>> reporter = JSONReporter(output_path=Path("reports/test.json"))
        """
        self.output_path = Path(output_path) if output_path else None

    @abstractmethod
    def generate(self, results: list[JourneyResult]) -> str | dict[str, Any] | bytes:
        """Generate a report from journey results.

        This method must be implemented by all subclasses to produce
        the report content in the appropriate format.

        Args:
            results: List of JourneyResult objects from test execution.
                     May be empty if no tests were run.

        Returns:
            The generated report content. Return types vary by reporter:
            - str: Text-based formats (Markdown, XML, HTML)
            - dict[str, Any]: Structured data (will be JSON serialized)
            - bytes: Binary formats

        Note:
            Implementations should handle empty results gracefully and
            produce a valid report even with no data.
        """
        ...

    def save(self, results: list[JourneyResult], path: str | Path | None = None) -> Path:
        """Save the generated report to a file.

        Creates parent directories if they don't exist. Uses the output_path
        from constructor if no path is provided.

        Args:
            results: List of JourneyResult objects to generate report from.
            path: Optional path to save the report. Uses output_path if not provided.

        Returns:
            Path object pointing to the saved report file.

        Raises:
            ValueError: If no output path is provided and none was set in constructor.

        Example:
            >>> reporter = MarkdownReporter(output_path="reports/")
            >>> saved_path = reporter.save(results, path="reports/test.md")
            >>> print(saved_path)
            reports/test.md

        Note:
            Automatically detects binary vs text output and uses appropriate
            file mode ('wb' vs 'w').
        """
        output_path = Path(path) if path else self.output_path
        if not output_path:
            raise ValueError(
                "Output path required for saving report. "
                "Provide 'path' argument or set 'output_path' in constructor."
            )

        content = self.generate(results)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        mode = "wb" if isinstance(content, bytes) else "w"
        encoding = None if isinstance(content, bytes) else "utf-8"
        with open(output_path, mode, encoding=encoding) as f:
            f.write(content)

        return output_path

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """Return the file extension for this reporter's output format.

        Returns:
            File extension including the dot (e.g., '.md', '.json', '.xml').

        Example:
            >>> MarkdownReporter().file_extension
            '.md'
            >>> JSONReporter().file_extension
            '.json'
        """
        ...

    @staticmethod
    def calculate_timing_stats(durations: list[float]) -> dict[str, float]:
        """Calculate timing statistics from a list of durations.

        Utility method available to all reporters for computing
        aggregate timing statistics.

        Args:
            durations: List of duration values in milliseconds.

        Returns:
            Dictionary containing:
            - total: Sum of all durations
            - min: Minimum duration
            - max: Maximum duration
            - mean: Average duration
            - median: Median duration
            - p95: 95th percentile duration
            - count: Number of samples

        Example:
            >>> BaseReporter.calculate_timing_stats([100, 200, 300, 400, 500])
            {'total': 1500.0, 'min': 100.0, 'max': 500.0, 'mean': 300.0, ...}
        """
        if not durations:
            return {
                "total": 0.0,
                "min": 0.0,
                "max": 0.0,
                "mean": 0.0,
                "median": 0.0,
                "p95": 0.0,
                "count": 0,
            }

        sorted_durations = sorted(durations)
        count = len(sorted_durations)
        total = sum(sorted_durations)

        def percentile(data: list[float], p: float) -> float:
            """Calculate percentile without numpy dependency."""
            if not data:
                return 0.0
            k = (len(data) - 1) * p / 100
            f = int(k)
            c = f + 1 if f + 1 < len(data) else f
            return data[f] + (k - f) * (data[c] - data[f])

        return {
            "total": total,
            "min": sorted_durations[0],
            "max": sorted_durations[-1],
            "mean": total / count,
            "median": sorted_durations[count // 2],
            "p95": percentile(sorted_durations, 95),
            "count": count,
        }
