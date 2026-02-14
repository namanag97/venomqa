"""Comparison reporting and baseline management for VenomQA.

This module provides tools for:
- Saving and loading baseline test runs
- Generating comparison reports in various formats
- Managing API response snapshots
- Analyzing trends over time

Example:
    >>> from venomqa.comparison.report import BaselineManager, TrendAnalyzer
    >>>
    >>> # Save a baseline
    >>> baseline = BaselineManager("./baselines")
    >>> baseline.save(journey_result, "checkout_flow")
    >>>
    >>> # Compare against baseline
    >>> diff = baseline.compare(new_result, "checkout_flow")
    >>> if diff.has_regressions:
    ...     print("Regression detected!")
"""

from __future__ import annotations

import html
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from venomqa.comparison.diff import (
    ChangeType,
    ComparisonResult,
    DiffConfig,
    DiffType,
    JSONDiff,
    RunComparator,
)

if TYPE_CHECKING:
    from venomqa.core.models import JourneyResult


@dataclass
class TrendPoint:
    """A single data point in trend analysis.

    Attributes:
        run_id: Identifier for the run.
        timestamp: When the run was executed.
        pass_rate: Percentage of passed steps.
        total_steps: Total number of steps.
        passed_steps: Number of passed steps.
        failed_steps: Number of failed steps.
        total_duration_ms: Total execution time.
        avg_step_duration_ms: Average step duration.
    """

    run_id: str
    timestamp: datetime
    pass_rate: float
    total_steps: int
    passed_steps: int
    failed_steps: int
    total_duration_ms: float
    avg_step_duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "pass_rate": self.pass_rate,
            "total_steps": self.total_steps,
            "passed_steps": self.passed_steps,
            "failed_steps": self.failed_steps,
            "total_duration_ms": self.total_duration_ms,
            "avg_step_duration_ms": self.avg_step_duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrendPoint:
        """Create from dictionary."""
        return cls(
            run_id=data["run_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            pass_rate=data["pass_rate"],
            total_steps=data["total_steps"],
            passed_steps=data["passed_steps"],
            failed_steps=data["failed_steps"],
            total_duration_ms=data["total_duration_ms"],
            avg_step_duration_ms=data["avg_step_duration_ms"],
        )


@dataclass
class TrendData:
    """Collection of trend data points with analysis.

    Attributes:
        points: List of trend data points.
        journey_name: Name of the journey being tracked.
    """

    points: list[TrendPoint] = field(default_factory=list)
    journey_name: str = ""

    @property
    def latest(self) -> TrendPoint | None:
        """Get the most recent data point."""
        if not self.points:
            return None
        return max(self.points, key=lambda p: p.timestamp)

    @property
    def pass_rate_trend(self) -> str:
        """Determine pass rate trend direction."""
        if len(self.points) < 2:
            return "stable"

        sorted_points = sorted(self.points, key=lambda p: p.timestamp)
        recent = sorted_points[-3:] if len(sorted_points) >= 3 else sorted_points

        if len(recent) < 2:
            return "stable"

        first_rate = recent[0].pass_rate
        last_rate = recent[-1].pass_rate

        if last_rate > first_rate + 5:
            return "improving"
        elif last_rate < first_rate - 5:
            return "degrading"
        return "stable"

    @property
    def timing_trend(self) -> str:
        """Determine timing trend direction."""
        if len(self.points) < 2:
            return "stable"

        sorted_points = sorted(self.points, key=lambda p: p.timestamp)
        recent = sorted_points[-3:] if len(sorted_points) >= 3 else sorted_points

        if len(recent) < 2:
            return "stable"

        first_duration = recent[0].total_duration_ms
        last_duration = recent[-1].total_duration_ms

        percent_change = ((last_duration - first_duration) / first_duration) * 100 if first_duration > 0 else 0

        if percent_change > 10:
            return "slowing"
        elif percent_change < -10:
            return "improving"
        return "stable"

    def average_pass_rate(self, last_n: int | None = None) -> float:
        """Calculate average pass rate over recent runs."""
        if not self.points:
            return 0.0

        points = self.points
        if last_n:
            sorted_points = sorted(points, key=lambda p: p.timestamp, reverse=True)
            points = sorted_points[:last_n]

        return sum(p.pass_rate for p in points) / len(points)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "journey_name": self.journey_name,
            "points": [p.to_dict() for p in self.points],
            "pass_rate_trend": self.pass_rate_trend,
            "timing_trend": self.timing_trend,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrendData:
        """Create from dictionary."""
        return cls(
            journey_name=data.get("journey_name", ""),
            points=[TrendPoint.from_dict(p) for p in data.get("points", [])],
        )


class TrendAnalyzer:
    """Analyzes test results over time for trends.

    Tracks pass rates, timing, and detects degradation patterns.

    Example:
        >>> analyzer = TrendAnalyzer("./trends")
        >>> analyzer.record(journey_result, "run-123")
        >>> trend = analyzer.get_trend("checkout_flow")
        >>> if trend.pass_rate_trend == "degrading":
        ...     print("Pass rate is declining!")
    """

    def __init__(
        self,
        data_dir: str | Path,
        max_history: int = 100,
        degradation_threshold: float = 10.0,
    ) -> None:
        """Initialize the trend analyzer.

        Args:
            data_dir: Directory to store trend data.
            max_history: Maximum number of data points to keep.
            degradation_threshold: Percentage threshold for alerting.
        """
        self.data_dir = Path(data_dir)
        self.max_history = max_history
        self.degradation_threshold = degradation_threshold
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        results: list[JourneyResult] | JourneyResult,
        run_id: str,
    ) -> None:
        """Record results for trend tracking.

        Args:
            results: Journey results to record.
            run_id: Unique identifier for this run.
        """
        if not isinstance(results, list):
            results = [results]

        for result in results:
            self._record_journey(result, run_id)

    def _record_journey(self, result: JourneyResult, run_id: str) -> None:
        """Record a single journey result."""
        trend = self.get_trend(result.journey_name)

        # Calculate stats
        total_steps = result.total_steps
        passed_steps = result.passed_steps
        pass_rate = (passed_steps / total_steps * 100) if total_steps > 0 else 100.0
        avg_duration = result.duration_ms / total_steps if total_steps > 0 else 0.0

        point = TrendPoint(
            run_id=run_id,
            timestamp=result.finished_at,
            pass_rate=pass_rate,
            total_steps=total_steps,
            passed_steps=passed_steps,
            failed_steps=total_steps - passed_steps,
            total_duration_ms=result.duration_ms,
            avg_step_duration_ms=avg_duration,
        )

        trend.points.append(point)
        trend.journey_name = result.journey_name

        # Trim old data
        if len(trend.points) > self.max_history:
            trend.points = sorted(
                trend.points,
                key=lambda p: p.timestamp,
                reverse=True,
            )[:self.max_history]

        self._save_trend(trend)

    def get_trend(self, journey_name: str) -> TrendData:
        """Get trend data for a journey.

        Args:
            journey_name: Name of the journey.

        Returns:
            TrendData with historical points.
        """
        file_path = self._trend_file(journey_name)

        if not file_path.exists():
            return TrendData(journey_name=journey_name)

        with open(file_path) as f:
            data = json.load(f)
            return TrendData.from_dict(data)

    def _trend_file(self, journey_name: str) -> Path:
        """Get the file path for a journey's trend data."""
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in journey_name)
        return self.data_dir / f"{safe_name}_trend.json"

    def _save_trend(self, trend: TrendData) -> None:
        """Save trend data to file."""
        file_path = self._trend_file(trend.journey_name)
        with open(file_path, "w") as f:
            json.dump(trend.to_dict(), f, indent=2)

    def check_degradation(self, journey_name: str) -> dict[str, Any]:
        """Check if a journey is experiencing degradation.

        Args:
            journey_name: Name of the journey to check.

        Returns:
            Dictionary with degradation analysis.
        """
        trend = self.get_trend(journey_name)

        result = {
            "journey_name": journey_name,
            "pass_rate_degrading": False,
            "timing_degrading": False,
            "alerts": [],
        }

        if len(trend.points) < 2:
            return result

        # Check pass rate
        if trend.pass_rate_trend == "degrading":
            result["pass_rate_degrading"] = True
            result["alerts"].append(
                f"Pass rate is declining (trend: {trend.pass_rate_trend})"
            )

        # Check timing
        if trend.timing_trend == "slowing":
            result["timing_degrading"] = True
            result["alerts"].append(
                f"Execution time is increasing (trend: {trend.timing_trend})"
            )

        # Check against threshold
        avg_rate = trend.average_pass_rate(last_n=5)
        latest = trend.latest
        if latest and latest.pass_rate < avg_rate - self.degradation_threshold:
            result["alerts"].append(
                f"Latest pass rate ({latest.pass_rate:.1f}%) is significantly "
                f"below average ({avg_rate:.1f}%)"
            )

        return result

    def get_all_trends(self) -> dict[str, TrendData]:
        """Get trend data for all tracked journeys.

        Returns:
            Dictionary mapping journey names to their trend data.
        """
        trends = {}
        for file_path in self.data_dir.glob("*_trend.json"):
            with open(file_path) as f:
                data = json.load(f)
                trend = TrendData.from_dict(data)
                trends[trend.journey_name] = trend
        return trends


