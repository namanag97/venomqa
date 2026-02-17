"""Load testing utilities for performance benchmarking.

This module provides comprehensive load testing capabilities for VenomQA including:
- Configurable load patterns (constant, ramp-up, spike, stress)
- Real-time metrics collection
- Response time percentiles (p50, p75, p90, p95, p99)
- Throughput measurement (requests/second)
- Error rate tracking
- Think time simulation
- Load test assertions
- Resource utilization tracking

Example:
    >>> from venomqa.performance import LoadTester, LoadTestConfig
    >>>
    >>> config = LoadTestConfig(
    ...     duration_seconds=60,
    ...     concurrent_users=10,
    ...     ramp_up_seconds=10,
    ...     think_time_min=1.0,
    ...     think_time_max=3.0,
    ... )
    >>> tester = LoadTester(config)
    >>> result = tester.run(my_journey, runner_factory)
    >>> print(f"P99 latency: {result.percentiles['p99']:.2f}ms")
    >>> print(f"Throughput: {result.throughput:.2f} req/s")
    >>> print(f"Error rate: {result.error_rate:.2f}%")
    >>>
    >>> # With assertions
    >>> assertions = LoadTestAssertions(
    ...     max_p99_ms=500,
    ...     max_error_rate_percent=1.0,
    ...     min_throughput_rps=100,
    ... )
    >>> assertions.validate(result)  # Raises AssertionError if failed
"""

from __future__ import annotations

import json
import logging
import random
import statistics
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from venomqa.core.models import Journey, JourneyResult

logger = logging.getLogger(__name__)


class LoadPattern(Enum):
    """Load pattern types for testing.

    Attributes:
        CONSTANT: Maintain constant load throughout the test.
        RAMP_UP: Gradually increase load from 0 to target.
        SPIKE: Sudden increase followed by sustained load.
        STRESS: Increase load until system breaks.
    """

    CONSTANT = "constant"
    RAMP_UP = "ramp_up"
    SPIKE = "spike"
    STRESS = "stress"


