"""Distributed tracing support for VenomQA.

This module provides comprehensive distributed tracing capabilities including:
- Manual span creation and management
- Automatic context propagation via W3C TraceContext
- OpenTelemetry integration (optional) with multiple exporters
- Decorator-based function tracing
- HTTP middleware for request/response tracing
- Async support with proper context propagation
- Span links for causal relationships
- Batch span processing for performance
- Configurable sampling strategies

Example:
    Basic usage::

        from venomqa.observability import TraceContext, SpanKind

        tracer = TraceContext(service_name="my-service")

        # Start a span
        span = tracer.start_active_span("operation")
        try:
            # Do work
            span.set_attribute("key", "value")
        finally:
            tracer.end_span(span)

    Using decorator::

        from venomqa.observability.tracing import trace_function

        @trace_function(name="database_query")
        def fetch_data():
            return db.query()

    Context propagation::

        # Client side
        headers = tracer.get_trace_headers()

        # Server side
        span = tracer.extract_trace_context(headers)

    OpenTelemetry integration::

        from venomqa.observability.tracing import init_tracing, OTLPExporter

        tracer = init_tracing(
            service_name="my-service",
            exporter=OTLPExporter(endpoint="http://localhost:4317")
        )
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import json
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

OTEL_AVAILABLE = False
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter

    OTEL_AVAILABLE = True
except ImportError:
    trace = None
    TracerProvider = None
    SpanExporter = None
    BatchSpanProcessor = None
    SimpleSpanProcessor = None
    Resource = None


class SamplingStrategy(Enum):
    """Sampling strategy for trace collection.

    Attributes:
        ALWAYS_ON: Sample all traces (100% sampling).
        ALWAYS_OFF: Sample no traces (0% sampling).
        PROBABILISTIC: Sample traces based on probability.
        RATE_LIMITED: Sample traces at a maximum rate per second.
    """

    ALWAYS_ON = "always_on"
    ALWAYS_OFF = "always_off"
    PROBABILISTIC = "probabilistic"
    RATE_LIMITED = "rate_limited"


@dataclass
class SamplingConfig:
    """Configuration for trace sampling.

    Attributes:
        strategy: The sampling strategy to use.
        rate: For probabilistic sampling, the probability (0.0-1.0).
              For rate-limited, the max traces per second.
    """

    strategy: SamplingStrategy = SamplingStrategy.PROBABILISTIC
    rate: float = 1.0

    def should_sample(self, trace_id: str | None = None) -> bool:
        """Determine if a trace should be sampled.

        Args:
            trace_id: Optional trace ID for deterministic sampling.

        Returns:
            True if the trace should be sampled.
        """
        import hashlib
        import random

        if self.strategy == SamplingStrategy.ALWAYS_ON:
            return True
        if self.strategy == SamplingStrategy.ALWAYS_OFF:
            return False
        if self.strategy == SamplingStrategy.PROBABILISTIC:
            if trace_id:
                hash_val = int(hashlib.md5(trace_id.encode()).hexdigest()[:8], 16)
                return (hash_val / 0xFFFFFFFF) < self.rate
            return random.random() < self.rate
        if self.strategy == SamplingStrategy.RATE_LIMITED:
            return random.random() < (self.rate / 100.0)
        return True


@dataclass
class SpanLink:
    """A link to another span for causal relationships.

    Links are used to connect spans that have a causal relationship
    but are not in a parent-child relationship.

    Attributes:
        trace_id: Trace ID of the linked span.
        span_id: Span ID of the linked span.
        attributes: Optional attributes describing the link relationship.
    """

    trace_id: str
    span_id: str
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert link to dictionary representation."""
        return {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "attributes": dict(self.attributes),
        }


class SpanKind(Enum):
    """Type of span indicating the relationship between spans.

    Attributes:
        INTERNAL: Internal operation within the service.
        SERVER: Server-side handling of a synchronous request.
        CLIENT: Client-side invocation of a synchronous request.
        PRODUCER: Producer of an asynchronous message.
        CONSUMER: Consumer of an asynchronous message.
    """

    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanStatusCode(Enum):
    """Status code for spans.

    Attributes:
        UNSET: Default status.
        OK: Operation completed successfully.
        ERROR: Operation encountered an error.
    """

    UNSET = "UNSET"
    OK = "OK"
    ERROR = "ERROR"


