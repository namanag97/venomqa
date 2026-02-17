"""Metrics collection for VenomQA with Prometheus-compatible export.

This module provides comprehensive metrics collection capabilities including:
- Counter: Monotonically increasing values
- Gauge: Values that can go up and down
- Histogram: Distribution of values in configurable buckets
- Timer: Context manager for timing operations
- Prometheus-compatible export format

Example:
    Basic usage::

        from venomqa.observability.metrics import MetricsCollector

        metrics = MetricsCollector()

        # Record a counter
        metrics.counter("requests_total").inc()

        # Time an operation
        with metrics.timer("request_duration"):
            process_request()

        # Export to Prometheus format
        print(metrics.to_prometheus())
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricValue:
    """A single metric value with labels and timestamp.

    Attributes:
        value: The numeric value of the metric.
        labels: Key-value pairs for metric dimensions.
        timestamp: Unix timestamp when the value was recorded.
    """

    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "value": self.value,
            "labels": dict(self.labels),
            "timestamp": self.timestamp,
        }


class Counter:
    """A monotonically increasing counter metric.

    Counters are used for cumulative values like requests served,
    tasks completed, or errors encountered. They can only increase
    (or be reset to zero).

    Attributes:
        name: Metric name (should follow Prometheus naming conventions).
        description: Help text describing the metric.

    Example:
        >>> counter = Counter("http_requests_total", "Total HTTP requests")
        >>> counter.inc()
        >>> counter.inc(5)
        >>> counter.get()
        6.0
        >>> print(counter.to_prometheus())
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        labels: dict[str, str] | None = None,
    ) -> None:
        """Initialize a counter metric.

        Args:
            name: Metric name (use snake_case, include unit suffix).
            description: Help text for the metric.
            labels: Optional static labels for this metric instance.
        """
        self.name = name
        self.description = description
        self._labels = labels or {}
        self._value: float = 0.0
        self._lock = threading.Lock()
        self._created: float = time.time()

    def inc(self, amount: float = 1.0) -> None:
        """Increment the counter by the given amount.

        Args:
            amount: Amount to increment by (must be non-negative).

        Raises:
            ValueError: If amount is negative.
        """
        if amount < 0:
            raise ValueError("Counter can only be incremented by non-negative values")
        with self._lock:
            self._value += amount

    def labels(self, **label_values: str) -> LabeledCounter:
        """Create a counter with additional labels.

        Args:
            **label_values: Label key-value pairs.

        Returns:
            A LabeledCounter with the specified labels.

        Example:
            >>> counter.labels(method="GET", status="200").inc()
        """
        merged = {**self._labels, **label_values}
        return LabeledCounter(self, merged)

    def get(self) -> float:
        """Get the current counter value."""
        with self._lock:
            return self._value

    def reset(self) -> None:
        """Reset the counter to zero."""
        with self._lock:
            self._value = 0.0

    def to_prometheus(self) -> str:
        """Export in Prometheus text format.

        Returns:
            Prometheus-formatted metric string.
        """
        lines = []
        if self.description:
            lines.append(f"# HELP {self.name} {self.description}")
        lines.append(f"# TYPE {self.name} counter")
        label_str = self._format_labels(self._labels)
        lines.append(f"{self.name}{label_str} {self._value}")
        return "\n".join(lines)

    @staticmethod
    def _format_labels(labels: dict[str, str]) -> str:
        """Format labels for Prometheus output."""
        if not labels:
            return ""
        pairs = [f'{k}="{_escape_label_value(v)}"' for k, v in sorted(labels.items())]
        return "{" + ", ".join(pairs) + "}"


class LabeledCounter:
    """A counter with fixed labels for convenient incrementing.

    This is returned by Counter.labels() and provides a simplified
    interface for incrementing a counter with pre-set labels.
    """

    def __init__(self, parent: Counter, labels: dict[str, str]) -> None:
        self._parent = parent
        self._labels = labels

    def inc(self, amount: float = 1.0) -> None:
        """Increment the parent counter with this label set.

        Note: This increments the base counter; label differentiation
        must be handled by the metrics collector.
        """
        self._parent.inc(amount)


