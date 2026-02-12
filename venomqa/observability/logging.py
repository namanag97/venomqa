"""Structured JSON logging for VenomQA."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

_context_fields: ContextVar[dict[str, Any] | None] = ContextVar("log_context", default=None)


class StructuredLogRecord(logging.LogRecord):
    """LogRecord with structured data support."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.structured_data: dict[str, Any] = {}


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def __init__(
        self,
        include_timestamp: bool = True,
        include_level: bool = True,
        include_logger: bool = True,
        include_location: bool = False,
        timestamp_format: str = "iso",
        extra_fields: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.include_timestamp = include_timestamp
        self.include_level = include_level
        self.include_logger = include_logger
        self.include_location = include_location
        self.timestamp_format = timestamp_format
        self.extra_fields = extra_fields or {}

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
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
            }

        context = _context_fields.get()
        if context:
            log_data["context"] = context

        if hasattr(record, "structured_data"):
            log_data["data"] = record.structured_data

        if hasattr(record, "exc_info") and record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info),
            }

        for key, value in self.extra_fields.items():
            if key not in log_data:
                log_data[key] = value

        return json.dumps(log_data, default=str, ensure_ascii=False)


class HumanReadableFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for human reading."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        color = self.COLORS.get(record.levelname, "")
        level = f"{color}{record.levelname:8}{self.RESET}"

        base = f"{timestamp} {level} [{record.name}] {record.getMessage()}"

        context = _context_fields.get()
        if context:
            base += f" | context={json.dumps(context)}"

        if hasattr(record, "structured_data") and record.structured_data:
            base += f" | data={json.dumps(record.structured_data, default=str)}"

        if record.exc_info:
            base += f"\n{self.formatException(record.exc_info)}"

        return base


class StructuredLogger:
    """Logger with structured logging capabilities."""

    def __init__(
        self,
        name: str,
        level: int = logging.INFO,
        json_format: bool = True,
        include_location: bool = False,
        extra_fields: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._logger.handlers.clear()

        self._handler = logging.StreamHandler(sys.stdout)
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

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        """Internal logging method."""
        record = self._logger.makeRecord(
            self.name,
            level,
            None,
            None,
            message,
            (),
            None,
        )
        record.structured_data = kwargs
        self._logger.handle(record)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message."""
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message."""
        self._log(logging.CRITICAL, message, **kwargs)

    def exception(self, message: str, exc_info: Any = True, **kwargs: Any) -> None:
        """Log exception with traceback."""
        kwargs["exc_info"] = exc_info
        self._log(logging.ERROR, message, **kwargs)

    def bind(self, **kwargs: Any) -> BoundLogger:
        """Create a logger with bound fields."""
        return BoundLogger(self, kwargs)

    def with_context(self, **kwargs: Any) -> None:
        """Add context fields for all subsequent logs in this context."""
        current = _context_fields.get().copy()
        current.update(kwargs)
        _context_fields.set(current)

    def clear_context(self) -> None:
        """Clear context fields."""
        _context_fields.set({})

    def set_level(self, level: int | str) -> None:
        """Set logging level."""
        if isinstance(level, str):
            level = getattr(logging, level.upper(), logging.INFO)
        self._logger.setLevel(level)
        self._handler.setLevel(level)


class BoundLogger:
    """Logger with pre-bound fields."""

    def __init__(self, logger: StructuredLogger, fields: dict[str, Any]) -> None:
        self._logger = logger
        self._fields = fields

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        merged = {**self._fields, **kwargs}
        self._logger._log(level, message, **merged)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, message, **kwargs)


_loggers: dict[str, StructuredLogger] = {}
_loggers_lock = threading.Lock()


def get_logger(
    name: str = "venomqa",
    level: int | str = logging.INFO,
    json_format: bool | None = None,
    include_location: bool = False,
    extra_fields: dict[str, Any] | None = None,
) -> StructuredLogger:
    """Get or create a structured logger."""
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
    """Configure global logging for VenomQA."""
    root_logger = logging.getLogger("venomqa")
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level if isinstance(level, int) else getattr(logging, level.upper()))

    if json_format:
        formatter = StructuredFormatter(
            include_location=include_location,
            extra_fields=extra_fields,
        )
    else:
        formatter = HumanReadableFormatter()

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(level if isinstance(level, int) else getattr(logging, level.upper()))


def log_context(**kwargs: Any):
    """Context manager for temporary log context."""

    @contextmanager
    def _ctx():
        current = _context_fields.get()
        if current is None:
            current = {}
        current = current.copy()
        current.update(kwargs)
        token = _context_fields.set(current)
        try:
            yield
        finally:
            _context_fields.reset(token)

    return _ctx()