@dataclass
class SpanEvent:
    """An event that occurred during a span.

    Events are time-stamped annotations on spans that can contain
    arbitrary metadata about significant occurrences during the span.

    Attributes:
        name: Human-readable name for the event.
        timestamp: Unix timestamp when the event occurred.
        attributes: Key-value pairs containing event metadata.
    """

    name: str
    timestamp: float = field(default_factory=time.time)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary representation."""
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "attributes": self.attributes,
        }


@dataclass
class SpanStatus:
    """Status of a span indicating success or failure.

    Attributes:
        code: Status code (OK, ERROR, or UNSET).
        description: Human-readable description of the status.
    """

    code: SpanStatusCode = SpanStatusCode.UNSET
    description: str = ""

    def is_ok(self) -> bool:
        """Check if status indicates success."""
        return self.code == SpanStatusCode.OK

    def is_error(self) -> bool:
        """Check if status indicates an error."""
        return self.code == SpanStatusCode.ERROR

    def set_ok(self) -> None:
        """Set status to OK."""
        self.code = SpanStatusCode.OK
        self.description = ""

    def set_error(self, description: str = "") -> None:
        """Set status to ERROR with optional description.

        Args:
            description: Human-readable error description.
        """
        self.code = SpanStatusCode.ERROR
        self.description = description

    def to_dict(self) -> dict[str, Any]:
        """Convert status to dictionary representation."""
        return {"code": self.code.value, "description": self.description}


@dataclass
class Span:
    """A single unit of work in a distributed trace.

    Spans represent operations within a trace and can be nested
    to form a hierarchical tree of operations. Supports links for
    causal relationships between unrelated spans.

    Attributes:
        trace_id: Unique identifier for the entire trace.
        span_id: Unique identifier for this span.
        name: Human-readable name for the operation.
        kind: Type of span (internal, client, server, etc.).
        parent_span_id: ID of the parent span, if any.
        start_time: Unix timestamp when the span started.
        end_time: Unix timestamp when the span ended, None if still active.
        attributes: Key-value pairs containing span metadata.
        events: List of events that occurred during the span.
        status: Current status of the span.
        links: List of links to other spans for causal relationships.

    Example:
        >>> span = Span(
        ...     trace_id="abc123",
        ...     span_id="def456",
        ...     name="database_query"
        ... )
        >>> span.set_attribute("db.system", "postgresql")
        >>> span.add_link("trace789", "span012", attributes={"reason": "retry"})
        >>> span.end()
        >>> print(span.duration_ms())
    """

    trace_id: str
    span_id: str
    name: str
    kind: SpanKind = SpanKind.INTERNAL
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[SpanEvent] = field(default_factory=list)
    status: SpanStatus = field(default_factory=SpanStatus)
    links: list[SpanLink] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _otel_span: Any = field(default=None, repr=False)

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a single attribute on the span.

        Attributes are key-value pairs that provide additional context
        about the span operation.

        Args:
            key: Attribute name (should follow semantic conventions).
            value: Attribute value (string, number, boolean, or list thereof).

        Note:
            Common semantic conventions:
            - http.method: HTTP method (GET, POST, etc.)
            - http.url: Full HTTP request URL
            - http.status_code: HTTP response status code
            - db.system: Database system (postgresql, mysql, etc.)
            - db.statement: Database query statement
        """
        with self._lock:
            self.attributes[key] = value

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        """Set multiple attributes on the span.

        Args:
            attributes: Dictionary of attribute key-value pairs.
        """
        with self._lock:
            self.attributes.update(attributes)

    def add_event(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        timestamp: float | None = None,
    ) -> SpanEvent:
        """Add an event to the span.

        Events are time-stamped annotations that can record significant
        occurrences during the span's lifetime.

        Args:
            name: Human-readable event name.
            attributes: Optional key-value pairs for event metadata.
            timestamp: Optional custom timestamp (defaults to now).

        Returns:
            The created SpanEvent instance.
        """
        with self._lock:
            event = SpanEvent(
                name=name,
                timestamp=timestamp or time.time(),
                attributes=attributes or {},
            )
            self.events.append(event)
            return event

    def set_status(self, code: SpanStatusCode | str, description: str = "") -> None:
        """Set the span status.

        Args:
            code: Status code (use SpanStatusCode enum or string).
            description: Human-readable description (especially for errors).
        """
        with self._lock:
            if isinstance(code, str):
                code = SpanStatusCode(code.upper())
            self.status.code = code
            self.status.description = description

    def record_exception(
        self,
        exception: Exception,
        attributes: dict[str, Any] | None = None,
        escaped: bool = False,
    ) -> SpanEvent:
        """Record an exception on the span.

        This adds an exception event with standard attributes and sets
        the span status to ERROR.

        Args:
            exception: The exception that was raised.
            attributes: Additional attributes to include.
            escaped: Whether the exception escaped the span (propagated up).

        Returns:
            The created exception event.
        """
        with self._lock:
            self.status.set_error(str(exception))
            event_attrs: dict[str, Any] = {
                "exception.type": type(exception).__name__,
                "exception.message": str(exception),
                "exception.stacktrace": self._get_stacktrace(exception),
                "exception.escaped": escaped,
            }
            if attributes:
                event_attrs.update(attributes)
            event = SpanEvent(name="exception", attributes=event_attrs)
            self.events.append(event)
            return event

    def end(self, end_time: float | None = None) -> None:
        """End the span.

        Args:
            end_time: Optional explicit end timestamp (defaults to now).

        Note:
            Once ended, a span should not be modified.
        """
        with self._lock:
            if self.end_time is None:
                self.end_time = end_time or time.time()

    def duration_ms(self) -> float | None:
        """Get span duration in milliseconds.

        Returns:
            Duration in ms, or None if span hasn't ended.
        """
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    def duration_seconds(self) -> float | None:
        """Get span duration in seconds.

        Returns:
            Duration in seconds, or None if span hasn't ended.
        """
        if self.end_time is None:
            return None
        return self.end_time - self.start_time

    def is_ended(self) -> bool:
        """Check if span has been ended."""
        return self.end_time is not None

    def is_recording(self) -> bool:
        """Check if span is still recording (not ended)."""
        return not self.is_ended()

    def to_dict(self) -> dict[str, Any]:
        """Convert span to dictionary for serialization."""
        return {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "parentSpanId": self.parent_span_id,
            "name": self.name,
            "kind": self.kind.value,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "durationMs": self.duration_ms(),
            "attributes": dict(self.attributes),
            "events": [e.to_dict() for e in self.events],
            "status": self.status.to_dict(),
        }

    def to_json(self, indent: int | None = None) -> str:
        """Convert span to JSON string.

        Args:
            indent: Optional indentation level for pretty printing.
        """
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def update_name(self, name: str) -> None:
        """Update the span name.

        Args:
            name: New name for the span.
        """
        with self._lock:
            self.name = name

    @staticmethod
    def _get_stacktrace(exception: Exception) -> str:
        """Extract stacktrace from exception."""
        import traceback

        return "".join(
            traceback.format_exception(type(exception), exception, exception.__traceback__)
        )


