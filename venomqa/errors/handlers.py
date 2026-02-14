"""Global error handlers and recovery strategies."""

from __future__ import annotations

import functools
import json
import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from venomqa.errors.base import (
    CircuitOpenError,
    ConnectionError,
    ConnectionTimeoutError,
    ErrorContext,
    RateLimitedError,
    RetryExhaustedError,
    StateNotConnectedError,
    ValidationError,
    VenomQAError,
)
from venomqa.errors.retry import CircuitBreaker, RetryPolicy

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


class RecoveryStrategy(Enum):
    """Available recovery strategies."""

    SKIP = "skip"
    ABORT = "abort"
    RETRY = "retry"
    FALLBACK = "fallback"
    RAISE = "raise"


@dataclass
class RecoveryResult(Generic[T]):
    """Result of a recovery attempt."""

    success: bool
    value: T | None = None
    error: Exception | None = None
    strategy_used: RecoveryStrategy | None = None
    retries: int = 0


@dataclass
class ErrorHandlerConfig:
    """Configuration for error handler behavior."""

    default_strategy: RecoveryStrategy = RecoveryStrategy.RAISE
    enable_circuit_breaker: bool = True
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 30.0
    retry_policy: RetryPolicy | None = None
    fallback_handler: Callable[[Exception], Any] | None = None
    on_error: Callable[[VenomQAError], None] | None = None
    log_errors: bool = True
    include_traceback: bool = True


class ErrorLogger:
    """Structured error logging with context."""

    def __init__(
        self,
        name: str = "venomqa",
        include_traceback: bool = True,
    ) -> None:
        self.logger = logging.getLogger(name)
        self.include_traceback = include_traceback

    def log_error(
        self,
        error: Exception,
        context: ErrorContext | None = None,
        level: int = logging.ERROR,
    ) -> None:
        """Log an error with structured context."""
        error_data = self._build_error_data(error, context)

        if isinstance(error, VenomQAError):
            message = f"[{error.error_code.value}] {error.message}"
        else:
            message = str(error)

        self.logger.log(level, message, extra={"error_data": error_data})

    def log_warning(
        self,
        error: Exception,
        context: ErrorContext | None = None,
    ) -> None:
        """Log an error as a warning."""
        self.log_error(error, context, level=logging.WARNING)

    def _build_error_data(
        self,
        error: Exception,
        context: ErrorContext | None = None,
    ) -> dict[str, Any]:
        """Build structured error data for logging."""
        data: dict[str, Any] = {
            "error_type": error.__class__.__name__,
            "message": str(error),
        }

        if isinstance(error, VenomQAError):
            data.update(error.to_dict())

        if context:
            data["context"] = context.to_dict()

        if self.include_traceback:
            data["traceback"] = traceback.format_exc()

        return data

    def log_structured(
        self,
        event: str,
        **kwargs: Any,
    ) -> None:
        """Log a structured event."""
        self.logger.info(
            json.dumps({"event": event, **kwargs}),
            extra={"structured": True},
        )