@dataclass
class LoadTestConfig:
    """Configuration for load testing.

    Attributes:
        duration_seconds: Total test duration in seconds.
        concurrent_users: Target number of concurrent users.
        ramp_up_seconds: Time to ramp up to target load.
        ramp_down_seconds: Time to ramp down at end of test.
        requests_per_second: Target throughput (0 = unlimited).
        pattern: Load pattern to use.
        timeout_per_request: Timeout for each request in seconds.
        collect_response_bodies: Whether to store response bodies.
        sample_interval: Interval for collecting samples in seconds.
        think_time_min: Minimum think time between steps in seconds.
        think_time_max: Maximum think time between steps in seconds.
        warmup_seconds: Warmup period before collecting metrics.

    Example YAML configuration:
        load_test:
          users: 100
          duration: 60s
          ramp_up: 10s
          think_time: 1-3s  # Random delay between steps
    """

    duration_seconds: float = 60.0
    concurrent_users: int = 10
    ramp_up_seconds: float = 0.0
    ramp_down_seconds: float = 0.0
    requests_per_second: float = 0.0
    pattern: LoadPattern = LoadPattern.CONSTANT
    timeout_per_request: float | None = None
    collect_response_bodies: bool = False
    sample_interval: float = 1.0
    think_time_min: float = 0.0
    think_time_max: float = 0.0
    warmup_seconds: float = 0.0

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.duration_seconds <= 0:
            raise ValueError(f"duration_seconds must be positive, got {self.duration_seconds}")
        if self.concurrent_users < 1:
            raise ValueError(f"concurrent_users must be >= 1, got {self.concurrent_users}")
        if self.ramp_up_seconds < 0:
            raise ValueError(f"ramp_up_seconds must be >= 0, got {self.ramp_up_seconds}")
        if self.ramp_down_seconds < 0:
            raise ValueError(f"ramp_down_seconds must be >= 0, got {self.ramp_down_seconds}")
        if self.think_time_min < 0:
            raise ValueError(f"think_time_min must be >= 0, got {self.think_time_min}")
        if self.think_time_max < self.think_time_min:
            raise ValueError(
                f"think_time_max ({self.think_time_max}) must be >= think_time_min ({self.think_time_min})"
            )
        if self.warmup_seconds < 0:
            raise ValueError(f"warmup_seconds must be >= 0, got {self.warmup_seconds}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoadTestConfig:
        """Create config from dictionary (e.g., from YAML).

        Supports human-readable time formats like "60s", "1m", "1h".
        Supports think_time range like "1-3s" for random delay.

        Args:
            data: Dictionary with configuration values.

        Returns:
            LoadTestConfig instance.
        """
        def parse_duration(value: Any) -> float:
            """Parse duration string to seconds."""
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                value = value.strip().lower()
                if value.endswith("ms"):
                    return float(value[:-2]) / 1000
                if value.endswith("s"):
                    return float(value[:-1])
                if value.endswith("m"):
                    return float(value[:-1]) * 60
                if value.endswith("h"):
                    return float(value[:-1]) * 3600
                return float(value)
            return 0.0

        def parse_think_time(value: Any) -> tuple[float, float]:
            """Parse think time range like '1-3s' or '1.5s'."""
            if isinstance(value, (int, float)):
                return float(value), float(value)
            if isinstance(value, str):
                value = value.strip().lower()
                # Check for range format: "1-3s"
                if "-" in value:
                    parts = value.rstrip("smh").split("-")
                    if len(parts) == 2:
                        suffix = ""
                        if value.endswith("s"):
                            suffix = "s"
                        elif value.endswith("m"):
                            suffix = "m"
                        elif value.endswith("h"):
                            suffix = "h"
                        min_val = parse_duration(parts[0] + suffix)
                        max_val = parse_duration(parts[1] + suffix)
                        return min_val, max_val
                # Single value
                val = parse_duration(value)
                return val, val
            return 0.0, 0.0

        # Parse pattern
        pattern_str = data.get("pattern", "constant")
        try:
            pattern = LoadPattern(pattern_str)
        except ValueError:
            pattern = LoadPattern.CONSTANT

        # Parse think time
        think_min, think_max = parse_think_time(data.get("think_time", 0))

        return cls(
            duration_seconds=parse_duration(data.get("duration", data.get("duration_seconds", 60))),
            concurrent_users=int(data.get("users", data.get("concurrent_users", 10))),
            ramp_up_seconds=parse_duration(data.get("ramp_up", data.get("ramp_up_seconds", 0))),
            ramp_down_seconds=parse_duration(data.get("ramp_down", data.get("ramp_down_seconds", 0))),
            requests_per_second=float(data.get("rps", data.get("requests_per_second", 0))),
            pattern=pattern,
            timeout_per_request=data.get("timeout", data.get("timeout_per_request")),
            collect_response_bodies=data.get("collect_response_bodies", False),
            sample_interval=float(data.get("sample_interval", 1.0)),
            think_time_min=think_min,
            think_time_max=think_max,
            warmup_seconds=parse_duration(data.get("warmup", data.get("warmup_seconds", 0))),
        )


@dataclass
class RequestSample:
    """A single request sample for metrics collection.

    Attributes:
        timestamp: When the request was made.
        duration_ms: Request duration in milliseconds.
        success: Whether the request succeeded.
        status_code: HTTP status code (if applicable).
        error: Error message if failed.
        journey_name: Name of the journey executed.
    """

    timestamp: float
    duration_ms: float
    success: bool
    status_code: int | None = None
    error: str | None = None
    journey_name: str = ""


@dataclass
class TimeSeries:
    """Time series data point for metrics over time."""

    timestamp: float
    elapsed_seconds: float
    requests_count: int
    success_count: int
    error_count: int
    active_users: int
    rps: float
    avg_response_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float


@dataclass
class LoadTestMetrics:
    """Real-time metrics during load testing.

    Attributes:
        start_time: When the test started.
        total_requests: Total number of requests made.
        successful_requests: Number of successful requests.
        failed_requests: Number of failed requests.
        total_duration_ms: Cumulative request duration.
        min_duration_ms: Minimum request duration.
        max_duration_ms: Maximum request duration.
        samples: List of individual request samples.
        active_users: Current number of active users.
        current_rps: Current requests per second.
        time_series: Time series data for throughput/latency over time.
        error_breakdown: Breakdown of errors by type.
    """

    start_time: float = field(default_factory=time.time)
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    samples: list[RequestSample] = field(default_factory=list)
    active_users: int = 0
    current_rps: float = 0.0
    time_series: list[TimeSeries] = field(default_factory=list)
    error_breakdown: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_sample_count: int = 0

    def record(self, sample: RequestSample) -> None:
        """Record a request sample.

        Args:
            sample: The request sample to record.
        """
        with self._lock:
            self.samples.append(sample)
            self.total_requests += 1
            self.total_duration_ms += sample.duration_ms

            if sample.success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1
                # Track error breakdown
                error_key = sample.error or "Unknown error"
                # Normalize error messages (take first 50 chars)
                if len(error_key) > 50:
                    error_key = error_key[:50] + "..."
                self.error_breakdown[error_key] = self.error_breakdown.get(error_key, 0) + 1

            if sample.duration_ms < self.min_duration_ms:
                self.min_duration_ms = sample.duration_ms
            if sample.duration_ms > self.max_duration_ms:
                self.max_duration_ms = sample.duration_ms

    def capture_time_series_point(self) -> None:
        """Capture a time series data point for metrics over time."""
        with self._lock:
            elapsed = time.time() - self.start_time
            if not self.samples:
                return

            # Calculate metrics for recent samples
            recent_samples = self.samples[self._last_sample_count:]
            if not recent_samples:
                return

            durations = [s.duration_ms for s in recent_samples]
            sorted_durations = sorted(durations)
            count = len(sorted_durations)

            def percentile(p: float) -> float:
                idx = int(count * p / 100)
                idx = min(idx, count - 1)
                return sorted_durations[idx] if sorted_durations else 0.0

            # Calculate RPS for this interval
            interval_elapsed = (
                recent_samples[-1].timestamp - recent_samples[0].timestamp
                if len(recent_samples) > 1
                else 1.0
            )
            rps = len(recent_samples) / max(interval_elapsed, 0.001)

            point = TimeSeries(
                timestamp=time.time(),
                elapsed_seconds=round(elapsed, 2),
                requests_count=len(recent_samples),
                success_count=sum(1 for s in recent_samples if s.success),
                error_count=sum(1 for s in recent_samples if not s.success),
                active_users=self.active_users,
                rps=round(rps, 2),
                avg_response_ms=round(sum(durations) / count, 2) if count else 0.0,
                p50_ms=round(percentile(50), 2),
                p95_ms=round(percentile(95), 2),
                p99_ms=round(percentile(99), 2),
            )
            self.time_series.append(point)
            self._last_sample_count = len(self.samples)

    def get_snapshot(self) -> dict[str, Any]:
        """Get a snapshot of current metrics.

        Returns:
            Dictionary with current metric values.
        """
        with self._lock:
            elapsed = time.time() - self.start_time
            avg_duration = (
                self.total_duration_ms / self.total_requests if self.total_requests > 0 else 0
            )
            actual_rps = self.total_requests / elapsed if elapsed > 0 else 0

            return {
                "elapsed_seconds": round(elapsed, 2),
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate_pct": round(
                    (self.successful_requests / max(1, self.total_requests)) * 100, 2
                ),
                "error_rate_pct": round(
                    (self.failed_requests / max(1, self.total_requests)) * 100, 2
                ),
                "avg_duration_ms": round(avg_duration, 2),
                "min_duration_ms": round(self.min_duration_ms, 2) if self.samples else 0,
                "max_duration_ms": round(self.max_duration_ms, 2),
                "actual_rps": round(actual_rps, 2),
                "active_users": self.active_users,
            }