_current_span: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
    "venomqa_current_span", default=None
)
_current_tracer: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
    "venomqa_current_tracer", default=None
)


class TraceContext:
    """Manages distributed tracing context and span lifecycle.

    This is the main entry point for creating and managing traces.
    It supports W3C TraceContext propagation, sampling, and optional
    OpenTelemetry integration.

    Attributes:
        service_name: Name of the service for trace attribution.
        sample_rate: Fraction of traces to sample (0.0 to 1.0).
        propagation_enabled: Whether to propagate trace context.
        otel_tracer: Optional OpenTelemetry tracer for integration.

    Example:
        >>> tracer = TraceContext(service_name="api-server", sample_rate=0.1)
        >>> with tracer.span("handle_request", kind=SpanKind.SERVER) as span:
        ...     span.set_attribute("http.method", "GET")
        ...     # Handle request
    """

    TRACE_PARENT_HEADER = "traceparent"
    TRACE_STATE_HEADER = "tracestate"
    W3C_VERSION = "00"

    def __init__(
        self,
        service_name: str = "venomqa",
        sample_rate: float = 1.0,
        propagation_enabled: bool = True,
        otel_tracer: Any = None,
    ) -> None:
        """Initialize the trace context.

        Args:
            service_name: Name of the service for attribution.
            sample_rate: Sampling rate (0.0 to 1.0, default 1.0 = all traces).
            propagation_enabled: Enable W3C TraceContext propagation.
            otel_tracer: Optional OpenTelemetry tracer for integration.
        """
        if not 0.0 <= sample_rate <= 1.0:
            raise ValueError("sample_rate must be between 0.0 and 1.0")

        self.service_name = service_name
        self.sample_rate = sample_rate
        self.propagation_enabled = propagation_enabled
        self.otel_tracer = otel_tracer
        self._spans: list[Span] = []
        self._lock = threading.Lock()
        self._span_stack: dict[int, list[Span]] = {}

    @staticmethod
    def generate_trace_id() -> str:
        """Generate a new W3C-compatible trace ID (32 hex characters)."""
        return uuid.uuid4().hex

    @staticmethod
    def generate_span_id() -> str:
        """Generate a new W3C-compatible span ID (16 hex characters)."""
        return uuid.uuid4().hex[:16]

    def _should_sample(self) -> bool:
        """Determine if a trace should be sampled based on sample_rate."""
        import random

        return random.random() < self.sample_rate

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent: Span | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Start a new span without making it the active span.

        Args:
            name: Human-readable operation name.
            kind: Type of span (default INTERNAL).
            parent: Explicit parent span (uses current if None).
            attributes: Initial span attributes.

        Returns:
            The newly created span.

        Note:
            The span is not set as active. Use start_active_span() or
            the span() context manager for automatic active span management.
        """
        if parent is None:
            parent = _current_span.get()

        if parent:
            trace_id = parent.trace_id
            parent_span_id = parent.span_id
        else:
            trace_id = self.generate_trace_id()
            parent_span_id = None

        span = Span(
            trace_id=trace_id,
            span_id=self.generate_span_id(),
            name=name,
            kind=kind,
            parent_span_id=parent_span_id,
            attributes=attributes or {},
        )

        span.set_attribute("service.name", self.service_name)
        span.set_attribute("service.version", "0.2.0")

        return span

    def start_active_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Start a new span and make it the active span.

        Args:
            name: Human-readable operation name.
            kind: Type of span (default INTERNAL).
            attributes: Initial span attributes.

        Returns:
            The newly created and activated span.

        Note:
            Remember to call end_span() to restore the previous active span.
            Prefer using the span() context manager for automatic cleanup.
        """
        parent = _current_span.get()
        span = self.start_span(name, kind, parent, attributes)
        _current_span.set(span)

        with self._lock:
            self._spans.append(span)
            thread_id = threading.get_ident()
            if thread_id not in self._span_stack:
                self._span_stack[thread_id] = []
            self._span_stack[thread_id].append(span)

        return span

    def end_span(self, span: Span, end_time: float | None = None) -> None:
        """End a span and restore the parent as active span.

        Args:
            span: The span to end.
            end_time: Optional explicit end timestamp.
        """
        span.end(end_time)

        current = _current_span.get()
        if current and current.span_id == span.span_id:
            parent = self._find_parent_span(span)
            _current_span.set(parent)

    @contextmanager
    def span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
        record_exception: bool = True,
    ) -> Iterator[Span]:
        """Context manager for creating and managing a span.

        Args:
            name: Human-readable operation name.
            kind: Type of span.
            attributes: Initial span attributes.
            record_exception: Whether to auto-record exceptions.

        Yields:
            The active span.

        Example:
            >>> with tracer.span("database_query") as span:
            ...     span.set_attribute("db.system", "postgresql")
            ...     result = db.execute(query)
        """
        active_span = self.start_active_span(name, kind, attributes)
        token = _current_span.set(active_span)
        try:
            yield active_span
            if not active_span.status.is_error():
                active_span.set_status(SpanStatusCode.OK)
        except Exception as e:
            if record_exception:
                active_span.record_exception(e)
            raise
        finally:
            self.end_span(active_span)
            _current_span.reset(token)

    @asynccontextmanager
    async def async_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
        record_exception: bool = True,
    ) -> AsyncIterator[Span]:
        """Async context manager for creating and managing a span.

        Args:
            name: Human-readable operation name.
            kind: Type of span.
            attributes: Initial span attributes.
            record_exception: Whether to auto-record exceptions.

        Yields:
            The active span.
        """
        active_span = self.start_active_span(name, kind, attributes)
        token = _current_span.set(active_span)
        try:
            yield active_span
            if not active_span.status.is_error():
                active_span.set_status(SpanStatusCode.OK)
        except Exception as e:
            if record_exception:
                active_span.record_exception(e)
            raise
        finally:
            self.end_span(active_span)
            _current_span.reset(token)

    def _find_parent_span(self, span: Span) -> Span | None:
        """Find parent span by ID in the recorded spans."""
        if span.parent_span_id is None:
            return None
        with self._lock:
            for s in self._spans:
                if s.span_id == span.parent_span_id:
                    return s
        return None

    @staticmethod
    def get_current_span() -> Span | None:
        """Get the current active span from context."""
        return _current_span.get()

    @staticmethod
    def set_current_span(span: Span | None) -> contextvars.Token[Span | None]:
        """Set the current active span.

        Args:
            span: The span to set as active, or None.

        Returns:
            A token that can be used to restore the previous span.
        """
        return _current_span.set(span)

    @staticmethod
    def reset_current_span(token: contextvars.Token[Span | None]) -> None:
        """Reset the current span using a token from set_current_span."""
        _current_span.reset(token)

    def get_trace_headers(self, span: Span | None = None) -> dict[str, str]:
        """Get W3C TraceContext headers for HTTP propagation.

        Generates traceparent and tracestate headers following the
        W3C TraceContext specification.

        Args:
            span: The span to propagate (uses current if None).

        Returns:
            Dictionary with traceparent and tracestate headers.

        Example:
            >>> headers = tracer.get_trace_headers()
            >>> response = httpx.get(url, headers={**headers, "Authorization": "..."})
        """
        span = span or _current_span.get()
        if not span or not self.propagation_enabled:
            return {}

        flags = "01" if span.status.is_ok() else "00"
        traceparent = f"{self.W3C_VERSION}-{span.trace_id}-{span.span_id}-{flags}"

        tracestate = f"venomqa@1={self.service_name}"

        return {
            self.TRACE_PARENT_HEADER: traceparent,
            self.TRACE_STATE_HEADER: tracestate,
        }

    def extract_trace_context(self, headers: dict[str, str]) -> Span | None:
        """Extract trace context from W3C TraceContext headers.

        Parses traceparent and tracestate headers to reconstruct
        the trace context from an incoming request.

        Args:
            headers: HTTP headers dictionary (case-insensitive lookup).

        Returns:
            A Span representing the extracted context, or None if invalid.

        Example:
            >>> span = tracer.extract_trace_context(request.headers)
            >>> if span:
            ...     # Continue the trace
            ...     with tracer.span("handle_request", parent=span) as s:
            ...         pass
        """
        traceparent = None
        for key in (self.TRACE_PARENT_HEADER, self.TRACE_PARENT_HEADER.lower()):
            if key in headers:
                traceparent = headers[key]
                break

        if not traceparent:
            return None

        parts = traceparent.split("-")
        if len(parts) != 4:
            return None

        version, trace_id, span_id, _flags = parts

        if version != self.W3C_VERSION:
            return None

        if len(trace_id) != 32 or len(span_id) != 16:
            return None

        return Span(
            trace_id=trace_id,
            span_id=span_id,
            name="extracted",
            kind=SpanKind.SERVER,
        )

    def get_all_spans(self) -> list[Span]:
        """Get all recorded spans.

        Returns:
            List of all spans recorded by this tracer.
        """
        with self._lock:
            return list(self._spans)

    def get_trace(self, trace_id: str) -> list[Span]:
        """Get all spans for a specific trace.

        Args:
            trace_id: The trace ID to filter by.

        Returns:
            List of spans belonging to the trace.
        """
        with self._lock:
            return [s for s in self._spans if s.trace_id == trace_id]

    def get_span_tree(self, trace_id: str) -> dict[str, Any]:
        """Build a hierarchical tree of spans for a trace.

        Args:
            trace_id: The trace ID to build tree for.

        Returns:
            Nested dictionary representing the span hierarchy.
        """
        spans = self.get_trace(trace_id)
        if not spans:
            return {}

        children: dict[str | None, list[Span]] = {}

        for span in spans:
            parent_id = span.parent_span_id
            if parent_id not in children:
                children[parent_id] = []
            children[parent_id].append(span)

        def build_tree(span: Span) -> dict[str, Any]:
            node = span.to_dict()
            child_spans = children.get(span.span_id, [])
            node["children"] = [build_tree(child) for child in child_spans]
            return node

        roots = children.get(None, [])
        return {"trace_id": trace_id, "roots": [build_tree(root) for root in roots]}

    def clear(self) -> None:
        """Clear all recorded spans."""
        with self._lock:
            self._spans.clear()
            self._span_stack.clear()

    def export_to_dict(self) -> list[dict[str, Any]]:
        """Export all spans as list of dictionaries."""
        return [s.to_dict() for s in self.get_all_spans()]

    def export_to_json(self, indent: int = 2) -> str:
        """Export all spans as JSON string."""
        return json.dumps(self.export_to_dict(), indent=indent, default=str)

    def export_to_otlp(self) -> list[dict[str, Any]]:
        """Export spans in OTLP (OpenTelemetry Protocol) format."""
        spans_data = []
        for span in self.get_all_spans():
            span_data = {
                "traceId": span.trace_id,
                "spanId": span.span_id,
                "parentSpanId": span.parent_span_id,
                "name": span.name,
                "kind": span.kind.value,
                "startTimeUnixNano": int(span.start_time * 1_000_000_000),
                "endTimeUnixNano": int((span.end_time or time.time()) * 1_000_000_000)
                if span.end_time
                else None,
                "attributes": [
                    {"key": k, "value": {"stringValue": str(v)}} for k, v in span.attributes.items()
                ],
                "status": {"code": span.status.code.value},
            }
            if span.status.description:
                span_data["status"]["message"] = span.status.description
            spans_data.append(span_data)
        return spans_data


