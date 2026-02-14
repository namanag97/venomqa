"""Retry policies with exponential backoff and jitter.

This module provides comprehensive retry and circuit breaker functionality:
- Configurable retry policies with multiple backoff strategies
- YAML-based configuration support
- Service-specific circuit breakers
- Enhanced timeout error messages
- Async/sync support

Example:
    >>> from venomqa.errors.retry import RetryPolicy, RetryConfig, BackoffStrategy
    >>>
    >>> # Create from YAML config
    >>> config = RetryConfig.from_yaml({
    ...     "max_attempts": 3,
    ...     "backoff": "exponential",
    ...     "initial_delay": 1.0,
    ...     "max_delay": 30.0,
    ...     "retry_on": [500, 502, 503, 504, "ConnectionError", "Timeout"]
    ... })
    >>> policy = RetryPolicy(config)
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from venomqa.errors.base import (
    CircuitOpenError,
    ErrorCode,
    RateLimitedError,
    RetryExhaustedError,
    TimeoutError as VenomTimeoutError,
    VenomQAError,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


class BackoffStrategy(Enum):
    """Available backoff strategies.

    Attributes:
        FIXED: Same delay between each retry.
        LINEAR: Delay increases linearly (delay * attempt).
        EXPONENTIAL: Delay doubles each retry.
        EXPONENTIAL_FULL_JITTER: Exponential with random jitter (0 to exp_delay).
        EXPONENTIAL_EQUAL_JITTER: Exponential with half-jitter.
        EXPONENTIAL_DECORRELATED_JITTER: Decorrelated jitter for better distribution.
    """

    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_FULL_JITTER = "exponential_full_jitter"
    EXPONENTIAL_EQUAL_JITTER = "exponential_equal_jitter"
    EXPONENTIAL_DECORRELATED_JITTER = "exponential_decorrelated_jitter"

    @classmethod
    def from_string(cls, value: str) -> BackoffStrategy:
        """Create BackoffStrategy from string value.

        Args:
            value: Strategy name (e.g., "exponential", "linear", "fixed").

        Returns:
            Corresponding BackoffStrategy enum value.

        Raises:
            ValueError: If strategy name is not recognized.
        """
        value_lower = value.lower().replace("-", "_").replace(" ", "_")
        mapping = {
            "fixed": cls.FIXED,
            "linear": cls.LINEAR,
            "exponential": cls.EXPONENTIAL,
            "exponential_full_jitter": cls.EXPONENTIAL_FULL_JITTER,
            "exponential_equal_jitter": cls.EXPONENTIAL_EQUAL_JITTER,
            "exponential_decorrelated_jitter": cls.EXPONENTIAL_DECORRELATED_JITTER,
            # Aliases
            "exp": cls.EXPONENTIAL,
            "exp_jitter": cls.EXPONENTIAL_FULL_JITTER,
        }
        if value_lower not in mapping:
            valid = ", ".join(sorted(mapping.keys()))
            raise ValueError(f"Unknown backoff strategy: {value}. Valid: {valid}")
        return mapping[value_lower]


class StepTimeoutError(VenomTimeoutError):
    """Raised when a step times out.

    Provides enhanced error messages with context about what was being
    executed and suggestions for resolution.
    """

    error_code = ErrorCode.REQUEST_TIMEOUT
    default_message = "Step execution timed out"

    def __init__(
        self,
        message: str | None = None,
        step_name: str | None = None,
        timeout_seconds: float | None = None,
        elapsed_seconds: float | None = None,
        operation_description: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize step timeout error with context.

        Args:
            message: Custom error message.
            step_name: Name of the step that timed out.
            timeout_seconds: Configured timeout value.
            elapsed_seconds: Actual elapsed time.
            operation_description: What the step was trying to do.
            **kwargs: Additional context passed to base class.
        """
        self.step_name = step_name
        self.timeout_seconds = timeout_seconds
        self.elapsed_seconds = elapsed_seconds
        self.operation_description = operation_description

        if message is None:
            message = self._build_message()

        super().__init__(message=message, **kwargs)

    def _build_message(self) -> str:
        """Build a descriptive error message."""
        parts = []

        if self.step_name:
            parts.append(f"Step '{self.step_name}' timed out")
        else:
            parts.append("Step timed out")

        if self.timeout_seconds is not None:
            parts.append(f"after {self.timeout_seconds:.1f}s timeout")

        if self.elapsed_seconds is not None:
            parts.append(f"(elapsed: {self.elapsed_seconds:.2f}s)")

        if self.operation_description:
            parts.append(f"while: {self.operation_description}")

        return " ".join(parts)

    @property
    def suggestion(self) -> str:
        """Get a suggestion for resolving the timeout."""
        suggestions = [
            f"Consider increasing the step timeout beyond {self.timeout_seconds}s",
            "Check if the operation is hanging or waiting for a resource",
            "Verify the service is responding in a timely manner",
            "Add retry logic if the operation is flaky",
        ]
        if self.timeout_seconds and self.timeout_seconds < 30:
            suggestions.insert(0, f"Current timeout ({self.timeout_seconds}s) may be too short")
        return "; ".join(suggestions[:2])

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary."""
        result = super().to_dict()
        result.update({
            "step_name": self.step_name,
            "timeout_seconds": self.timeout_seconds,
            "elapsed_seconds": self.elapsed_seconds,
            "operation_description": self.operation_description,
            "suggestion": self.suggestion,
        })
        return result


class JourneyTimeoutError(VenomTimeoutError):
    """Raised when a journey times out.

    Provides enhanced error messages with context about which step
    was executing when the timeout occurred.
    """

    error_code = ErrorCode.JOURNEY_TIMEOUT
    default_message = "Journey execution timed out"

    def __init__(
        self,
        message: str | None = None,
        journey_name: str | None = None,
        timeout_seconds: float | None = None,
        elapsed_seconds: float | None = None,
        current_step: str | None = None,
        completed_steps: int = 0,
        total_steps: int = 0,
        **kwargs: Any,
    ) -> None:
        """Initialize journey timeout error with context.

        Args:
            message: Custom error message.
            journey_name: Name of the journey that timed out.
            timeout_seconds: Configured journey timeout value.
            elapsed_seconds: Actual elapsed time.
            current_step: Step being executed when timeout occurred.
            completed_steps: Number of steps completed before timeout.
            total_steps: Total number of steps in journey.
            **kwargs: Additional context passed to base class.
        """
        self.journey_name = journey_name
        self.timeout_seconds = timeout_seconds
        self.elapsed_seconds = elapsed_seconds
        self.current_step = current_step
        self.completed_steps = completed_steps
        self.total_steps = total_steps

        if message is None:
            message = self._build_message()

        super().__init__(message=message, **kwargs)

    def _build_message(self) -> str:
        """Build a descriptive error message."""
        parts = []

        if self.journey_name:
            parts.append(f"Journey '{self.journey_name}' timed out")
        else:
            parts.append("Journey timed out")

        if self.timeout_seconds is not None:
            parts.append(f"after {self.timeout_seconds:.1f}s")

        if self.current_step:
            parts.append(f"while executing step '{self.current_step}'")

        if self.total_steps > 0:
            parts.append(f"({self.completed_steps}/{self.total_steps} steps completed)")

        return " ".join(parts)

    @property
    def suggestion(self) -> str:
        """Get a suggestion for resolving the timeout."""
        if self.total_steps > 0 and self.completed_steps > 0:
            avg_time = (self.elapsed_seconds or 0) / self.completed_steps
            estimated_total = avg_time * self.total_steps
            return (
                f"Consider increasing journey timeout to at least {estimated_total:.0f}s "
                f"(estimated based on {avg_time:.1f}s per step)"
            )
        return f"Consider increasing the journey timeout beyond {self.timeout_seconds}s"

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary."""
        result = super().to_dict()
        result.update({
            "journey_name": self.journey_name,
            "timeout_seconds": self.timeout_seconds,
            "elapsed_seconds": self.elapsed_seconds,
            "current_step": self.current_step,
            "completed_steps": self.completed_steps,
            "total_steps": self.total_steps,
            "suggestion": self.suggestion,
        })
        return result


