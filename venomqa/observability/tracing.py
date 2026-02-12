"""Distributed tracing support for VenomQA."""

from __future__ import annotations

import contextvars
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SpanKind(Enum):
    """Type of span."""

    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


@dataclass
class SpanEvent:
    """An event that occurred during a span."""

    name: str
    timestamp: float = field(default_factory=time.time)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpanStatus:
    """Status of a span."""

    code: str = "OK"
    description: str = ""

    def is_ok(self) -> bool:
        return self.code == "OK"

    def set_error(self, description: str) -> None:
        self.code = "ERROR"
        self.description = description


@dataclass
class Span:
    """A single unit of work in a trace."""

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

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    def set_attribute(self, key: str, value: Any) -> None:
        """Set an attribute on the span."""
        with self._lock:
            self.attributes[key] = value

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add an event to the span."""
        with self._lock:
            event = SpanEvent(name=name, attributes=attributes or {})
            self.events.append(event)

    def set_status(self, code: str, description: str = "") -> None:
        """Set the span status."""
        with self._lock:
            self.status.code = code
            self.status.description = description

    def record_exception(
        self, exception: Exception, attributes: dict[str, Any] | None = None
    ) -> None:
        """Record an exception on the span."""
        with self._lock:
            self.status.set_error(str(exception))
            event_attrs = {
                "exception.type": type(exception).__name__,
                "exception.message": str(exception),
                "exception.stacktrace": self._get_stacktrace(exception),
            }
            if attributes:
                event_attrs.update(attributes)
            self.events.append(SpanEvent(name="exception", attributes=event_attrs))

    def end(self, end_time: float | None = None) -> None:
        """End the span."""
        with self._lock:
            self.end_time = end_time or time.time()

    def duration_ms(self) -> float | None:
        """Get span duration in milliseconds."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    def is_ended(self) -> bool:
        """Check if span has ended."""
        return self.end_time is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert span to dictionary."""
        return {
            "traceId": self.trace_id,
            "spanId": self.span_id,
            "parentSpanId": self.parent_span_id,
            "name": self.name,
            "kind": self.kind.value,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "durationMs": self.duration_ms(),
            "attributes": self.attributes,
            "events": [
                {"name": e.name, "timestamp": e.timestamp, "attributes": e.attributes}
                for e in self.events
            ],
            "status": {"code": self.status.code, "description": self.status.description},
        }

    def to_json(self) -> str:
        """Convert span to JSON."""
        return json.dumps(self.to_dict())

    @staticmethod
    def _get_stacktrace(exception: Exception) -> str:
        import traceback

        return "".join(
            traceback.format_exception(type(exception), exception, exception.__traceback__)
        )


_current_span: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
    "current_span", default=None
)


class TraceContext:
    """Manages distributed tracing context."""

    TRACE_PARENT_HEADER = "traceparent"
    TRACE_STATE_HEADER = "tracestate"

    def __init__(
        self,
        service_name: str = "venomqa",
        sample_rate: float = 1.0,
        propagation_enabled: bool = True,
    ) -> None:
        self.service_name = service_name
        self.sample_rate = sample_rate
        self.propagation_enabled = propagation_enabled
        self._spans: list[Span] = []
        self._lock = threading.Lock()

    @staticmethod
    def generate_trace_id() -> str:
        """Generate a new trace ID."""
        return uuid.uuid4().hex

    @staticmethod
    def generate_span_id() -> str:
        """Generate a new span ID."""
        return uuid.uuid4().hex[:16]

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        parent: Span | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Start a new span."""
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
        return span

    def start_active_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Start a new span and make it the active span."""
        parent = _current_span.get()
        span = self.start_span(name, kind, parent, attributes)
        _current_span.set(span)

        with self._lock:
            self._spans.append(span)

        return span

    def end_span(self, span: Span) -> None:
        """End a span and restore parent as active."""
        span.end()

        current = _current_span.get()
        if current and current.span_id == span.span_id:
            parent = self._find_parent_span(span)
            _current_span.set(parent)

    def _find_parent_span(self, span: Span) -> Span | None:
        """Find parent span by ID."""
        if span.parent_span_id is None:
            return None
        with self._lock:
            for s in self._spans:
                if s.span_id == span.parent_span_id:
                    return s
        return None

    @staticmethod
    def get_current_span() -> Span | None:
        """Get the current active span."""
        return _current_span.get()

    @staticmethod
    def set_current_span(span: Span | None) -> None:
        """Set the current active span."""
        _current_span.set(span)

    def get_trace_headers(self, span: Span | None = None) -> dict[str, str]:
        """Get trace headers for HTTP propagation."""
        span = span or _current_span.get()
        if not span or not self.propagation_enabled:
            return {}

        traceparent = f"00-{span.trace_id}-{span.span_id}-01"

        tracestate = f"venomqa@1={self.service_name}"

        return {
            self.TRACE_PARENT_HEADER: traceparent,
            self.TRACE_STATE_HEADER: tracestate,
        }

    def extract_trace_context(self, headers: dict[str, str]) -> Span | None:
        """Extract trace context from HTTP headers."""
        traceparent = headers.get(self.TRACE_PARENT_HEADER)
        if not traceparent:
            return None

        parts = traceparent.split("-")
        if len(parts) != 4:
            return None

        version, trace_id, span_id, flags = parts

        if version != "00":
            return None

        return Span(
            trace_id=trace_id,
            span_id=span_id,
            name="extracted",
            kind=SpanKind.SERVER,
        )

    def get_all_spans(self) -> list[Span]:
        """Get all recorded spans."""
        with self._lock:
            return list(self._spans)

    def get_trace(self, trace_id: str) -> list[Span]:
        """Get all spans for a trace."""
        with self._lock:
            return [s for s in self._spans if s.trace_id == trace_id]

    def clear(self) -> None:
        """Clear all recorded spans."""
        with self._lock:
            self._spans.clear()

    def export_to_dict(self) -> list[dict[str, Any]]:
        """Export all spans as dictionaries."""
        return [s.to_dict() for s in self.get_all_spans()]

    def export_to_json(self) -> str:
        """Export all spans as JSON."""
        return json.dumps(self.export_to_dict(), indent=2)


class TracingMiddleware:
    """Middleware for automatic HTTP request tracing."""

    def __init__(self, tracer: TraceContext) -> None:
        self.tracer = tracer

    def before_request(
        self, method: str, url: str, headers: dict[str, str]
    ) -> tuple[Span, dict[str, str]]:
        """Start a span before making a request."""
        span = self.tracer.start_active_span(
            name=f"HTTP {method} {url}",
            kind=SpanKind.CLIENT,
            attributes={"http.method": method, "http.url": url},
        )

        trace_headers = self.tracer.get_trace_headers(span)
        merged_headers = {**headers, **trace_headers}

        return span, merged_headers

    def after_request(
        self,
        span: Span,
        status_code: int,
        response_size: int | None = None,
    ) -> None:
        """End span after receiving response."""
        span.set_attribute("http.status_code", status_code)

        if response_size is not None:
            span.set_attribute("http.response_size", response_size)

        if status_code >= 400:
            span.set_status("ERROR", f"HTTP {status_code}")

        self.tracer.end_span(span)

    def on_exception(self, span: Span, exception: Exception) -> None:
        """Handle request exception."""
        span.record_exception(exception)
        self.tracer.end_span(span)


def trace_function(name: str | None = None, kind: SpanKind = SpanKind.INTERNAL):
    """Decorator to trace a function."""

    def decorator(func):
        import functools

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = TraceContext()
            span_name = name or func.__name__
            span = tracer.start_active_span(span_name, kind=kind)
            try:
                result = func(*args, **kwargs)
                span.set_status("OK")
                return result
            except Exception as e:
                span.record_exception(e)
                raise
            finally:
                tracer.end_span(span)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = TraceContext()
            span_name = name or func.__name__
            span = tracer.start_active_span(span_name, kind=kind)
            try:
                result = await func(*args, **kwargs)
                span.set_status("OK")
                return result
            except Exception as e:
                span.record_exception(e)
                raise
            finally:
                tracer.end_span(span)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
