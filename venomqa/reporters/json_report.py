"""JSON reporter for structured test output.

Generates machine-readable JSON reports suitable for programmatic consumption,
CI/CD integration, and data analysis. Reports include metadata, summary
statistics, and detailed journey/step/issue information.

Example:
    >>> from venomqa.reporters import JSONReporter
    >>> reporter = JSONReporter(indent=4)
    >>> json_output = reporter.generate(journey_results)
    >>> data = json.loads(json_output)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from venomqa.core.models import (
    BranchResult,
    Issue,
    JourneyResult,
    StepResult,
)
from venomqa.reporters.base import BaseReporter


class JSONReporter(BaseReporter):
    """Generate JSON reports for programmatic consumption.

    Produces structured JSON documents with:
    - Report metadata (version, timestamp)
    - Summary statistics (counts, rates, durations)
    - Complete journey details (steps, branches, issues)
    - Full error context for debugging

    Attributes:
        output_path: Optional default path for saving reports.
        indent: Number of spaces for JSON indentation (default: 2).

    Example:
        >>> reporter = JSONReporter(output_path="reports/test.json", indent=4)
        >>> reporter.save(results)
        PosixPath('reports/test.json')
    """

    @property
    def file_extension(self) -> str:
        """Return the JSON file extension."""
        return ".json"

    def __init__(
        self,
        output_path: str | Path | None = None,
        indent: int = 2,
    ) -> None:
        """Initialize the JSON reporter.

        Args:
            output_path: Default path for saving reports.
            indent: Number of spaces for JSON pretty-printing. Set to None for compact output.
        """
        super().__init__(output_path)
        self.indent = indent

    def generate(self, results: list[JourneyResult]) -> str:
        """Generate a JSON report from journey results.

        Args:
            results: List of JourneyResult objects from test execution.

        Returns:
            JSON-formatted report string.
        """
        report = self._build_report(results)
        return json.dumps(report, indent=self.indent, default=self._json_serializer)

    def _build_report(self, results: list[JourneyResult]) -> dict[str, Any]:
        """Build the complete report dictionary structure.

        Args:
            results: List of JourneyResult objects.

        Returns:
            Dictionary containing report metadata, summary, and journey details.
        """
        return {
            "report": {
                "generated_at": datetime.now().isoformat(),
                "version": "1.0",
            },
            "summary": self._build_summary(results),
            "journeys": [self._serialize_journey(r) for r in results],
        }

    def _build_summary(self, results: list[JourneyResult]) -> dict[str, Any]:
        """Build summary statistics dictionary.

        Calculates aggregate metrics across all journeys including
        pass rates, counts, and total duration.

        Args:
            results: List of JourneyResult objects.

        Returns:
            Dictionary with summary statistics.
        """
        total = len(results)
        passed = sum(1 for r in results if r.success)
        total_steps = sum(r.total_steps for r in results)
        passed_steps = sum(r.passed_steps for r in results)
        total_paths = sum(r.total_paths for r in results)
        passed_paths = sum(r.passed_paths for r in results)
        total_issues = sum(len(r.issues) for r in results)
        total_duration_ms = sum(r.duration_ms for r in results)

        return {
            "total_journeys": total,
            "passed_journeys": passed,
            "failed_journeys": total - passed,
            "total_steps": total_steps,
            "passed_steps": passed_steps,
            "failed_steps": total_steps - passed_steps,
            "total_paths": total_paths,
            "passed_paths": passed_paths,
            "failed_paths": total_paths - passed_paths,
            "total_issues": total_issues,
            "total_duration_ms": total_duration_ms,
            "success_rate": (passed / total * 100) if total > 0 else 100.0,
        }

    def _serialize_journey(self, result: JourneyResult) -> dict[str, Any]:
        """Serialize a single journey result to dictionary format.

        Args:
            result: JourneyResult object to serialize.

        Returns:
            Dictionary representation of the journey result.
        """
        return {
            "journey_name": result.journey_name,
            "success": result.success,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
            "duration_ms": result.duration_ms,
            "total_steps": result.total_steps,
            "passed_steps": result.passed_steps,
            "total_paths": result.total_paths,
            "passed_paths": result.passed_paths,
            "step_results": [self._serialize_step(s) for s in result.step_results],
            "branch_results": [self._serialize_branch(b) for b in result.branch_results],
            "issues": [self._serialize_issue(i) for i in result.issues],
        }

    def _serialize_step(self, step: StepResult) -> dict[str, Any]:
        """Serialize a step result to dictionary format.

        Args:
            step: StepResult object to serialize.

        Returns:
            Dictionary representation of the step result.
        """
        return {
            "step_name": step.step_name,
            "success": step.success,
            "started_at": step.started_at.isoformat(),
            "finished_at": step.finished_at.isoformat(),
            "duration_ms": step.duration_ms,
            "error": step.error,
            "request": step.request,
            "response": step.response,
        }

    def _serialize_branch(self, branch: BranchResult) -> dict[str, Any]:
        """Serialize a branch result to dictionary format.

        Args:
            branch: BranchResult object to serialize.

        Returns:
            Dictionary representation of the branch result.
        """
        return {
            "checkpoint_name": branch.checkpoint_name,
            "all_passed": branch.all_passed,
            "path_results": [
                {
                    "path_name": p.path_name,
                    "success": p.success,
                    "error": p.error,
                    "step_results": [self._serialize_step(s) for s in p.step_results],
                }
                for p in branch.path_results
            ],
        }

    def _serialize_issue(self, issue: Issue) -> dict[str, Any]:
        """Serialize an issue to dictionary format.

        Args:
            issue: Issue object to serialize.

        Returns:
            Dictionary representation of the issue.
        """
        return {
            "journey": issue.journey,
            "path": issue.path,
            "step": issue.step,
            "error": issue.error,
            "severity": issue.severity.value,
            "request": issue.request,
            "response": issue.response,
            "logs": issue.logs,
            "suggestion": issue.suggestion,
            "timestamp": issue.timestamp.isoformat(),
        }

    @staticmethod
    def _json_serializer(obj: Any) -> Any:
        """Custom JSON serializer for non-standard types.

        Handles datetime objects and other types that aren't natively
        JSON-serializable.

        Args:
            obj: Object to serialize.

        Returns:
            JSON-serializable representation of the object.

        Raises:
            TypeError: If the object type cannot be serialized.
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