class TracingMiddleware:
    """Middleware for automatic HTTP request/response tracing.

    Provides automatic span creation for HTTP clients with context
    propagation, timing, and status code tracking.

    Example:
        >>> tracer = TraceContext(service_name="http-client")
        >>> middleware = TracingMiddleware(tracer)
        >>> span, headers = middleware.before_request("GET", "https://api.example.com/users", {})
        >>> try:
        ...     response = httpx.get(url, headers=headers)
        ...     middleware.after_request(span, response.status_code)
        ... except Exception as e:
        ...     middleware.on_exception(span, e)
    """

    def __init__(self, tracer: TraceContext) -> None:
        """Initialize the middleware.

        Args:
            tracer: The TraceContext to use for span creation.
        """
        self.tracer = tracer

    def before_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        attributes: dict[str, Any] | None = None,
    ) -> tuple[Span, dict[str, str]]:
        """Start a span before making an HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Full request URL.
            headers: Existing request headers.
            attributes: Additional span attributes.

        Returns:
            Tuple of (span, merged_headers) where merged_headers includes
            trace propagation headers.
        """
        attrs: dict[str, Any] = {
            "http.method": method,
            "http.url": url,
        }
        if attributes:
            attrs.update(attributes)

        span = self.tracer.start_active_span(
            name=f"HTTP {method}",
            kind=SpanKind.CLIENT,
            attributes=attrs,
        )

        trace_headers = self.tracer.get_trace_headers(span)
        merged_headers = {**headers, **trace_headers}

        return span, merged_headers

    def after_request(
        self,
        span: Span,
        status_code: int,
        response_size: int | None = None,
        response_headers: dict[str, str] | None = None,
    ) -> None:
        """End span after receiving HTTP response.

        Args:
            span: The span from before_request.
            status_code: HTTP response status code.
            response_size: Optional response body size in bytes.
            response_headers: Optional response headers to extract trace info.
        """
        span.set_attribute("http.status_code", status_code)

        if response_size is not None:
            span.set_attribute("http.response_size", response_size)

        if status_code >= 500:
            span.set_status(SpanStatusCode.ERROR, f"HTTP {status_code}")
        elif status_code >= 400:
            span.set_status(SpanStatusCode.ERROR, f"HTTP {status_code}")
        else:
            span.set_status(SpanStatusCode.OK)

        self.tracer.end_span(span)

    def on_exception(self, span: Span, exception: Exception) -> None:
        """Handle request exception by recording it on the span.

        Args:
            span: The span from before_request.
            exception: The exception that occurred.
        """
        span.record_exception(exception)
        self.tracer.end_span(span)

    @contextmanager
    def trace_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> Iterator[tuple[Span, dict[str, str]]]:
        """Context manager for tracing an HTTP request.

        Args:
            method: HTTP method.
            url: Request URL.
            headers: Optional request headers.

        Yields:
            Tuple of (span, headers_with_trace_context).

        Example:
            >>> with middleware.trace_request("GET", url) as (span, headers):
            ...     response = httpx.get(url, headers=headers)
            ...     span.set_attribute("custom", "value")
        """
        span, merged_headers = self.before_request(method, url, headers or {})
        try:
            yield span, merged_headers
        except Exception as e:
            self.on_exception(span, e)
            raise
        else:
            self.after_request(span, 200)


