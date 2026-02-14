"""Custom exception hierarchy for VenomQA.

VenomQA provides a comprehensive error hierarchy with:
- Structured error codes for programmatic handling
- Rich context for debugging
- Actionable suggestions for recovery
- Documentation links for learning more

All VenomQA errors inherit from VenomQAError and include:
- error_code: A unique ErrorCode enum for categorization
- context: ErrorContext with journey/step/request details
- suggestions: List of actionable steps to resolve the issue
- docs_url: Link to relevant documentation

Example:
    try:
        runner.run(journey)
    except ConnectionError as e:
        print(f"Error: {e}")
        print(f"Suggestions: {e.suggestions}")
        print(f"Learn more: {e.docs_url}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# Base documentation URL
DOCS_BASE_URL = "https://venomqa.dev/docs"


class ErrorCode(Enum):
    """Standardized error codes for VenomQA.

    Error codes are organized by category:
    - E0xx: Connection errors
    - E1xx: Request errors
    - E2xx: Validation errors
    - E3xx: State management errors
    - E4xx: Journey execution errors
    - E5xx: Resilience errors (circuit breaker, retry, rate limit)
    - E6xx: Plugin/reporter errors
    - E9xx: Unknown/internal errors

    Use these codes for:
    - Programmatic error handling in CI/CD
    - Log aggregation and alerting
    - Error categorization in reports
    """

    # Connection errors (E0xx)
    CONNECTION_FAILED = "E001"
    CONNECTION_TIMEOUT = "E002"
    CONNECTION_REFUSED = "E003"
    CONNECTION_RESET = "E004"

    # Request errors (E1xx)
    REQUEST_TIMEOUT = "E101"
    REQUEST_FAILED = "E102"
    REQUEST_ABORTED = "E103"

    # Validation errors (E2xx)
    VALIDATION_FAILED = "E201"
    INVALID_CONFIG = "E202"
    INVALID_JOURNEY = "E203"
    INVALID_STEP = "E204"
    SCHEMA_MISMATCH = "E205"

    # State management errors (E3xx)
    STATE_NOT_CONNECTED = "E301"
    STATE_CHECKPOINT_FAILED = "E302"
    STATE_ROLLBACK_FAILED = "E303"
    STATE_RESET_FAILED = "E304"

    # Journey execution errors (E4xx)
    JOURNEY_FAILED = "E401"
    JOURNEY_TIMEOUT = "E402"
    JOURNEY_ABORTED = "E403"
    BRANCH_FAILED = "E404"
    PATH_FAILED = "E405"

    # Resilience errors (E5xx)
    CIRCUIT_OPEN = "E501"
    RETRY_EXHAUSTED = "E502"
    RATE_LIMITED = "E503"

    # Plugin/reporter errors (E6xx)
    PLUGIN_ERROR = "E601"
    REPORTER_ERROR = "E602"

    # Unknown/internal errors (E9xx)
    UNKNOWN = "E999"

    @property
    def category(self) -> str:
        """Get the error category name."""
        code_num = int(self.value[1:])
        if code_num < 100:
            return "connection"
        elif code_num < 200:
            return "request"
        elif code_num < 300:
            return "validation"
        elif code_num < 400:
            return "state"
        elif code_num < 500:
            return "journey"
        elif code_num < 600:
            return "resilience"
        elif code_num < 700:
            return "plugin"
        else:
            return "unknown"


@dataclass
class ErrorContext:
    """Structured context for error logging and debugging."""

    journey_name: str | None = None
    path_name: str | None = None
    step_name: str | None = None
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    traceback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "journey_name": self.journey_name,
            "path_name": self.path_name,
            "step_name": self.step_name,
            "request": self.request,
            "response": self.response,
            "extra": self.extra,
            "timestamp": self.timestamp.isoformat(),
            "traceback": self.traceback,
        }
        return {k: v for k, v in result.items() if v is not None}


class VenomQAError(Exception):
    """Base exception for all VenomQA errors."""

    error_code: ErrorCode = ErrorCode.UNKNOWN
    default_message: str = "An unexpected error occurred"

    def __init__(
        self,
        message: str | None = None,
        error_code: ErrorCode | None = None,
        context: ErrorContext | None = None,
        cause: Exception | None = None,
        recoverable: bool = True,
        **extra_context: Any,
    ) -> None:
        self.message = message or self.default_message
        self.error_code = error_code or self.error_code
        self.context = context or ErrorContext()
        self.cause = cause
        self.recoverable = recoverable

        if extra_context:
            self.context.extra.update(extra_context)

        super().__init__(self.message)

    def __str__(self) -> str:
        parts = [f"[{self.error_code.value}] {self.message}"]
        if self.context.journey_name:
            parts.append(f"journey={self.context.journey_name}")
        if self.context.path_name:
            parts.append(f"path={self.context.path_name}")
        if self.context.step_name:
            parts.append(f"step={self.context.step_name}")
        return " | ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code.value,
            "error_type": self.__class__.__name__,
            "message": self.message,
            "recoverable": self.recoverable,
            "context": self.context.to_dict(),
            "cause": str(self.cause) if self.cause else None,
        }


class ConnectionError(VenomQAError):
    """Error establishing connection to a service."""

    error_code = ErrorCode.CONNECTION_FAILED
    default_message = "Failed to establish connection"


class ConnectionTimeoutError(ConnectionError):
    """Connection timed out."""

    error_code = ErrorCode.CONNECTION_TIMEOUT
    default_message = "Connection timed out"


class ConnectionRefusedError(ConnectionError):
    """Connection was refused by the server."""

    error_code = ErrorCode.CONNECTION_REFUSED
    default_message = "Connection refused by server"


class ConnectionResetError(ConnectionError):
    """Connection was reset by the peer."""

    error_code = ErrorCode.CONNECTION_RESET
    default_message = "Connection reset by peer"


class TimeoutError(VenomQAError):
    """Operation timed out."""

    error_code = ErrorCode.REQUEST_TIMEOUT
    default_message = "Operation timed out"


class RequestTimeoutError(TimeoutError):
    """HTTP request timed out."""

    error_code = ErrorCode.REQUEST_TIMEOUT
    default_message = "HTTP request timed out"


class RequestFailedError(VenomQAError):
    """HTTP request failed."""

    error_code = ErrorCode.REQUEST_FAILED
    default_message = "HTTP request failed"

    def __init__(
        self,
        message: str | None = None,
        status_code: int | None = None,
        **kwargs: Any,
    ) -> None:
        self.status_code = status_code
        super().__init__(message=message, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["status_code"] = self.status_code
        return result


class ValidationError(VenomQAError):
    """Validation failed."""

    error_code = ErrorCode.VALIDATION_FAILED
    default_message = "Validation failed"
    recoverable = False

    def __init__(
        self,
        message: str | None = None,
        field: str | None = None,
        value: Any = None,
        **kwargs: Any,
    ) -> None:
        self.field = field
        self.value = value
        super().__init__(message=message, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["field"] = self.field
        result["value"] = repr(self.value)
        return result


class ConfigValidationError(ValidationError):
    """Configuration validation failed."""

    error_code = ErrorCode.INVALID_CONFIG
    default_message = "Invalid configuration"


class JourneyValidationError(ValidationError):
    """Journey validation failed."""

    error_code = ErrorCode.INVALID_JOURNEY
    default_message = "Invalid journey definition"


class StepValidationError(ValidationError):
    """Step validation failed."""

    error_code = ErrorCode.INVALID_STEP
    default_message = "Invalid step definition"


class SchemaMismatchError(ValidationError):
    """Response schema mismatch."""

    error_code = ErrorCode.SCHEMA_MISMATCH
    default_message = "Response does not match expected schema"


class StateError(VenomQAError):
    """State management error."""

    error_code = ErrorCode.STATE_NOT_CONNECTED
    default_message = "State management error"


class StateNotConnectedError(StateError):
    """State manager not connected."""

    error_code = ErrorCode.STATE_NOT_CONNECTED
    default_message = "State manager not connected. Call connect() first."
    recoverable = True


class CheckpointError(StateError):
    """Checkpoint operation failed."""

    error_code = ErrorCode.STATE_CHECKPOINT_FAILED
    default_message = "Checkpoint operation failed"


class RollbackError(StateError):
    """Rollback operation failed."""

    error_code = ErrorCode.STATE_ROLLBACK_FAILED
    default_message = "Rollback operation failed"


class ResetError(StateError):
    """Reset operation failed."""

    error_code = ErrorCode.STATE_RESET_FAILED
    default_message = "Reset operation failed"


class JourneyError(VenomQAError):
    """Journey execution error."""

    error_code = ErrorCode.JOURNEY_FAILED
    default_message = "Journey execution failed"


class JourneyTimeoutError(JourneyError):
    """Journey execution timed out."""

    error_code = ErrorCode.JOURNEY_TIMEOUT
    default_message = "Journey execution timed out"


class JourneyAbortedError(JourneyError):
    """Journey was aborted."""

    error_code = ErrorCode.JOURNEY_ABORTED
    default_message = "Journey was aborted"


class BranchError(JourneyError):
    """Branch execution error."""

    error_code = ErrorCode.BRANCH_FAILED
    default_message = "Branch execution failed"


class PathError(JourneyError):
    """Path execution error."""

    error_code = ErrorCode.PATH_FAILED
    default_message = "Path execution failed"


class CircuitOpenError(VenomQAError):
    """Circuit breaker is open."""

    error_code = ErrorCode.CIRCUIT_OPEN
    default_message = "Circuit breaker is open - too many recent failures"

    def __init__(
        self,
        message: str | None = None,
        failures_count: int = 0,
        reset_timeout: float = 0,
        **kwargs: Any,
    ) -> None:
        self.failures_count = failures_count
        self.reset_timeout = reset_timeout
        super().__init__(message=message, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["failures_count"] = self.failures_count
        result["reset_timeout"] = self.reset_timeout
        return result


class RetryExhaustedError(VenomQAError):
    """All retry attempts exhausted."""

    error_code = ErrorCode.RETRY_EXHAUSTED
    default_message = "All retry attempts exhausted"

    def __init__(
        self,
        message: str | None = None,
        attempts: int = 0,
        last_error: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(message=message, cause=last_error, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["attempts"] = self.attempts
        return result


class RateLimitedError(VenomQAError):
    """Rate limit exceeded."""

    error_code = ErrorCode.RATE_LIMITED
    default_message = "Rate limit exceeded"

    def __init__(
        self,
        message: str | None = None,
        retry_after: float | None = None,
        **kwargs: Any,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message=message, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["retry_after"] = self.retry_after
        return result


class PluginError(VenomQAError):
    """Plugin execution error."""

    error_code = ErrorCode.PLUGIN_ERROR
    default_message = "Plugin execution failed"


class ReporterError(VenomQAError):
    """Reporter execution error."""

    error_code = ErrorCode.REPORTER_ERROR
    default_message = "Reporter execution failed"