class WaitTimeoutError(VenomTimeoutError):
    """Raised when a wait/poll operation times out.

    Provides enhanced error messages with context about the condition
    being waited for.
    """

    error_code = ErrorCode.REQUEST_TIMEOUT
    default_message = "Wait operation timed out"

    def __init__(
        self,
        message: str | None = None,
        condition_description: str | None = None,
        timeout_seconds: float | None = None,
        elapsed_seconds: float | None = None,
        poll_attempts: int = 0,
        poll_interval: float | None = None,
        last_value: Any = None,
        expected_value: Any = None,
        **kwargs: Any,
    ) -> None:
        """Initialize wait timeout error with context.

        Args:
            message: Custom error message.
            condition_description: Description of what was being waited for.
            timeout_seconds: Configured timeout value.
            elapsed_seconds: Actual elapsed time.
            poll_attempts: Number of poll attempts made.
            poll_interval: Interval between polls.
            last_value: Last observed value before timeout.
            expected_value: Expected value being waited for.
            **kwargs: Additional context passed to base class.
        """
        self.condition_description = condition_description
        self.timeout_seconds = timeout_seconds
        self.elapsed_seconds = elapsed_seconds
        self.poll_attempts = poll_attempts
        self.poll_interval = poll_interval
        self.last_value = last_value
        self.expected_value = expected_value

        if message is None:
            message = self._build_message()

        super().__init__(message=message, **kwargs)

    def _build_message(self) -> str:
        """Build a descriptive error message."""
        parts = ["Timeout"]

        if self.elapsed_seconds is not None:
            parts.append(f"after {self.elapsed_seconds:.1f}s")

        if self.condition_description:
            parts.append(f"waiting for: {self.condition_description}")

        if self.poll_attempts > 0:
            parts.append(f"({self.poll_attempts} attempts)")

        if self.last_value is not None and self.expected_value is not None:
            parts.append(f"[last={self.last_value!r}, expected={self.expected_value!r}]")
        elif self.last_value is not None:
            parts.append(f"[last value: {self.last_value!r}]")

        return " ".join(parts)

    @property
    def suggestion(self) -> str:
        """Get a suggestion for resolving the timeout."""
        suggestions = []

        if self.timeout_seconds is not None:
            suggestions.append(f"increase timeout beyond {self.timeout_seconds}s")

        if self.poll_interval and self.poll_interval > 1:
            suggestions.append(f"consider reducing poll interval from {self.poll_interval}s")

        if self.last_value is not None and self.expected_value is not None:
            suggestions.append(
                f"verify condition logic (last={self.last_value!r}, expected={self.expected_value!r})"
            )

        suggestions.append("check if the condition can ever be satisfied")

        return "Suggestions: " + "; ".join(suggestions[:3])

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary."""
        result = super().to_dict()
        result.update({
            "condition_description": self.condition_description,
            "timeout_seconds": self.timeout_seconds,
            "elapsed_seconds": self.elapsed_seconds,
            "poll_attempts": self.poll_attempts,
            "poll_interval": self.poll_interval,
            "last_value": repr(self.last_value) if self.last_value is not None else None,
            "expected_value": repr(self.expected_value) if self.expected_value is not None else None,
            "suggestion": self.suggestion,
        })
        return result


@dataclass
class RetryConfig:
    """Configuration for retry behavior.

    Can be created from YAML/dict configuration for easy setup.

    Attributes:
        max_attempts: Maximum number of retry attempts.
        base_delay: Initial delay between retries (seconds).
        max_delay: Maximum delay between retries (seconds).
        backoff_strategy: Strategy for calculating retry delays.
        exponential_base: Base for exponential backoff.
        jitter_factor: Jitter factor for delay randomization.
        retryable_exceptions: Tuple of exception types to retry on.
        retryable_status_codes: Set of HTTP status codes to retry on.
        on_retry: Callback invoked before each retry.

    Example:
        >>> # From YAML config
        >>> config = RetryConfig.from_yaml({
        ...     "max_attempts": 3,
        ...     "backoff": "exponential",
        ...     "initial_delay": 1.0,
        ...     "max_delay": 30.0,
        ...     "retry_on": [500, 502, 503, 504, "ConnectionError"]
        ... })
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL_FULL_JITTER
    exponential_base: float = 2.0
    jitter_factor: float = 0.5
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)
    retryable_status_codes: set[int] = field(default_factory=lambda: {429, 500, 502, 503, 504})
    on_retry: Callable[[int, Exception, float], None] | None = None

    @classmethod
    def from_yaml(cls, config: dict[str, Any]) -> RetryConfig:
        """Create RetryConfig from YAML/dict configuration.

        Supports the following YAML format:
            retry:
              max_attempts: 3
              backoff: exponential  # or linear, fixed
              initial_delay: 1.0
              max_delay: 30.0
              retry_on:
                - 500
                - 502
                - 503
                - 504
                - ConnectionError
                - Timeout

        Args:
            config: Dictionary configuration (from YAML or direct).

        Returns:
            Configured RetryConfig instance.
        """
        # Handle nested "retry" key
        if "retry" in config:
            config = config["retry"]

        # Parse backoff strategy
        backoff_str = config.get("backoff", config.get("backoff_strategy", "exponential"))
        if isinstance(backoff_str, str):
            backoff = BackoffStrategy.from_string(backoff_str)
        elif isinstance(backoff_str, BackoffStrategy):
            backoff = backoff_str
        else:
            backoff = BackoffStrategy.EXPONENTIAL_FULL_JITTER

        # Parse retryable conditions
        retry_on = config.get("retry_on", [])
        status_codes: set[int] = set()
        exception_types: list[type[Exception]] = []

        exception_mapping: dict[str, type[Exception]] = {
            "connectionerror": ConnectionError,
            "timeout": TimeoutError,
            "timeouterror": TimeoutError,
            "exception": Exception,
            "oserror": OSError,
            "ioerror": IOError,
        }

        for item in retry_on:
            if isinstance(item, int):
                status_codes.add(item)
            elif isinstance(item, str):
                if item.isdigit():
                    status_codes.add(int(item))
                else:
                    exc_name = item.lower().replace("_", "").replace("-", "")
                    if exc_name in exception_mapping:
                        exception_types.append(exception_mapping[exc_name])
                    else:
                        logger.warning(f"Unknown exception type in retry config: {item}")

        # Default status codes if not specified
        if not status_codes:
            status_codes = {429, 500, 502, 503, 504}

        # Default exceptions if not specified
        if not exception_types:
            exception_types = [ConnectionError, TimeoutError]

        return cls(
            max_attempts=config.get("max_attempts", 3),
            base_delay=config.get("initial_delay", config.get("base_delay", 1.0)),
            max_delay=config.get("max_delay", 60.0),
            backoff_strategy=backoff,
            exponential_base=config.get("exponential_base", 2.0),
            jitter_factor=config.get("jitter_factor", 0.5),
            retryable_exceptions=tuple(exception_types),
            retryable_status_codes=status_codes,
        )

    def to_yaml(self) -> dict[str, Any]:
        """Convert to YAML-compatible dictionary.

        Returns:
            Dictionary that can be serialized to YAML.
        """
        exception_names = [exc.__name__ for exc in self.retryable_exceptions]
        retry_on = list(self.retryable_status_codes) + exception_names

        return {
            "max_attempts": self.max_attempts,
            "backoff": self.backoff_strategy.value,
            "initial_delay": self.base_delay,
            "max_delay": self.max_delay,
            "retry_on": retry_on,
        }


