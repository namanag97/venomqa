"""Observability module for VenomQA - metrics, tracing, logging, and health checks.

This module provides comprehensive observability capabilities for VenomQA:

- **Metrics**: Prometheus-compatible counters, gauges, and histograms
- **Tracing**: Distributed tracing with W3C TraceContext support
- **Logging**: Structured JSON logging with context support
- **Health**: Kubernetes-compatible health check endpoints

Example:
    Basic usage::

        from venomqa.observability import (
            MetricsCollector,
            TraceContext,
            get_logger,
            HealthCheck,
        )

        # Metrics
        metrics = MetricsCollector()
        metrics.counter("requests").inc()

        # Tracing
        tracer = TraceContext(service_name="my-service")
        with tracer.span("operation") as span:
            span.set_attribute("key", "value")

        # Logging
        logger = get_logger("myapp")
        logger.info("Request processed", duration_ms=45)

        # Health checks
        health = HealthCheck()
        readiness = health.readiness()

    Integration with OpenTelemetry::

        from venomqa.observability.tracing import OTEL_AVAILABLE, init_tracing

        if OTEL_AVAILABLE:
            # OpenTelemetry is installed, use it
            pass
"""

from venomqa.observability.health import (
    HealthCheck,
    HealthCheckResult,
    HealthStatus,
    create_database_health_check,
    create_disk_health_check,
    create_http_health_check,
    create_memory_health_check,
    create_redis_health_check,
    create_tcp_health_check,
)
from venomqa.observability.logging import (
    BoundLogger,
    HumanReadableFormatter,
    StructuredFormatter,
    StructuredLogger,
    add_context,
    clear_context,
    configure_logging,
    get_context,
    get_logger,
    log_context,
)
from venomqa.observability.metrics import (
    Counter,
    Gauge,
    Histogram,
    LabeledCounter,
    LabeledGauge,
    LabeledHistogram,
    MetricsCollector,
    MetricsConfig,
    Timer,
    sanitize_metric_name,
)
from venomqa.observability.tracing import (
    OTEL_AVAILABLE,
    NoOpSpan,
    Span,
    SpanEvent,
    SpanKind,
    SpanStatus,
    SpanStatusCode,
    TraceContext,
    TracingMiddleware,
    get_tracer,
    init_tracing,
    set_tracer,
    trace_function,
    traced,
)

__all__ = [
    "MetricsCollector",
    "MetricsConfig",
    "Counter",
    "Gauge",
    "Histogram",
    "LabeledCounter",
    "LabeledGauge",
    "LabeledHistogram",
    "Timer",
    "sanitize_metric_name",
    "StructuredLogger",
    "StructuredFormatter",
    "HumanReadableFormatter",
    "BoundLogger",
    "get_logger",
    "configure_logging",
    "log_context",
    "get_context",
    "add_context",
    "clear_context",
    "TraceContext",
    "TracingMiddleware",
    "Span",
    "SpanKind",
    "SpanStatus",
    "SpanStatusCode",
    "SpanEvent",
    "NoOpSpan",
    "trace_function",
    "traced",
    "get_tracer",
    "set_tracer",
    "init_tracing",
    "OTEL_AVAILABLE",
    "HealthCheck",
    "HealthCheckResult",
    "HealthStatus",
    "create_database_health_check",
    "create_http_health_check",
    "create_tcp_health_check",
    "create_memory_health_check",
    "create_disk_health_check",
    "create_redis_health_check",
]
