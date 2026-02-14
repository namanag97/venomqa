"""Debug utilities for enhanced error messages and troubleshooting.

This module provides comprehensive debugging capabilities including:
- Detailed error context formatting
- Actionable troubleshooting suggestions
- Filtered stack traces showing user code
- Debug logging for HTTP requests, SQL queries, and timing

Example:
    >>> from venomqa.errors.debug import DebugContext, ErrorFormatter
    >>>
    >>> # Create debug context for step failure
    >>> debug_ctx = DebugContext(
    ...     step_name="login",
    ...     journey_name="user_auth",
    ...     request={"method": "POST", "url": "/api/login"},
    ...     response={"status_code": 401}
    ... )
    >>>
    >>> # Format with suggestions
    >>> formatter = ErrorFormatter(debug_ctx)
    >>> print(formatter.format())
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from venomqa.errors.base import VenomQAError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# Common HTTP error patterns and their troubleshooting suggestions
ERROR_SUGGESTIONS: dict[str, dict[str, str]] = {
    # Connection errors
    "connection refused": {
        "cause": "The service is not accepting connections on the specified port.",
        "suggestion": "Is the service running? Check with `docker ps` or `systemctl status <service>`.",
        "actions": [
            "Verify the service is started: `docker-compose up -d`",
            "Check if the port is correct in your configuration",
            "Ensure no firewall is blocking the connection",
            "Try connecting manually: `curl http://localhost:<port>/health`",
        ],
    },
    "connection reset": {
        "cause": "The connection was forcibly closed by the server.",
        "suggestion": "The service may have crashed or hit a resource limit.",
        "actions": [
            "Check service logs for crashes: `docker logs <container>`",
            "Verify service memory/CPU limits",
            "Look for connection timeout settings",
        ],
    },
    "connection timeout": {
        "cause": "Could not establish a connection within the timeout period.",
        "suggestion": "The service may be overloaded or unreachable.",
        "actions": [
            "Increase the connection timeout in your config",
            "Check network connectivity to the service",
            "Verify DNS resolution is working",
            "Check if the service is under heavy load",
        ],
    },
    "name resolution": {
        "cause": "DNS lookup failed for the hostname.",
        "suggestion": "The hostname cannot be resolved to an IP address.",
        "actions": [
            "Verify the hostname is correct",
            "Check DNS configuration",
            "Try using IP address directly",
            "Check /etc/hosts for local overrides",
        ],
    },
    "ssl": {
        "cause": "SSL/TLS handshake or certificate verification failed.",
        "suggestion": "Certificate issues or protocol mismatch.",
        "actions": [
            "Check if certificate is valid and not expired",
            "Verify SSL certificate chain is complete",
            "Try with `verify_ssl=False` for testing (not production)",
            "Ensure TLS versions match between client and server",
        ],
    },
    # HTTP status codes
    "400": {
        "cause": "Bad Request - The server cannot process the request due to client error.",
        "suggestion": "Check request body format and required fields.",
        "actions": [
            "Validate JSON structure against API schema",
            "Check for missing required fields",
            "Verify Content-Type header matches body format",
            "Look for invalid characters in the request",
        ],
    },
    "401": {
        "cause": "Unauthorized - Authentication credentials are missing or invalid.",
        "suggestion": "Check authentication token or credentials.",
        "actions": [
            "Verify the token is included in Authorization header",
            "Check if the token has expired",
            "Ensure token format is correct (e.g., 'Bearer <token>')",
            "Re-authenticate to get a fresh token",
        ],
    },
    "403": {
        "cause": "Forbidden - The user does not have permission for this action.",
        "suggestion": "Check user roles and permissions.",
        "actions": [
            "Verify the user has the required role",
            "Check if the resource belongs to the user",
            "Review permission configuration",
            "Try with an admin/superuser account",
        ],
    },
    "404": {
        "cause": "Not Found - The requested resource does not exist.",
        "suggestion": "Check endpoint path and resource ID.",
        "actions": [
            "Verify the URL path is correct",
            "Check if the resource was created before accessing",
            "Ensure route is registered in the application",
            "Look for typos in the endpoint path",
        ],
    },
    "405": {
        "cause": "Method Not Allowed - HTTP method not supported for this endpoint.",
        "suggestion": "Check if the correct HTTP method is used.",
        "actions": [
            "Verify the API documentation for allowed methods",
            "Check for GET vs POST mismatch",
            "Ensure the route handler exists for this method",
        ],
    },
    "409": {
        "cause": "Conflict - Request conflicts with current resource state.",
        "suggestion": "Check for duplicate entries or state conflicts.",
        "actions": [
            "Verify the resource doesn't already exist",
            "Check for unique constraint violations",
            "Review optimistic locking/version conflicts",
        ],
    },
    "422": {
        "cause": "Unprocessable Entity - Validation failed for the request.",
        "suggestion": "Check request data against validation rules.",
        "actions": [
            "Review field validation rules in the API",
            "Check data types match expectations",
            "Verify string lengths, number ranges, etc.",
            "Look at the response body for specific field errors",
        ],
    },
    "429": {
        "cause": "Too Many Requests - Rate limit exceeded.",
        "suggestion": "Reduce request frequency or wait before retrying.",
        "actions": [
            "Add delays between requests",
            "Check Retry-After header for wait time",
            "Implement exponential backoff",
            "Request a higher rate limit if needed",
        ],
    },
    "500": {
        "cause": "Internal Server Error - An unhandled error occurred on the server.",
        "suggestion": "Check backend logs for exception traceback.",
        "actions": [
            "Review server logs: `docker logs <container>`",
            "Look for stack traces in error responses",
            "Check if database is accessible",
            "Verify external service dependencies",
        ],
    },
    "502": {
        "cause": "Bad Gateway - The upstream server returned an invalid response.",
        "suggestion": "Check upstream service availability.",
        "actions": [
            "Verify all backend services are running",
            "Check for network issues between services",
            "Review proxy/load balancer configuration",
        ],
    },
    "503": {
        "cause": "Service Unavailable - The service is temporarily unavailable.",
        "suggestion": "The service may be overloaded or under maintenance.",
        "actions": [
            "Check service health endpoints",
            "Verify service has adequate resources",
            "Look for deployment or restart in progress",
            "Check circuit breaker status",
        ],
    },
    "504": {
        "cause": "Gateway Timeout - The upstream server did not respond in time.",
        "suggestion": "The upstream service is too slow to respond.",
        "actions": [
            "Increase gateway/proxy timeout",
            "Check upstream service performance",
            "Look for slow database queries",
            "Consider caching or pagination",
        ],
    },
    # Timeout errors
    "timeout": {
        "cause": "The operation did not complete within the allowed time.",
        "suggestion": "The service may be slow or unresponsive.",
        "actions": [
            "Increase timeout in configuration",
            "Check if service is under heavy load",
            "Verify network latency",
            "Look for slow database queries or external calls",
        ],
    },
    "read timeout": {
        "cause": "No data received from server within timeout period.",
        "suggestion": "The server is taking too long to respond.",
        "actions": [
            "Increase read timeout",
            "Check for long-running operations on server",
            "Consider async/background processing for heavy tasks",
        ],
    },
    # Validation errors
    "validation": {
        "cause": "Request data failed validation rules.",
        "suggestion": "Check input data matches expected format.",
        "actions": [
            "Review field requirements in API docs",
            "Check for required vs optional fields",
            "Verify data types and formats",
        ],
    },
    "schema": {
        "cause": "Response does not match expected schema.",
        "suggestion": "The API response structure has changed.",
        "actions": [
            "Update response schema expectations",
            "Check API version compatibility",
            "Review response body for actual structure",
        ],
    },
    # Database errors
    "unique constraint": {
        "cause": "Duplicate value violates unique constraint.",
        "suggestion": "A record with this value already exists.",
        "actions": [
            "Check for existing record with same key",
            "Generate unique values for test data",
            "Clean up test data between runs",
        ],
    },
    "foreign key": {
        "cause": "Referenced record does not exist.",
        "suggestion": "Create the referenced record first.",
        "actions": [
            "Ensure parent records are created before children",
            "Check cascade delete settings",
            "Verify relationship order in test setup",
        ],
    },
}


class DebugLevel(Enum):
    """Debug verbosity levels."""

    OFF = 0
    BASIC = 1
    DETAILED = 2
    VERBOSE = 3


@dataclass
class DebugContext:
    """Rich context for debugging failed operations.

    Captures comprehensive state at the time of failure including
    request/response data, database state, and execution context.

    Attributes:
        step_name: Name of the step that failed.
        journey_name: Name of the journey being executed.
        path_name: Name of the current path (if in a branch).
        request: Full request data (method, URL, headers, body).
        response: Full response data (status, headers, body).
        database_state: Relevant database tables/rows at failure.
        context_data: Execution context variables.
        stack_trace: Filtered stack trace (user code only).
        timing: Timing information for the operation.
        suggestions: Auto-generated troubleshooting suggestions.
        timestamp: When the failure occurred.
    """

    step_name: str = ""
    journey_name: str = ""
    path_name: str = "main"
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    database_state: dict[str, Any] | None = None
    context_data: dict[str, Any] = field(default_factory=dict)
    stack_trace: str = ""
    timing: dict[str, float] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    error_message: str = ""
    error_type: str = ""
    http_status: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "step_name": self.step_name,
            "journey_name": self.journey_name,
            "path_name": self.path_name,
            "request": self.request,
            "response": self.response,
            "database_state": self.database_state,
            "context_data": self.context_data,
            "stack_trace": self.stack_trace,
            "timing": self.timing,
            "suggestions": self.suggestions,
            "timestamp": self.timestamp.isoformat(),
            "error_message": self.error_message,
            "error_type": self.error_type,
            "http_status": self.http_status,
        }


class StackTraceFilter:
    """Filters stack traces to highlight user code and hide framework internals.

    Provides clean stack traces that focus on the test code rather than
    framework implementation details.
    """

    # Patterns for framework code to hide
    FRAMEWORK_PATTERNS = [
        "site-packages",
        "venomqa/runner",
        "venomqa/client",
        "venomqa/errors",
        "venomqa/core",
        "httpx",
        "urllib3",
        "asyncio",
        "concurrent/futures",
        "threading",
        "_pytest",
        "pluggy",
        "<frozen",
    ]

    # Patterns for user code to highlight
    USER_PATTERNS = [
        "journeys/",
        "actions/",
        "fixtures/",
        "tests/",
        "test_",
        "_test.py",
    ]

    @classmethod
    def filter_traceback(
        cls,
        tb: str | None = None,
        show_framework: bool = False,
    ) -> str:
        """Filter a traceback to show relevant user code.

        Args:
            tb: Traceback string. If None, captures current exception.
            show_framework: If True, includes framework code marked as [framework].

        Returns:
            Filtered traceback string.
        """
        if tb is None:
            tb = traceback.format_exc()

        lines = tb.split("\n")
        filtered_lines: list[str] = []
        skip_next = False
        in_user_code = False

        for i, line in enumerate(lines):
            # Check if this is a file location line
            if line.strip().startswith("File "):
                is_framework = any(p in line for p in cls.FRAMEWORK_PATTERNS)
                is_user = any(p in line for p in cls.USER_PATTERNS)

                if is_user:
                    in_user_code = True
                    filtered_lines.append(f"  >>> {line.strip()}")  # Highlight user code
                    skip_next = False
                elif is_framework and not show_framework:
                    in_user_code = False
                    skip_next = True  # Skip the following code line too
                    continue
                else:
                    in_user_code = False
                    if show_framework:
                        filtered_lines.append(f"      {line.strip()}  [framework]")
                        skip_next = False
                    else:
                        skip_next = True
                        continue
            elif skip_next and line.strip() and not line.strip().startswith(
                ("File ", "Traceback", "During")
            ):
                skip_next = False
                continue
            elif line.strip().startswith(("Traceback", "During handling")):
                filtered_lines.append(line)
            elif line.strip() and not skip_next:
                # This is either the error message or code line
                if in_user_code or not any(p in lines[i - 1] if i > 0 else "" for p in cls.FRAMEWORK_PATTERNS):
                    filtered_lines.append(line)

        return "\n".join(filtered_lines)

    @classmethod
    def get_user_frame(cls) -> tuple[str, int, str] | None:
        """Get the first user code frame from current stack.

        Returns:
            Tuple of (filename, lineno, function) or None if not found.
        """
        for frame_info in inspect.stack():
            filename = frame_info.filename
            if any(p in filename for p in cls.USER_PATTERNS) and not any(
                p in filename for p in cls.FRAMEWORK_PATTERNS
            ):
                return (filename, frame_info.lineno, frame_info.function)
        return None


class TroubleshootingEngine:
    """Generates actionable troubleshooting suggestions based on error patterns."""

    @classmethod
    def get_suggestions(
        cls,
        error: str | Exception,
        http_status: int | None = None,
        response_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get troubleshooting suggestions for an error.

        Args:
            error: Error message or exception.
            http_status: HTTP status code if applicable.
            response_body: Response body if available.

        Returns:
            Dict with 'cause', 'suggestion', and 'actions' keys.
        """
        error_str = str(error).lower()
        result: dict[str, Any] = {
            "cause": "Unknown error occurred.",
            "suggestion": "Review the error details and check system logs.",
            "actions": [],
        }

        # Check HTTP status code first (most specific)
        if http_status:
            status_str = str(http_status)
            if status_str in ERROR_SUGGESTIONS:
                result = ERROR_SUGGESTIONS[status_str].copy()
                # Add response body info if available
                if response_body:
                    result["response_hint"] = cls._extract_response_hint(response_body)
                return result

        # Check for specific error patterns
        for pattern, suggestion_data in ERROR_SUGGESTIONS.items():
            if pattern in error_str:
                result = suggestion_data.copy()
                break

        return result

    @classmethod
    def _extract_response_hint(cls, response_body: dict[str, Any]) -> str:
        """Extract useful hint from response body."""
        hints = []

        # Common error field names
        for key in ["detail", "message", "error", "errors", "msg"]:
            if key in response_body:
                value = response_body[key]
                if isinstance(value, str):
                    hints.append(value)
                elif isinstance(value, list):
                    hints.extend(str(v) for v in value[:3])
                elif isinstance(value, dict):
                    hints.append(json.dumps(value, indent=2)[:200])

        return "; ".join(hints) if hints else ""


