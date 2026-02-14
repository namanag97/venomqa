"""Structured JSON logging for VenomQA.

This module provides structured logging capabilities including:
- JSON-formatted log output for machine consumption
- Human-readable colored output for development
- Context-aware logging with bound fields
- Thread-safe logging with context propagation
- Integration with Python's standard logging module

Example:
    Basic usage::

        from venomqa.observability.logging import get_logger

        logger = get_logger("myapp")
        logger.info("Request processed", method="GET", path="/users", duration_ms=45)

    With context::

        from venomqa.observability.logging import log_context, get_logger

        logger = get_logger("myapp")

        with log_context(request_id="abc-123", user_id="user-1"):
            logger.info("Processing request")  # Includes request_id and user_id

    Bound logger::

        logger = get_logger("myapp")
        request_logger = logger.bind(request_id="abc-123")
        request_logger.info("Processing")  # Always includes request_id
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

_context_fields: ContextVar[dict[str, Any] | None] = ContextVar("venomqa_log_context", default=None)


class StructuredLogRecord(logging.LogRecord):
    """LogRecord with structured data support.

    Extends the standard LogRecord to support additional structured
    data that can be included in JSON output.

    Attributes:
        structured_data: Dictionary of structured fields for this log record.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.structured_data: dict[str, Any] = {}


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging.

    Formats log records as JSON objects suitable for log aggregation
    systems like Elasticsearch, Splunk, or CloudWatch.

    Attributes:
        include_timestamp: Whether to include timestamp in output.
        include_level: Whether to include log level in output.
        include_logger: Whether to include logger name in output.
        include_location: Whether to include file/line/function in output.
        timestamp_format: Format for timestamp ('iso', 'unix', or strftime format).
        extra_fields: Additional fields to include in every log record.

    Example:
        >>> formatter = StructuredFormatter(include_location=True)
        >>> handler.setFormatter(formatter)
    """

    def __init__(
        self,
        include_timestamp: bool = True,
        include_level: bool = True,
        include_logger: bool = True,
        include_location: bool = False,
        timestamp_format: str = "iso",
        extra_fields: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the structured formatter.

        Args:
            include_timestamp: Include timestamp field in output.
            include_level: Include level and level_num fields.
            include_logger: Include logger name field.
            include_location: Include file, line, and function fields.
            timestamp_format: 'iso' for ISO 8601, 'unix' for epoch, or strftime.
            extra_fields: Static fields to add to every log record.
        """
        super().__init__()
        self.include_timestamp = include_timestamp
        self.include_level = include_level
        self.include_logger = include_logger
        self.include_location = include_location
        self.timestamp_format = timestamp_format
        self.extra_fields = extra_fields or {}

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: The log record to format.

        Returns:
            JSON-formatted log string.
        """
        log_data: dict[str, Any] = {}

        if self.include_timestamp:
            if self.timestamp_format == "iso":
                log_data["timestamp"] = datetime.now(timezone.utc).isoformat()
            elif self.timestamp_format == "unix":
                log_data["timestamp"] = time.time()
            else:
                log_data["timestamp"] = self.formatTime(record, self.timestamp_format)

        if self.include_level:
            log_data["level"] = record.levelname.lower()
            log_data["level_num"] = record.levelno

        log_data["message"] = record.getMessage()

        if self.include_logger:
            log_data["logger"] = record.name

        if self.include_location:
            log_data["location"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
                "module": record.module,
                "path": record.pathname,
            }

        context = _context_fields.get()
        if context:
            log_data["context"] = dict(context)

        structured_data = getattr(record, "structured_data", None)
        if structured_data:
            log_data["data"] = dict(structured_data)

        if record.exc_info and record.exc_info[0] is not None:
            exc_type = record.exc_info[0].__name__ if record.exc_info[0] else None
            exc_msg = str(record.exc_info[1]) if record.exc_info[1] else None
            log_data["exception"] = {
                "type": exc_type,
                "message": exc_msg,
                "traceback": self.formatException(record.exc_info),
            }

        for key, value in self.extra_fields.items():
            if key not in log_data:
                log_data[key] = value

        return json.dumps(log_data, default=str, ensure_ascii=False)


class HumanReadableFormatter(logging.Formatter):
    """Human-readable formatter for development.

    Formats log records with colors and readable layout for
    console output during development.

    Example:
        >>> formatter = HumanReadableFormatter()
        >>> handler.setFormatter(formatter)
    """

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def __init__(self, use_colors: bool = True) -> None:
        """Initialize the human-readable formatter.

        Args:
            use_colors: Whether to use ANSI colors in output.
        """
        super().__init__()
        self.use_colors = use_colors and self._supports_color()

    @staticmethod
    def _supports_color() -> bool:
        """Check if the terminal supports colors."""
        if sys.platform == "win32":
            return os.environ.get("ANSICON") is not None or "WT_SESSION" in os.environ
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for human reading.

        Args:
            record: The log record to format.

        Returns:
            Human-readable log string.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        if self.use_colors:
            color = self.COLORS.get(record.levelname, "")
            level = f"{color}{record.levelname:8}{self.RESET}"
        else:
            level = f"{record.levelname:8}"

        base = f"{timestamp} {level} [{record.name}] {record.getMessage()}"

        context = _context_fields.get()
        if context:
            base += f" | context={json.dumps(dict(context))}"

        structured_data = getattr(record, "structured_data", None)
        if structured_data:
            base += f" | data={json.dumps(structured_data, default=str)}"

        if record.exc_info:
            base += f"\n{self.formatException(record.exc_info)}"

        return base


class StructuredLogger:
    """Logger with structured logging capabilities.

    Provides methods for logging at different levels with structured
    key-value data. Supports both JSON and human-readable output formats.

    Attributes:
        name: Logger name.

    Example:
        >>> logger = StructuredLogger("myapp")
        >>> logger.info("User logged in", user_id="123", ip="10.0.0.1")
        >>> logger.error("Database error", error_code="E001", retries=3)
    """

    def __init__(
        self,
        name: str,
        level: int = logging.INFO,
        json_format: bool = True,
        include_location: bool = False,
        extra_fields: dict[str, Any] | None = None,
        stream: Any | None = None,
    ) -> None:
        """Initialize the structured logger.

        Args:
            name: Logger name (typically module or service name).
            level: Minimum log level to output.
            json_format: Use JSON format (True) or human-readable (False).
            include_location: Include file/line/function in output.
            extra_fields: Static fields to include in every log record.
            stream: Output stream (defaults to sys.stdout).
        """
        self.name = name
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._logger.handlers.clear()
        self._logger.propagate = False

        output_stream = stream or sys.stdout
        self._handler = logging.StreamHandler(output_stream)
        self._handler.setLevel(level)

        if json_format:
            self._formatter = StructuredFormatter(
                include_location=include_location,
                extra_fields=extra_fields,
            )
        else:
            self._formatter = HumanReadableFormatter()

        self._handler.setFormatter(self._formatter)
        self._logger.addHandler(self._handler)

        self._extra_fields = extra_fields or {}
        self._lock = threading.Lock()
        self._json_format = json_format

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        """Internal logging method.

        Args:
            level: Log level.
            message: Log message.
            **kwargs: Additional structured data.
        """
        record = self._logger.makeRecord(
            self.name,
            level,
            "",
            0,
            message,
            (),
            None,
        )
        record.structured_data = kwargs  # type: ignore[attr-defined]
        self._logger.handle(record)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message.

        Args:
            message: Log message.
            **kwargs: Additional structured data.
        """
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info message.

        Args:
            message: Log message.
            **kwargs: Additional structured data.
        """
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning message.

        Args:
            message: Log message.
            **kwargs: Additional structured data.
        """
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error message.

        Args:
            message: Log message.
            **kwargs: Additional structured data.
        """
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log a critical message.

        Args:
            message: Log message.
            **kwargs: Additional structured data.
        """
        self._log(logging.CRITICAL, message, **kwargs)

    def exception(
        self,
        message: str,
        exc_info: Any = True,
        **kwargs: Any,
    ) -> None:
        """Log an exception with traceback.

        Args:
            message: Log message.
            exc_info: Exception info (True for current, or exception tuple).
            **kwargs: Additional structured data.
        """
        record = self._logger.makeRecord(
            self.name,
            logging.ERROR,
            "",
            0,
            message,
            (),
            exc_info if exc_info is not True else sys.exc_info(),
        )
        record.structured_data = kwargs  # type: ignore[attr-defined]
        self._logger.handle(record)

    def log(self, level: int | str, message: str, **kwargs: Any) -> None:
        """Log a message at the specified level.

        Args:
            level: Log level (int or string like 'INFO', 'ERROR').
            message: Log message.
            **kwargs: Additional structured data.
        """
        if isinstance(level, str):
            level = getattr(logging, level.upper(), logging.INFO)
        self._log(level, message, **kwargs)

    def bind(self, **kwargs: Any) -> BoundLogger:
        """Create a logger with bound fields.

        The bound fields will be included in all log messages from
        the returned logger.

        Args:
            **kwargs: Fields to bind to the logger.

        Returns:
            A BoundLogger instance with the specified fields.

        Example:
            >>> request_logger = logger.bind(request_id="abc-123")
            >>> request_logger.info("Processing")  # Includes request_id
        """
        return BoundLogger(self, kwargs)

    def with_context(self, **kwargs: Any) -> None:
        """Add context fields for all subsequent logs in this context.

        Args:
            **kwargs: Fields to add to the logging context.

        Note:
            This modifies thread-local context. Use log_context()
            context manager for safer context management.
        """
        current = _context_fields.get()
        if current is None:
            current = {}
        current = dict(current)
        current.update(kwargs)
        _context_fields.set(current)

    def clear_context(self) -> None:
        """Clear all context fields."""
        _context_fields.set({})

    def set_level(self, level: int | str) -> None:
        """Set the logging level.

        Args:
            level: Log level (int or string like 'INFO', 'DEBUG').
        """
        if isinstance(level, str):
            level = getattr(logging, level.upper(), logging.INFO)
        self._logger.setLevel(level)
        self._handler.setLevel(level)

    def get_level(self) -> int:
        """Get the current logging level."""
        return self._logger.level