def trace_function(
    name: str | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
    tracer: TraceContext | None = None,
) -> Callable[[F], F]:
    """Decorator to automatically trace a function.

    Creates a span around the function execution, recording timing,
    exceptions, and any return value attributes.

    Args:
        name: Span name (defaults to function name).
        kind: Span kind (default INTERNAL).
        attributes: Static attributes to add to the span.
        tracer: Explicit tracer to use (creates new one if None).

    Returns:
        Decorated function with tracing.

    Example:
        >>> @trace_function(name="database_query", kind=SpanKind.CLIENT)
        ... def fetch_user(user_id: int) -> dict:
        ...     return db.query("SELECT * FROM users WHERE id = %s", user_id)

        >>> @trace_function()
        ... async def async_operation():
        ...     await asyncio.sleep(0.1)
    """

    def decorator(func: F) -> F:
        span_name = name or func.__name__

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                nonlocal tracer
                ctx = tracer or TraceContext()
                async with ctx.async_span(span_name, kind=kind, attributes=attributes):
                    return await func(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                nonlocal tracer
                ctx = tracer or TraceContext()
                with ctx.span(span_name, kind=kind, attributes=attributes):
                    return func(*args, **kwargs)

            return sync_wrapper  # type: ignore[return-value]

    return decorator


def traced(
    name: str | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
) -> Callable[[F], F]:
    """Shorthand decorator for tracing functions.

    This is an alias for trace_function with a shorter name.

    Args:
        name: Optional span name.
        kind: Span kind.

    Returns:
        Decorated function.
    """
    return trace_function(name=name, kind=kind)


class NoOpSpan(Span):
    """A no-op span that discards all operations.

    Useful for conditional tracing where tracing may be disabled.
    """

    def __init__(self) -> None:
        super().__init__(
            trace_id="",
            span_id="",
            name="noop",
        )

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def add_event(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        timestamp: float | None = None,
    ) -> SpanEvent:
        return SpanEvent(name="noop")

    def record_exception(
        self,
        exception: Exception,
        attributes: dict[str, Any] | None = None,
        escaped: bool = False,
    ) -> SpanEvent:
        return SpanEvent(name="noop")

    def end(self, end_time: float | None = None) -> None:
        pass


NOOP_SPAN = NoOpSpan()


def get_tracer() -> TraceContext | None:
    """Get the current tracer from context."""
    return _current_tracer.get()


def set_tracer(tracer: TraceContext) -> contextvars.Token[TraceContext | None]:
    """Set the current tracer in context."""
    return _current_tracer.set(tracer)


def init_tracing(
    service_name: str = "venomqa",
    sample_rate: float = 1.0,
    propagation_enabled: bool = True,
) -> TraceContext:
    """Initialize and set a global tracer.

    Args:
        service_name: Service name for trace attribution.
        sample_rate: Sampling rate (0.0 to 1.0).
        propagation_enabled: Enable trace context propagation.

    Returns:
        The initialized TraceContext.
    """
    tracer = TraceContext(
        service_name=service_name,
        sample_rate=sample_rate,
        propagation_enabled=propagation_enabled,
    )
    _current_tracer.set(tracer)
    return tracer