class RetryPolicy:
    """Configurable retry policy with various backoff strategies."""

    def __init__(self, config: RetryConfig | None = None) -> None:
        self.config = config or RetryConfig()

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number (0-indexed)."""
        strategy = self.config.backoff_strategy

        if strategy == BackoffStrategy.FIXED:
            delay = self.config.base_delay

        elif strategy == BackoffStrategy.LINEAR:
            delay = self.config.base_delay * (attempt + 1)

        elif strategy == BackoffStrategy.EXPONENTIAL:
            delay = self.config.base_delay * (self.config.exponential_base**attempt)

        elif strategy == BackoffStrategy.EXPONENTIAL_FULL_JITTER:
            exponential_delay = self.config.base_delay * (self.config.exponential_base**attempt)
            delay = random.uniform(0, exponential_delay)

        elif strategy == BackoffStrategy.EXPONENTIAL_EQUAL_JITTER:
            exponential_delay = self.config.base_delay * (self.config.exponential_base**attempt)
            jitter = random.uniform(0, exponential_delay / 2)
            delay = exponential_delay / 2 + jitter

        elif strategy == BackoffStrategy.EXPONENTIAL_DECORRELATED_JITTER:
            if attempt == 0:
                delay = random.uniform(0, self.config.base_delay)
            else:
                cap = self.config.base_delay * 3
                delay = random.uniform(self.config.base_delay, min(cap, self.config.max_delay))

        else:
            delay = self.config.base_delay

        return min(delay, self.config.max_delay)

    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Determine if the operation should be retried."""
        if attempt >= self.config.max_attempts:
            return False

        if isinstance(exception, RateLimitedError):
            return True

        if isinstance(exception, VenomQAError):
            if not exception.recoverable:
                return False

        return isinstance(exception, self.config.retryable_exceptions)

    def execute(self, operation: Callable[[], T]) -> T:
        """Execute an operation with retry logic."""
        last_error: Exception | None = None

        for attempt in range(self.config.max_attempts):
            try:
                return operation()
            except Exception as e:
                last_error = e

                if not self.should_retry(e, attempt):
                    raise

                if attempt < self.config.max_attempts - 1:
                    delay = self._get_delay_for_exception(e, attempt)

                    if self.config.on_retry:
                        self.config.on_retry(attempt + 1, e, delay)

                    logger.warning(
                        f"Retry {attempt + 1}/{self.config.max_attempts} "
                        f"after {delay:.2f}s due to: {e}"
                    )
                    time.sleep(delay)

        raise RetryExhaustedError(
            message=f"All {self.config.max_attempts} retry attempts exhausted",
            attempts=self.config.max_attempts,
            last_error=last_error,
        )

    async def execute_async(self, operation: Callable[[], T]) -> T:
        """Execute an async operation with retry logic."""
        last_error: Exception | None = None

        for attempt in range(self.config.max_attempts):
            try:
                result = operation()
                if asyncio.iscoroutine(result):
                    return await result
                return result
            except Exception as e:
                last_error = e

                if not self.should_retry(e, attempt):
                    raise

                if attempt < self.config.max_attempts - 1:
                    delay = self._get_delay_for_exception(e, attempt)

                    if self.config.on_retry:
                        self.config.on_retry(attempt + 1, e, delay)

                    logger.warning(
                        f"Retry {attempt + 1}/{self.config.max_attempts} "
                        f"after {delay:.2f}s due to: {e}"
                    )
                    await asyncio.sleep(delay)

        raise RetryExhaustedError(
            message=f"All {self.config.max_attempts} retry attempts exhausted",
            attempts=self.config.max_attempts,
            last_error=last_error,
        )

    def _get_delay_for_exception(self, exception: Exception, attempt: int) -> float:
        """Get delay, respecting Retry-After header if present."""
        if isinstance(exception, RateLimitedError) and exception.retry_after:
            return exception.retry_after
        return self.calculate_delay(attempt)