class RecoveryHandler:
    """Handles error recovery with configurable strategies."""

    def __init__(self, config: ErrorHandlerConfig | None = None) -> None:
        self.config = config or ErrorHandlerConfig()
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._fallback_handlers: dict[type[Exception], Callable[[Exception], Any]] = {}
        self._logger = ErrorLogger(include_traceback=self.config.include_traceback)

        if self.config.fallback_handler:
            self._fallback_handlers[Exception] = self.config.fallback_handler

    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """Get or create a circuit breaker by name."""
        if name not in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreaker(
                failure_threshold=self.config.circuit_breaker_threshold,
                recovery_timeout=self.config.circuit_breaker_timeout,
            )
        return self._circuit_breakers[name]

    def register_fallback(
        self,
        exception_type: type[Exception],
        handler: Callable[[Exception], Any],
    ) -> None:
        """Register a fallback handler for a specific exception type."""
        self._fallback_handlers[exception_type] = handler

    def handle(
        self,
        error: Exception,
        strategy: RecoveryStrategy | None = None,
        context: ErrorContext | None = None,
        operation: Callable[[], T] | None = None,
        circuit_name: str | None = None,
    ) -> RecoveryResult[T]:
        """Handle an error using the specified strategy."""
        strategy = strategy or self._get_strategy_for_error(error)

        if self.config.log_errors:
            self._logger.log_error(error, context)

        if self.config.on_error and isinstance(error, VenomQAError):
            self.config.on_error(error)

        try:
            if strategy == RecoveryStrategy.SKIP:
                return RecoveryResult(success=True, strategy_used=strategy)

            elif strategy == RecoveryStrategy.ABORT:
                return RecoveryResult(success=False, error=error, strategy_used=strategy)

            elif strategy == RecoveryStrategy.RETRY:
                return self._handle_retry(error, operation, context)

            elif strategy == RecoveryStrategy.FALLBACK:
                return self._handle_fallback(error, context)

            else:
                raise error

        except Exception as e:
            return RecoveryResult(success=False, error=e, strategy_used=strategy)

    def _get_strategy_for_error(self, error: Exception) -> RecoveryStrategy:
        """Determine recovery strategy based on error type."""
        if isinstance(error, ValidationError):
            return RecoveryStrategy.ABORT

        if isinstance(error, StateNotConnectedError):
            return RecoveryStrategy.ABORT

        if isinstance(error, CircuitOpenError):
            return RecoveryStrategy.FALLBACK

        if isinstance(error, RateLimitedError):
            return RecoveryStrategy.RETRY

        if isinstance(error, (ConnectionError, ConnectionTimeoutError)):
            return RecoveryStrategy.RETRY

        return self.config.default_strategy

    def _handle_retry(
        self,
        error: Exception,
        operation: Callable[[], T] | None,
        context: ErrorContext | None,
    ) -> RecoveryResult[T]:
        """Handle error with retry."""
        if operation is None:
            return RecoveryResult(success=False, error=error, strategy_used=RecoveryStrategy.RETRY)

        retry_policy = self.config.retry_policy or RetryPolicy()

        try:
            result = retry_policy.execute(operation)
            return RecoveryResult(success=True, value=result, strategy_used=RecoveryStrategy.RETRY)
        except RetryExhaustedError as e:
            return RecoveryResult(
                success=False,
                error=e,
                strategy_used=RecoveryStrategy.RETRY,
                retries=e.attempts,
            )

    def _handle_fallback(
        self,
        error: Exception,
        context: ErrorContext | None,
    ) -> RecoveryResult[T]:
        """Handle error with fallback handler."""
        for exc_type, handler in self._fallback_handlers.items():
            if isinstance(error, exc_type):
                try:
                    result = handler(error)
                    return RecoveryResult(
                        success=True,
                        value=result,
                        strategy_used=RecoveryStrategy.FALLBACK,
                    )
                except Exception as e:
                    return RecoveryResult(
                        success=False,
                        error=e,
                        strategy_used=RecoveryStrategy.FALLBACK,
                    )

        return RecoveryResult(success=False, error=error, strategy_used=RecoveryStrategy.FALLBACK)


class GlobalErrorHandler:
    """Global error handler for VenomQA."""

    _instance: GlobalErrorHandler | None = None

    def __init__(self) -> None:
        self._handlers: dict[type[Exception], Callable[[Exception], Any]] = {}
        self._recovery_handler = RecoveryHandler()
        self._logger = ErrorLogger()

    @classmethod
    def get_instance(cls) -> GlobalErrorHandler:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def register_handler(
        self,
        exception_type: type[Exception],
        handler: Callable[[Exception], Any],
    ) -> None:
        """Register a handler for a specific exception type."""
        self._handlers[exception_type] = handler

    def handle(self, error: Exception, context: ErrorContext | None = None) -> Any:
        """Handle an exception using registered handlers."""
        self._logger.log_error(error, context)

        for exc_type, handler in self._handlers.items():
            if isinstance(error, exc_type):
                return handler(error)

        raise error

    def wrap(
        self,
        func: F,
        strategy: RecoveryStrategy = RecoveryStrategy.RAISE,
        context: ErrorContext | None = None,
    ) -> F:
        """Wrap a function with error handling."""

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                result = self._recovery_handler.handle(
                    e,
                    strategy=strategy,
                    context=context,
                    operation=lambda: func(*args, **kwargs),
                )
                if result.success:
                    return result.value
                if result.error is not None:
                    raise result.error from e
                raise e

        return wrapper


def handle_errors(
    strategy: RecoveryStrategy = RecoveryStrategy.RAISE,
    reraise: bool = True,
) -> Callable[[F], F]:
    """Decorator for handling errors in functions."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            handler = GlobalErrorHandler.get_instance()
            try:
                return func(*args, **kwargs)
            except Exception as e:
                ctx = ErrorContext(extra={"function": func.__name__})
                result = handler._recovery_handler.handle(
                    e,
                    strategy=strategy,
                    context=ctx,
                    operation=lambda: func(*args, **kwargs),
                )
                if result.success:
                    return result.value
                if reraise:
                    exc = result.error if result.error is not None else e
                    raise exc from e
                return None

        return wrapper

    return decorator


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> Callable[[F], F]:
    """Decorator to add retry logic to a function."""
    from venomqa.errors.retry import RetryConfig, RetryPolicy

    policy = RetryPolicy(
        RetryConfig(
            max_attempts=max_attempts,
            base_delay=base_delay,
        )
    )

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return policy.execute(lambda: func(*args, **kwargs))

        return wrapper

    return decorator


def with_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
) -> Callable[[F], F]:
    """Decorator to add circuit breaker protection to a function."""
    handler = GlobalErrorHandler.get_instance()
    circuit = handler._recovery_handler.get_circuit_breaker(name)

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return circuit.execute(lambda: func(*args, **kwargs))

        return wrapper

    return decorator