class ErrorFormatter:
    """Formats errors with rich context for display.

    Provides multiple output formats (CLI, log, JSON) with
    consistent structure and helpful information.
    """

    BORDER_CHAR = "="
    SECTION_CHAR = "-"

    def __init__(
        self,
        debug_context: DebugContext,
        use_color: bool = True,
        verbose: bool = False,
    ) -> None:
        """Initialize formatter.

        Args:
            debug_context: The debug context containing error details.
            use_color: Whether to use ANSI colors in output.
            verbose: Whether to include extra details.
        """
        self.ctx = debug_context
        self.use_color = use_color
        self.verbose = verbose

    def _color(self, text: str, color: str) -> str:
        """Apply ANSI color if enabled."""
        if not self.use_color:
            return text

        colors = {
            "red": "\033[91m",
            "green": "\033[92m",
            "yellow": "\033[93m",
            "blue": "\033[94m",
            "cyan": "\033[96m",
            "white": "\033[97m",
            "bold": "\033[1m",
            "dim": "\033[2m",
            "reset": "\033[0m",
        }
        return f"{colors.get(color, '')}{text}{colors['reset']}"

    def format(self) -> str:
        """Format the error for CLI display."""
        lines: list[str] = []

        # Header
        header = f" STEP FAILED: {self.ctx.step_name} "
        border = self.BORDER_CHAR * 60
        lines.append(self._color(border, "red"))
        lines.append(self._color(header.center(60, self.BORDER_CHAR), "red"))
        lines.append(self._color(border, "red"))
        lines.append("")

        # Location
        lines.append(self._color("Location:", "bold"))
        lines.append(f"  Journey: {self.ctx.journey_name}")
        lines.append(f"  Path:    {self.ctx.path_name}")
        lines.append(f"  Step:    {self.ctx.step_name}")
        lines.append(f"  Time:    {self.ctx.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Error
        lines.append(self._color("Error:", "bold"))
        lines.append(f"  Type: {self._color(self.ctx.error_type, 'yellow')}")
        lines.append(f"  Message: {self._color(self.ctx.error_message, 'red')}")
        lines.append("")

        # Request (if available)
        if self.ctx.request:
            lines.append(self._color("Request:", "bold"))
            lines.append(self._format_request())
            lines.append("")

        # Response (if available)
        if self.ctx.response:
            lines.append(self._color("Response:", "bold"))
            lines.append(self._format_response())
            lines.append("")

        # Timing (if available)
        if self.ctx.timing:
            lines.append(self._color("Timing:", "bold"))
            for name, duration in self.ctx.timing.items():
                lines.append(f"  {name}: {duration:.2f}ms")
            lines.append("")

        # Database state (if available and verbose)
        if self.verbose and self.ctx.database_state:
            lines.append(self._color("Database State:", "bold"))
            lines.append(self._format_dict(self.ctx.database_state, indent=2))
            lines.append("")

        # Stack trace (filtered)
        if self.ctx.stack_trace:
            lines.append(self._color("Stack Trace (user code):", "bold"))
            for line in self.ctx.stack_trace.split("\n"):
                if line.strip():
                    if ">>>" in line:
                        lines.append(self._color(line, "cyan"))
                    else:
                        lines.append(self._color(f"  {line}", "dim"))
            lines.append("")

        # Troubleshooting
        if self.ctx.suggestions:
            lines.append(self._color("Troubleshooting:", "bold"))
            for suggestion in self.ctx.suggestions:
                lines.append(f"  - {suggestion}")
            lines.append("")

        # Get detailed suggestions
        suggestions = TroubleshootingEngine.get_suggestions(
            self.ctx.error_message,
            self.ctx.http_status,
            self.ctx.response.get("body") if self.ctx.response else None,
        )

        lines.append(self._color("Possible Cause:", "bold"))
        lines.append(f"  {suggestions.get('cause', 'Unknown')}")
        lines.append("")
        lines.append(self._color("Suggested Fix:", "bold"))
        lines.append(f"  {suggestions.get('suggestion', 'Review logs')}")
        lines.append("")

        if suggestions.get("actions"):
            lines.append(self._color("Actions to Try:", "bold"))
            for action in suggestions["actions"]:
                lines.append(f"  {self._color('[>]', 'green')} {action}")
            lines.append("")

        lines.append(self._color(border, "red"))

        return "\n".join(lines)

    def _format_request(self) -> str:
        """Format request data for display."""
        if not self.ctx.request:
            return "  (no request data)"

        lines = []
        req = self.ctx.request

        method = req.get("method", "?")
        url = req.get("url", "?")
        lines.append(f"  {self._color(method, 'cyan')} {url}")

        if self.verbose and req.get("headers"):
            lines.append("  Headers:")
            for k, v in req["headers"].items():
                # Mask sensitive headers
                if k.lower() in ("authorization", "x-api-key", "cookie"):
                    v = "[REDACTED]"
                lines.append(f"    {k}: {v}")

        if req.get("body"):
            lines.append("  Body:")
            body_str = self._format_body(req["body"])
            for line in body_str.split("\n"):
                lines.append(f"    {line}")

        return "\n".join(lines)

    def _format_response(self) -> str:
        """Format response data for display."""
        if not self.ctx.response:
            return "  (no response data)"

        lines = []
        resp = self.ctx.response

        status = resp.get("status_code", "?")
        status_color = "green" if 200 <= int(status or 0) < 300 else "red"
        lines.append(f"  Status: {self._color(str(status), status_color)}")

        if self.verbose and resp.get("headers"):
            lines.append("  Headers:")
            for k, v in list(resp["headers"].items())[:10]:
                lines.append(f"    {k}: {v}")

        if resp.get("body"):
            lines.append("  Body:")
            body_str = self._format_body(resp["body"])
            # Truncate long responses
            if len(body_str) > 500:
                body_str = body_str[:500] + "... [truncated]"
            for line in body_str.split("\n"):
                lines.append(f"    {line}")

        return "\n".join(lines)

    def _format_body(self, body: Any) -> str:
        """Format request/response body."""
        if isinstance(body, str):
            try:
                parsed = json.loads(body)
                return json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                return body
        elif isinstance(body, (dict, list)):
            return json.dumps(body, indent=2, default=str)
        return str(body)

    def _format_dict(self, d: dict[str, Any], indent: int = 0) -> str:
        """Format a dictionary for display."""
        prefix = " " * indent
        return prefix + json.dumps(d, indent=2, default=str).replace("\n", f"\n{prefix}")

    def to_json(self) -> str:
        """Format error as JSON for structured logging."""
        return json.dumps(self.ctx.to_dict(), indent=2, default=str)


class DebugLogger:
    """Debug logger for capturing detailed execution information.

    Logs HTTP requests/responses, SQL queries, and timing information
    to a file and/or console based on configuration.
    """

    _instance: DebugLogger | None = None
    _lock = threading.Lock()

    def __init__(
        self,
        enabled: bool = False,
        log_file: str | Path | None = None,
        level: DebugLevel = DebugLevel.BASIC,
    ) -> None:
        """Initialize debug logger.

        Args:
            enabled: Whether debug logging is enabled.
            log_file: Path to debug log file. None for console only.
            level: Debug verbosity level.
        """
        self.enabled = enabled
        self.level = level
        self._log_file: Path | None = Path(log_file) if log_file else None
        self._file_handle: Any = None
        self._start_time = time.time()
        self._request_count = 0
        self._query_count = 0

    @classmethod
    def get_instance(cls) -> DebugLogger:
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def configure(
        cls,
        enabled: bool = True,
        log_file: str | Path | None = None,
        level: DebugLevel = DebugLevel.BASIC,
    ) -> DebugLogger:
        """Configure and return the debug logger."""
        with cls._lock:
            cls._instance = cls(enabled=enabled, log_file=log_file, level=level)
            if log_file and enabled:
                cls._instance._open_file()
        return cls._instance

    def _open_file(self) -> None:
        """Open log file for writing."""
        if self._log_file:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            self._file_handle = open(self._log_file, "a", encoding="utf-8")
            self._write_header()

    def _write_header(self) -> None:
        """Write log file header."""
        if self._file_handle:
            self._file_handle.write(f"\n{'=' * 60}\n")
            self._file_handle.write(f"VenomQA Debug Log - {datetime.now().isoformat()}\n")
            self._file_handle.write(f"{'=' * 60}\n\n")
            self._file_handle.flush()

    def _log(self, message: str, level: DebugLevel = DebugLevel.BASIC) -> None:
        """Write a log message."""
        if not self.enabled or level.value > self.level.value:
            return

        elapsed = time.time() - self._start_time
        timestamp = f"[{elapsed:8.3f}s]"
        full_message = f"{timestamp} {message}\n"

        # Write to file
        if self._file_handle:
            self._file_handle.write(full_message)
            self._file_handle.flush()

        # Write to console if verbose
        if self.level.value >= DebugLevel.DETAILED.value:
            sys.stderr.write(full_message)

    def log_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: Any = None,
    ) -> int:
        """Log an HTTP request.

        Returns:
            Request ID for correlation with response.
        """
        self._request_count += 1
        request_id = self._request_count

        self._log(f">>> HTTP Request #{request_id}", DebugLevel.BASIC)
        self._log(f"    {method} {url}", DebugLevel.BASIC)

        if self.level.value >= DebugLevel.DETAILED.value and headers:
            self._log("    Headers:", DebugLevel.DETAILED)
            for k, v in headers.items():
                if k.lower() in ("authorization", "x-api-key"):
                    v = "[REDACTED]"
                self._log(f"      {k}: {v}", DebugLevel.DETAILED)

        if self.level.value >= DebugLevel.VERBOSE.value and body:
            self._log(f"    Body: {json.dumps(body, default=str)[:500]}", DebugLevel.VERBOSE)

        return request_id

    def log_response(
        self,
        request_id: int,
        status: int,
        duration_ms: float,
        headers: dict[str, str] | None = None,
        body: Any = None,
    ) -> None:
        """Log an HTTP response."""
        self._log(
            f"<<< HTTP Response #{request_id}: {status} ({duration_ms:.2f}ms)",
            DebugLevel.BASIC,
        )

        if self.level.value >= DebugLevel.DETAILED.value and headers:
            self._log("    Headers:", DebugLevel.DETAILED)
            for k, v in list(headers.items())[:10]:
                self._log(f"      {k}: {v}", DebugLevel.DETAILED)

        if self.level.value >= DebugLevel.VERBOSE.value and body:
            body_str = json.dumps(body, default=str) if not isinstance(body, str) else body
            self._log(f"    Body: {body_str[:500]}", DebugLevel.VERBOSE)

    def log_sql(
        self,
        query: str,
        params: tuple[Any, ...] | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Log a SQL query."""
        self._query_count += 1
        query_id = self._query_count

        duration_str = f" ({duration_ms:.2f}ms)" if duration_ms else ""
        self._log(f"SQL Query #{query_id}{duration_str}:", DebugLevel.BASIC)
        self._log(f"    {query}", DebugLevel.BASIC)

        if self.level.value >= DebugLevel.VERBOSE.value and params:
            self._log(f"    Params: {params}", DebugLevel.VERBOSE)

    def log_timing(self, name: str, duration_ms: float) -> None:
        """Log timing information."""
        self._log(f"TIMING [{name}]: {duration_ms:.2f}ms", DebugLevel.BASIC)

    def log_step_start(self, step_name: str, journey_name: str, path_name: str = "main") -> None:
        """Log step start."""
        self._log(
            f"\n{'=' * 40}",
            DebugLevel.BASIC,
        )
        self._log(
            f"STEP START: {journey_name}/{path_name}/{step_name}",
            DebugLevel.BASIC,
        )

    def log_step_end(
        self,
        step_name: str,
        success: bool,
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        """Log step end."""
        status = "PASS" if success else "FAIL"
        self._log(
            f"STEP END: {step_name} - {status} ({duration_ms:.2f}ms)",
            DebugLevel.BASIC,
        )
        if error:
            self._log(f"    Error: {error}", DebugLevel.BASIC)
        self._log(f"{'=' * 40}\n", DebugLevel.BASIC)

    def close(self) -> None:
        """Close log file."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None


class StepThroughController:
    """Controller for step-through debugging mode.

    Allows pausing execution after each step, inspecting state,
    and continuing or aborting the test run.
    """

    def __init__(self, enabled: bool = False) -> None:
        """Initialize step-through controller.

        Args:
            enabled: Whether step-through mode is enabled.
        """
        self.enabled = enabled
        self._paused = False
        self._skip_to_end = False
        self._breakpoints: set[str] = set()

    def should_pause(self, step_name: str) -> bool:
        """Check if execution should pause at this step."""
        if self._skip_to_end:
            return False
        if not self.enabled:
            return False
        if self._breakpoints and step_name not in self._breakpoints:
            return False
        return True

    def add_breakpoint(self, step_name: str) -> None:
        """Add a breakpoint at a specific step."""
        self._breakpoints.add(step_name)

    def remove_breakpoint(self, step_name: str) -> None:
        """Remove a breakpoint."""
        self._breakpoints.discard(step_name)

    def clear_breakpoints(self) -> None:
        """Clear all breakpoints."""
        self._breakpoints.clear()

    def pause(
        self,
        step_name: str,
        context: dict[str, Any],
        last_result: Any = None,
    ) -> str:
        """Pause execution and wait for user input.

        Args:
            step_name: Name of the current step.
            context: Current execution context.
            last_result: Result of the last step (if any).

        Returns:
            User command: 'continue', 'skip', 'abort', or 'inspect'.
        """
        if not self.should_pause(step_name):
            return "continue"

        self._paused = True

        print(f"\n{'=' * 60}")
        print(f"PAUSED after step: {step_name}")
        print("=" * 60)

        # Show context summary
        print("\nContext variables:")
        for key, value in list(context.items())[:10]:
            value_str = str(value)[:50]
            print(f"  {key}: {value_str}")
        if len(context) > 10:
            print(f"  ... and {len(context) - 10} more")

        # Show last result
        if last_result is not None:
            print("\nLast step result:")
            if hasattr(last_result, "status_code"):
                print(f"  HTTP {last_result.status_code}")
            elif isinstance(last_result, dict):
                print(f"  {json.dumps(last_result, default=str)[:100]}")
            else:
                print(f"  {str(last_result)[:100]}")

        print("\nCommands:")
        print("  [Enter]   - Continue to next step")
        print("  'skip'    - Skip remaining pauses")
        print("  'abort'   - Abort test run")
        print("  'inspect' - Show full context")
        print("  'help'    - Show all commands")

        while True:
            try:
                user_input = input("\n> ").strip().lower()

                if user_input in ("", "continue", "c"):
                    self._paused = False
                    return "continue"
                elif user_input in ("skip", "s"):
                    self._skip_to_end = True
                    self._paused = False
                    return "skip"
                elif user_input in ("abort", "a", "quit", "q"):
                    return "abort"
                elif user_input in ("inspect", "i"):
                    self._show_full_context(context, last_result)
                elif user_input in ("help", "h", "?"):
                    self._show_help()
                elif user_input.startswith("get "):
                    key = user_input[4:].strip()
                    self._show_context_key(context, key)
                elif user_input.startswith("break "):
                    bp_step = user_input[6:].strip()
                    self.add_breakpoint(bp_step)
                    print(f"Breakpoint set at: {bp_step}")
                else:
                    print(f"Unknown command: {user_input}. Type 'help' for commands.")

            except (KeyboardInterrupt, EOFError):
                print("\nAborted by user.")
                return "abort"

    def _show_full_context(self, context: dict[str, Any], last_result: Any) -> None:
        """Show full context data."""
        print("\n" + "=" * 40)
        print("FULL CONTEXT")
        print("=" * 40)
        print(json.dumps(context, indent=2, default=str))

        if last_result is not None:
            print("\n" + "-" * 40)
            print("LAST RESULT")
            print("-" * 40)
            if hasattr(last_result, "__dict__"):
                print(json.dumps(last_result.__dict__, indent=2, default=str))
            else:
                print(str(last_result))

    def _show_context_key(self, context: dict[str, Any], key: str) -> None:
        """Show a specific context key."""
        if key in context:
            print(f"\n{key}:")
            print(json.dumps(context[key], indent=2, default=str))
        else:
            print(f"Key '{key}' not found in context.")
            similar = [k for k in context if key.lower() in k.lower()]
            if similar:
                print(f"Similar keys: {', '.join(similar)}")

    def _show_help(self) -> None:
        """Show help message."""
        print(
            """
Available commands:
  [Enter], continue, c  - Continue to next step
  skip, s               - Skip remaining pauses
  abort, a, quit, q     - Abort test run
  inspect, i            - Show full context
  get <key>             - Show specific context key
  break <step>          - Set breakpoint at step
  help, h, ?            - Show this help
"""
        )


def create_debug_context(
    step_name: str,
    journey_name: str,
    path_name: str = "main",
    error: Exception | None = None,
    request: dict[str, Any] | None = None,
    response: dict[str, Any] | None = None,
    context_data: dict[str, Any] | None = None,
    timing: dict[str, float] | None = None,
) -> DebugContext:
    """Create a DebugContext from failure information.

    Factory function for creating debug contexts with all
    relevant information populated.

    Args:
        step_name: Name of the failed step.
        journey_name: Name of the journey.
        path_name: Name of the current path.
        error: The exception that was raised.
        request: Request data.
        response: Response data.
        context_data: Execution context variables.
        timing: Timing information.

    Returns:
        Populated DebugContext instance.
    """
    # Extract HTTP status from response
    http_status = None
    if response and "status_code" in response:
        http_status = response["status_code"]

    # Get filtered stack trace
    stack_trace = ""
    if error:
        stack_trace = StackTraceFilter.filter_traceback()

    # Get error details
    error_message = str(error) if error else ""
    error_type = type(error).__name__ if error else ""

    # Generate suggestions
    suggestions_data = TroubleshootingEngine.get_suggestions(
        error_message,
        http_status,
        response.get("body") if response else None,
    )

    suggestions = []
    if suggestions_data.get("suggestion"):
        suggestions.append(suggestions_data["suggestion"])

    return DebugContext(
        step_name=step_name,
        journey_name=journey_name,
        path_name=path_name,
        request=request,
        response=response,
        context_data=context_data or {},
        stack_trace=stack_trace,
        timing=timing or {},
        suggestions=suggestions,
        error_message=error_message,
        error_type=error_type,
        http_status=http_status,
    )


def format_error(
    step_name: str,
    journey_name: str,
    error: Exception,
    request: dict[str, Any] | None = None,
    response: dict[str, Any] | None = None,
    verbose: bool = False,
) -> str:
    """Format an error for CLI display.

    Convenience function for quick error formatting.

    Args:
        step_name: Name of the failed step.
        journey_name: Name of the journey.
        error: The exception that was raised.
        request: Request data.
        response: Response data.
        verbose: Whether to include extra details.

    Returns:
        Formatted error string.
    """
    ctx = create_debug_context(
        step_name=step_name,
        journey_name=journey_name,
        error=error,
        request=request,
        response=response,
    )
    formatter = ErrorFormatter(ctx, verbose=verbose)
    return formatter.format()