class CircuitState(Enum):
    """Circuit breaker states.

    Attributes:
        CLOSED: Normal operation, requests allowed.
        OPEN: Circuit tripped, requests blocked.
        HALF_OPEN: Testing state, limited requests allowed.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitStats:
    """Statistics for circuit breaker.

    Attributes:
        failures: Total failure count.
        successes: Total success count.
        last_failure_time: Timestamp of last failure.
        last_success_time: Timestamp of last success.
        consecutive_failures: Current streak of consecutive failures.
        total_requests: Total number of requests processed.
        rejected_requests: Number of requests rejected due to open circuit.
    """

    failures: int = 0
    successes: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None
    consecutive_failures: int = 0
    total_requests: int = 0
    rejected_requests: int = 0

    @property
    def failure_rate(self) -> float:
        """Calculate the failure rate as a percentage."""
        total = self.failures + self.successes
        if total == 0:
            return 0.0
        return (self.failures / total) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "failures": self.failures,
            "successes": self.successes,
            "consecutive_failures": self.consecutive_failures,
            "total_requests": self.total_requests,
            "rejected_requests": self.rejected_requests,
            "failure_rate": f"{self.failure_rate:.1f}%",
            "last_failure_time": (
                datetime.fromtimestamp(self.last_failure_time).isoformat()
                if self.last_failure_time
                else None
            ),
            "last_success_time": (
                datetime.fromtimestamp(self.last_success_time).isoformat()
                if self.last_success_time
                else None
            ),
        }


class CircuitBreaker:
    """Circuit breaker pattern implementation.

    Prevents cascading failures by stopping requests to failing services.
    After a threshold of failures, the circuit "opens" and rejects requests
    for a cooldown period before attempting recovery.

    Attributes:
        name: Optional name for this circuit breaker (for logging/registry).
        failure_threshold: Number of consecutive failures before opening.
        recovery_timeout: Seconds to wait before attempting recovery.
        half_open_max_calls: Max test calls in half-open state.
        on_state_change: Callback when state changes.

    Example:
        >>> breaker = CircuitBreaker(
        ...     name="payment-service",
        ...     failure_threshold=5,
        ...     recovery_timeout=30.0
        ... )
        >>> result = breaker.execute(lambda: call_payment_api())
    """

    def __init__(
        self,
        name: str | None = None,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        on_state_change: Callable[[CircuitState, CircuitState], None] | None = None,
        failure_rate_threshold: float | None = None,
        min_requests_for_rate: int = 10,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            name: Optional name for identification.
            failure_threshold: Consecutive failures to trip circuit.
            recovery_timeout: Cooldown seconds before testing recovery.
            half_open_max_calls: Max calls allowed in half-open state.
            on_state_change: Callback for state transitions.
            failure_rate_threshold: Alternative: trip on failure % (e.g., 50.0).
            min_requests_for_rate: Min requests before checking rate threshold.
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.on_state_change = on_state_change
        self.failure_rate_threshold = failure_rate_threshold
        self.min_requests_for_rate = min_requests_for_rate

        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._half_open_calls = 0
        self._lock = threading.RLock()
        self._async_lock: asyncio.Lock | None = None

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, auto-transitioning if needed."""
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)."""
        return self.state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self.state == CircuitState.HALF_OPEN

    @property
    def stats(self) -> CircuitStats:
        """Get current statistics."""
        with self._lock:
            return self._stats

    @property
    def time_until_reset(self) -> float | None:
        """Get seconds until circuit attempts reset, or None if not open."""
        with self._lock:
            if self._state != CircuitState.OPEN:
                return None
            if self._stats.last_failure_time is None:
                return None
            elapsed = time.time() - self._stats.last_failure_time
            remaining = self.recovery_timeout - elapsed
            return max(0.0, remaining)

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self._stats.last_failure_time is None:
            return False
        elapsed = time.time() - self._stats.last_failure_time
        return elapsed >= self.recovery_timeout

    def _should_trip_on_failure_rate(self) -> bool:
        """Check if circuit should trip based on failure rate."""
        if self.failure_rate_threshold is None:
            return False
        total = self._stats.failures + self._stats.successes
        if total < self.min_requests_for_rate:
            return False
        return self._stats.failure_rate >= self.failure_rate_threshold

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0

        if old_state != new_state:
            name_str = f"[{self.name}] " if self.name else ""
            logger.info(f"{name_str}Circuit breaker: {old_state.value} -> {new_state.value}")

            if self.on_state_change:
                try:
                    self.on_state_change(old_state, new_state)
                except Exception as e:
                    logger.error(f"Error in circuit breaker state change callback: {e}")

    def _check_circuit(self) -> None:
        """Check if circuit allows execution, raising if not."""
        with self._lock:
            self._stats.total_requests += 1
            state = self.state

            if state == CircuitState.OPEN:
                self._stats.rejected_requests += 1
                name_str = f" for service '{self.name}'" if self.name else ""
                time_info = ""
                remaining = self.time_until_reset
                if remaining is not None:
                    time_info = f" (retry in {remaining:.1f}s)"

                raise CircuitOpenError(
                    message=f"Circuit breaker is open{name_str}{time_info}",
                    failures_count=self._stats.consecutive_failures,
                    reset_timeout=self.recovery_timeout,
                )

            if state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    self._stats.rejected_requests += 1
                    raise CircuitOpenError(
                        message=f"Circuit breaker in half-open state, max test calls ({self.half_open_max_calls}) reached",
                        failures_count=self._stats.failures,
                        reset_timeout=self.recovery_timeout,
                    )

    def _record_success(self) -> None:
        """Record a successful operation."""
        with self._lock:
            self._stats.successes += 1
            self._stats.last_success_time = time.time()
            self._stats.consecutive_failures = 0

            if self._state == CircuitState.HALF_OPEN:
                # Successfully recovered - close the circuit
                self._transition_to(CircuitState.CLOSED)
                # Reset stats for fresh start
                old_rejected = self._stats.rejected_requests
                self._stats = CircuitStats()
                self._stats.rejected_requests = old_rejected  # Preserve rejected count

    def _record_failure(self, exception: Exception | None = None) -> None:
        """Record a failed operation."""
        with self._lock:
            self._stats.failures += 1
            self._stats.last_failure_time = time.time()
            self._stats.consecutive_failures += 1

            if self._state == CircuitState.HALF_OPEN:
                # Recovery failed - reopen circuit
                self._transition_to(CircuitState.OPEN)

            elif self._state == CircuitState.CLOSED:
                # Check both consecutive threshold and rate threshold
                should_trip = (
                    self._stats.consecutive_failures >= self.failure_threshold
                    or self._should_trip_on_failure_rate()
                )
                if should_trip:
                    name_str = f"[{self.name}] " if self.name else ""
                    logger.warning(
                        f"{name_str}Circuit breaker tripping after "
                        f"{self._stats.consecutive_failures} consecutive failures "
                        f"(total: {self._stats.failures}, rate: {self._stats.failure_rate:.1f}%)"
                    )
                    self._transition_to(CircuitState.OPEN)

    def execute(self, operation: Callable[[], T]) -> T:
        """Execute an operation through the circuit breaker.

        Args:
            operation: Callable to execute.

        Returns:
            Result of the operation.

        Raises:
            CircuitOpenError: If circuit is open.
            Any exception from the operation.
        """
        self._check_circuit()

        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

        try:
            result = operation()
            self._record_success()
            return result
        except Exception as e:
            self._record_failure(e)
            raise

    async def execute_async(self, operation: Callable[[], T | Awaitable[T]]) -> T:
        """Execute an async operation through the circuit breaker.

        Args:
            operation: Callable (sync or async) to execute.

        Returns:
            Result of the operation.

        Raises:
            CircuitOpenError: If circuit is open.
            Any exception from the operation.
        """
        self._check_circuit()

        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

        try:
            result = operation()
            if asyncio.iscoroutine(result):
                typed_result: T = await result
                self._record_success()
                return typed_result
            self._record_success()
            return result
        except Exception as e:
            self._record_failure(e)
            raise

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        with self._lock:
            self._stats = CircuitStats()
            self._transition_to(CircuitState.CLOSED)

    def trip(self) -> None:
        """Force the circuit breaker to open immediately."""
        with self._lock:
            self._stats.last_failure_time = time.time()
            self._transition_to(CircuitState.OPEN)

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics as a dictionary."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "stats": self._stats.to_dict(),
                "config": {
                    "failure_threshold": self.failure_threshold,
                    "recovery_timeout": self.recovery_timeout,
                    "half_open_max_calls": self.half_open_max_calls,
                    "failure_rate_threshold": self.failure_rate_threshold,
                },
                "time_until_reset": self.time_until_reset,
            }


@dataclass
class ResilientClient(Generic[T]):
    """Combines retry policy with circuit breaker for resilient operations.

    Example:
        >>> policy = RetryPolicy()
        >>> breaker = CircuitBreaker(name="api")
        >>> client = ResilientClient(policy, breaker)
        >>> result = client.execute(lambda: call_api())
    """

    retry_policy: RetryPolicy
    circuit_breaker: CircuitBreaker

    def execute(self, operation: Callable[[], T]) -> T:
        """Execute with both retry and circuit breaker protection."""
        return self.circuit_breaker.execute(lambda: self.retry_policy.execute(operation))

    async def execute_async(self, operation: Callable[[], T | Awaitable[T]]) -> T:
        """Execute async with both retry and circuit breaker protection."""

        async def wrapped() -> T:
            return await self.retry_policy.execute_async(operation)

        return await self.circuit_breaker.execute_async(wrapped)


class CircuitBreakerRegistry:
    """Registry for service-specific circuit breakers.

    Manages a collection of circuit breakers, one per service, enabling
    isolated failure handling for different backends.

    Example:
        >>> registry = CircuitBreakerRegistry.get_instance()
        >>> payment_breaker = registry.get_or_create("payment-service")
        >>> result = payment_breaker.execute(lambda: call_payment_api())

    YAML Configuration:
        circuit_breakers:
          payment-service:
            failure_threshold: 5
            recovery_timeout: 30.0
          inventory-service:
            failure_threshold: 3
            recovery_timeout: 60.0
    """

    _instance: CircuitBreakerRegistry | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        """Initialize the registry."""
        self._breakers: dict[str, CircuitBreaker] = {}
        self._default_config: dict[str, Any] = {
            "failure_threshold": 5,
            "recovery_timeout": 30.0,
            "half_open_max_calls": 3,
        }
        self._service_configs: dict[str, dict[str, Any]] = {}
        self._registry_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> CircuitBreakerRegistry:
        """Get the singleton registry instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance._breakers.clear()
            cls._instance = None

    def configure(self, config: dict[str, Any]) -> None:
        """Configure the registry from YAML/dict.

        Args:
            config: Configuration dict, optionally with "circuit_breakers" key.
        """
        with self._registry_lock:
            if "circuit_breakers" in config:
                config = config["circuit_breakers"]

            if "default" in config:
                self._default_config.update(config.pop("default"))

            for service_name, service_config in config.items():
                self._service_configs[service_name] = {
                    **self._default_config,
                    **service_config,
                }

    def get_or_create(
        self,
        service_name: str,
        failure_threshold: int | None = None,
        recovery_timeout: float | None = None,
        **kwargs: Any,
    ) -> CircuitBreaker:
        """Get existing or create new circuit breaker for a service.

        Args:
            service_name: Name of the service.
            failure_threshold: Override default failure threshold.
            recovery_timeout: Override default recovery timeout.
            **kwargs: Additional circuit breaker configuration.

        Returns:
            CircuitBreaker instance for the service.
        """
        with self._registry_lock:
            if service_name not in self._breakers:
                # Get service-specific config or defaults
                config = self._service_configs.get(service_name, self._default_config.copy())

                # Apply overrides
                if failure_threshold is not None:
                    config["failure_threshold"] = failure_threshold
                if recovery_timeout is not None:
                    config["recovery_timeout"] = recovery_timeout
                config.update(kwargs)

                self._breakers[service_name] = CircuitBreaker(
                    name=service_name,
                    **config,
                )

            return self._breakers[service_name]

    def get(self, service_name: str) -> CircuitBreaker | None:
        """Get circuit breaker for a service if it exists.

        Args:
            service_name: Name of the service.

        Returns:
            CircuitBreaker or None if not found.
        """
        with self._registry_lock:
            return self._breakers.get(service_name)

    def remove(self, service_name: str) -> bool:
        """Remove a circuit breaker from the registry.

        Args:
            service_name: Name of the service.

        Returns:
            True if removed, False if not found.
        """
        with self._registry_lock:
            if service_name in self._breakers:
                del self._breakers[service_name]
                return True
            return False

    def reset_all(self) -> None:
        """Reset all circuit breakers to closed state."""
        with self._registry_lock:
            for breaker in self._breakers.values():
                breaker.reset()

    def trip_all(self) -> None:
        """Trip all circuit breakers to open state."""
        with self._registry_lock:
            for breaker in self._breakers.values():
                breaker.trip()

    def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all circuit breakers.

        Returns:
            Dictionary mapping service names to their stats.
        """
        with self._registry_lock:
            return {name: breaker.get_stats() for name, breaker in self._breakers.items()}

    def get_open_circuits(self) -> list[str]:
        """Get list of services with open circuits.

        Returns:
            List of service names with open circuits.
        """
        with self._registry_lock:
            return [name for name, breaker in self._breakers.items() if breaker.is_open]

    def __len__(self) -> int:
        """Get number of registered circuit breakers."""
        with self._registry_lock:
            return len(self._breakers)

    def __contains__(self, service_name: str) -> bool:
        """Check if a service has a circuit breaker."""
        with self._registry_lock:
            return service_name in self._breakers


def create_default_retry_policy(
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> RetryPolicy:
    """Create a retry policy with sensible defaults.

    Args:
        max_attempts: Maximum retry attempts.
        base_delay: Initial delay between retries.

    Returns:
        Configured RetryPolicy instance.
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        backoff_strategy=BackoffStrategy.EXPONENTIAL_FULL_JITTER,
        retryable_exceptions=(
            ConnectionError,
            TimeoutError,
        ),
    )
    return RetryPolicy(config)


