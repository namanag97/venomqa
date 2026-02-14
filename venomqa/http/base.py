"""Abstract base client classes for VenomQA protocol clients.

This module provides the foundation for all protocol-specific clients,
including HTTP, WebSocket, gRPC, and GraphQL clients.

Classes:
    ClientRecord: Data class for recording request/response history.
    AuthCredentials: Authentication credentials with refresh capability.
    BaseClient: Abstract base for synchronous clients.
    BaseAsyncClient: Abstract base for asynchronous clients.

Example:
    >>> from venomqa.clients.base import BaseClient, AuthCredentials
    >>> class MyClient(BaseClient[dict]):
    ...     def connect(self) -> None:
    ...         self._connected = True
    ...     def disconnect(self) -> None:
    ...         self._connected = False
    ...     def is_connected(self) -> bool:
    ...         return self._connected
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ClientError(Exception):
    """Base exception for client-related errors."""

    def __init__(self, message: str, client_name: str | None = None) -> None:
        self.client_name = client_name
        super().__init__(message)


class ValidationError(ClientError):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        value: Any | None = None,
    ) -> None:
        self.field_name = field_name
        self.value = value
        super().__init__(message)


@dataclass
class ClientRecord:
    """Record of a client request/response for history tracking.

    Attributes:
        operation: The operation name (e.g., 'GET /users', 'send', 'execute').
        request_data: The request payload or parameters.
        response_data: The response data received.
        duration_ms: Request duration in milliseconds.
        timestamp: When the request was made.
        error: Error message if the request failed.
        metadata: Additional context-specific metadata.

    Example:
        >>> record = ClientRecord(
        ...     operation="GET /users/1",
        ...     request_data=None,
        ...     response_data={"id": 1, "name": "Alice"},
        ...     duration_ms=45.2,
        ... )
    """

    operation: str
    request_data: Any | None
    response_data: Any | None
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.duration_ms < 0:
            raise ValidationError(
                "duration_ms must be non-negative",
                field_name="duration_ms",
                value=self.duration_ms,
            )


@dataclass
class AuthCredentials:
    """Authentication credentials with optional refresh capability.

    Supports OAuth2-style tokens with automatic expiration checking and
    refresh token management.

    Attributes:
        token: The access token string.
        token_type: Token type (default: "Bearer").
        expires_at: Token expiration datetime, if applicable.
        refresh_token: Refresh token for obtaining new access tokens.

    Example:
        >>> from datetime import datetime, timedelta
        >>> creds = AuthCredentials(
        ...     token="access_token_123",
        ...     expires_at=datetime.now() + timedelta(hours=1),
        ...     refresh_token="refresh_token_456",
        ... )
        >>> creds.is_expired()
        False
        >>> creds.authorization_header
        'Bearer access_token_123'
    """

    token: str
    token_type: str = "Bearer"
    expires_at: datetime | None = None
    refresh_token: str | None = None
    _buffer_seconds: int = 60

    def __post_init__(self) -> None:
        if not self.token:
            raise ValidationError(
                "Token cannot be empty",
                field_name="token",
                value=self.token,
            )
        if not self.token_type:
            raise ValidationError(
                "Token type cannot be empty",
                field_name="token_type",
                value=self.token_type,
            )

    def is_expired(self) -> bool:
        """Check if the token has expired or will expire soon.

        Uses a buffer period (default 60 seconds) to proactively
        refresh tokens before actual expiration.

        Returns:
            True if token is expired or will expire within buffer period.
        """
        if self.expires_at is None:
            return False
        buffer = timedelta(seconds=self._buffer_seconds)
        return datetime.now() >= (self.expires_at - buffer)

    def needs_refresh(self) -> bool:
        """Check if token should be refreshed.

        Returns:
            True if token is expired and a refresh token is available.
        """
        return self.refresh_token is not None and self.is_expired()

    @property
    def authorization_header(self) -> str:
        """Get the Authorization header value.

        Returns:
            Formatted authorization header (e.g., "Bearer token123").
        """
        return f"{self.token_type} {self.token}"


def _validate_endpoint(endpoint: str, protocols: list[str] | None = None) -> str:
    """Validate and normalize an endpoint URL.

    Args:
        endpoint: The endpoint URL to validate.
        protocols: List of allowed protocols (e.g., ['http', 'https']).

    Returns:
        Normalized endpoint URL without trailing slash.

    Raises:
        ValidationError: If endpoint is invalid or uses disallowed protocol.
    """
    if not endpoint:
        raise ValidationError(
            "Endpoint URL cannot be empty",
            field_name="endpoint",
            value=endpoint,
        )

    endpoint = endpoint.strip()
    if not endpoint:
        raise ValidationError(
            "Endpoint URL cannot be whitespace only",
            field_name="endpoint",
            value=endpoint,
        )

    if protocols:
        protocol_match = False
        for protocol in protocols:
            if endpoint.startswith(f"{protocol}://"):
                protocol_match = True
                break
        if not protocol_match:
            raise ValidationError(
                f"Endpoint must use one of: {', '.join(protocols)}",
                field_name="endpoint",
                value=endpoint,
            )

    return endpoint.rstrip("/")


def _validate_positive_number(
    value: float,
    field_name: str,
    allow_zero: bool = False,
) -> None:
    """Validate that a number is positive.

    Args:
        value: The value to validate.
        field_name: Name of the field for error messages.
        allow_zero: Whether zero is allowed.

    Raises:
        ValidationError: If value is not positive.
    """
    if allow_zero:
        if value < 0:
            raise ValidationError(
                f"{field_name} must be non-negative",
                field_name=field_name,
                value=value,
            )
    else:
        if value <= 0:
            raise ValidationError(
                f"{field_name} must be positive",
                field_name=field_name,
                value=value,
            )


def _validate_retry_config(retry_count: int, retry_delay: float) -> None:
    """Validate retry configuration parameters.

    Args:
        retry_count: Number of retry attempts.
        retry_delay: Delay between retries in seconds.

    Raises:
        ValidationError: If parameters are invalid.
    """
    if retry_count < 0:
        raise ValidationError(
            "retry_count must be non-negative",
            field_name="retry_count",
            value=retry_count,
        )
    if retry_delay < 0:
        raise ValidationError(
            "retry_delay must be non-negative",
            field_name="retry_delay",
            value=retry_delay,
        )


class BaseClient(ABC, Generic[T]):
    """Abstract base class for all synchronous protocol clients.

    Provides common functionality including:
    - Connection management with context manager support
    - Authentication with automatic token refresh
    - Request history tracking
    - Retry logic with exponential backoff

    Type Parameters:
        T: The response type for this client.

    Attributes:
        endpoint: The service endpoint URL.
        timeout: Default request timeout in seconds.
        default_headers: Headers to include in all requests.
        retry_count: Maximum number of retry attempts.
        retry_delay: Base delay between retries in seconds.
        history: List of recorded requests.

    Example:
        >>> class MyClient(BaseClient[dict]):
        ...     def connect(self) -> None:
        ...         self._connected = True
        ...     def disconnect(self) -> None:
        ...         self._connected = False
        ...     def is_connected(self) -> bool:
        ...         return self._connected
        >>> with MyClient("http://api.example.com") as client:
        ...     client.set_auth_token("my-token")
    """

    def __init__(
        self,
        endpoint: str,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """Initialize the base client.

        Args:
            endpoint: Service endpoint URL.
            timeout: Request timeout in seconds (default: 30.0).
            default_headers: Headers for all requests (default: None).
            retry_count: Maximum retry attempts (default: 3).
            retry_delay: Base retry delay in seconds (default: 1.0).

        Raises:
            ValidationError: If parameters are invalid.
        """
        self.endpoint = _validate_endpoint(endpoint)
        _validate_positive_number(timeout, "timeout")
        _validate_retry_config(retry_count, retry_delay)

        self.timeout = timeout
        self.default_headers = default_headers or {}
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.history: list[ClientRecord] = []
        self._credentials: AuthCredentials | None = None
        self._token_refresh_callback: Callable[[], AuthCredentials] | None = None
        self._connected = False

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the service.

        Implementations should set self._connected = True on success
        and raise appropriate exceptions on failure.
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the service.

        Implementations should set self._connected = False and
        clean up any resources.
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if client is currently connected.

        Returns:
            True if connected and ready for requests.
        """
        pass

    def set_auth_token(self, token: str, token_type: str = "Bearer") -> None:
        """Set authentication token for subsequent requests.

        Args:
            token: The authentication token.
            token_type: Token type prefix (default: "Bearer").

        Raises:
            ValidationError: If token is empty.
        """
        if not token:
            raise ValidationError(
                "Token cannot be empty",
                field_name="token",
                value=token,
            )
        self._credentials = AuthCredentials(token=token, token_type=token_type)

    def set_credentials(
        self,
        token: str,
        token_type: str = "Bearer",
        expires_in_seconds: int | None = None,
        refresh_token: str | None = None,
    ) -> None:
        """Set credentials with optional expiration and refresh.

        Args:
            token: The access token.
            token_type: Token type prefix (default: "Bearer").
            expires_in_seconds: Token lifetime in seconds (optional).
            refresh_token: Token for refreshing credentials (optional).

        Raises:
            ValidationError: If token is empty or expires_in_seconds is invalid.
        """
        if not token:
            raise ValidationError(
                "Token cannot be empty",
                field_name="token",
                value=token,
            )
        if expires_in_seconds is not None and expires_in_seconds <= 0:
            raise ValidationError(
                "expires_in_seconds must be positive",
                field_name="expires_in_seconds",
                value=expires_in_seconds,
            )

        expires_at = None
        if expires_in_seconds is not None:
            expires_at = datetime.now() + timedelta(seconds=expires_in_seconds)
        self._credentials = AuthCredentials(
            token=token,
            token_type=token_type,
            expires_at=expires_at,
            refresh_token=refresh_token,
        )

    def set_token_refresh_callback(self, callback: Callable[[], AuthCredentials]) -> None:
        """Set callback for automatic token refresh.

        The callback will be invoked when the token expires or
        is about to expire.

        Args:
            callback: Function that returns new AuthCredentials.
        """
        if callback is None:
            raise ValidationError(
                "Callback cannot be None",
                field_name="callback",
                value=None,
            )
        self._token_refresh_callback = callback

    def _refresh_token_if_needed(self) -> None:
        """Refresh token if expired and callback is available.

        This method is called automatically before each request.
        """
        if self._credentials and self._credentials.needs_refresh():
            if self._token_refresh_callback:
                try:
                    new_creds = self._token_refresh_callback()
                    self._credentials = new_creds
                    logger.debug("Token refreshed successfully")
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}")
            else:
                logger.warning("Token expired but no refresh callback configured")

    def clear_auth(self) -> None:
        """Clear authentication credentials.

        After calling this method, requests will not include
        authentication headers until new credentials are set.
        """
        self._credentials = None

    def get_auth_header(self) -> dict[str, str]:
        """Get authorization header if credentials are set.

        Automatically refreshes token if needed.

        Returns:
            Dict with Authorization header, or empty dict if no credentials.
        """
        self._refresh_token_if_needed()
        if self._credentials:
            return {"Authorization": self._credentials.authorization_header}
        return {}

    def _record_request(
        self,
        operation: str,
        request_data: Any | None,
        response_data: Any | None,
        duration_ms: float,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ClientRecord:
        """Record a request/response to history.

        Args:
            operation: The operation name.
            request_data: Request payload.
            response_data: Response data.
            duration_ms: Duration in milliseconds.
            error: Error message if failed (optional).
            metadata: Additional metadata (optional).

        Returns:
            The created ClientRecord.
        """
        if not operation:
            operation = "<unknown>"

        record = ClientRecord(
            operation=operation,
            request_data=request_data,
            response_data=response_data,
            duration_ms=max(0.0, duration_ms),
            error=error,
            metadata=metadata or {},
        )
        self.history.append(record)
        return record

    def get_history(self) -> list[ClientRecord]:
        """Get all request history.

        Returns:
            Copy of the history list.
        """
        return self.history.copy()

    def clear_history(self) -> None:
        """Clear request history."""
        self.history.clear()

    def last_request(self) -> ClientRecord | None:
        """Get the most recent request record.

        Returns:
            The last ClientRecord, or None if history is empty.
        """
        return self.history[-1] if self.history else None

    def _ensure_connected(self) -> None:
        """Ensure client is connected before operations.

        Automatically connects if not already connected.
        """
        if not self._connected:
            self.connect()

    def _retry_with_backoff(
        self, operation: Callable[[], T], is_retryable: Callable[[Exception], bool]
    ) -> T:
        """Execute operation with retry and exponential backoff.

        Args:
            operation: The operation to execute.
            is_retryable: Function to determine if error is retryable.

        Returns:
            The operation result.

        Raises:
            Exception: The last exception after all retries exhausted.
        """
        last_error: Exception | None = None
        for attempt in range(self.retry_count):
            try:
                return operation()
            except Exception as e:
                last_error = e
                if not is_retryable(e) or attempt == self.retry_count - 1:
                    raise
                delay = self.retry_delay * (2**attempt)
                logger.warning(
                    f"Operation failed, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{self.retry_count}): {e}"
                )
                time.sleep(delay)
        raise last_error or Exception("Operation failed after retries")

    def __enter__(self) -> BaseClient[T]:
        """Enter context manager, establishing connection."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager, closing connection."""
        self.disconnect()


class BaseAsyncClient(ABC, Generic[T]):
    """Abstract base class for all asynchronous protocol clients.

    Provides the same functionality as BaseClient but with async/await
    support for non-blocking operations.

    Type Parameters:
        T: The response type for this client.

    Attributes:
        endpoint: The service endpoint URL.
        timeout: Default request timeout in seconds.
        default_headers: Headers to include in all requests.
        retry_count: Maximum number of retry attempts.
        retry_delay: Base delay between retries in seconds.
        history: List of recorded requests.

    Example:
        >>> class MyAsyncClient(BaseAsyncClient[dict]):
        ...     async def connect(self) -> None:
        ...         self._connected = True
        ...     async def disconnect(self) -> None:
        ...         self._connected = False
        ...     async def is_connected(self) -> bool:
        ...         return self._connected
        >>> async def main():
        ...     async with MyAsyncClient("http://api.example.com") as client:
        ...         await client.set_auth_token("my-token")
    """

    def __init__(
        self,
        endpoint: str,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """Initialize the async base client.

        Args:
            endpoint: Service endpoint URL.
            timeout: Request timeout in seconds (default: 30.0).
            default_headers: Headers for all requests (default: None).
            retry_count: Maximum retry attempts (default: 3).
            retry_delay: Base retry delay in seconds (default: 1.0).

        Raises:
            ValidationError: If parameters are invalid.
        """
        self.endpoint = _validate_endpoint(endpoint)
        _validate_positive_number(timeout, "timeout")
        _validate_retry_config(retry_count, retry_delay)

        self.timeout = timeout
        self.default_headers = default_headers or {}
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.history: list[ClientRecord] = []
        self._credentials: AuthCredentials | None = None
        self._token_refresh_callback: (
            Callable[[], AuthCredentials]
            | Callable[[], Coroutine[Any, Any, AuthCredentials]]
            | None
        ) = None
        self._connected = False

    @abstractmethod
    async def connect(self) -> None:
        """Asynchronously establish connection to the service.

        Implementations should set self._connected = True on success
        and raise appropriate exceptions on failure.
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Asynchronously close connection to the service.

        Implementations should set self._connected = False and
        clean up any resources.
        """
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Asynchronously check if client is connected.

        Returns:
            True if connected and ready for requests.
        """
        pass

    def set_auth_token(self, token: str, token_type: str = "Bearer") -> None:
        """Set authentication token for subsequent requests.

        Args:
            token: The authentication token.
            token_type: Token type prefix (default: "Bearer").

        Raises:
            ValidationError: If token is empty.
        """
        if not token:
            raise ValidationError(
                "Token cannot be empty",
                field_name="token",
                value=token,
            )
        self._credentials = AuthCredentials(token=token, token_type=token_type)

    def set_credentials(
        self,
        token: str,
        token_type: str = "Bearer",
        expires_in_seconds: int | None = None,
        refresh_token: str | None = None,
    ) -> None:
        """Set credentials with optional expiration and refresh.

        Args:
            token: The access token.
            token_type: Token type prefix (default: "Bearer").
            expires_in_seconds: Token lifetime in seconds (optional).
            refresh_token: Token for refreshing credentials (optional).

        Raises:
            ValidationError: If token is empty or expires_in_seconds is invalid.
        """
        if not token:
            raise ValidationError(
                "Token cannot be empty",
                field_name="token",
                value=token,
            )
        if expires_in_seconds is not None and expires_in_seconds <= 0:
            raise ValidationError(
                "expires_in_seconds must be positive",
                field_name="expires_in_seconds",
                value=expires_in_seconds,
            )

        expires_at = None
        if expires_in_seconds is not None:
            expires_at = datetime.now() + timedelta(seconds=expires_in_seconds)
        self._credentials = AuthCredentials(
            token=token,
            token_type=token_type,
            expires_at=expires_at,
            refresh_token=refresh_token,
        )

    def set_token_refresh_callback(
        self,
        callback: (
            Callable[[], AuthCredentials] | Callable[[], Coroutine[Any, Any, AuthCredentials]]
        ),
    ) -> None:
        """Set callback for automatic token refresh.

        Supports both synchronous and asynchronous callbacks.

        Args:
            callback: Function that returns new AuthCredentials.
        """
        if callback is None:
            raise ValidationError(
                "Callback cannot be None",
                field_name="callback",
                value=None,
            )
        self._token_refresh_callback = callback

    async def _refresh_token_if_needed(self) -> None:
        """Refresh token if expired and callback is available.

        Supports both sync and async refresh callbacks.
        """
        if self._credentials and self._credentials.needs_refresh():
            if self._token_refresh_callback:
                try:
                    import asyncio

                    result = self._token_refresh_callback()
                    if asyncio.iscoroutine(result):
                        new_creds = await result
                    else:
                        new_creds = result
                    self._credentials = new_creds
                    logger.debug("Token refreshed successfully")
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}")
            else:
                logger.warning("Token expired but no refresh callback configured")

    def clear_auth(self) -> None:
        """Clear authentication credentials."""
        self._credentials = None

    async def get_auth_header(self) -> dict[str, str]:
        """Get authorization header if credentials are set.

        Automatically refreshes token if needed (async-safe).

        Returns:
            Dict with Authorization header, or empty dict if no credentials.
        """
        await self._refresh_token_if_needed()
        if self._credentials:
            return {"Authorization": self._credentials.authorization_header}
        return {}

    def _record_request(
        self,
        operation: str,
        request_data: Any | None,
        response_data: Any | None,
        duration_ms: float,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ClientRecord:
        """Record a request/response to history.

        Args:
            operation: The operation name.
            request_data: Request payload.
            response_data: Response data.
            duration_ms: Duration in milliseconds.
            error: Error message if failed (optional).
            metadata: Additional metadata (optional).

        Returns:
            The created ClientRecord.
        """
        if not operation:
            operation = "<unknown>"

        record = ClientRecord(
            operation=operation,
            request_data=request_data,
            response_data=response_data,
            duration_ms=max(0.0, duration_ms),
            error=error,
            metadata=metadata or {},
        )
        self.history.append(record)
        return record

    def get_history(self) -> list[ClientRecord]:
        """Get all request history.

        Returns:
            Copy of the history list.
        """
        return self.history.copy()

    def clear_history(self) -> None:
        """Clear request history."""
        self.history.clear()

    def last_request(self) -> ClientRecord | None:
        """Get the most recent request record.

        Returns:
            The last ClientRecord, or None if history is empty.
        """
        return self.history[-1] if self.history else None

    async def _ensure_connected(self) -> None:
        """Ensure client is connected before operations.

        Automatically connects if not already connected.
        """
        if not self._connected:
            await self.connect()

    async def _retry_with_backoff(
        self,
        operation: Callable[[], Coroutine[Any, Any, T]],
        is_retryable: Callable[[Exception], bool],
    ) -> T:
        """Execute async operation with retry and exponential backoff.

        Args:
            operation: The async operation to execute.
            is_retryable: Function to determine if error is retryable.

        Returns:
            The operation result.

        Raises:
            Exception: The last exception after all retries exhausted.
        """
        import asyncio

        last_error: Exception | None = None
        for attempt in range(self.retry_count):
            try:
                return await operation()
            except Exception as e:
                last_error = e
                if not is_retryable(e) or attempt == self.retry_count - 1:
                    raise
                delay = self.retry_delay * (2**attempt)
                logger.warning(
                    f"Async operation failed, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{self.retry_count}): {e}"
                )
                await asyncio.sleep(delay)
        raise last_error or Exception("Operation failed after retries")

    async def __aenter__(self) -> BaseAsyncClient[T]:
        """Enter async context manager, establishing connection."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager, closing connection."""
        await self.disconnect()
