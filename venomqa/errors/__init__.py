"""VenomQA Error Handling Module.

Provides comprehensive error handling, debugging, and troubleshooting:

- Custom exception hierarchy with error codes
- Retry policies with exponential backoff
- Circuit breaker pattern for resilience
- Debug context for detailed error information
- Troubleshooting suggestions for common errors
- Filtered stack traces highlighting user code
"""

from venomqa.errors.base import (
    BranchError,
    CheckpointError,
    CircuitOpenError,
    ConfigValidationError,
    ConnectionError,
    ConnectionRefusedError,
    ConnectionResetError,
    ConnectionTimeoutError,
    ErrorCode,
    ErrorContext,
    JourneyAbortedError,
    JourneyError,
    JourneyTimeoutError,
    JourneyValidationError,
    PathError,
    PluginError,
    RateLimitedError,
    ReporterError,
    RequestFailedError,
    RequestTimeoutError,
    ResetError,
    RetryExhaustedError,
    RollbackError,
    SchemaMismatchError,
    StateError,
    StateNotConnectedError,
    StepValidationError,
    TimeoutError,
    ValidationError,
    VenomQAError,
)
from venomqa.errors.debug import (
    DebugContext,
    DebugLevel,
    DebugLogger,
    ErrorFormatter,
    StackTraceFilter,
    StepThroughController,
    TroubleshootingEngine,
    create_debug_context,
    format_error,
)
from venomqa.errors.handlers import (
    ErrorHandlerConfig,
    ErrorLogger,
    GlobalErrorHandler,
    RecoveryHandler,
    RecoveryResult,
    RecoveryStrategy,
    handle_errors,
    with_circuit_breaker,
    with_retry,
)
from venomqa.errors.retry import (
    BackoffStrategy,
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
    CircuitStats,
    ResilientClient,
    RetryConfig,
    RetryPolicy,
    StepTimeoutError,
    WaitTimeoutError,
    create_default_circuit_breaker,
    create_default_retry_policy,
    execute_with_timeout,
    execute_with_timeout_async,
    with_timeout,
    with_timeout_async,
)
from venomqa.errors.retry import (
    JourneyTimeoutError as JourneyTimeoutErrorEnhanced,
)
from venomqa.errors.retry import (
    RetryExhaustedError as RetryExhaustedErrorRetry,  # noqa: F401
)

__all__ = [
    # Base exceptions
    "VenomQAError",
    "ErrorCode",
    "ErrorContext",
    # Connection errors
    "ConnectionError",
    "ConnectionTimeoutError",
    "ConnectionRefusedError",
    "ConnectionResetError",
    # Timeout errors
    "TimeoutError",
    "RequestTimeoutError",
    "RequestFailedError",
    # Validation errors
    "ValidationError",
    "ConfigValidationError",
    "JourneyValidationError",
    "StepValidationError",
    "SchemaMismatchError",
    # State errors
    "StateError",
    "StateNotConnectedError",
    "CheckpointError",
    "RollbackError",
    "ResetError",
    # Journey errors
    "JourneyError",
    "JourneyTimeoutError",
    "JourneyAbortedError",
    "BranchError",
    "PathError",
    # Resilience errors
    "CircuitOpenError",
    "RetryExhaustedError",
    "RateLimitedError",
    # Plugin errors
    "PluginError",
    "ReporterError",
    # Retry/Circuit breaker
    "BackoffStrategy",
    "RetryConfig",
    "RetryPolicy",
    "CircuitState",
    "CircuitStats",
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "ResilientClient",
    "create_default_retry_policy",
    "create_default_circuit_breaker",
    # Timeout utilities
    "StepTimeoutError",
    "WaitTimeoutError",
    "JourneyTimeoutErrorEnhanced",
    "with_timeout",
    "with_timeout_async",
    "execute_with_timeout",
    "execute_with_timeout_async",
    # Recovery
    "RecoveryStrategy",
    "RecoveryResult",
    "ErrorHandlerConfig",
    "RecoveryHandler",
    "ErrorLogger",
    "GlobalErrorHandler",
    "handle_errors",
    "with_retry",
    "with_circuit_breaker",
    # Debug utilities
    "DebugContext",
    "DebugLevel",
    "DebugLogger",
    "ErrorFormatter",
    "StackTraceFilter",
    "StepThroughController",
    "TroubleshootingEngine",
    "create_debug_context",
    "format_error",
]
