"""Timing analyzer plugin for VenomQA.

This plugin analyzes step execution times and identifies performance
issues like slow steps, regressions, and outliers.

Configuration:
    ```yaml
    plugins:
      - name: venomqa.plugins.examples.timing_analyzer
        config:
          threshold_warning_ms: 1000
          threshold_critical_ms: 5000
          track_percentiles: [50, 90, 95, 99]
          report_slow_steps: true
    ```

Example:
    >>> from venomqa.plugins.examples import TimingAnalyzerPlugin
    >>>
    >>> plugin = TimingAnalyzerPlugin()
    >>> plugin.on_load({"threshold_warning_ms": 500})
    >>>
    >>> # After test execution
    >>> report = plugin.get_timing_report()
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from venomqa.plugins.base import HookPlugin
from venomqa.plugins.types import (
    HookPriority,
    JourneyContext,
    PluginType,
    StepContext,
)

if TYPE_CHECKING:
    from venomqa.core.models import Journey, JourneyResult, Step, StepResult

logger = logging.getLogger(__name__)


@dataclass
class StepTiming:
    """Timing data for a single step execution."""

    journey_name: str
    path_name: str
    step_name: str
    duration_ms: float
    success: bool


@dataclass
class StepTimingStats:
    """Aggregated timing statistics for a step."""

    step_name: str
    execution_count: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    durations: list[float] = field(default_factory=list)
    failures: int = 0

    @property
    def mean_duration_ms(self) -> float:
        """Calculate mean duration."""
        if self.execution_count == 0:
            return 0.0
        return self.total_duration_ms / self.execution_count

    @property
    def median_duration_ms(self) -> float:
        """Calculate median duration."""
        if not self.durations:
            return 0.0
        return statistics.median(self.durations)

    @property
    def stdev_duration_ms(self) -> float:
        """Calculate standard deviation."""
        if len(self.durations) < 2:
            return 0.0
        return statistics.stdev(self.durations)

    def percentile(self, p: float) -> float:
        """Calculate percentile.

        Args:
            p: Percentile (0-100)

        Returns:
            Duration at percentile
        """
        if not self.durations:
            return 0.0
        sorted_durations = sorted(self.durations)
        k = (len(sorted_durations) - 1) * p / 100
        f = int(k)
        c = min(f + 1, len(sorted_durations) - 1)
        return sorted_durations[f] + (k - f) * (sorted_durations[c] - sorted_durations[f])

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate."""
        if self.execution_count == 0:
            return 0.0
        return self.failures / self.execution_count


@dataclass
class JourneyTimingStats:
    """Aggregated timing statistics for a journey."""

    journey_name: str
    execution_count: int = 0
    total_duration_ms: float = 0.0
    durations: list[float] = field(default_factory=list)
    successes: int = 0

    @property
    def mean_duration_ms(self) -> float:
        """Calculate mean duration."""
        if self.execution_count == 0:
            return 0.0
        return self.total_duration_ms / self.execution_count

    @property
    def median_duration_ms(self) -> float:
        """Calculate median duration."""
        if not self.durations:
            return 0.0
        return statistics.median(self.durations)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.execution_count == 0:
            return 0.0
        return self.successes / self.execution_count


