"""Benchmarking utilities for VenomQA performance analysis.

This module provides comprehensive benchmarking capabilities including:
- Journey and step execution timing
- Throughput measurement (steps/second, journeys/minute)
- Memory usage tracking
- Detailed performance profiling
- Export to various formats for analysis

Example:
    >>> from venomqa.performance import Benchmarker, BenchmarkConfig
    >>>
    >>> config = BenchmarkConfig(
    ...     iterations=100,
    ...     warmup_iterations=10,
    ...     track_memory=True,
    ... )
    >>> benchmarker = Benchmarker(config)
    >>> result = benchmarker.run(journey, runner_factory)
    >>> print(result.get_summary())
"""

from __future__ import annotations

import gc
import json
import logging
import statistics
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from venomqa.core.models import Journey, JourneyResult

logger = logging.getLogger(__name__)


class BenchmarkMetric(Enum):
    """Types of metrics collected during benchmarking."""

    DURATION_MS = "duration_ms"
    STEPS_PER_SECOND = "steps_per_second"
    JOURNEYS_PER_MINUTE = "journeys_per_minute"
    MEMORY_MB = "memory_mb"
    SUCCESS_RATE = "success_rate"


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark runs.

    Attributes:
        iterations: Number of iterations to run (excluding warmup).
        warmup_iterations: Number of warmup iterations (not counted).
        track_memory: Whether to track memory usage.
        collect_gc_stats: Whether to collect garbage collection stats.
        timeout_per_iteration: Maximum time per iteration in seconds.
        parallel_workers: Number of parallel workers (1 = sequential).
        verbose: Whether to log detailed progress.
    """

    iterations: int = 100
    warmup_iterations: int = 10
    track_memory: bool = False
    collect_gc_stats: bool = False
    timeout_per_iteration: float | None = None
    parallel_workers: int = 1
    verbose: bool = False

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.iterations < 1:
            raise ValueError(f"iterations must be >= 1, got {self.iterations}")
        if self.warmup_iterations < 0:
            raise ValueError(f"warmup_iterations must be >= 0, got {self.warmup_iterations}")
        if self.parallel_workers < 1:
            raise ValueError(f"parallel_workers must be >= 1, got {self.parallel_workers}")


@dataclass
class IterationResult:
    """Result of a single benchmark iteration.

    Attributes:
        iteration: Iteration number (0-based).
        duration_ms: Duration of this iteration in milliseconds.
        success: Whether the iteration succeeded.
        steps_executed: Number of steps executed.
        memory_mb: Memory usage at end of iteration (if tracked).
        error: Error message if iteration failed.
    """

    iteration: int
    duration_ms: float
    success: bool
    steps_executed: int = 0
    memory_mb: float | None = None
    error: str | None = None


@dataclass
class BenchmarkResult:
    """Complete benchmark result with statistics.

    Attributes:
        config: Configuration used for this benchmark.
        journey_name: Name of the benchmarked journey.
        started_at: When the benchmark started.
        finished_at: When the benchmark completed.
        total_duration_ms: Total benchmark duration in milliseconds.
        iterations: List of individual iteration results.
        warmup_iterations: Number of warmup iterations run.
        gc_stats: Garbage collection statistics (if collected).
    """

    config: BenchmarkConfig
    journey_name: str
    started_at: datetime
    finished_at: datetime
    total_duration_ms: float
    iterations: list[IterationResult] = field(default_factory=list)
    warmup_iterations: int = 0
    gc_stats: dict[str, Any] = field(default_factory=dict)

    @property
    def successful_iterations(self) -> list[IterationResult]:
        """Get only successful iterations."""
        return [i for i in self.iterations if i.success]

    @property
    def failed_iterations(self) -> list[IterationResult]:
        """Get only failed iterations."""
        return [i for i in self.iterations if not i.success]

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if not self.iterations:
            return 0.0
        return (len(self.successful_iterations) / len(self.iterations)) * 100

    @property
    def durations(self) -> list[float]:
        """Get list of durations from successful iterations."""
        return [i.duration_ms for i in self.successful_iterations]

    @property
    def avg_duration_ms(self) -> float:
        """Calculate average duration in milliseconds."""
        durations = self.durations
        if not durations:
            return 0.0
        return statistics.mean(durations)

    @property
    def min_duration_ms(self) -> float:
        """Get minimum duration in milliseconds."""
        durations = self.durations
        if not durations:
            return 0.0
        return min(durations)

    @property
    def max_duration_ms(self) -> float:
        """Get maximum duration in milliseconds."""
        durations = self.durations
        if not durations:
            return 0.0
        return max(durations)

    @property
    def std_dev_ms(self) -> float:
        """Calculate standard deviation of durations."""
        durations = self.durations
        if len(durations) < 2:
            return 0.0
        return statistics.stdev(durations)

    @property
    def median_duration_ms(self) -> float:
        """Get median duration in milliseconds."""
        durations = self.durations
        if not durations:
            return 0.0
        return statistics.median(durations)

    def percentile(self, p: float) -> float:
        """Calculate a specific percentile of durations.

        Args:
            p: Percentile value (0-100).

        Returns:
            Duration at the given percentile in milliseconds.
        """
        durations = sorted(self.durations)
        if not durations:
            return 0.0
        idx = int(len(durations) * p / 100)
        idx = min(idx, len(durations) - 1)
        return durations[idx]

    @property
    def p50_ms(self) -> float:
        """Get 50th percentile (median) duration."""
        return self.percentile(50)

    @property
    def p90_ms(self) -> float:
        """Get 90th percentile duration."""
        return self.percentile(90)

    @property
    def p95_ms(self) -> float:
        """Get 95th percentile duration."""
        return self.percentile(95)

    @property
    def p99_ms(self) -> float:
        """Get 99th percentile duration."""
        return self.percentile(99)

    @property
    def steps_per_second(self) -> float:
        """Calculate average steps executed per second."""
        successful = self.successful_iterations
        if not successful:
            return 0.0
        total_steps = sum(i.steps_executed for i in successful)
        total_duration_s = sum(i.duration_ms for i in successful) / 1000
        if total_duration_s == 0:
            return 0.0
        return total_steps / total_duration_s

    @property
    def journeys_per_minute(self) -> float:
        """Calculate journeys executed per minute."""
        durations = self.durations
        if not durations:
            return 0.0
        avg_duration_s = self.avg_duration_ms / 1000
        if avg_duration_s == 0:
            return 0.0
        return 60 / avg_duration_s

    @property
    def throughput_rps(self) -> float:
        """Calculate throughput in requests (journeys) per second."""
        durations = self.durations
        if not durations:
            return 0.0
        avg_duration_s = self.avg_duration_ms / 1000
        if avg_duration_s == 0:
            return 0.0
        return 1 / avg_duration_s

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for serialization.

        Returns:
            Dictionary with all benchmark metrics.
        """
        return {
            "journey_name": self.journey_name,
            "config": {
                "iterations": self.config.iterations,
                "warmup_iterations": self.config.warmup_iterations,
                "parallel_workers": self.config.parallel_workers,
            },
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "total_duration_ms": round(self.total_duration_ms, 2),
            "metrics": {
                "iterations_total": len(self.iterations),
                "iterations_success": len(self.successful_iterations),
                "iterations_failed": len(self.failed_iterations),
                "success_rate_pct": round(self.success_rate, 2),
                "avg_duration_ms": round(self.avg_duration_ms, 2),
                "min_duration_ms": round(self.min_duration_ms, 2),
                "max_duration_ms": round(self.max_duration_ms, 2),
                "std_dev_ms": round(self.std_dev_ms, 2),
                "median_duration_ms": round(self.median_duration_ms, 2),
                "p50_ms": round(self.p50_ms, 2),
                "p90_ms": round(self.p90_ms, 2),
                "p95_ms": round(self.p95_ms, 2),
                "p99_ms": round(self.p99_ms, 2),
                "steps_per_second": round(self.steps_per_second, 2),
                "journeys_per_minute": round(self.journeys_per_minute, 2),
                "throughput_rps": round(self.throughput_rps, 4),
            },
            "gc_stats": self.gc_stats,
        }

    def get_summary(self) -> str:
        """Get a human-readable summary of the benchmark.

        Returns:
            Formatted summary string.
        """
        lines = [
            "=" * 60,
            f"Benchmark Results: {self.journey_name}",
            "=" * 60,
            "",
            "Configuration:",
            f"  Iterations: {self.config.iterations} (+ {self.config.warmup_iterations} warmup)",
            f"  Parallel workers: {self.config.parallel_workers}",
            "",
            "Summary:",
            f"  Total time: {self.total_duration_ms:.2f}ms ({self.total_duration_ms/1000:.2f}s)",
            f"  Success rate: {self.success_rate:.1f}%",
            "",
            "Latency (ms):",
            f"  Min:    {self.min_duration_ms:>10.2f}",
            f"  Avg:    {self.avg_duration_ms:>10.2f}",
            f"  Max:    {self.max_duration_ms:>10.2f}",
            f"  StdDev: {self.std_dev_ms:>10.2f}",
            "",
            "Percentiles (ms):",
            f"  p50:    {self.p50_ms:>10.2f}",
            f"  p90:    {self.p90_ms:>10.2f}",
            f"  p95:    {self.p95_ms:>10.2f}",
            f"  p99:    {self.p99_ms:>10.2f}",
            "",
            "Throughput:",
            f"  Steps/second:     {self.steps_per_second:>10.2f}",
            f"  Journeys/minute:  {self.journeys_per_minute:>10.2f}",
            f"  Requests/second:  {self.throughput_rps:>10.4f}",
            "=" * 60,
        ]
        return "\n".join(lines)

    def to_json(self, indent: int = 2) -> str:
        """Export result as JSON string.

        Args:
            indent: JSON indentation level.

        Returns:
            JSON-formatted string.
        """
        return json.dumps(self.to_dict(), indent=indent)

    def to_csv_row(self) -> str:
        """Export result as a CSV row.

        Returns:
            Comma-separated values string.
        """
        d = self.to_dict()
        metrics = d["metrics"]
        return ",".join([
            d["journey_name"],
            str(metrics["iterations_total"]),
            str(metrics["success_rate_pct"]),
            str(metrics["avg_duration_ms"]),
            str(metrics["min_duration_ms"]),
            str(metrics["max_duration_ms"]),
            str(metrics["p50_ms"]),
            str(metrics["p95_ms"]),
            str(metrics["p99_ms"]),
            str(metrics["steps_per_second"]),
            str(metrics["journeys_per_minute"]),
        ])

    @staticmethod
    def csv_header() -> str:
        """Get CSV header for benchmark results."""
        return (
            "journey_name,iterations,success_rate_pct,avg_ms,min_ms,max_ms,"
            "p50_ms,p95_ms,p99_ms,steps_per_sec,journeys_per_min"
        )