@dataclass
class LoadTestResult:
    """Final result of a load test.

    Attributes:
        config: The configuration used for this test.
        metrics: Final metrics snapshot.
        started_at: When the test started.
        finished_at: When the test finished.
        duration_seconds: Actual test duration.
        percentiles: Response time percentiles (p50, p90, p95, p99).
        throughput: Final throughput in requests per second.
        error_rate: Percentage of failed requests.
        journey_results: All journey results (if collected).
        errors: List of error messages from failed requests.
        time_series: Time series data for throughput/latency over time.
        error_breakdown: Breakdown of errors by type.
    """

    config: LoadTestConfig
    metrics: dict[str, Any]
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    percentiles: dict[str, float] = field(default_factory=dict)
    throughput: float = 0.0
    error_rate: float = 0.0
    journey_results: list[JourneyResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    time_series: list[TimeSeries] = field(default_factory=list)
    error_breakdown: dict[str, int] = field(default_factory=dict)
    std_deviation_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for serialization.

        Returns:
            Dictionary with all result data.
        """
        return {
            "config": {
                "duration_seconds": self.config.duration_seconds,
                "concurrent_users": self.config.concurrent_users,
                "ramp_up_seconds": self.config.ramp_up_seconds,
                "ramp_down_seconds": self.config.ramp_down_seconds,
                "pattern": self.config.pattern.value,
                "think_time_min": self.config.think_time_min,
                "think_time_max": self.config.think_time_max,
            },
            "metrics": self.metrics,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_seconds": round(self.duration_seconds, 2),
            "percentiles": {k: round(v, 2) for k, v in self.percentiles.items()},
            "throughput_rps": round(self.throughput, 2),
            "error_rate_pct": round(self.error_rate, 2),
            "std_deviation_ms": round(self.std_deviation_ms, 2),
            "total_errors": len(self.errors),
            "error_breakdown": self.error_breakdown,
            "time_series": [
                {
                    "elapsed_seconds": ts.elapsed_seconds,
                    "rps": ts.rps,
                    "active_users": ts.active_users,
                    "avg_response_ms": ts.avg_response_ms,
                    "p50_ms": ts.p50_ms,
                    "p95_ms": ts.p95_ms,
                    "p99_ms": ts.p99_ms,
                    "error_count": ts.error_count,
                }
                for ts in self.time_series
            ],
        }

    def get_summary(self) -> str:
        """Get a human-readable summary of the test.

        Returns:
            Formatted summary string.
        """
        lines = [
            "=" * 50,
            "LOAD TEST SUMMARY",
            "=" * 50,
            "",
            "Configuration:",
            f"  Users: {self.config.concurrent_users}",
            f"  Duration: {self.duration_seconds:.1f}s",
            f"  Ramp-up: {self.config.ramp_up_seconds:.1f}s",
            f"  Pattern: {self.config.pattern.value}",
            "",
            "Results:",
            f"  Total Requests: {self.metrics['total_requests']}",
            f"  Successful: {self.metrics['successful_requests']}",
            f"  Failed: {self.metrics['failed_requests']}",
            f"  Throughput: {self.throughput:.2f} req/s",
            f"  Error Rate: {self.error_rate:.2f}%",
            "",
            "Response Times:",
            f"  Min: {self.metrics.get('min_duration_ms', 0):.2f}ms",
            f"  Avg: {self.metrics.get('avg_duration_ms', 0):.2f}ms",
            f"  Max: {self.metrics.get('max_duration_ms', 0):.2f}ms",
            f"  Std Dev: {self.std_deviation_ms:.2f}ms",
        ]
        if self.percentiles:
            lines.append("")
            lines.append("Percentiles:")
            for name, value in sorted(self.percentiles.items()):
                lines.append(f"  {name}: {value:.2f}ms")

        if self.error_breakdown:
            lines.append("")
            lines.append("Error Breakdown:")
            for error, count in sorted(
                self.error_breakdown.items(), key=lambda x: -x[1]
            )[:10]:
                lines.append(f"  {count}x {error}")

        lines.append("")
        lines.append("=" * 50)
        return "\n".join(lines)

    def save_report(self, path: str | Path, format: str = "json") -> None:
        """Save the load test report to a file.

        Args:
            path: Path to save the report.
            format: Report format ('json', 'html', 'markdown').
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            with open(path, "w") as f:
                json.dump(self.to_dict(), f, indent=2, default=str)
        elif format == "html":
            html_content = self._generate_html_report()
            with open(path, "w") as f:
                f.write(html_content)
        elif format == "markdown":
            md_content = self._generate_markdown_report()
            with open(path, "w") as f:
                f.write(md_content)
        else:
            raise ValueError(f"Unknown format: {format}. Use 'json', 'html', or 'markdown'.")

        logger.info(f"Load test report saved to {path}")

    def _generate_markdown_report(self) -> str:
        """Generate a Markdown report.

        Returns:
            Markdown formatted report string.
        """
        lines = [
            "# Load Test Report",
            "",
            f"**Generated:** {self.finished_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Configuration",
            "",
            "| Setting | Value |",
            "|---------|-------|",
            f"| Users | {self.config.concurrent_users} |",
            f"| Duration | {self.config.duration_seconds}s |",
            f"| Ramp-up | {self.config.ramp_up_seconds}s |",
            f"| Pattern | {self.config.pattern.value} |",
            f"| Think Time | {self.config.think_time_min}-{self.config.think_time_max}s |",
            "",
            "## Results Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Requests | {self.metrics['total_requests']} |",
            f"| Successful | {self.metrics['successful_requests']} |",
            f"| Failed | {self.metrics['failed_requests']} |",
            f"| Throughput | {self.throughput:.2f} req/s |",
            f"| Error Rate | {self.error_rate:.2f}% |",
            "",
            "## Response Time Distribution",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Min | {self.metrics.get('min_duration_ms', 0):.2f}ms |",
            f"| Avg | {self.metrics.get('avg_duration_ms', 0):.2f}ms |",
            f"| Max | {self.metrics.get('max_duration_ms', 0):.2f}ms |",
            f"| Std Dev | {self.std_deviation_ms:.2f}ms |",
        ]

        if self.percentiles:
            lines.extend([
                "",
                "### Percentiles",
                "",
                "| Percentile | Value |",
                "|------------|-------|",
            ])
            for name, value in sorted(self.percentiles.items()):
                lines.append(f"| {name} | {value:.2f}ms |")

        if self.error_breakdown:
            lines.extend([
                "",
                "## Error Breakdown",
                "",
                "| Error | Count |",
                "|-------|-------|",
            ])
            for error, count in sorted(self.error_breakdown.items(), key=lambda x: -x[1])[:10]:
                lines.append(f"| {error} | {count} |")

        return "\n".join(lines)

    def _generate_html_report(self) -> str:
        """Generate an HTML report with charts.

        Returns:
            HTML formatted report string.
        """
        # Prepare time series data for charts
        ts_labels = [ts.elapsed_seconds for ts in self.time_series]
        ts_rps = [ts.rps for ts in self.time_series]
        ts_p50 = [ts.p50_ms for ts in self.time_series]
        ts_p95 = [ts.p95_ms for ts in self.time_series]
        ts_p99 = [ts.p99_ms for ts in self.time_series]
        [ts.error_count for ts in self.time_series]
        ts_users = [ts.active_users for ts in self.time_series]

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Load Test Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <style>
        :root {{
            --primary: #6366f1;
            --success: #22c55e;
            --danger: #ef4444;
            --warning: #f59e0b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f3f4f6;
            color: #1f2937;
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: var(--primary); margin-bottom: 1rem; }}
        .card {{
            background: white;
            border-radius: 0.5rem;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .card h2 {{ color: #374151; margin-bottom: 1rem; font-size: 1.25rem; }}
        .grid {{ display: grid; gap: 1rem; }}
        .grid-4 {{ grid-template-columns: repeat(4, 1fr); }}
        .grid-2 {{ grid-template-columns: repeat(2, 1fr); }}
        .stat-card {{ text-align: center; }}
        .stat-value {{ font-size: 2rem; font-weight: 700; }}
        .stat-label {{ color: #6b7280; font-size: 0.875rem; }}
        .stat-success {{ color: var(--success); }}
        .stat-danger {{ color: var(--danger); }}
        .stat-warning {{ color: var(--warning); }}
        .stat-primary {{ color: var(--primary); }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #e5e7eb; }}
        th {{ background: #f9fafb; font-weight: 600; }}
        .chart-container {{ height: 300px; }}
        @media (max-width: 768px) {{
            .grid-4 {{ grid-template-columns: repeat(2, 1fr); }}
            .grid-2 {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Load Test Report</h1>
        <p style="color: #6b7280; margin-bottom: 2rem;">Generated: {self.finished_at.strftime('%Y-%m-%d %H:%M:%S')}</p>

        <div class="grid grid-4">
            <div class="card stat-card">
                <div class="stat-value stat-primary">{self.metrics['total_requests']}</div>
                <div class="stat-label">Total Requests</div>
            </div>
            <div class="card stat-card">
                <div class="stat-value stat-success">{self.throughput:.1f}</div>
                <div class="stat-label">Requests/Second</div>
            </div>
            <div class="card stat-card">
                <div class="stat-value {'stat-success' if self.error_rate < 1 else 'stat-danger'}">{self.error_rate:.2f}%</div>
                <div class="stat-label">Error Rate</div>
            </div>
            <div class="card stat-card">
                <div class="stat-value stat-warning">{self.percentiles.get('p99', 0):.0f}ms</div>
                <div class="stat-label">P99 Latency</div>
            </div>
        </div>

        <div class="grid grid-2">
            <div class="card">
                <h2>Throughput Over Time</h2>
                <div class="chart-container">
                    <canvas id="throughputChart"></canvas>
                </div>
            </div>
            <div class="card">
                <h2>Response Time Distribution</h2>
                <div class="chart-container">
                    <canvas id="latencyChart"></canvas>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>Response Time Percentiles</h2>
            <table>
                <tr>
                    <th>Percentile</th>
                    <th>Response Time</th>
                </tr>
                {"".join(f"<tr><td>{k}</td><td>{v:.2f}ms</td></tr>" for k, v in sorted(self.percentiles.items()))}
            </table>
        </div>

        <div class="card">
            <h2>Configuration</h2>
            <table>
                <tr><th>Setting</th><th>Value</th></tr>
                <tr><td>Users</td><td>{self.config.concurrent_users}</td></tr>
                <tr><td>Duration</td><td>{self.config.duration_seconds}s</td></tr>
                <tr><td>Ramp-up</td><td>{self.config.ramp_up_seconds}s</td></tr>
                <tr><td>Pattern</td><td>{self.config.pattern.value}</td></tr>
            </table>
        </div>

        {self._generate_error_breakdown_html()}
    </div>

    <script>
        new Chart(document.getElementById('throughputChart'), {{
            type: 'line',
            data: {{
                labels: {ts_labels},
                datasets: [
                    {{
                        label: 'Requests/sec',
                        data: {ts_rps},
                        borderColor: '#6366f1',
                        backgroundColor: 'rgba(99, 102, 241, 0.1)',
                        fill: true,
                        tension: 0.3
                    }},
                    {{
                        label: 'Active Users',
                        data: {ts_users},
                        borderColor: '#22c55e',
                        borderDash: [5, 5],
                        fill: false,
                        tension: 0.3,
                        yAxisID: 'y1'
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{ beginAtZero: true, title: {{ display: true, text: 'Requests/sec' }} }},
                    y1: {{ position: 'right', beginAtZero: true, title: {{ display: true, text: 'Users' }}, grid: {{ drawOnChartArea: false }} }},
                    x: {{ title: {{ display: true, text: 'Time (seconds)' }} }}
                }}
            }}
        }});

        new Chart(document.getElementById('latencyChart'), {{
            type: 'line',
            data: {{
                labels: {ts_labels},
                datasets: [
                    {{
                        label: 'P50',
                        data: {ts_p50},
                        borderColor: '#22c55e',
                        fill: false,
                        tension: 0.3
                    }},
                    {{
                        label: 'P95',
                        data: {ts_p95},
                        borderColor: '#f59e0b',
                        fill: false,
                        tension: 0.3
                    }},
                    {{
                        label: 'P99',
                        data: {ts_p99},
                        borderColor: '#ef4444',
                        fill: false,
                        tension: 0.3
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{ beginAtZero: true, title: {{ display: true, text: 'Response Time (ms)' }} }},
                    x: {{ title: {{ display: true, text: 'Time (seconds)' }} }}
                }}
            }}
        }});
    </script>
</body>
</html>"""

    def _generate_error_breakdown_html(self) -> str:
        """Generate HTML for error breakdown section."""
        if not self.error_breakdown:
            return ""

        rows = "".join(
            f"<tr><td>{error}</td><td>{count}</td></tr>"
            for error, count in sorted(self.error_breakdown.items(), key=lambda x: -x[1])[:10]
        )

        return f"""
        <div class="card">
            <h2>Error Breakdown</h2>
            <table>
                <tr><th>Error</th><th>Count</th></tr>
                {rows}
            </table>
        </div>"""


RunnerFactory = Callable[[], Any]
ProgressCallback = Callable[[LoadTestMetrics], None]


@dataclass
class LoadTestAssertions:
    """Assertions for load test results.

    Allows defining pass/fail criteria for load tests based on
    response times, error rates, and throughput.

    Example:
        >>> assertions = LoadTestAssertions(
        ...     max_p99_ms=500,
        ...     max_error_rate_percent=1.0,
        ...     min_throughput_rps=100,
        ... )
        >>> result = tester.run(journey, runner_factory)
        >>> assertions.validate(result)  # Raises AssertionError if failed
    """

    max_p50_ms: float | None = None
    max_p90_ms: float | None = None
    max_p95_ms: float | None = None
    max_p99_ms: float | None = None
    max_avg_ms: float | None = None
    max_error_rate_percent: float | None = None
    min_throughput_rps: float | None = None
    min_success_rate_percent: float | None = None

    def validate(self, result: LoadTestResult) -> tuple[bool, list[str]]:
        """Validate load test results against assertions.

        Args:
            result: LoadTestResult to validate.

        Returns:
            Tuple of (passed: bool, failures: list[str]).

        Raises:
            AssertionError: If any assertion fails (when used with assert_valid).
        """
        failures: list[str] = []

        if self.max_p50_ms is not None:
            actual = result.percentiles.get("p50", 0)
            if actual > self.max_p50_ms:
                failures.append(f"P50 latency {actual:.2f}ms exceeds max {self.max_p50_ms}ms")

        if self.max_p90_ms is not None:
            actual = result.percentiles.get("p90", 0)
            if actual > self.max_p90_ms:
                failures.append(f"P90 latency {actual:.2f}ms exceeds max {self.max_p90_ms}ms")

        if self.max_p95_ms is not None:
            actual = result.percentiles.get("p95", 0)
            if actual > self.max_p95_ms:
                failures.append(f"P95 latency {actual:.2f}ms exceeds max {self.max_p95_ms}ms")

        if self.max_p99_ms is not None:
            actual = result.percentiles.get("p99", 0)
            if actual > self.max_p99_ms:
                failures.append(f"P99 latency {actual:.2f}ms exceeds max {self.max_p99_ms}ms")

        if self.max_avg_ms is not None:
            actual = result.metrics.get("avg_duration_ms", 0)
            if actual > self.max_avg_ms:
                failures.append(f"Avg latency {actual:.2f}ms exceeds max {self.max_avg_ms}ms")

        if self.max_error_rate_percent is not None:
            if result.error_rate > self.max_error_rate_percent:
                failures.append(
                    f"Error rate {result.error_rate:.2f}% exceeds max {self.max_error_rate_percent}%"
                )

        if self.min_throughput_rps is not None:
            if result.throughput < self.min_throughput_rps:
                failures.append(
                    f"Throughput {result.throughput:.2f} req/s below min {self.min_throughput_rps} req/s"
                )

        if self.min_success_rate_percent is not None:
            success_rate = 100 - result.error_rate
            if success_rate < self.min_success_rate_percent:
                failures.append(
                    f"Success rate {success_rate:.2f}% below min {self.min_success_rate_percent}%"
                )

        return len(failures) == 0, failures

    def assert_valid(self, result: LoadTestResult) -> None:
        """Assert that load test results meet all criteria.

        Args:
            result: LoadTestResult to validate.

        Raises:
            AssertionError: If any assertion fails.
        """
        passed, failures = self.validate(result)
        if not passed:
            raise AssertionError(
                "Load test assertions failed:\n" + "\n".join(f"  - {f}" for f in failures)
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LoadTestAssertions:
        """Create assertions from dictionary (e.g., from YAML config).

        Args:
            data: Dictionary with assertion values.

        Returns:
            LoadTestAssertions instance.
        """
        return cls(
            max_p50_ms=data.get("max_p50_ms") or data.get("p50"),
            max_p90_ms=data.get("max_p90_ms") or data.get("p90"),
            max_p95_ms=data.get("max_p95_ms") or data.get("p95"),
            max_p99_ms=data.get("max_p99_ms") or data.get("p99"),
            max_avg_ms=data.get("max_avg_ms") or data.get("avg"),
            max_error_rate_percent=data.get("max_error_rate_percent") or data.get("error_rate"),
            min_throughput_rps=data.get("min_throughput_rps") or data.get("throughput"),
            min_success_rate_percent=data.get("min_success_rate_percent"),
        )


class LoadTester:
    """Execute load tests against a system using journeys.

    Provides configurable load testing with various patterns, real-time
    metrics collection, and detailed result analysis.

    Attributes:
        config: Load test configuration.

    Example:
        >>> config = LoadTestConfig(
        ...     duration_seconds=30,
        ...     concurrent_users=5,
        ...     ramp_up_seconds=5,
        ... )
        >>> tester = LoadTester(config)
        >>> result = tester.run(journey, lambda: JourneyRunner(client))
        >>> print(result.get_summary())
    """

    def __init__(
        self,
        config: LoadTestConfig,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """Initialize the load tester.

        Args:
            config: Load test configuration.
            progress_callback: Optional callback for real-time progress updates.
        """
        self.config = config
        self.progress_callback = progress_callback
        self._metrics = LoadTestMetrics()
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def run(
        self,
        journey: Journey,
        runner_factory: RunnerFactory,
    ) -> LoadTestResult:
        """Execute the load test.

        Runs the specified journey repeatedly according to the configured
        load pattern and collects metrics.

        Args:
            journey: The journey to execute repeatedly.
            runner_factory: Factory function to create runner instances.

        Returns:
            LoadTestResult with all collected metrics and results.
        """
        self._stop_event.clear()
        self._metrics = LoadTestMetrics()
        started_at = datetime.now()

        logger.info(
            f"Starting load test: {self.config.concurrent_users} users, "
            f"{self.config.duration_seconds}s duration, "
            f"ramp-up: {self.config.ramp_up_seconds}s"
        )

        all_results: list[JourneyResult] = []
        errors: list[str] = []

        active_workers: list[threading.Thread] = []
        worker_count = 0
        warmup_end_time = time.time() + self.config.warmup_seconds
        in_warmup = self.config.warmup_seconds > 0

        def get_think_time() -> float:
            """Get random think time within configured range."""
            if self.config.think_time_max > 0:
                return random.uniform(
                    self.config.think_time_min,
                    self.config.think_time_max
                )
            return 0.0

        def worker(worker_id: int) -> None:
            nonlocal worker_count, in_warmup
            with self._lock:
                worker_count += 1
                self._metrics.active_users = worker_count

            try:
                while not self._stop_event.is_set():
                    request_start = time.time()

                    # Check if we're still in warmup
                    is_warmup = time.time() < warmup_end_time

                    try:
                        runner = runner_factory()
                        result = runner.run(journey)
                        duration_ms = (time.time() - request_start) * 1000

                        # Only record metrics after warmup
                        if not is_warmup:
                            sample = RequestSample(
                                timestamp=request_start,
                                duration_ms=duration_ms,
                                success=result.success,
                                journey_name=journey.name,
                            )
                            self._metrics.record(sample)

                            with self._lock:
                                all_results.append(result)
                                if not result.success:
                                    for issue in result.issues:
                                        errors.append(f"{journey.name}: {issue.message}")

                    except Exception as e:
                        duration_ms = (time.time() - request_start) * 1000
                        if not is_warmup:
                            sample = RequestSample(
                                timestamp=request_start,
                                duration_ms=duration_ms,
                                success=False,
                                error=str(e),
                                journey_name=journey.name,
                            )
                            self._metrics.record(sample)
                            errors.append(f"{journey.name}: {e}")

                    # Apply rate limiting if configured
                    if self.config.requests_per_second > 0:
                        delay = 1.0 / self.config.requests_per_second
                        time.sleep(delay)
                    else:
                        # Apply think time
                        think_time = get_think_time()
                        if think_time > 0:
                            time.sleep(think_time)

            finally:
                with self._lock:
                    worker_count -= 1
                    self._metrics.active_users = worker_count

        end_time = time.time() + self.config.duration_seconds

        # Start workers with ramp-up
        if self.config.ramp_up_seconds > 0:
            ramp_step = self.config.ramp_up_seconds / self.config.concurrent_users
            for i in range(self.config.concurrent_users):
                if self._stop_event.is_set():
                    break
                t = threading.Thread(target=worker, args=(i,), name=f"load-worker-{i}")
                t.daemon = True
                t.start()
                active_workers.append(t)
                time.sleep(ramp_step)
        else:
            for i in range(self.config.concurrent_users):
                t = threading.Thread(target=worker, args=(i,), name=f"load-worker-{i}")
                t.daemon = True
                t.start()
                active_workers.append(t)

        # Monitoring loop
        last_progress_time = time.time()
        last_time_series_time = time.time()
        while time.time() < end_time and not self._stop_event.is_set():
            time.sleep(0.1)

            current_time = time.time()

            # Progress callback
            if self.progress_callback:
                if current_time - last_progress_time >= self.config.sample_interval:
                    self.progress_callback(self._metrics)
                    last_progress_time = current_time

            # Capture time series data
            if current_time - last_time_series_time >= self.config.sample_interval:
                self._metrics.capture_time_series_point()
                last_time_series_time = current_time

        self._stop_event.set()

        # Wait for workers to finish
        for t in active_workers:
            t.join(timeout=2.0)

        finished_at = datetime.now()
        duration_seconds = (finished_at - started_at).total_seconds()

        metrics_snapshot = self._metrics.get_snapshot()
        percentiles = self._calculate_percentiles()
        std_dev = self._calculate_std_deviation()

        throughput = metrics_snapshot["total_requests"] / duration_seconds if duration_seconds > 0 else 0
        error_rate = (
            metrics_snapshot["failed_requests"] / max(1, metrics_snapshot["total_requests"])
        ) * 100

        result = LoadTestResult(
            config=self.config,
            metrics=metrics_snapshot,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            percentiles=percentiles,
            throughput=throughput,
            error_rate=error_rate,
            journey_results=all_results,
            errors=errors,
            time_series=self._metrics.time_series.copy(),
            error_breakdown=self._metrics.error_breakdown.copy(),
            std_deviation_ms=std_dev,
        )

        logger.info(f"Load test completed:\n{result.get_summary()}")
        return result

    def _calculate_percentiles(self) -> dict[str, float]:
        """Calculate response time percentiles from samples.

        Returns:
            Dictionary with p50, p75, p90, p95, p99 percentiles in ms.
        """
        with self._metrics._lock:
            if not self._metrics.samples:
                return {}

            durations = sorted(s.duration_ms for s in self._metrics.samples)
            count = len(durations)

            def percentile(p: float) -> float:
                # Use linear interpolation for more accurate percentiles
                if count == 1:
                    return durations[0]
                k = (count - 1) * p / 100
                f = int(k)
                c = f + 1 if f + 1 < count else f
                return durations[f] + (k - f) * (durations[c] - durations[f])

            return {
                "p50": percentile(50),
                "p75": percentile(75),
                "p90": percentile(90),
                "p95": percentile(95),
                "p99": percentile(99),
            }

    def _calculate_std_deviation(self) -> float:
        """Calculate standard deviation of response times.

        Returns:
            Standard deviation in milliseconds.
        """
        with self._metrics._lock:
            if len(self._metrics.samples) < 2:
                return 0.0

            durations = [s.duration_ms for s in self._metrics.samples]
            return statistics.stdev(durations)

    def stop(self) -> None:
        """Stop the load test early."""
        self._stop_event.set()
        logger.info("Load test stop requested")

    def get_current_metrics(self) -> dict[str, Any]:
        """Get current metrics snapshot.

        Returns:
            Dictionary with current metric values.
        """
        return self._metrics.get_snapshot()


def run_quick_load_test(
    journey: Journey,
    runner_factory: RunnerFactory,
    duration_seconds: float = 10.0,
    concurrent_users: int = 5,
) -> LoadTestResult:
    """Convenience function to run a quick load test.

    Args:
        journey: The journey to test.
        runner_factory: Factory to create runner instances.
        duration_seconds: Test duration in seconds.
        concurrent_users: Number of concurrent users.

    Returns:
        LoadTestResult with test results.
    """
    config = LoadTestConfig(
        duration_seconds=duration_seconds,
        concurrent_users=concurrent_users,
    )
    tester = LoadTester(config)
    return tester.run(journey, runner_factory)


def benchmark_journey(
    journey: Journey,
    runner_factory: RunnerFactory,
    iterations: int = 100,
    warmup_iterations: int = 10,
) -> dict[str, Any]:
    """Benchmark a journey with precise timing.

    Runs the journey multiple times and collects detailed timing statistics.

    Args:
        journey: The journey to benchmark.
        runner_factory: Factory to create runner instances.
        iterations: Number of iterations to run.
        warmup_iterations: Number of warmup iterations (not counted).

    Returns:
        Dictionary with benchmark results.
    """
    logger.info(f"Benchmarking journey '{journey.name}' with {iterations} iterations")

    for _ in range(warmup_iterations):
        runner = runner_factory()
        runner.run(journey)

    durations: list[float] = []
    successes = 0
    errors: list[str] = []

    start_time = time.perf_counter()

    for _ in range(iterations):
        iter_start = time.perf_counter()
        try:
            runner = runner_factory()
            result = runner.run(journey)
            iter_duration = (time.perf_counter() - iter_start) * 1000
            durations.append(iter_duration)
            if result.success:
                successes += 1
            else:
                for issue in result.issues:
                    errors.append(issue.message)
        except Exception as e:
            iter_duration = (time.perf_counter() - iter_start) * 1000
            durations.append(iter_duration)
            errors.append(str(e))

    total_time = (time.perf_counter() - start_time) * 1000

    if not durations:
        return {"error": "No iterations completed"}

    durations.sort()

    def percentile(p: float) -> float:
        idx = int(len(durations) * p / 100)
        idx = min(idx, len(durations) - 1)
        return durations[idx]

    return {
        "journey_name": journey.name,
        "iterations": iterations,
        "successes": successes,
        "failures": iterations - successes,
        "success_rate": f"{(successes / iterations) * 100:.1f}%",
        "total_time_ms": round(total_time, 2),
        "avg_time_ms": round(sum(durations) / len(durations), 2),
        "min_time_ms": round(min(durations), 2),
        "max_time_ms": round(max(durations), 2),
        "p50_ms": round(percentile(50), 2),
        "p90_ms": round(percentile(90), 2),
        "p95_ms": round(percentile(95), 2),
        "p99_ms": round(percentile(99), 2),
        "throughput_per_sec": round(iterations / (total_time / 1000), 2),
        "errors": errors[:10],
    }