class BaselineManager:
    """Manages baseline test runs for comparison.

    Saves, loads, and compares test results against stored baselines.

    Example:
        >>> baseline = BaselineManager("./baselines")
        >>> baseline.save(result, "checkout_flow")
        >>> diff = baseline.compare(new_result, "checkout_flow")
    """

    def __init__(
        self,
        baselines_dir: str | Path,
        config: DiffConfig | None = None,
    ) -> None:
        """Initialize the baseline manager.

        Args:
            baselines_dir: Directory to store baselines.
            config: Configuration for comparisons.
        """
        self.baselines_dir = Path(baselines_dir)
        self.baselines_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or DiffConfig()
        self.comparator = RunComparator(self.config)

    def save(
        self,
        results: list[JourneyResult] | JourneyResult,
        name: str,
    ) -> Path:
        """Save results as a named baseline.

        Args:
            results: Journey results to save.
            name: Name for the baseline.

        Returns:
            Path to the saved baseline file.
        """
        if not isinstance(results, list):
            results = [results]

        baseline_path = self._baseline_path(name)

        data = {
            "name": name,
            "saved_at": datetime.now().isoformat(),
            "results": [self._serialize_result(r) for r in results],
        }

        with open(baseline_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        return baseline_path

    def load(self, name: str) -> list[dict[str, Any]] | None:
        """Load a saved baseline.

        Args:
            name: Name of the baseline.

        Returns:
            List of serialized journey results, or None if not found.
        """
        baseline_path = self._baseline_path(name)

        if not baseline_path.exists():
            return None

        with open(baseline_path) as f:
            data = json.load(f)
            return data.get("results", [])

    def compare(
        self,
        current_results: list[JourneyResult] | JourneyResult,
        baseline_name: str,
    ) -> ComparisonResult | None:
        """Compare current results against a saved baseline.

        Args:
            current_results: Current journey results.
            baseline_name: Name of the baseline to compare against.

        Returns:
            ComparisonResult, or None if baseline not found.
        """
        baseline_data = self.load(baseline_name)
        if baseline_data is None:
            return None

        # Convert baseline data back to JourneyResult-like objects
        baseline_results = [
            self._deserialize_result(r)
            for r in baseline_data
        ]

        if not isinstance(current_results, list):
            current_results = [current_results]

        return self.comparator.compare(
            baseline_results,
            current_results,
            old_run_id=f"baseline:{baseline_name}",
            new_run_id="current",
        )

    def list_baselines(self) -> list[dict[str, Any]]:
        """List all available baselines.

        Returns:
            List of baseline metadata.
        """
        baselines = []
        for path in self.baselines_dir.glob("*.json"):
            with open(path) as f:
                data = json.load(f)
                baselines.append({
                    "name": data.get("name", path.stem),
                    "saved_at": data.get("saved_at"),
                    "journey_count": len(data.get("results", [])),
                    "path": str(path),
                })
        return baselines

    def delete(self, name: str) -> bool:
        """Delete a baseline.

        Args:
            name: Name of the baseline.

        Returns:
            True if deleted, False if not found.
        """
        baseline_path = self._baseline_path(name)
        if baseline_path.exists():
            baseline_path.unlink()
            return True
        return False

    def _baseline_path(self, name: str) -> Path:
        """Get the file path for a baseline."""
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return self.baselines_dir / f"{safe_name}.json"

    def _serialize_result(self, result: JourneyResult) -> dict[str, Any]:
        """Serialize a JourneyResult to dictionary."""
        return {
            "journey_name": result.journey_name,
            "success": result.success,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
            "duration_ms": result.duration_ms,
            "step_results": [
                {
                    "step_name": s.step_name,
                    "success": s.success,
                    "started_at": s.started_at.isoformat(),
                    "finished_at": s.finished_at.isoformat(),
                    "duration_ms": s.duration_ms,
                    "error": s.error,
                    "request": s.request,
                    "response": s.response,
                }
                for s in result.step_results
            ],
            "branch_results": [
                {
                    "checkpoint_name": b.checkpoint_name,
                    "path_results": [
                        {
                            "path_name": p.path_name,
                            "success": p.success,
                            "error": p.error,
                            "step_results": [
                                {
                                    "step_name": s.step_name,
                                    "success": s.success,
                                    "started_at": s.started_at.isoformat(),
                                    "finished_at": s.finished_at.isoformat(),
                                    "duration_ms": s.duration_ms,
                                    "error": s.error,
                                    "request": s.request,
                                    "response": s.response,
                                }
                                for s in p.step_results
                            ],
                        }
                        for p in b.path_results
                    ],
                }
                for b in result.branch_results
            ],
            "issues": [
                {
                    "journey": i.journey,
                    "path": i.path,
                    "step": i.step,
                    "error": i.error,
                    "severity": i.severity.value,
                }
                for i in result.issues
            ],
        }

    def _deserialize_result(self, data: dict[str, Any]) -> Any:
        """Deserialize dictionary to JourneyResult-like object."""
        # Create a simple object that has the same interface
        from types import SimpleNamespace
        from datetime import datetime

        def parse_step(s: dict[str, Any]) -> SimpleNamespace:
            return SimpleNamespace(
                step_name=s["step_name"],
                success=s["success"],
                started_at=datetime.fromisoformat(s["started_at"]),
                finished_at=datetime.fromisoformat(s["finished_at"]),
                duration_ms=s["duration_ms"],
                error=s.get("error"),
                request=s.get("request"),
                response=s.get("response"),
            )

        def parse_path(p: dict[str, Any]) -> SimpleNamespace:
            return SimpleNamespace(
                path_name=p["path_name"],
                success=p["success"],
                error=p.get("error"),
                step_results=[parse_step(s) for s in p.get("step_results", [])],
            )

        def parse_branch(b: dict[str, Any]) -> SimpleNamespace:
            return SimpleNamespace(
                checkpoint_name=b["checkpoint_name"],
                path_results=[parse_path(p) for p in b.get("path_results", [])],
            )

        step_results = [parse_step(s) for s in data.get("step_results", [])]
        branch_results = [parse_branch(b) for b in data.get("branch_results", [])]

        return SimpleNamespace(
            journey_name=data["journey_name"],
            success=data["success"],
            started_at=datetime.fromisoformat(data["started_at"]),
            finished_at=datetime.fromisoformat(data["finished_at"]),
            duration_ms=data["duration_ms"],
            step_results=step_results,
            branch_results=branch_results,
            total_steps=len(step_results),
            passed_steps=sum(1 for s in step_results if s.success),
            issues=[],
        )


class SnapshotManager:
    """Manages API response snapshots for comparison.

    Saves expected responses and compares actual responses against them.

    Example:
        >>> snapshots = SnapshotManager("./snapshots")
        >>> snapshots.save("get_user", {"id": 1, "name": "Test"})
        >>> result = snapshots.compare("get_user", actual_response)
        >>> if result["matches"]:
        ...     print("Response matches snapshot!")
    """

    def __init__(
        self,
        snapshots_dir: str | Path,
        config: DiffConfig | None = None,
    ) -> None:
        """Initialize the snapshot manager.

        Args:
            snapshots_dir: Directory to store snapshots.
            config: Configuration for comparisons.
        """
        self.snapshots_dir = Path(snapshots_dir)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or DiffConfig()
        self.json_diff = JSONDiff(self.config)

    def save(
        self,
        name: str,
        response: Any,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Save a response as a snapshot.

        Args:
            name: Name for the snapshot.
            response: Response data to save.
            metadata: Optional metadata about the snapshot.

        Returns:
            Path to the saved snapshot file.
        """
        snapshot_path = self._snapshot_path(name)

        data = {
            "name": name,
            "saved_at": datetime.now().isoformat(),
            "metadata": metadata or {},
            "response": response,
        }

        with open(snapshot_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        return snapshot_path

    def load(self, name: str) -> Any | None:
        """Load a saved snapshot.

        Args:
            name: Name of the snapshot.

        Returns:
            The snapshot response data, or None if not found.
        """
        snapshot_path = self._snapshot_path(name)

        if not snapshot_path.exists():
            return None

        with open(snapshot_path) as f:
            data = json.load(f)
            return data.get("response")

    def compare(
        self,
        name: str,
        actual: Any,
    ) -> dict[str, Any]:
        """Compare actual response against saved snapshot.

        Args:
            name: Name of the snapshot.
            actual: Actual response to compare.

        Returns:
            Dictionary with comparison results.
        """
        expected = self.load(name)

        if expected is None:
            return {
                "matches": False,
                "snapshot_exists": False,
                "diffs": [],
                "message": f"Snapshot '{name}' not found",
            }

        diffs = self.json_diff.compare(expected, actual)
        has_changes = any(d.diff_type != DiffType.UNCHANGED for d in diffs)

        return {
            "matches": not has_changes,
            "snapshot_exists": True,
            "diffs": [d.to_dict() for d in diffs if d.diff_type != DiffType.UNCHANGED],
            "expected": expected,
            "actual": actual,
        }

    def update(
        self,
        name: str,
        response: Any,
    ) -> Path:
        """Update an existing snapshot with new response.

        Args:
            name: Name of the snapshot.
            response: New response data.

        Returns:
            Path to the updated snapshot file.
        """
        return self.save(name, response)

    def list_snapshots(self) -> list[dict[str, Any]]:
        """List all available snapshots.

        Returns:
            List of snapshot metadata.
        """
        snapshots = []
        for path in self.snapshots_dir.glob("*.json"):
            with open(path) as f:
                data = json.load(f)
                snapshots.append({
                    "name": data.get("name", path.stem),
                    "saved_at": data.get("saved_at"),
                    "metadata": data.get("metadata", {}),
                    "path": str(path),
                })
        return snapshots

    def delete(self, name: str) -> bool:
        """Delete a snapshot.

        Args:
            name: Name of the snapshot.

        Returns:
            True if deleted, False if not found.
        """
        snapshot_path = self._snapshot_path(name)
        if snapshot_path.exists():
            snapshot_path.unlink()
            return True
        return False

    def _snapshot_path(self, name: str) -> Path:
        """Get the file path for a snapshot."""
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return self.snapshots_dir / f"{safe_name}.snap.json"


class ComparisonReporter:
    """Generates text-based comparison reports.

    Creates human-readable reports summarizing differences between runs.
    """

    def generate(self, comparison: ComparisonResult) -> str:
        """Generate a text comparison report.

        Args:
            comparison: The comparison result to report.

        Returns:
            Formatted text report.
        """
        lines = [
            "=" * 60,
            "VenomQA Comparison Report",
            "=" * 60,
            "",
            f"Baseline Run: {comparison.old_run_id}",
            f"Current Run:  {comparison.new_run_id}",
            f"Compared at:  {comparison.compared_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        # Summary
        lines.append("-" * 40)
        lines.append("SUMMARY")
        lines.append("-" * 40)
        lines.append(f"Regressions (pass -> fail):  {comparison.regression_count}")
        lines.append(f"Improvements (fail -> pass): {comparison.improvement_count}")
        lines.append(f"Added steps:                 {len(comparison.added_steps)}")
        lines.append(f"Removed steps:               {len(comparison.removed_steps)}")
        lines.append(f"Timing changes:              {len(comparison.timing_diffs)}")
        lines.append(f"Response changes:            {len(comparison.response_diffs)}")
        lines.append("")

        # Regressions
        if comparison.has_regressions:
            lines.append("-" * 40)
            lines.append("REGRESSIONS (pass -> fail)")
            lines.append("-" * 40)
            for reg in comparison.get_regressions():
                lines.append(f"  * {reg.journey_name} / {reg.path_name} / {reg.step_name}")
                if reg.new_error:
                    lines.append(f"    Error: {reg.new_error}")
            lines.append("")

        # Improvements
        if comparison.has_improvements:
            lines.append("-" * 40)
            lines.append("IMPROVEMENTS (fail -> pass)")
            lines.append("-" * 40)
            for imp in comparison.get_improvements():
                lines.append(f"  * {imp.journey_name} / {imp.path_name} / {imp.step_name}")
                if imp.old_error:
                    lines.append(f"    (Was: {imp.old_error})")
            lines.append("")

        # Added/Removed steps
        if comparison.added_steps:
            lines.append("-" * 40)
            lines.append("ADDED STEPS")
            lines.append("-" * 40)
            for step in comparison.added_steps:
                lines.append(f"  + {step}")
            lines.append("")

        if comparison.removed_steps:
            lines.append("-" * 40)
            lines.append("REMOVED STEPS")
            lines.append("-" * 40)
            for step in comparison.removed_steps:
                lines.append(f"  - {step}")
            lines.append("")

        # Significant timing changes
        sig_timing = [t for t in comparison.timing_diffs if t.is_significant]
        if sig_timing:
            lines.append("-" * 40)
            lines.append("SIGNIFICANT TIMING CHANGES")
            lines.append("-" * 40)
            for timing in sig_timing:
                direction = "slower" if timing.diff_ms > 0 else "faster"
                lines.append(
                    f"  * {timing.step_name}: "
                    f"{timing.old_duration_ms:.0f}ms -> {timing.new_duration_ms:.0f}ms "
                    f"({timing.diff_percent:+.1f}% {direction})"
                )
            lines.append("")

        # Response changes
        if comparison.response_diffs:
            lines.append("-" * 40)
            lines.append("RESPONSE CHANGES")
            lines.append("-" * 40)
            for resp in comparison.response_diffs:
                if resp.has_changes:
                    lines.append(f"  * {resp.step_name}")
                    if resp.status_code_changed:
                        lines.append(
                            f"    Status: {resp.old_status_code} -> {resp.new_status_code}"
                        )
                    if resp.body_diffs:
                        lines.append(f"    Body changes: {len(resp.body_diffs)}")
                        for diff in resp.body_diffs[:5]:  # Limit to first 5
                            lines.append(
                                f"      - {diff.path}: {diff.diff_type.value}"
                            )
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)


class ComparisonHTMLReporter:
    """Generates HTML comparison reports with visual diff.

    Creates interactive HTML reports with side-by-side comparison,
    diff highlighting, and collapsible sections.
    """

    def generate(self, comparison: ComparisonResult) -> str:
        """Generate an HTML comparison report.

        Args:
            comparison: The comparison result to report.

        Returns:
            Complete HTML document.
        """
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VenomQA Comparison Report</title>
    <style>
        {self._get_styles()}
    </style>
</head>
<body>
    <div class="container">
        {self._render_header(comparison)}
        {self._render_summary(comparison)}
        {self._render_regressions(comparison)}
        {self._render_improvements(comparison)}
        {self._render_added_removed(comparison)}
        {self._render_timing_changes(comparison)}
        {self._render_response_changes(comparison)}
    </div>
    <script>
        {self._get_javascript()}
    </script>
</body>
</html>"""

    def _get_styles(self) -> str:
        """Get CSS styles for the report."""
        return """
        :root {
            --primary: #6366f1;
            --success: #22c55e;
            --danger: #ef4444;
            --warning: #f59e0b;
            --info: #3b82f6;
            --dark: #1f2937;
            --light: #f3f4f6;
            --border: #e5e7eb;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--light);
            color: var(--dark);
            line-height: 1.6;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        .header {
            background: linear-gradient(135deg, var(--primary), #4f46e5);
            color: white;
            padding: 2rem;
            border-radius: 1rem;
            margin-bottom: 2rem;
        }
        .header h1 { font-size: 1.75rem; margin-bottom: 0.5rem; }
        .header .meta { opacity: 0.9; font-size: 0.9rem; }
        .card {
            background: white;
            border-radius: 0.75rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 1.5rem;
            overflow: hidden;
        }
        .card-header {
            background: var(--light);
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
        }
        .card-header:hover { background: var(--border); }
        .card-body { padding: 1.5rem; }
        .card-body.collapsed { display: none; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-bottom: 1rem;
        }
        .stat-card {
            text-align: center;
            padding: 1rem;
            border-radius: 0.5rem;
            background: var(--light);
        }
        .stat-value { font-size: 2rem; font-weight: 700; }
        .stat-label { font-size: 0.8rem; color: #6b7280; text-transform: uppercase; }
        .stat-danger .stat-value { color: var(--danger); }
        .stat-success .stat-value { color: var(--success); }
        .stat-warning .stat-value { color: var(--warning); }
        .stat-info .stat-value { color: var(--info); }
        .badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge-danger { background: #fee2e2; color: #991b1b; }
        .badge-success { background: #dcfce7; color: #166534; }
        .badge-warning { background: #fef3c7; color: #92400e; }
        .badge-info { background: #dbeafe; color: #1e40af; }
        .item {
            padding: 1rem;
            border-bottom: 1px solid var(--border);
        }
        .item:last-child { border-bottom: none; }
        .item-header { font-weight: 600; margin-bottom: 0.5rem; }
        .item-detail { color: #6b7280; font-size: 0.9rem; }
        .diff-added { background: #dcfce7; color: #166534; padding: 0.25rem 0.5rem; border-radius: 0.25rem; }
        .diff-removed { background: #fee2e2; color: #991b1b; padding: 0.25rem 0.5rem; border-radius: 0.25rem; }
        .diff-changed { background: #fef3c7; color: #92400e; padding: 0.25rem 0.5rem; border-radius: 0.25rem; }
        .code {
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.85rem;
            background: #f3f4f6;
            padding: 0.25rem 0.5rem;
            border-radius: 0.25rem;
        }
        .toggle-icon { transition: transform 0.2s; }
        .toggle-icon.collapsed { transform: rotate(-90deg); }
        .empty-state {
            text-align: center;
            padding: 2rem;
            color: #6b7280;
        }
        .side-by-side {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }
        .side-panel {
            background: #f9fafb;
            padding: 1rem;
            border-radius: 0.5rem;
        }
        .side-panel h4 {
            font-size: 0.9rem;
            color: #6b7280;
            margin-bottom: 0.5rem;
        }
        pre {
            background: #282c34;
            color: #abb2bf;
            padding: 1rem;
            border-radius: 0.5rem;
            overflow-x: auto;
            font-size: 0.8rem;
            max-height: 300px;
        }
        @media (max-width: 768px) {
            .container { padding: 1rem; }
            .side-by-side { grid-template-columns: 1fr; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
        }
        """

    def _get_javascript(self) -> str:
        """Get JavaScript for interactivity."""
        return """
        function toggleCard(cardId) {
            const body = document.getElementById(cardId + '-body');
            const icon = document.getElementById(cardId + '-icon');
            body.classList.toggle('collapsed');
            icon.classList.toggle('collapsed');
        }
        """

    def _render_header(self, comparison: ComparisonResult) -> str:
        """Render the report header."""
        status = "has-regressions" if comparison.has_regressions else "clean"
        status_text = "REGRESSIONS DETECTED" if comparison.has_regressions else "NO REGRESSIONS"
        status_color = "#fee2e2" if comparison.has_regressions else "#dcfce7"

        return f"""
        <div class="header">
            <h1>VenomQA Comparison Report</h1>
            <div class="meta">
                <span style="background: {status_color}; color: #1f2937; padding: 0.25rem 0.75rem; border-radius: 9999px; font-weight: 600;">
                    {status_text}
                </span>
            </div>
            <div class="meta" style="margin-top: 1rem;">
                <strong>Baseline:</strong> {html.escape(comparison.old_run_id)} |
                <strong>Current:</strong> {html.escape(comparison.new_run_id)} |
                <strong>Compared:</strong> {comparison.compared_at.strftime("%Y-%m-%d %H:%M:%S")}
            </div>
        </div>
        """

    def _render_summary(self, comparison: ComparisonResult) -> str:
        """Render the summary statistics."""
        return f"""
        <div class="stats-grid">
            <div class="stat-card stat-danger">
                <div class="stat-value">{comparison.regression_count}</div>
                <div class="stat-label">Regressions</div>
            </div>
            <div class="stat-card stat-success">
                <div class="stat-value">{comparison.improvement_count}</div>
                <div class="stat-label">Improvements</div>
            </div>
            <div class="stat-card stat-info">
                <div class="stat-value">{len(comparison.added_steps)}</div>
                <div class="stat-label">Added</div>
            </div>
            <div class="stat-card stat-warning">
                <div class="stat-value">{len(comparison.removed_steps)}</div>
                <div class="stat-label">Removed</div>
            </div>
        </div>
        """

    def _render_regressions(self, comparison: ComparisonResult) -> str:
        """Render regressions section."""
        regressions = comparison.get_regressions()

        if not regressions:
            return ""

        items = []
        for reg in regressions:
            error_html = ""
            if reg.new_error:
                error_html = f'<div class="item-detail"><strong>Error:</strong> <code class="code">{html.escape(reg.new_error)}</code></div>'

            items.append(f"""
            <div class="item">
                <div class="item-header">
                    <span class="badge badge-danger">FAIL</span>
                    {html.escape(reg.journey_name)} / {html.escape(reg.path_name)} / {html.escape(reg.step_name)}
                </div>
                {error_html}
            </div>
            """)

        return f"""
        <div class="card">
            <div class="card-header" onclick="toggleCard('regressions')">
                <span>Regressions (Pass -> Fail) ({len(regressions)})</span>
                <span class="toggle-icon" id="regressions-icon">&#9660;</span>
            </div>
            <div class="card-body" id="regressions-body">
                {"".join(items)}
            </div>
        </div>
        """

    def _render_improvements(self, comparison: ComparisonResult) -> str:
        """Render improvements section."""
        improvements = comparison.get_improvements()

        if not improvements:
            return ""

        items = []
        for imp in improvements:
            old_error = ""
            if imp.old_error:
                old_error = f'<div class="item-detail"><strong>Was:</strong> <code class="code">{html.escape(imp.old_error)}</code></div>'

            items.append(f"""
            <div class="item">
                <div class="item-header">
                    <span class="badge badge-success">PASS</span>
                    {html.escape(imp.journey_name)} / {html.escape(imp.path_name)} / {html.escape(imp.step_name)}
                </div>
                {old_error}
            </div>
            """)

        return f"""
        <div class="card">
            <div class="card-header" onclick="toggleCard('improvements')">
                <span>Improvements (Fail -> Pass) ({len(improvements)})</span>
                <span class="toggle-icon" id="improvements-icon">&#9660;</span>
            </div>
            <div class="card-body" id="improvements-body">
                {"".join(items)}
            </div>
        </div>
        """

    def _render_added_removed(self, comparison: ComparisonResult) -> str:
        """Render added/removed steps section."""
        if not comparison.added_steps and not comparison.removed_steps:
            return ""

        added_items = "\n".join(
            f'<div class="item"><span class="diff-added">+ {html.escape(s)}</span></div>'
            for s in comparison.added_steps
        )
        removed_items = "\n".join(
            f'<div class="item"><span class="diff-removed">- {html.escape(s)}</span></div>'
            for s in comparison.removed_steps
        )

        return f"""
        <div class="card">
            <div class="card-header" onclick="toggleCard('changes')">
                <span>Added / Removed Steps ({len(comparison.added_steps) + len(comparison.removed_steps)})</span>
                <span class="toggle-icon" id="changes-icon">&#9660;</span>
            </div>
            <div class="card-body" id="changes-body">
                <div class="side-by-side">
                    <div class="side-panel">
                        <h4>Added ({len(comparison.added_steps)})</h4>
                        {added_items or '<div class="empty-state">No added steps</div>'}
                    </div>
                    <div class="side-panel">
                        <h4>Removed ({len(comparison.removed_steps)})</h4>
                        {removed_items or '<div class="empty-state">No removed steps</div>'}
                    </div>
                </div>
            </div>
        </div>
        """

    def _render_timing_changes(self, comparison: ComparisonResult) -> str:
        """Render timing changes section."""
        sig_timing = [t for t in comparison.timing_diffs if t.is_significant]

        if not sig_timing:
            return ""

        items = []
        for timing in sig_timing:
            direction = "slower" if timing.diff_ms > 0 else "faster"
            badge_class = "badge-danger" if timing.diff_ms > 0 else "badge-success"
            arrow = "&#8593;" if timing.diff_ms > 0 else "&#8595;"

            items.append(f"""
            <div class="item">
                <div class="item-header">
                    <span class="badge {badge_class}">{arrow} {abs(timing.diff_percent):.1f}%</span>
                    {html.escape(timing.step_name)}
                </div>
                <div class="item-detail">
                    {timing.old_duration_ms:.0f}ms &rarr; {timing.new_duration_ms:.0f}ms
                    ({timing.diff_ms:+.0f}ms {direction})
                </div>
            </div>
            """)

        return f"""
        <div class="card">
            <div class="card-header" onclick="toggleCard('timing')">
                <span>Timing Changes ({len(sig_timing)})</span>
                <span class="toggle-icon" id="timing-icon">&#9660;</span>
            </div>
            <div class="card-body" id="timing-body">
                {"".join(items)}
            </div>
        </div>
        """

    def _render_response_changes(self, comparison: ComparisonResult) -> str:
        """Render response changes section."""
        changes = [r for r in comparison.response_diffs if r.has_changes]

        if not changes:
            return ""

        items = []
        for resp in changes:
            status_html = ""
            if resp.status_code_changed:
                status_html = f"""
                <div class="item-detail">
                    <strong>Status:</strong>
                    <span class="diff-removed">{resp.old_status_code}</span>
                    &rarr;
                    <span class="diff-added">{resp.new_status_code}</span>
                </div>
                """

            diffs_html = ""
            if resp.body_diffs:
                diff_items = []
                for diff in resp.body_diffs[:10]:  # Limit display
                    diff_class = {
                        DiffType.ADDED: "diff-added",
                        DiffType.REMOVED: "diff-removed",
                        DiffType.CHANGED: "diff-changed",
                        DiffType.TYPE_CHANGED: "diff-changed",
                    }.get(diff.diff_type, "")

                    diff_items.append(
                        f'<div><span class="{diff_class}">{diff.diff_type.value}</span> '
                        f'<code class="code">{html.escape(diff.path)}</code></div>'
                    )

                diffs_html = f"""
                <div class="item-detail" style="margin-top: 0.5rem;">
                    <strong>Body changes:</strong>
                    <div style="margin-top: 0.25rem;">{"".join(diff_items)}</div>
                </div>
                """

            items.append(f"""
            <div class="item">
                <div class="item-header">
                    {html.escape(resp.journey_name)} / {html.escape(resp.path_name)} / {html.escape(resp.step_name)}
                </div>
                {status_html}
                {diffs_html}
            </div>
            """)

        return f"""
        <div class="card">
            <div class="card-header" onclick="toggleCard('responses')">
                <span>Response Changes ({len(changes)})</span>
                <span class="toggle-icon" id="responses-icon">&#9660;</span>
            </div>
            <div class="card-body" id="responses-body">
                {"".join(items)}
            </div>
        </div>
        """