class BoundLogger:
    """Logger with pre-bound fields.

    Created by StructuredLogger.bind(), includes the bound fields
    in every log message.

    Example:
        >>> logger = get_logger("myapp")
        >>> request_logger = logger.bind(request_id="abc-123")
        >>> request_logger.info("Processing")  # Always includes request_id
    """

    def __init__(self, logger: StructuredLogger, fields: dict[str, Any]) -> None:
        """Initialize bound logger.

        Args:
            logger: Parent StructuredLogger.
            fields: Fields to include in all log messages.
        """
        self._logger = logger
        self._fields = fields

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        merged = {**self._fields, **kwargs}
        self._logger._log(level, message, **merged)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message with bound fields."""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info message with bound fields."""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning message with bound fields."""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error message with bound fields."""
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log a critical message with bound fields."""
        self._log(logging.CRITICAL, message, **kwargs)

    def exception(self, message: str, exc_info: Any = True, **kwargs: Any) -> None:
        """Log an exception with bound fields."""
        merged = {**self._fields, **kwargs}
        self._logger.exception(message, exc_info=exc_info, **merged)

    def bind(self, **kwargs: Any) -> BoundLogger:
        """Create a new bound logger with additional fields."""
        merged = {**self._fields, **kwargs}
        return BoundLogger(self._logger, merged)


_loggers: dict[str, StructuredLogger] = {}
_loggers_lock = threading.Lock()


def get_logger(
    name: str = "venomqa",
    level: int | str = logging.INFO,
    json_format: bool | None = None,
    include_location: bool = False,
    extra_fields: dict[str, Any] | None = None,
) -> StructuredLogger:
    """Get or create a structured logger.

    This is the main entry point for obtaining a logger. Loggers are
    cached by name, so subsequent calls with the same name return
    the same logger instance.

    Args:
        name: Logger name (typically module or service name).
        level: Minimum log level (int or string like 'INFO', 'DEBUG').
        json_format: Use JSON format. If None, uses VENOMQA_JSON_LOGS env var.
        include_location: Include file/line/function in output.
        extra_fields: Static fields to include in every log record.

    Returns:
        A StructuredLogger instance.

    Example:
        >>> logger = get_logger("myapp")
        >>> logger.info("Server started", port=8080)

        >>> # Force JSON format
        >>> logger = get_logger("myapp", json_format=True)

        >>> # With extra fields
        >>> logger = get_logger("myapp", extra_fields={"service": "api"})
    """
    if json_format is None:
        json_format = os.environ.get("VENOMQA_JSON_LOGS", "false").lower() == "true"

    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    with _loggers_lock:
        if name not in _loggers:
            _loggers[name] = StructuredLogger(
                name=name,
                level=level,
                json_format=json_format,
                include_location=include_location,
                extra_fields=extra_fields,
            )
        return _loggers[name]


def configure_logging(
    level: int | str = logging.INFO,
    json_format: bool = False,
    include_location: bool = False,
    extra_fields: dict[str, Any] | None = None,
) -> None:
    """Configure global logging for VenomQA.

    Sets up the root venomqa logger with the specified configuration.

    Args:
        level: Minimum log level.
        json_format: Use JSON format for output.
        include_location: Include file/line/function in output.
        extra_fields: Static fields to include in every log record.

    Example:
        >>> configure_logging(level="DEBUG", json_format=True)
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger("venomqa")
    root_logger.handlers.clear()
    root_logger.propagate = False

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if json_format:
        formatter = StructuredFormatter(
            include_location=include_location,
            extra_fields=extra_fields,
        )
    else:
        formatter = HumanReadableFormatter()

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


@contextmanager
def log_context(**kwargs: Any) -> Iterator[None]:
    """Context manager for temporary log context.

    Adds the specified fields to all log messages within the context,
    then restores the previous context on exit.

    Args:
        **kwargs: Fields to add to logging context.

    Yields:
        None

    Example:
        >>> with log_context(request_id="abc-123", user_id="user-1"):
        ...     logger.info("Processing request")  # Includes both fields
        >>> logger.info("Done")  # Does not include the fields
    """
    current = _context_fields.get()
    if current is None:
        current = {}
    current = dict(current)
    current.update(kwargs)
    token = _context_fields.set(current)
    try:
        yield
    finally:
        _context_fields.reset(token)


def get_context() -> dict[str, Any]:
    """Get the current logging context.

    Returns:
        Copy of the current context fields.
    """
    current = _context_fields.get()
    return dict(current) if current else {}


def clear_context() -> None:
    """Clear the current logging context."""
    _context_fields.set({})


def add_context(**kwargs: Any) -> None:
    """Add fields to the current logging context.

    Args:
        **kwargs: Fields to add.
    """
    current = _context_fields.get()
    if current is None:
        current = {}
    current = dict(current)
    current.update(kwargs)
    _context_fields.set(current)