class TimingAnalyzerPlugin(HookPlugin):
    """Analyze step and journey timing patterns.

    This plugin collects timing data during test execution and
    provides analysis including:
    - Slow step detection
    - Performance percentiles
    - Regression detection (when baseline provided)
    - Timing reports

    Configuration Options:
        threshold_warning_ms: Warning threshold for slow steps
        threshold_critical_ms: Critical threshold for slow steps
        track_percentiles: Percentiles to track (default: [50, 90, 95, 99])
        report_slow_steps: Log slow steps immediately
        baseline_file: Path to baseline timing file for regression detection
    """

    name = "timing-analyzer"
    version = "1.0.0"
    plugin_type = PluginType.HOOK
    description = "Analyze step execution timing"
    author = "VenomQA Team"
    priority = HookPriority.HIGH  # Run early to capture accurate timing

    def __init__(self) -> None:
        super().__init__()
        self.threshold_warning_ms: float = 1000.0
        self.threshold_critical_ms: float = 5000.0
        self.track_percentiles: list[int] = [50, 90, 95, 99]
        self.report_slow_steps: bool = True
        self.baseline_file: str | None = None

        self._step_timings: list[StepTiming] = []
        self._step_stats: dict[str, StepTimingStats] = defaultdict(
            lambda: StepTimingStats(step_name="")
        )
        self._journey_stats: dict[str, JourneyTimingStats] = defaultdict(
            lambda: JourneyTimingStats(journey_name="")
        )
        self._baseline: dict[str, float] | None = None
        self._slow_steps: list[StepTiming] = []
        self._critical_steps: list[StepTiming] = []

    def on_load(self, config: dict[str, Any]) -> None:
        """Load plugin configuration.

        Args:
            config: Plugin configuration
        """
        super().on_load(config)

        self.threshold_warning_ms = config.get("threshold_warning_ms", 1000.0)
        self.threshold_critical_ms = config.get("threshold_critical_ms", 5000.0)
        self.track_percentiles = config.get("track_percentiles", [50, 90, 95, 99])
        self.report_slow_steps = config.get("report_slow_steps", True)
        self.baseline_file = config.get("baseline_file")

        # Load baseline if provided
        if self.baseline_file:
            self._load_baseline()

    def _load_baseline(self) -> None:
        """Load baseline timing data from file."""
        import json
        from pathlib import Path

        baseline_path = Path(self.baseline_file)
        if not baseline_path.exists():
            self._logger.warning(f"Baseline file not found: {self.baseline_file}")
            return

        try:
            with open(baseline_path) as f:
                self._baseline = json.load(f)
            self._logger.info(f"Loaded baseline with {len(self._baseline)} steps")
        except Exception as e:
            self._logger.error(f"Failed to load baseline: {e}")

    def on_step_complete(
        self,
        step: Step,
        result: StepResult,
        context: StepContext,
    ) -> None:
        """Record step timing.

        Args:
            step: The completed step
            result: Step result
            context: Step context
        """
        timing = StepTiming(
            journey_name=context.journey_name,
            path_name=context.path_name,
            step_name=step.name,
            duration_ms=result.duration_ms,
            success=result.success,
        )

        self._step_timings.append(timing)

        # Update stats
        stats = self._step_stats[step.name]
        stats.step_name = step.name
        stats.execution_count += 1
        stats.total_duration_ms += result.duration_ms
        stats.min_duration_ms = min(stats.min_duration_ms, result.duration_ms)
        stats.max_duration_ms = max(stats.max_duration_ms, result.duration_ms)
        stats.durations.append(result.duration_ms)
        if not result.success:
            stats.failures += 1

        # Check for slow steps
        if result.duration_ms >= self.threshold_critical_ms:
            self._critical_steps.append(timing)
            if self.report_slow_steps:
                self._logger.error(
                    f"CRITICAL: Step '{step.name}' took {result.duration_ms:.0f}ms "
                    f"(threshold: {self.threshold_critical_ms}ms)"
                )
        elif result.duration_ms >= self.threshold_warning_ms:
            self._slow_steps.append(timing)
            if self.report_slow_steps:
                self._logger.warning(
                    f"SLOW: Step '{step.name}' took {result.duration_ms:.0f}ms "
                    f"(threshold: {self.threshold_warning_ms}ms)"
                )

        # Check for regression against baseline
        if self._baseline and step.name in self._baseline:
            baseline_ms = self._baseline[step.name]
            if result.duration_ms > baseline_ms * 1.5:  # 50% slower than baseline
                self._logger.warning(
                    f"REGRESSION: Step '{step.name}' is {result.duration_ms / baseline_ms:.1f}x "
                    f"slower than baseline ({result.duration_ms:.0f}ms vs {baseline_ms:.0f}ms)"
                )

    def on_journey_complete(
        self,
        journey: Journey,
        result: JourneyResult,
        context: JourneyContext,
    ) -> None:
        """Record journey timing.

        Args:
            journey: The completed journey
            result: Journey result
            context: Journey context
        """
        stats = self._journey_stats[journey.name]
        stats.journey_name = journey.name
        stats.execution_count += 1
        stats.total_duration_ms += result.duration_ms
        stats.durations.append(result.duration_ms)
        if result.success:
            stats.successes += 1

    def get_timing_report(self) -> dict[str, Any]:
        """Generate timing analysis report.

        Returns:
            Dictionary with timing analysis
        """
        step_reports = {}
        for step_name, stats in self._step_stats.items():
            percentiles = {
                f"p{p}": stats.percentile(p) for p in self.track_percentiles
            }
            step_reports[step_name] = {
                "execution_count": stats.execution_count,
                "mean_ms": round(stats.mean_duration_ms, 2),
                "median_ms": round(stats.median_duration_ms, 2),
                "min_ms": round(stats.min_duration_ms, 2),
                "max_ms": round(stats.max_duration_ms, 2),
                "stdev_ms": round(stats.stdev_duration_ms, 2),
                "failure_rate": round(stats.failure_rate, 4),
                "percentiles": {k: round(v, 2) for k, v in percentiles.items()},
            }

        journey_reports = {}
        for journey_name, stats in self._journey_stats.items():
            journey_reports[journey_name] = {
                "execution_count": stats.execution_count,
                "mean_ms": round(stats.mean_duration_ms, 2),
                "median_ms": round(stats.median_duration_ms, 2),
                "success_rate": round(stats.success_rate, 4),
            }

        return {
            "summary": {
                "total_steps": len(self._step_timings),
                "unique_steps": len(self._step_stats),
                "slow_steps": len(self._slow_steps),
                "critical_steps": len(self._critical_steps),
                "total_journeys": sum(s.execution_count for s in self._journey_stats.values()),
            },
            "slow_steps": [
                {
                    "step": t.step_name,
                    "journey": t.journey_name,
                    "duration_ms": round(t.duration_ms, 2),
                }
                for t in self._slow_steps
            ],
            "critical_steps": [
                {
                    "step": t.step_name,
                    "journey": t.journey_name,
                    "duration_ms": round(t.duration_ms, 2),
                }
                for t in self._critical_steps
            ],
            "steps": step_reports,
            "journeys": journey_reports,
        }

    def get_baseline_data(self) -> dict[str, float]:
        """Get current step timings as baseline data.

        Use this to generate a baseline file for regression detection.

        Returns:
            Dictionary mapping step names to median durations
        """
        return {
            step_name: stats.median_duration_ms
            for step_name, stats in self._step_stats.items()
        }

    def save_baseline(self, filepath: str) -> None:
        """Save current timings as baseline file.

        Args:
            filepath: Path to save baseline data
        """
        import json
        from pathlib import Path

        baseline = self.get_baseline_data()
        Path(filepath).write_text(json.dumps(baseline, indent=2))
        self._logger.info(f"Saved baseline to {filepath}")

    def get_slowest_steps(self, n: int = 10) -> list[dict[str, Any]]:
        """Get the N slowest steps.

        Args:
            n: Number of steps to return

        Returns:
            List of slowest steps with timing info
        """
        sorted_stats = sorted(
            self._step_stats.values(),
            key=lambda s: s.mean_duration_ms,
            reverse=True,
        )

        return [
            {
                "step": stats.step_name,
                "mean_ms": round(stats.mean_duration_ms, 2),
                "max_ms": round(stats.max_duration_ms, 2),
                "execution_count": stats.execution_count,
            }
            for stats in sorted_stats[:n]
        ]

    def clear(self) -> None:
        """Clear all timing data."""
        self._step_timings.clear()
        self._step_stats.clear()
        self._journey_stats.clear()
        self._slow_steps.clear()
        self._critical_steps.clear()


# Allow direct import as plugin
Plugin = TimingAnalyzerPlugin
plugin = TimingAnalyzerPlugin()
