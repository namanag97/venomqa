"""Retry policies with exponential backoff and jitter."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Generic, TypeVar

from venomqa.errors.base import (
    CircuitOpenError,
    RateLimitedError,
    RetryExhaustedError,
    VenomQAError,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BackoffStrategy(Enum):
    """Available backoff strategies."""

    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_FULL_JITTER = "exponential_full_jitter"
    EXPONENTIAL_EQUAL_JITTER = "exponential_equal_jitter"
    EXPONENTIAL_DECORRELATED_JITTER = "exponential_decorrelated_jitter"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL_FULL_JITTER
    exponential_base: float = 2.0
    jitter_factor: float = 0.5
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)
    retryable_status_codes: set[int] = field(default_factory=lambda: {429, 500, 502, 503, 504})
    on_retry: Callable[[int, Exception, float], None] | None = None


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
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitStats:
    """Statistics for circuit breaker."""

    failures: int = 0
    successes: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None
    consecutive_failures: int = 0


class CircuitBreaker:
    """Circuit breaker pattern implementation."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
        on_state_change: Callable[[CircuitState, CircuitState], None] | None = None,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.on_state_change = on_state_change

        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._half_open_calls = 0
        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to(CircuitState.HALF_OPEN)
        return self._state

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        return self.state == CircuitState.HALF_OPEN

    def _should_attempt_reset(self) -> bool:
        if self._stats.last_failure_time is None:
            return False
        elapsed = time.time() - self._stats.last_failure_time
        return elapsed >= self.recovery_timeout

    def _transition_to(self, new_state: CircuitState) -> None:
        old_state = self._state
        self._state = new_state
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
        if self.on_state_change and old_state != new_state:
            logger.info(f"Circuit breaker: {old_state.value} -> {new_state.value}")
            self.on_state_change(old_state, new_state)

    def _check_circuit(self) -> None:
        """Check if circuit allows execution."""
        state = self.state

        if state == CircuitState.OPEN:
            raise CircuitOpenError(
                message="Circuit breaker is open",
                failures_count=self._stats.failures,
                reset_timeout=self.recovery_timeout,
            )

        if state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.half_open_max_calls:
                raise CircuitOpenError(
                    message="Circuit breaker in half-open state, max calls reached",
                    failures_count=self._stats.failures,
                    reset_timeout=self.recovery_timeout,
                )

    def _record_success(self) -> None:
        """Record a successful operation."""
        self._stats.successes += 1
        self._stats.last_success_time = time.time()
        self._stats.consecutive_failures = 0

        if self._state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.CLOSED)
            self._stats = CircuitStats()

    def _record_failure(self) -> None:
        """Record a failed operation."""
        self._stats.failures += 1
        self._stats.last_failure_time = time.time()
        self._stats.consecutive_failures += 1

        if self._state == CircuitState.HALF_OPEN:
            self._transition_to(CircuitState.OPEN)

        elif self._state == CircuitState.CLOSED:
            if self._stats.consecutive_failures >= self.failure_threshold:
                self._transition_to(CircuitState.OPEN)

    def execute(self, operation: Callable[[], T]) -> T:
        """Execute an operation through the circuit breaker."""
        self._check_circuit()

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1

        try:
            result = operation()
            self._record_success()
            return result
        except Exception:
            self._record_failure()
            raise

    async def execute_async(self, operation: Callable[[], T]) -> T:
        """Execute an async operation through the circuit breaker."""
        self._check_circuit()

        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1

        try:
            result = operation()
            if asyncio.iscoroutine(result):
                result = await result
            self._record_success()
            return result
        except Exception:
            self._record_failure()
            raise

    def reset(self) -> None:
        """Reset the circuit breaker to closed state."""
        self._stats = CircuitStats()
        self._transition_to(CircuitState.CLOSED)

    def trip(self) -> None:
        """Force the circuit breaker to open."""
        self._stats.last_failure_time = time.time()
        self._transition_to(CircuitState.OPEN)


@dataclass
class ResilientClient(Generic[T]):
    """Combines retry policy with circuit breaker for resilient operations."""

    retry_policy: RetryPolicy
    circuit_breaker: CircuitBreaker

    def execute(self, operation: Callable[[], T]) -> T:
        """Execute with both retry and circuit breaker protection."""
        return self.circuit_breaker.execute(lambda: self.retry_policy.execute(operation))

    async def execute_async(self, operation: Callable[[], T]) -> T:
        """Execute async with both retry and circuit breaker protection."""
        return await self.circuit_breaker.execute_async(
            lambda: self.retry_policy.execute_async(operation)
        )


def create_default_retry_policy(
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> RetryPolicy:
    """Create a retry policy with sensible defaults."""
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
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
) -> CircuitBreaker:
    """Create a circuit breaker with sensible defaults."""
    return CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
    )