def create_default_circuit_breaker(
    name: str | None = None,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
) -> CircuitBreaker:
    """Create a circuit breaker with sensible defaults.

    Args:
        name: Optional name for the circuit breaker.
        failure_threshold: Failures before circuit opens.
        recovery_timeout: Cooldown before recovery attempt.

    Returns:
        Configured CircuitBreaker instance.
    """
    return CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
    )


def with_timeout(
    timeout: float,
    operation_description: str | None = None,
) -> Callable[[F], F]:
    """Decorator to add timeout to a synchronous function.

    Args:
        timeout: Timeout in seconds.
        operation_description: Description for error messages.

    Returns:
        Decorated function.

    Example:
        >>> @with_timeout(10.0, "fetching user data")
        ... def get_user(user_id: int):
        ...     return api.get(f"/users/{user_id}")
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            import concurrent.futures

            start_time = time.time()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, *args, **kwargs)
                try:
                    return future.result(timeout=timeout)
                except concurrent.futures.TimeoutError:
                    elapsed = time.time() - start_time
                    raise StepTimeoutError(
                        step_name=func.__name__,
                        timeout_seconds=timeout,
                        elapsed_seconds=elapsed,
                        operation_description=operation_description,
                    )

        return wrapper  # type: ignore

    return decorator


def with_timeout_async(
    timeout: float,
    operation_description: str | None = None,
) -> Callable[[F], F]:
    """Decorator to add timeout to an async function.

    Args:
        timeout: Timeout in seconds.
        operation_description: Description for error messages.

    Returns:
        Decorated async function.

    Example:
        >>> @with_timeout_async(10.0, "fetching user data")
        ... async def get_user(user_id: int):
        ...     return await api.get(f"/users/{user_id}")
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                raise StepTimeoutError(
                    step_name=func.__name__,
                    timeout_seconds=timeout,
                    elapsed_seconds=elapsed,
                    operation_description=operation_description,
                )

        return wrapper  # type: ignore

    return decorator


def execute_with_timeout(
    operation: Callable[[], T],
    timeout: float,
    operation_description: str | None = None,
) -> T:
    """Execute an operation with a timeout.

    Args:
        operation: Callable to execute.
        timeout: Timeout in seconds.
        operation_description: Description for error messages.

    Returns:
        Result of the operation.

    Raises:
        StepTimeoutError: If operation times out.
    """
    import concurrent.futures

    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(operation)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            elapsed = time.time() - start_time
            raise StepTimeoutError(
                timeout_seconds=timeout,
                elapsed_seconds=elapsed,
                operation_description=operation_description,
            )


async def execute_with_timeout_async(
    operation: Callable[[], Awaitable[T]],
    timeout: float,
    operation_description: str | None = None,
) -> T:
    """Execute an async operation with a timeout.

    Args:
        operation: Async callable to execute.
        timeout: Timeout in seconds.
        operation_description: Description for error messages.

    Returns:
        Result of the operation.

    Raises:
        StepTimeoutError: If operation times out.
    """
    start_time = time.time()
    try:
        return await asyncio.wait_for(operation(), timeout=timeout)
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        raise StepTimeoutError(
            timeout_seconds=timeout,
            elapsed_seconds=elapsed,
            operation_description=operation_description,
        )