RunnerFactory = Callable[[], Any]
ProgressCallback = Callable[[int, int, float], None]


class Benchmarker:
    """Execute benchmarks against journeys with detailed metrics.

    Provides comprehensive benchmarking with warmup, iteration tracking,
    memory profiling, and statistical analysis.

    Attributes:
        config: Benchmark configuration.

    Example:
        >>> benchmarker = Benchmarker(BenchmarkConfig(iterations=50))
        >>> result = benchmarker.run(my_journey, lambda: JourneyRunner(client))
        >>> print(result.get_summary())
    """

    def __init__(
        self,
        config: BenchmarkConfig | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """Initialize the benchmarker.

        Args:
            config: Benchmark configuration. Uses defaults if not provided.
            progress_callback: Optional callback(iteration, total, duration_ms).
        """
        self.config = config or BenchmarkConfig()
        self.progress_callback = progress_callback
        self._stop_event = threading.Event()

    def run(
        self,
        journey: Journey,
        runner_factory: RunnerFactory,
    ) -> BenchmarkResult:
        """Execute the benchmark.

        Runs warmup iterations, then measured iterations, collecting
        detailed metrics throughout.

        Args:
            journey: The journey to benchmark.
            runner_factory: Factory function to create runner instances.

        Returns:
            BenchmarkResult with all collected metrics.
        """
        self._stop_event.clear()
        started_at = datetime.now()

        logger.info(
            f"Starting benchmark: {journey.name} with {self.config.iterations} iterations "
            f"(+ {self.config.warmup_iterations} warmup)"
        )

        # Collect initial GC stats if enabled
        gc_stats_before = {}
        if self.config.collect_gc_stats:
            gc.collect()
            gc_stats_before = {
                "collections": list(gc.get_count()),
                "threshold": list(gc.get_threshold()),
            }

        # Run warmup iterations
        for i in range(self.config.warmup_iterations):
            if self._stop_event.is_set():
                break
            if self.config.verbose:
                logger.debug(f"Warmup iteration {i + 1}/{self.config.warmup_iterations}")
            self._run_single_iteration(journey, runner_factory)

        # Run measured iterations
        iteration_results: list[IterationResult] = []

        for i in range(self.config.iterations):
            if self._stop_event.is_set():
                break

            result = self._run_single_iteration(journey, runner_factory)
            result.iteration = i
            iteration_results.append(result)

            if self.progress_callback:
                self.progress_callback(i + 1, self.config.iterations, result.duration_ms)

            if self.config.verbose:
                logger.debug(
                    f"Iteration {i + 1}/{self.config.iterations}: "
                    f"{result.duration_ms:.2f}ms (success={result.success})"
                )

        finished_at = datetime.now()
        total_duration_ms = (finished_at - started_at).total_seconds() * 1000

        # Collect final GC stats
        gc_stats = {}
        if self.config.collect_gc_stats:
            gc.collect()
            gc_stats = {
                "before": gc_stats_before,
                "after": {
                    "collections": list(gc.get_count()),
                    "threshold": list(gc.get_threshold()),
                },
            }

        result = BenchmarkResult(
            config=self.config,
            journey_name=journey.name,
            started_at=started_at,
            finished_at=finished_at,
            total_duration_ms=total_duration_ms,
            iterations=iteration_results,
            warmup_iterations=self.config.warmup_iterations,
            gc_stats=gc_stats,
        )

        logger.info(f"Benchmark completed: {journey.name}")
        logger.info(f"  Avg: {result.avg_duration_ms:.2f}ms, P99: {result.p99_ms:.2f}ms")
        logger.info(f"  Throughput: {result.journeys_per_minute:.2f} journeys/min")

        return result

    def _run_single_iteration(
        self,
        journey: Journey,
        runner_factory: RunnerFactory,
    ) -> IterationResult:
        """Run a single benchmark iteration.

        Args:
            journey: Journey to execute.
            runner_factory: Factory to create runner.

        Returns:
            IterationResult for this iteration.
        """
        if self.config.track_memory:
            try:
                import tracemalloc
                tracemalloc.start()
                tracemalloc.get_traced_memory()[0]
            except ImportError:
                pass

        start_time = time.perf_counter()
        success = True
        error = None
        steps_executed = 0
        journey_result: JourneyResult | None = None

        try:
            runner = runner_factory()
            journey_result = runner.run(journey)
            success = journey_result.success
            steps_executed = journey_result.total_steps
        except Exception as e:
            success = False
            error = str(e)
            logger.warning(f"Benchmark iteration failed: {e}")

        duration_ms = (time.perf_counter() - start_time) * 1000

        memory_mb = None
        if self.config.track_memory:
            try:
                import tracemalloc
                current, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                memory_mb = current / (1024 * 1024)
            except ImportError:
                pass

        return IterationResult(
            iteration=0,  # Will be set by caller
            duration_ms=duration_ms,
            success=success,
            steps_executed=steps_executed,
            memory_mb=memory_mb,
            error=error,
        )

    def stop(self) -> None:
        """Stop the benchmark early."""
        self._stop_event.set()
        logger.info("Benchmark stop requested")


def run_benchmark(
    journey: Journey,
    runner_factory: RunnerFactory,
    iterations: int = 100,
    warmup: int = 10,
) -> BenchmarkResult:
    """Convenience function to run a quick benchmark.

    Args:
        journey: Journey to benchmark.
        runner_factory: Factory to create runner instances.
        iterations: Number of iterations to run.
        warmup: Number of warmup iterations.

    Returns:
        BenchmarkResult with all metrics.
    """
    config = BenchmarkConfig(
        iterations=iterations,
        warmup_iterations=warmup,
    )
    benchmarker = Benchmarker(config)
    return benchmarker.run(journey, runner_factory)


def compare_benchmarks(
    results: list[BenchmarkResult],
) -> dict[str, Any]:
    """Compare multiple benchmark results.

    Args:
        results: List of benchmark results to compare.

    Returns:
        Dictionary with comparison metrics.
    """
    if not results:
        return {"error": "No results to compare"}

    comparison = {
        "count": len(results),
        "journeys": [],
        "fastest": None,
        "slowest": None,
    }

    fastest_avg = float("inf")
    slowest_avg = 0.0

    for result in results:
        entry = {
            "name": result.journey_name,
            "iterations": len(result.iterations),
            "avg_ms": result.avg_duration_ms,
            "p99_ms": result.p99_ms,
            "steps_per_sec": result.steps_per_second,
        }
        comparison["journeys"].append(entry)

        if result.avg_duration_ms < fastest_avg:
            fastest_avg = result.avg_duration_ms
            comparison["fastest"] = result.journey_name

        if result.avg_duration_ms > slowest_avg:
            slowest_avg = result.avg_duration_ms
            comparison["slowest"] = result.journey_name

    return comparison


class BenchmarkSuite:
    """Run benchmarks for multiple journeys and aggregate results.

    Example:
        >>> suite = BenchmarkSuite(BenchmarkConfig(iterations=50))
        >>> suite.add(journey1, runner_factory1)
        >>> suite.add(journey2, runner_factory2)
        >>> results = suite.run_all()
        >>> print(suite.get_report())
    """

    def __init__(self, config: BenchmarkConfig | None = None) -> None:
        """Initialize the benchmark suite.

        Args:
            config: Configuration to use for all benchmarks.
        """
        self.config = config or BenchmarkConfig()
        self._benchmarks: list[tuple[Journey, RunnerFactory]] = []
        self._results: list[BenchmarkResult] = []

    def add(self, journey: Journey, runner_factory: RunnerFactory) -> None:
        """Add a journey to the benchmark suite.

        Args:
            journey: Journey to benchmark.
            runner_factory: Factory to create runner for this journey.
        """
        self._benchmarks.append((journey, runner_factory))

    def run_all(self) -> list[BenchmarkResult]:
        """Run all benchmarks in the suite.

        Returns:
            List of benchmark results.
        """
        self._results = []
        benchmarker = Benchmarker(self.config)

        for journey, factory in self._benchmarks:
            result = benchmarker.run(journey, factory)
            self._results.append(result)

        return self._results

    def get_results(self) -> list[BenchmarkResult]:
        """Get all benchmark results."""
        return self._results.copy()

    def get_comparison(self) -> dict[str, Any]:
        """Get comparison of all benchmark results."""
        return compare_benchmarks(self._results)

    def get_report(self) -> str:
        """Generate a summary report of all benchmarks.

        Returns:
            Formatted report string.
        """
        if not self._results:
            return "No benchmark results. Run benchmarks first."

        lines = [
            "=" * 70,
            "Benchmark Suite Report",
            "=" * 70,
            "",
            f"Total journeys benchmarked: {len(self._results)}",
            f"Iterations per journey: {self.config.iterations}",
            "",
            BenchmarkResult.csv_header(),
        ]

        for result in self._results:
            lines.append(result.to_csv_row())

        lines.append("")

        comparison = self.get_comparison()
        if comparison.get("fastest"):
            lines.append(f"Fastest: {comparison['fastest']}")
        if comparison.get("slowest"):
            lines.append(f"Slowest: {comparison['slowest']}")

        lines.append("=" * 70)

        return "\n".join(lines)

    def export_json(self, filepath: str) -> None:
        """Export all results to a JSON file.

        Args:
            filepath: Path to write the JSON file.
        """
        data = {
            "config": {
                "iterations": self.config.iterations,
                "warmup_iterations": self.config.warmup_iterations,
            },
            "results": [r.to_dict() for r in self._results],
            "comparison": self.get_comparison(),
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Exported benchmark results to {filepath}")

    def export_csv(self, filepath: str) -> None:
        """Export all results to a CSV file.

        Args:
            filepath: Path to write the CSV file.
        """
        lines = [BenchmarkResult.csv_header()]
        for result in self._results:
            lines.append(result.to_csv_row())

        with open(filepath, "w") as f:
            f.write("\n".join(lines))

        logger.info(f"Exported benchmark results to {filepath}")
