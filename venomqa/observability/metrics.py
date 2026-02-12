"""Metrics collection for VenomQA with Prometheus-compatible export."""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricValue:
    """A single metric value with labels."""

    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class Counter:
    """A monotonically increasing counter metric."""

    def __init__(
        self, name: str, description: str = "", labels: dict[str, str] | None = None
    ) -> None:
        self.name = name
        self.description = description
        self._labels = labels or {}
        self._value: float = 0.0
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Increment counter by amount."""
        with self._lock:
            self._value += amount

    def labels_set(self, **labels: str) -> Counter:
        """Create a new counter with fixed labels."""
        merged = {**self._labels, **labels}
        counter = Counter(self.name, self.description, merged)
        return counter

    def get(self) -> float:
        """Get current value."""
        with self._lock:
            return self._value

    def to_prometheus(self) -> str:
        """Export in Prometheus format."""
        lines = []
        if self.description:
            lines.append(f"# HELP {self.name} {self.description}")
        lines.append(f"# TYPE {self.name} counter")
        label_str = self._format_labels(self._labels)
        lines.append(f"{self.name}{label_str} {self._value}")
        return "\n".join(lines)

    @staticmethod
    def _format_labels(labels: dict[str, str]) -> str:
        if not labels:
            return ""
        pairs = [f'{k}="{v}"' for k, v in sorted(labels.items())]
        return "{" + ", ".join(pairs) + "}"


class Gauge:
    """A metric that can go up and down."""

    def __init__(
        self, name: str, description: str = "", labels: dict[str, str] | None = None
    ) -> None:
        self.name = name
        self.description = description
        self._labels = labels or {}
        self._value: float = 0.0
        self._lock = threading.Lock()

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        """Set gauge to a specific value."""
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        """Increment gauge by amount."""
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        """Decrement gauge by amount."""
        with self._lock:
            self._value -= amount

    def get(self) -> float:
        """Get current value."""
        with self._lock:
            return self._value

    def to_prometheus(self) -> str:
        """Export in Prometheus format."""
        lines = []
        if self.description:
            lines.append(f"# HELP {self.name} {self.description}")
        lines.append(f"# TYPE {self.name} gauge")
        label_str = Counter._format_labels(self._labels)
        lines.append(f"{self.name}{label_str} {self._value}")
        return "\n".join(lines)


class Histogram:
    """A metric that samples observations into buckets."""

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
        self.name = name
        self.description = description
        self._buckets = buckets or self.DEFAULT_BUCKETS
        self._labels = labels or {}
        self._counts: dict[float, int] = defaultdict(int)
        self._sum: float = 0.0
        self._count: int = 0
        self._lock = threading.Lock()

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        """Record an observation."""
        with self._lock:
            self._sum += value
            self._count += 1
            for bucket in self._buckets:
                if value <= bucket:
                    self._counts[bucket] += 1

    def get(self) -> dict[str, Any]:
        """Get histogram statistics."""
        with self._lock:
            return {
                "count": self._count,
                "sum": self._sum,
                "buckets": dict(self._counts),
            }

    def to_prometheus(self) -> str:
        """Export in Prometheus format."""
        lines = []
        if self.description:
            lines.append(f"# HELP {self.name} {self.description}")
        lines.append(f"# TYPE {self.name} histogram")

        label_str = Counter._format_labels(self._labels)

        cumulative = 0
        for bucket in self._buckets:
            if bucket == float("inf"):
                bucket_str = "+Inf"
            else:
                bucket_str = str(bucket)
            cumulative += self._counts.get(bucket, 0)
            bucket_labels = f'{{le="{bucket_str}"}}'
            if label_str:
                bucket_labels = (
                    f'{{{label_str[1:-1]}, le="{bucket_str}"}}' if label_str else bucket_labels
                )
            lines.append(f"{self.name}_bucket{bucket_labels} {cumulative}")

        lines.append(f"{self.name}_sum{label_str} {self._sum}")
        lines.append(f"{self.name}_count{label_str} {self._count}")
        return "\n".join(lines)


@dataclass
class MetricsConfig:
    """Configuration for metrics collection."""

    namespace: str = "venomqa"
    enable_default_metrics: bool = True
    histogram_buckets: tuple[float, ...] = Histogram.DEFAULT_BUCKETS


class MetricsCollector:
    """Central metrics collection and Prometheus export."""

    _instance: MetricsCollector | None = None
    _lock = threading.Lock()

    def __new__(cls, config: MetricsConfig | None = None) -> MetricsCollector:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, config: MetricsConfig | None = None) -> None:
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
            f"{ns}_journey_duration_ms",
            "Duration of journey execution in milliseconds",
            buckets=(100, 500, 1000, 2500, 5000, 10000, 30000, 60000, float("inf")),
        )

        self._histograms["step_duration"] = Histogram(
            f"{ns}_step_duration_ms",
            "Duration of step execution in milliseconds",
            buckets=(10, 50, 100, 250, 500, 1000, 2500, 5000, float("inf")),
        )

        self._counters["steps_total"] = Counter(
            f"{ns}_steps_total",
            "Total number of steps executed",
        )

        self._counters["steps_success"] = Counter(
            f"{ns}_steps_success_total",
            "Number of successful steps",
        )

        self._counters["steps_failure"] = Counter(
            f"{ns}_steps_failure_total",
            "Number of failed steps",
        )

        self._counters["journeys_total"] = Counter(
            f"{ns}_journeys_total",
            "Total number of journeys executed",
        )

        self._counters["journeys_success"] = Counter(
            f"{ns}_journeys_success_total",
            "Number of successful journeys",
        )

        self._counters["journeys_failure"] = Counter(
            f"{ns}_journeys_failure_total",
            "Number of failed journeys",
        )

        self._gauges["active_connections"] = Gauge(
            f"{ns}_active_connections",
            "Number of active connections",
        )

        self._gauges["active_journeys"] = Gauge(
            f"{ns}_active_journeys",
            "Number of currently running journeys",
        )

        self._counters["retries_total"] = Counter(
            f"{ns}_retries_total",
            "Total number of retries",
        )

        self._counters["http_requests_total"] = Counter(
            f"{ns}_http_requests_total",
            "Total HTTP requests made",
        )

        self._histograms["http_request_duration"] = Histogram(
            f"{ns}_http_request_duration_ms",
            "HTTP request duration in milliseconds",
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
        )

    def counter(self, name: str, description: str = "") -> Counter:
        """Get or create a counter metric."""
        with self._metrics_lock:
            if name not in self._counters:
                full_name = f"{self.config.namespace}_{name}"
                self._counters[name] = Counter(full_name, description)
            return self._counters[name]

    def gauge(self, name: str, description: str = "") -> Gauge:
        """Get or create a gauge metric."""
        with self._metrics_lock:
            if name not in self._gauges:
                full_name = f"{self.config.namespace}_{name}"
                self._gauges[name] = Gauge(full_name, description)
            return self._gauges[name]

    def histogram(
        self, name: str, description: str = "", buckets: tuple[float, ...] | None = None
    ) -> Histogram:
        """Get or create a histogram metric."""
        with self._metrics_lock:
            if name not in self._histograms:
                full_name = f"{self.config.namespace}_{name}"
                self._histograms[name] = Histogram(full_name, description, buckets)
            return self._histograms[name]

    def record_journey_start(self, journey_name: str) -> None:
        """Record journey start."""
        self._gauges["active_journeys"].inc()
        self._counters["journeys_total"].inc()

    def record_journey_end(self, journey_name: str, success: bool, duration_ms: float) -> None:
        """Record journey completion."""
        self._gauges["active_journeys"].dec()
        self._histograms["journey_duration"].observe(duration_ms)
        if success:
            self._counters["journeys_success"].inc()
        else:
            self._counters["journeys_failure"].inc()

    def record_step(self, step_name: str, success: bool, duration_ms: float) -> None:
        """Record step execution."""
        self._counters["steps_total"].inc()
        self._histograms["step_duration"].observe(duration_ms)
        if success:
            self._counters["steps_success"].inc()
        else:
            self._counters["steps_failure"].inc()

    def record_retry(self, step_name: str) -> None:
        """Record a retry attempt."""
        self._counters["retries_total"].inc()

    def record_http_request(self, method: str, status_code: int, duration_ms: float) -> None:
        """Record an HTTP request."""
        self._counters["http_requests_total"].inc()
        self._histograms["http_request_duration"].observe(duration_ms)

    def inc_connections(self) -> None:
        """Increment active connections."""
        self._gauges["active_connections"].inc()

    def dec_connections(self) -> None:
        """Decrement active connections."""
        self._gauges["active_connections"].dec()

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all metric values."""
        with self._metrics_lock:
            return {
                "counters": {name: c.get() for name, c in self._counters.items()},
                "gauges": {name: g.get() for name, g in self._gauges.items()},
                "histograms": {name: h.get() for name, h in self._histograms.items()},
            }

    def to_prometheus(self) -> str:
        """Export all metrics in Prometheus format."""
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

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing)."""
        with cls._lock:
            cls._instance = None


def sanitize_metric_name(name: str) -> str:
    """Sanitize a string for use as a metric name."""
    name = re.sub(r"[^a-zA-Z0-9_:]", "_", name)
    name = re.sub(r"^[^a-zA-Z_]", "_", name)
    return name.lower()