class Gauge:
    """A metric that can arbitrarily go up and down.

    Gauges are used for values that can increase or decrease,
    like current temperature, memory usage, or number of concurrent requests.

    Attributes:
        name: Metric name.
        description: Help text describing the metric.

    Example:
        >>> gauge = Gauge("active_connections", "Current active connections")
        >>> gauge.set(10)
        >>> gauge.inc()
        >>> gauge.dec()
        >>> gauge.get()
        10.0
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        labels: dict[str, str] | None = None,
    ) -> None:
        """Initialize a gauge metric.

        Args:
            name: Metric name (use snake_case, include unit suffix).
            description: Help text for the metric.
            labels: Optional static labels for this metric instance.
        """
        self.name = name
        self.description = description
        self._labels = labels or {}
        self._value: float = 0.0
        self._lock = threading.Lock()

    def set(self, value: float) -> None:
        """Set the gauge to a specific value.

        Args:
            value: The value to set.
        """
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        """Increment the gauge by the given amount.

        Args:
            amount: Amount to increment by.
        """
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        """Decrement the gauge by the given amount.

        Args:
            amount: Amount to decrement by.
        """
        with self._lock:
            self._value -= amount

    def get(self) -> float:
        """Get the current gauge value."""
        with self._lock:
            return self._value

    def labels(self, **label_values: str) -> LabeledGauge:
        """Create a gauge with additional labels."""
        merged = {**self._labels, **label_values}
        return LabeledGauge(self, merged)

    def to_prometheus(self) -> str:
        """Export in Prometheus text format."""
        lines = []
        if self.description:
            lines.append(f"# HELP {self.name} {self.description}")
        lines.append(f"# TYPE {self.name} gauge")
        label_str = Counter._format_labels(self._labels)
        lines.append(f"{self.name}{label_str} {self._value}")
        return "\n".join(lines)


class LabeledGauge:
    """A gauge with fixed labels for convenient operations."""

    def __init__(self, parent: Gauge, labels: dict[str, str]) -> None:
        self._parent = parent
        self._labels = labels

    def set(self, value: float) -> None:
        self._parent.set(value)

    def inc(self, amount: float = 1.0) -> None:
        self._parent.inc(amount)

    def dec(self, amount: float = 1.0) -> None:
        self._parent.dec(amount)


class Histogram:
    """A metric that samples observations into configurable buckets.

    Histograms are used to observe distributions of values, like
    request latencies or response sizes. They automatically compute
    bucket counts, sum, and count.

    Attributes:
        name: Metric name.
        description: Help text describing the metric.
        buckets: Tuple of upper bounds for histogram buckets.

    Example:
        >>> hist = Histogram("request_duration_ms", "Request duration")
        >>> hist.observe(150)
        >>> hist.observe(250)
        >>> print(hist.to_prometheus())
    """

    DEFAULT_BUCKETS = (
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
        5.0,
        10.0,
        float("inf"),
    )

    def __init__(
        self,
        name: str,
        description: str = "",
        buckets: tuple[float, ...] | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Initialize a histogram metric.

        Args:
            name: Metric name (use snake_case, include unit suffix).
            description: Help text for the metric.
            buckets: Optional custom bucket boundaries (must include +Inf).
            labels: Optional static labels for this metric instance.

        Note:
            If no buckets are provided, default Prometheus buckets are used.
            Buckets should be in ascending order.
        """
        self.name = name
        self.description = description
        self._buckets = buckets or self.DEFAULT_BUCKETS
        self._labels = labels or {}
        self._counts: dict[float, int] = defaultdict(int)
        self._sum: float = 0.0
        self._count: int = 0
        self._lock = threading.Lock()

        for bucket in self._buckets:
            self._counts[bucket] = 0

    def observe(self, value: float) -> None:
        """Record an observation.

        Args:
            value: The value to observe.
        """
        with self._lock:
            self._sum += value
            self._count += 1
            for bucket in self._buckets:
                if value <= bucket:
                    self._counts[bucket] += 1

    def get(self) -> dict[str, Any]:
        """Get histogram statistics.

        Returns:
            Dictionary with count, sum, and bucket counts.
        """
        with self._lock:
            return {
                "count": self._count,
                "sum": self._sum,
                "buckets": dict(self._counts),
                "mean": self._sum / self._count if self._count > 0 else 0.0,
            }

    def labels(self, **label_values: str) -> LabeledHistogram:
        """Create a histogram with additional labels."""
        merged = {**self._labels, **label_values}
        return LabeledHistogram(self, merged)

    def reset(self) -> None:
        """Reset all histogram data."""
        with self._lock:
            self._sum = 0.0
            self._count = 0
            for bucket in self._buckets:
                self._counts[bucket] = 0

    def to_prometheus(self) -> str:
        """Export in Prometheus text format.

        Returns:
            Prometheus-formatted histogram string with _bucket, _sum, and _count.
        """
        lines = []
        if self.description:
            lines.append(f"# HELP {self.name} {self.description}")
        lines.append(f"# TYPE {self.name} histogram")

        label_str = Counter._format_labels(self._labels)

        cumulative = 0
        for bucket in self._buckets:
            bucket_str = "+Inf" if bucket == float("inf") else str(bucket)
            cumulative += self._counts.get(bucket, 0)

            if label_str:
                bucket_labels = f'{{{label_str[1:-1]}, le="{bucket_str}"}}'
            else:
                bucket_labels = f'{{le="{bucket_str}"}}'

            lines.append(f"{self.name}_bucket{bucket_labels} {cumulative}")

        lines.append(f"{self.name}_sum{label_str} {self._sum}")
        lines.append(f"{self.name}_count{label_str} {self._count}")
        return "\n".join(lines)


class LabeledHistogram:
    """A histogram with fixed labels for convenient observing."""

    def __init__(self, parent: Histogram, labels: dict[str, str]) -> None:
        self._parent = parent
        self._labels = labels

    def observe(self, value: float) -> None:
        self._parent.observe(value)


class Timer:
    """A context manager for timing operations and recording to a histogram.

    Example:
        >>> histogram = Histogram("request_duration_seconds")
        >>> with Timer(histogram):
        ...     process_request()
    """

    def __init__(
        self,
        histogram: Histogram,
        callback: Any | None = None,
    ) -> None:
        """Initialize the timer.

        Args:
            histogram: The histogram to record observations to.
            callback: Optional callback called with duration on exit.
        """
        self._histogram = histogram
        self._callback = callback
        self._start_time: float | None = None
        self._end_time: float | None = None

    def __enter__(self) -> Timer:
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self._end_time = time.perf_counter()
        duration = self._end_time - self._start_time if self._start_time else 0
        self._histogram.observe(duration)
        if self._callback:
            self._callback(duration)

    @property
    def duration(self) -> float | None:
        """Get the recorded duration in seconds (only after exit)."""
        if self._start_time is not None and self._end_time is not None:
            return self._end_time - self._start_time
        return None

    @property
    def duration_ms(self) -> float | None:
        """Get the recorded duration in milliseconds."""
        duration = self.duration
        return duration * 1000 if duration is not None else None


@dataclass
class MetricsConfig:
    """Configuration for metrics collection.

    Attributes:
        namespace: Prefix for all metric names.
        enable_default_metrics: Whether to create default VenomQA metrics.
        histogram_buckets: Default buckets for histograms.
        labels: Static labels to add to all metrics.
    """

    namespace: str = "venomqa"
    enable_default_metrics: bool = True
    histogram_buckets: tuple[float, ...] = Histogram.DEFAULT_BUCKETS
    labels: dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """Central metrics collection and Prometheus export.

    This is a singleton class that manages all metrics for an application.
    It provides factory methods for creating counters, gauges, and histograms,
    and can export all metrics in Prometheus format.

    Attributes:
        config: Configuration for the metrics collector.

    Example:
        >>> metrics = MetricsCollector()
        >>> metrics.counter("requests").inc()
        >>> metrics.gauge("temperature").set(72.5)
        >>> print(metrics.to_prometheus())
    """

    _instance: MetricsCollector | None = None
    _lock = threading.Lock()
    _initialized: bool

    def __new__(cls, config: MetricsConfig | None = None) -> MetricsCollector:
        """Create or return the singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, config: MetricsConfig | None = None) -> None:
        """Initialize the metrics collector.

        Args:
            config: Optional configuration. If not provided, defaults are used.
        """
        if self._initialized:
            return
        self._initialized = True

        self.config = config or MetricsConfig()
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._metrics_lock = threading.Lock()

        if self.config.enable_default_metrics:
            self._init_default_metrics()

    def _init_default_metrics(self) -> None:
        """Initialize default VenomQA metrics."""
        ns = self.config.namespace

        self._histograms["journey_duration"] = Histogram(
            f"{ns}_journey_duration_seconds",
            "Duration of journey execution in seconds",
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float("inf")),
            labels=self.config.labels,
        )

        self._histograms["step_duration"] = Histogram(
            f"{ns}_step_duration_seconds",
            "Duration of step execution in seconds",
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, float("inf")),
            labels=self.config.labels,
        )

        self._counters["steps_total"] = Counter(
            f"{ns}_steps_total",
            "Total number of steps executed",
            labels=self.config.labels,
        )

        self._counters["steps_success"] = Counter(
            f"{ns}_steps_success_total",
            "Number of successful steps",
            labels=self.config.labels,
        )

        self._counters["steps_failure"] = Counter(
            f"{ns}_steps_failure_total",
            "Number of failed steps",
            labels=self.config.labels,
        )

        self._counters["journeys_total"] = Counter(
            f"{ns}_journeys_total",
            "Total number of journeys executed",
            labels=self.config.labels,
        )

        self._counters["journeys_success"] = Counter(
            f"{ns}_journeys_success_total",
            "Number of successful journeys",
            labels=self.config.labels,
        )

        self._counters["journeys_failure"] = Counter(
            f"{ns}_journeys_failure_total",
            "Number of failed journeys",
            labels=self.config.labels,
        )

        self._gauges["active_connections"] = Gauge(
            f"{ns}_active_connections",
            "Number of active connections",
            labels=self.config.labels,
        )

        self._gauges["active_journeys"] = Gauge(
            f"{ns}_active_journeys",
            "Number of currently running journeys",
            labels=self.config.labels,
        )

        self._counters["retries_total"] = Counter(
            f"{ns}_retries_total",
            "Total number of retries",
            labels=self.config.labels,
        )

        self._counters["http_requests_total"] = Counter(
            f"{ns}_http_requests_total",
            "Total HTTP requests made",
            labels=self.config.labels,
        )

        self._histograms["http_request_duration"] = Histogram(
            f"{ns}_http_request_duration_seconds",
            "HTTP request duration in seconds",
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf")),
            labels=self.config.labels,
        )

    def counter(self, name: str, description: str = "") -> Counter:
        """Get or create a counter metric.

        Args:
            name: Metric name (namespace will be prepended).
            description: Help text for the metric.

        Returns:
            The Counter instance.
        """
        with self._metrics_lock:
            if name not in self._counters:
                full_name = f"{self.config.namespace}_{name}"
                self._counters[name] = Counter(full_name, description, self.config.labels)
            return self._counters[name]

    def gauge(self, name: str, description: str = "") -> Gauge:
        """Get or create a gauge metric.

        Args:
            name: Metric name (namespace will be prepended).
            description: Help text for the metric.

        Returns:
            The Gauge instance.
        """
        with self._metrics_lock:
            if name not in self._gauges:
                full_name = f"{self.config.namespace}_{name}"
                self._gauges[name] = Gauge(full_name, description, self.config.labels)
            return self._gauges[name]

    def histogram(
        self,
        name: str,
        description: str = "",
        buckets: tuple[float, ...] | None = None,
    ) -> Histogram:
        """Get or create a histogram metric.

        Args:
            name: Metric name (namespace will be prepended).
            description: Help text for the metric.
            buckets: Optional custom bucket boundaries.

        Returns:
            The Histogram instance.
        """
        with self._metrics_lock:
            if name not in self._histograms:
                full_name = f"{self.config.namespace}_{name}"
                self._histograms[name] = Histogram(
                    full_name,
                    description,
                    buckets or self.config.histogram_buckets,
                    self.config.labels,
                )
            return self._histograms[name]

    @contextmanager
    def timer(
        self,
        name: str,
        description: str = "",
        buckets: tuple[float, ...] | None = None,
    ) -> Iterator[Timer]:
        """Context manager for timing an operation.

        Args:
            name: Histogram name for recording the timing.
            description: Help text for the histogram.
            buckets: Optional custom bucket boundaries.

        Yields:
            A Timer instance.

        Example:
            >>> with metrics.timer("operation_duration"):
            ...     do_something()
        """
        hist = self.histogram(name, description, buckets)
        timer = Timer(hist)
        with timer:
            yield timer

    def record_journey_start(self, journey_name: str) -> None:
        """Record journey start.

        Args:
            journey_name: Name of the journey being started.
        """
        self._gauges["active_journeys"].inc()
        self._counters["journeys_total"].inc()

    def record_journey_end(
        self,
        journey_name: str,
        success: bool,
        duration_seconds: float,
    ) -> None:
        """Record journey completion.

        Args:
            journey_name: Name of the journey.
            success: Whether the journey succeeded.
            duration_seconds: Duration in seconds.
        """
        self._gauges["active_journeys"].dec()
        self._histograms["journey_duration"].observe(duration_seconds)
        if success:
            self._counters["journeys_success"].inc()
        else:
            self._counters["journeys_failure"].inc()

    def record_step(
        self,
        step_name: str,
        success: bool,
        duration_seconds: float,
    ) -> None:
        """Record step execution.

        Args:
            step_name: Name of the step.
            success: Whether the step succeeded.
            duration_seconds: Duration in seconds.
        """
        self._counters["steps_total"].inc()
        self._histograms["step_duration"].observe(duration_seconds)
        if success:
            self._counters["steps_success"].inc()
        else:
            self._counters["steps_failure"].inc()

    def record_retry(self, step_name: str) -> None:
        """Record a retry attempt.

        Args:
            step_name: Name of the step being retried.
        """
        self._counters["retries_total"].inc()

    def record_http_request(
        self,
        method: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record an HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.).
            status_code: HTTP response status code.
            duration_seconds: Request duration in seconds.
        """
        self._counters["http_requests_total"].inc()
        self._histograms["http_request_duration"].observe(duration_seconds)

    def inc_connections(self) -> None:
        """Increment active connections gauge."""
        self._gauges["active_connections"].inc()

    def dec_connections(self) -> None:
        """Decrement active connections gauge."""
        self._gauges["active_connections"].dec()

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all metric values as a dictionary.

        Returns:
            Dictionary with counters, gauges, and histograms.
        """
        with self._metrics_lock:
            return {
                "counters": {name: c.get() for name, c in self._counters.items()},
                "gauges": {name: g.get() for name, g in self._gauges.items()},
                "histograms": {name: h.get() for name, h in self._histograms.items()},
            }

    def to_prometheus(self) -> str:
        """Export all metrics in Prometheus text format.

        Returns:
            Complete Prometheus exposition format string.
        """
        with self._metrics_lock:
            lines = []

            for counter in self._counters.values():
                lines.append(counter.to_prometheus())
                lines.append("")

            for gauge in self._gauges.values():
                lines.append(gauge.to_prometheus())
                lines.append("")

            for histogram in self._histograms.values():
                lines.append(histogram.to_prometheus())
                lines.append("")

            return "\n".join(lines).strip()

    def to_json(self, indent: int = 2) -> str:
        """Export all metrics as JSON.

        Args:
            indent: JSON indentation level.

        Returns:
            JSON string of all metrics.
        """
        import json

        return json.dumps(self.get_all_metrics(), indent=indent, default=str)

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (primarily for testing)."""
        with cls._lock:
            cls._instance = None


def sanitize_metric_name(name: str) -> str:
    """Sanitize a string for use as a Prometheus metric name.

    Prometheus metric names must match the regex [a-zA-Z_:][a-zA-Z0-9_:]*.

    Args:
        name: The input string to sanitize.

    Returns:
        A sanitized metric name.
    """
    name = re.sub(r"[^a-zA-Z0-9_:]", "_", name)
    name = re.sub(r"^[^a-zA-Z_]", "_", name)
    return name.lower()


def _escape_label_value(value: str) -> str:
    """Escape a label value for Prometheus output.

    Args:
        value: The label value to escape.

    Returns:
        Escaped label value.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
