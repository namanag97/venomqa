"""HTTP Client with history tracking and retry logic.

This module provides HTTP clients for testing REST APIs with comprehensive
features including request history tracking, automatic retries, authentication,
and sensitive data handling.

Classes:
    RequestRecord: Record of an HTTP request/response.
    SecureCredentials: Secure credential storage with auto-refresh.
    Client: Synchronous HTTP client.
    AsyncClient: Asynchronous HTTP client.

Example:
    >>> from venomqa.client import Client
    >>> with Client("https://api.example.com") as client:
    ...     client.set_auth_token("my-token")
    ...     response = client.get("/users")
    ...     print(response.json())
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx

from venomqa.errors import (
    ConnectionError,
    ConnectionRefusedError,
    ConnectionResetError,
    ConnectionTimeoutError,
    RequestTimeoutError,
    RetryPolicy,
)
from venomqa.errors import ErrorContext as ErrorContext
from venomqa.errors import RateLimitedError as RateLimitedError
from venomqa.errors import RequestFailedError as RequestFailedError
from venomqa.errors import RetryExhaustedError as RetryExhaustedError
from venomqa.errors.retry import BackoffStrategy, RetryConfig
from venomqa.security.sanitization import Sanitizer, SensitiveDataFilter
from venomqa.security.secrets import SecretsManager

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

for handler in logging.root.handlers:
    handler.addFilter(SensitiveDataFilter())


class ClientValidationError(Exception):
    """Raised when client input validation fails."""

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        value: Any | None = None,
    ) -> None:
        self.field_name = field_name
        self.value = value
        super().__init__(message)


def _validate_base_url(base_url: str) -> str:
    """Validate and normalize a base URL.

    Args:
        base_url: The base URL to validate.

    Returns:
        Normalized base URL without trailing slash.

    Raises:
        ClientValidationError: If URL is invalid.
    """
    if not base_url:
        raise ClientValidationError(
            "Base URL cannot be empty",
            field_name="base_url",
            value=base_url,
        )

    base_url = base_url.strip()
    if not base_url:
        raise ClientValidationError(
            "Base URL cannot be whitespace only",
            field_name="base_url",
            value=base_url,
        )

    if not base_url.startswith(("http://", "https://")):
        raise ClientValidationError(
            "Base URL must start with http:// or https://",
            field_name="base_url",
            value=base_url,
        )

    return base_url.rstrip("/")


@dataclass
class RequestRecord:
    """Record of an HTTP request/response for history tracking.

    Attributes:
        method: HTTP method (GET, POST, etc.).
        url: Full request URL.
        request_body: Request payload or None.
        response_status: HTTP status code (0 if failed).
        response_body: Response data or None.
        headers: Request headers.
        duration_ms: Request duration in milliseconds.
        timestamp: When the request was made.
        error: Error message if request failed.

    Example:
        >>> record = RequestRecord(
        ...     method="GET",
        ...     url="https://api.example.com/users/1",
        ...     request_body=None,
        ...     response_status=200,
        ...     response_body={"id": 1},
        ...     headers={"Authorization": "Bearer token"},
        ...     duration_ms=45.2,
        ... )
    """

    method: str
    url: str
    request_body: Any | None
    response_status: int
    response_body: Any | None
    headers: dict[str, str]
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    error: str | None = None

    @property
    def successful(self) -> bool:
        """Check if request was successful.

        Returns:
            True if response_status is 2xx.
        """
        return 200 <= self.response_status < 300


@dataclass
class SecureCredentials:
    """Secure credential storage with auto-refresh capability.

    Supports OAuth2-style tokens with automatic expiration checking.

    Attributes:
        access_token: The access token string.
        refresh_token: Token for obtaining new access tokens (optional).
        expires_at: Token expiration datetime (optional).
        token_type: Token type prefix (default: "Bearer").
    """

    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    token_type: str = "Bearer"
    _token_buffer_seconds: int = 60

    def __post_init__(self) -> None:
        if not self.access_token:
            raise ClientValidationError(
                "Access token cannot be empty",
                field_name="access_token",
                value=self.access_token,
            )

    def is_expired(self) -> bool:
        """Check if token has expired or will expire soon.

        Returns:
            True if expired or within buffer period.
        """
        if self.expires_at is None:
            return False
        buffer = timedelta(seconds=self._token_buffer_seconds)
        return datetime.now() >= (self.expires_at - buffer)

    def needs_refresh(self) -> bool:
        """Check if token should be refreshed.

        Returns:
            True if expired and refresh token available.
        """
        return self.refresh_token is not None and self.is_expired()

    @property
    def authorization_header(self) -> str:
        """Get the Authorization header value.

        Returns:
            Formatted authorization header.
        """
        return f"{self.token_type} {self.access_token}"


class Client:
    """HTTP client with request history tracking and retry logic.

    Provides comprehensive HTTP client functionality including:
    - Automatic retry with configurable policies
    - Request/response history tracking
    - Authentication with token refresh
    - Sensitive data sanitization
    - Context manager support

    Example:
        >>> from venomqa.client import Client
        >>> with Client("https://api.example.com", retry_count=3) as client:
        ...     client.set_auth_token("my-token")
        ...     response = client.get("/users")
        ...     print(f"Status: {response.status_code}")
        ...     history = client.get_history()
        >>> # Connection automatically closed

    Attributes:
        base_url: The base URL for all requests.
        timeout: Default request timeout in seconds.
        retry_count: Maximum retry attempts.
        retry_delay: Base delay between retries.
        default_headers: Headers for all requests.
        history: List of request records.
        retry_policy: Configured retry policy.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        retry_count: int = 3,
        retry_delay: float = 1.0,
        default_headers: dict[str, str] | None = None,
        retry_policy: RetryPolicy | None = None,
        secrets_manager: SecretsManager | None = None,
        token_refresh_callback: Callable[[], SecureCredentials] | None = None,
    ) -> None:
        """Initialize the HTTP client.

        Args:
            base_url: Base URL for all requests.
            timeout: Request timeout in seconds (default: 30.0).
            retry_count: Maximum retry attempts (default: 3).
            retry_delay: Base retry delay in seconds (default: 1.0).
            default_headers: Headers for all requests (default: None).
            retry_policy: Custom retry policy (default: None).
            secrets_manager: Secrets manager for credential loading (default: None).
            token_refresh_callback: Callback for token refresh (default: None).

        Raises:
            ClientValidationError: If parameters are invalid.
        """
        self.base_url = _validate_base_url(base_url)

        if timeout <= 0:
            raise ClientValidationError(
                "Timeout must be positive",
                field_name="timeout",
                value=timeout,
            )
        if retry_count < 0:
            raise ClientValidationError(
                "Retry count must be non-negative",
                field_name="retry_count",
                value=retry_count,
            )
        if retry_delay < 0:
            raise ClientValidationError(
                "Retry delay must be non-negative",
                field_name="retry_delay",
                value=retry_delay,
            )

        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.default_headers = default_headers or {}
        self.history: list[RequestRecord] = []
        self._auth_token: str | None = None
        self._credentials: SecureCredentials | None = None
        self._client: httpx.Client | None = None
        self._sanitizer = Sanitizer()
        self._secrets_manager = secrets_manager or SecretsManager()
        self._token_refresh_callback = token_refresh_callback
        self.retry_policy = retry_policy or RetryPolicy(
            RetryConfig(
                max_attempts=retry_count,
                base_delay=retry_delay,
                backoff_strategy=BackoffStrategy.EXPONENTIAL_FULL_JITTER,
                retryable_exceptions=(
                    ConnectionError,
                    ConnectionTimeoutError,
                    ConnectionRefusedError,
                    ConnectionResetError,
                    RequestTimeoutError,
                ),
            )
        )

    def connect(self) -> None:
        """Initialize the HTTP client.

        Creates an httpx.Client configured with the base URL and defaults.
        """
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self.default_headers,
        )
        logger.info(f"HTTP client connected to {self.base_url}")

    def disconnect(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client:
            self._client.close()
            self._client = None

    def set_auth_token(self, token: str, scheme: str = "Bearer") -> None:
        """Set authentication token for subsequent requests.

        Args:
            token: The authentication token.
            scheme: Token type prefix (default: "Bearer").

        Raises:
            ClientValidationError: If token is empty.
        """
        if not token:
            raise ClientValidationError(
                "Token cannot be empty",
                field_name="token",
                value=token,
            )
        self._auth_token = f"{scheme} {token}"

    def set_secure_credentials(
        self,
        access_token: str,
        refresh_token: str | None = None,
        expires_in_seconds: int | None = None,
        token_type: str = "Bearer",
    ) -> None:
        """Set secure credentials with optional auto-refresh.

        Args:
            access_token: The access token.
            refresh_token: Token for obtaining new access tokens (optional).
            expires_in_seconds: Token lifetime in seconds (optional).
            token_type: Token type prefix (default: "Bearer").

        Raises:
            ClientValidationError: If access_token is empty.
        """
        if not access_token:
            raise ClientValidationError(
                "Access token cannot be empty",
                field_name="access_token",
                value=access_token,
            )
        if expires_in_seconds is not None and expires_in_seconds <= 0:
            raise ClientValidationError(
                "expires_in_seconds must be positive",
                field_name="expires_in_seconds",
                value=expires_in_seconds,
            )

        expires_at = None
        if expires_in_seconds is not None:
            expires_at = datetime.now() + timedelta(seconds=expires_in_seconds)

        self._credentials = SecureCredentials(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            token_type=token_type,
        )
        self._auth_token = self._credentials.authorization_header

    def set_token_refresh_callback(self, callback: Callable[[], SecureCredentials]) -> None:
        """Set callback for automatic token refresh.

        Args:
            callback: Function that returns new SecureCredentials.

        Raises:
            ClientValidationError: If callback is None.
        """
        if callback is None:
            raise ClientValidationError(
                "Callback cannot be None",
                field_name="callback",
                value=None,
            )
        self._token_refresh_callback = callback

    def load_credentials_from_secrets(
        self,
        access_token_key: str = "ACCESS_TOKEN",
        refresh_token_key: str = "REFRESH_TOKEN",
    ) -> None:
        """Load credentials from secrets manager.

        Args:
            access_token_key: Key for access token in secrets (default: "ACCESS_TOKEN").
            refresh_token_key: Key for refresh token in secrets (default: "REFRESH_TOKEN").
        """
        access_token = self._secrets_manager.get(access_token_key, default="")
        refresh_token = self._secrets_manager.get(refresh_token_key, default=None)

        if access_token:
            self.set_secure_credentials(
                access_token=access_token,
                refresh_token=refresh_token,
            )

    def _refresh_token_if_needed(self) -> None:
        """Refresh token if expired and callback is available."""
        if self._credentials and self._credentials.needs_refresh():
            if self._token_refresh_callback:
                try:
                    new_creds = self._token_refresh_callback()
                    self._credentials = new_creds
                    self._auth_token = new_creds.authorization_header
                    logger.debug("Token refreshed successfully")
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}")
            else:
                logger.warning("Token expired but no refresh callback configured")

    def clear_auth(self) -> None:
        """Clear authentication token and credentials."""
        self._auth_token = None
        self._credentials = None

    def clear_sensitive_data(self) -> None:
        """Clear all sensitive data from memory."""
        if self._credentials:
            self._credentials.access_token = ""
            self._credentials.refresh_token = ""
        self._credentials = None
        self._auth_token = None
        self._secrets_manager.invalidate_cache()

    def get_sanitized_history(self) -> list[dict[str, Any]]:
        """Get request history with sensitive data redacted.

        Returns:
            List of request records with sanitized data.
        """
        sanitized = []
        for record in self.history:
            record_dict = {
                "method": record.method,
                "url": record.url,
                "request_body": self._sanitizer.sanitize_for_log(str(record.request_body))
                if record.request_body
                else None,
                "response_status": record.response_status,
                "response_body": self._sanitizer.sanitize_for_log(str(record.response_body))
                if record.response_body
                else None,
                "headers": self._sanitizer.sanitize_dict_values(record.headers),
                "duration_ms": record.duration_ms,
                "timestamp": record.timestamp.isoformat(),
                "error": record.error,
            }
            sanitized.append(record_dict)
        return sanitized

    def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with retry logic and history tracking.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: Request path (will be appended to base_url).
            **kwargs: Additional arguments passed to httpx.

        Returns:
            httpx.Response object.

        Raises:
            httpx.TimeoutException: If request times out after retries.
            httpx.RequestError: If request fails after retries.
        """
        if not self._client:
            self.connect()

        if not method:
            raise ClientValidationError(
                "HTTP method cannot be empty",
                field_name="method",
                value=method,
            )

        self._refresh_token_if_needed()

        headers = kwargs.pop("headers", {})
        if self._auth_token:
            headers["Authorization"] = self._auth_token

        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        request_body = kwargs.get("json") or kwargs.get("data") or kwargs.get("content")

        last_error: Exception | None = None

        for attempt in range(self.retry_count):
            try:
                start_time = time.perf_counter()
                assert self._client is not None  # Connected earlier
                response = self._client.request(method, path, headers=headers, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                record = RequestRecord(
                    method=method,
                    url=url,
                    request_body=request_body,
                    response_status=response.status_code,
                    response_body=self._safe_json(response),
                    headers=dict(headers),
                    duration_ms=duration_ms,
                )
                self.history.append(record)

                if response.is_server_error and attempt < self.retry_count - 1:
                    logger.warning(
                        f"Server error {response.status_code}, "
                        f"retrying ({attempt + 1}/{self.retry_count})"
                    )
                    time.sleep(self.retry_delay * (attempt + 1))
                    continue

                return response

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"Request timeout, retrying ({attempt + 1}/{self.retry_count})")
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay * (attempt + 1))

            except httpx.RequestError as e:
                last_error = e
                logger.error(f"Request error: {e}")
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay * (attempt + 1))

        duration_ms = 0.0
        record = RequestRecord(
            method=method,
            url=url,
            request_body=request_body,
            response_status=0,
            response_body=None,
            headers=dict(headers),
            duration_ms=duration_ms,
            error=str(last_error),
        )
        self.history.append(record)

        raise last_error or Exception("Request failed after retries")

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make a GET request.

        Args:
            path: Request path.
            **kwargs: Additional arguments.

        Returns:
            httpx.Response.
        """
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make a POST request.

        Args:
            path: Request path.
            **kwargs: Additional arguments.

        Returns:
            httpx.Response.
        """
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make a PUT request.

        Args:
            path: Request path.
            **kwargs: Additional arguments.

        Returns:
            httpx.Response.
        """
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make a PATCH request.

        Args:
            path: Request path.
            **kwargs: Additional arguments.

        Returns:
            httpx.Response.
        """
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make a DELETE request.

        Args:
            path: Request path.
            **kwargs: Additional arguments.

        Returns:
            httpx.Response.
        """
        return self.request("DELETE", path, **kwargs)

    def post_form(
        self,
        path: str,
        data: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a POST request with form-urlencoded data.

        Convenience method for OAuth2 login endpoints and other form-based APIs.

        Args:
            path: Request path.
            data: Form data as dictionary (will be URL-encoded).
            **kwargs: Additional arguments.

        Returns:
            httpx.Response.

        Example:
            >>> # OAuth2 password flow login
            >>> response = client.post_form(
            ...     "/api/login/access-token",
            ...     data={"username": "user@example.com", "password": "secret"}
            ... )
        """
        headers = kwargs.pop("headers", {})
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        return self.request("POST", path, data=data, headers=headers, **kwargs)

    def oauth2_login(
        self,
        path: str,
        username: str,
        password: str,
        scope: str = "",
        set_token: bool = True,
    ) -> httpx.Response:
        """Perform OAuth2 password flow login.

        Args:
            path: Login endpoint path.
            username: User's email or username.
            password: User's password.
            scope: OAuth2 scope string (optional).
            set_token: If True, automatically set the access token on success.

        Returns:
            httpx.Response.

        Example:
            >>> response = client.oauth2_login(
            ...     "/api/v1/login/access-token",
            ...     username="user@example.com",
            ...     password="secret123"
            ... )
            >>> # Token automatically set, subsequent requests authenticated
        """
        data = {
            "username": username,
            "password": password,
            "grant_type": "password",
        }
        if scope:
            data["scope"] = scope

        response = self.post_form(path, data=data)

        if set_token and response.status_code == 200:
            try:
                body = response.json()
                access_token = body.get("access_token")
                if access_token:
                    self.set_auth_token(access_token)
            except Exception:
                pass

        return response

    def upload_file(
        self,
        path: str,
        files: dict[str, tuple[str, bytes, str] | tuple[str, bytes]],
        **kwargs: Any,
    ) -> httpx.Response:
        """Upload files using multipart/form-data.

        Args:
            path: Upload endpoint path.
            files: Dictionary mapping field names to (filename, content, content_type) tuples.
            **kwargs: Additional arguments.

        Returns:
            httpx.Response.

        Example:
            >>> response = client.upload_file(
            ...     "/api/upload",
            ...     files={"file": ("document.pdf", pdf_bytes, "application/pdf")}
            ... )
        """
        return self.request("POST", path, files=files, **kwargs)

    def _safe_json(self, response: httpx.Response) -> Any:
        """Safely extract JSON from response.

        Args:
            response: The httpx response.

        Returns:
            Parsed JSON or text if parsing fails.
        """
        try:
            return response.json()
        except Exception:
            return response.text

    def get_history(self) -> list[RequestRecord]:
        """Get all request history.

        Returns:
            Copy of history list.
        """
        return self.history.copy()

    def clear_history(self) -> None:
        """Clear request history."""
        self.history.clear()

    def last_request(self) -> RequestRecord | None:
        """Get the most recent request record.

        Returns:
            Last RequestRecord or None if history is empty.
        """
        return self.history[-1] if self.history else None

    def __enter__(self) -> Client:
        """Enter context manager, connecting to server."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager, disconnecting from server."""
        self.disconnect()


class AsyncClient:
    """Async HTTP client with history tracking and retry logic.

    Provides the same functionality as Client but with async/await
    support for non-blocking operations.

    Example:
        >>> from venomqa.client import AsyncClient
        >>> async def main():
        ...     async with AsyncClient("https://api.example.com") as client:
        ...         client.set_auth_token("my-token")
        ...         response = await client.get("/users")
        ...         print(response.json())

    Attributes:
        base_url: The base URL for all requests.
        timeout: Default request timeout in seconds.
        retry_count: Maximum retry attempts.
        retry_delay: Base delay between retries.
        default_headers: Headers for all requests.
        history: List of request records.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        retry_count: int = 3,
        retry_delay: float = 1.0,
        default_headers: dict[str, str] | None = None,
        secrets_manager: SecretsManager | None = None,
        token_refresh_callback: (
            Callable[[], SecureCredentials]
            | Callable[[], Coroutine[Any, Any, SecureCredentials]]
            | None
        ) = None,
    ) -> None:
        """Initialize the async HTTP client.

        Args:
            base_url: Base URL for all requests.
            timeout: Request timeout in seconds (default: 30.0).
            retry_count: Maximum retry attempts (default: 3).
            retry_delay: Base retry delay in seconds (default: 1.0).
            default_headers: Headers for all requests (default: None).
            secrets_manager: Secrets manager for credential loading (default: None).
            token_refresh_callback: Callback for token refresh (default: None).

        Raises:
            ClientValidationError: If parameters are invalid.
        """
        self.base_url = _validate_base_url(base_url)

        if timeout <= 0:
            raise ClientValidationError(
                "Timeout must be positive",
                field_name="timeout",
                value=timeout,
            )
        if retry_count < 0:
            raise ClientValidationError(
                "Retry count must be non-negative",
                field_name="retry_count",
                value=retry_count,
            )
        if retry_delay < 0:
            raise ClientValidationError(
                "Retry delay must be non-negative",
                field_name="retry_delay",
                value=retry_delay,
            )

        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.default_headers = default_headers or {}
        self.history: list[RequestRecord] = []
        self._auth_token: str | None = None
        self._credentials: SecureCredentials | None = None
        self._client: httpx.AsyncClient | None = None
        self._sanitizer = Sanitizer()
        self._secrets_manager = secrets_manager or SecretsManager()
        self._token_refresh_callback = token_refresh_callback

    async def connect(self) -> None:
        """Initialize the async HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self.default_headers,
        )
        logger.info(f"Async HTTP client connected to {self.base_url}")

    async def disconnect(self) -> None:
        """Close the async HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def set_auth_token(self, token: str, scheme: str = "Bearer") -> None:
        """Set authentication token for subsequent requests.

        Args:
            token: The authentication token.
            scheme: Token type prefix (default: "Bearer").

        Raises:
            ClientValidationError: If token is empty.
        """
        if not token:
            raise ClientValidationError(
                "Token cannot be empty",
                field_name="token",
                value=token,
            )
        self._auth_token = f"{scheme} {token}"

    def set_secure_credentials(
        self,
        access_token: str,
        refresh_token: str | None = None,
        expires_in_seconds: int | None = None,
        token_type: str = "Bearer",
    ) -> None:
        """Set secure credentials with optional auto-refresh.

        Args:
            access_token: The access token.
            refresh_token: Token for obtaining new access tokens (optional).
            expires_in_seconds: Token lifetime in seconds (optional).
            token_type: Token type prefix (default: "Bearer").
        """
        if not access_token:
            raise ClientValidationError(
                "Access token cannot be empty",
                field_name="access_token",
                value=access_token,
            )
        if expires_in_seconds is not None and expires_in_seconds <= 0:
            raise ClientValidationError(
                "expires_in_seconds must be positive",
                field_name="expires_in_seconds",
                value=expires_in_seconds,
            )

        expires_at = None
        if expires_in_seconds is not None:
            expires_at = datetime.now() + timedelta(seconds=expires_in_seconds)

        self._credentials = SecureCredentials(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            token_type=token_type,
        )
        self._auth_token = self._credentials.authorization_header

    def set_token_refresh_callback(
        self,
        callback: (
            Callable[[], SecureCredentials] | Callable[[], Coroutine[Any, Any, SecureCredentials]]
        ),
    ) -> None:
        """Set callback for automatic token refresh.

        Supports both sync and async callbacks.

        Args:
            callback: Function that returns new SecureCredentials.
        """
        if callback is None:
            raise ClientValidationError(
                "Callback cannot be None",
                field_name="callback",
                value=None,
            )
        self._token_refresh_callback = callback

    def load_credentials_from_secrets(
        self,
        access_token_key: str = "ACCESS_TOKEN",
        refresh_token_key: str = "REFRESH_TOKEN",
    ) -> None:
        """Load credentials from secrets manager."""
        access_token = self._secrets_manager.get(access_token_key, default="")
        refresh_token = self._secrets_manager.get(refresh_token_key, default=None)

        if access_token:
            self.set_secure_credentials(
                access_token=access_token,
                refresh_token=refresh_token,
            )

    async def _refresh_token_if_needed(self) -> None:
        """Refresh token if expired and callback is available."""
        if self._credentials and self._credentials.needs_refresh():
            if self._token_refresh_callback:
                try:
                    result = self._token_refresh_callback()
                    if asyncio.iscoroutine(result):
                        new_creds = await result
                    else:
                        new_creds = result
                    self._credentials = new_creds
                    self._auth_token = new_creds.authorization_header
                    logger.debug("Token refreshed successfully")
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}")
            else:
                logger.warning("Token expired but no refresh callback configured")

    def clear_auth(self) -> None:
        """Clear authentication token and credentials."""
        self._auth_token = None
        self._credentials = None

    def clear_sensitive_data(self) -> None:
        """Clear all sensitive data from memory."""
        if self._credentials:
            self._credentials.access_token = ""
            self._credentials.refresh_token = ""
        self._credentials = None
        self._auth_token = None
        self._secrets_manager.invalidate_cache()

    def get_sanitized_history(self) -> list[dict[str, Any]]:
        """Get request history with sensitive data redacted."""
        sanitized = []
        for record in self.history:
            record_dict = {
                "method": record.method,
                "url": record.url,
                "request_body": self._sanitizer.sanitize_for_log(str(record.request_body))
                if record.request_body
                else None,
                "response_status": record.response_status,
                "response_body": self._sanitizer.sanitize_for_log(str(record.response_body))
                if record.response_body
                else None,
                "headers": self._sanitizer.sanitize_dict_values(record.headers),
                "duration_ms": record.duration_ms,
                "timestamp": record.timestamp.isoformat(),
                "error": record.error,
            }
            sanitized.append(record_dict)
        return sanitized

    async def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an async HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: Request path (will be appended to base_url).
            **kwargs: Additional arguments passed to httpx.

        Returns:
            httpx.Response object.

        Raises:
            httpx.TimeoutException: If request times out after retries.
            httpx.RequestError: If request fails after retries.
        """
        if not self._client:
            await self.connect()

        if not method:
            raise ClientValidationError(
                "HTTP method cannot be empty",
                field_name="method",
                value=method,
            )

        await self._refresh_token_if_needed()

        headers = kwargs.pop("headers", {})
        if self._auth_token:
            headers["Authorization"] = self._auth_token

        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        request_body = kwargs.get("json") or kwargs.get("data") or kwargs.get("content")

        last_error: Exception | None = None

        for attempt in range(self.retry_count):
            try:
                start_time = time.perf_counter()
                response = await self._client.request(method, path, headers=headers, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                record = RequestRecord(
                    method=method,
                    url=url,
                    request_body=request_body,
                    response_status=response.status_code,
                    response_body=self._safe_json(response),
                    headers=dict(headers),
                    duration_ms=duration_ms,
                )
                self.history.append(record)

                if response.is_server_error and attempt < self.retry_count - 1:
                    logger.warning(
                        f"Server error {response.status_code}, "
                        f"retrying ({attempt + 1}/{self.retry_count})"
                    )
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue

                return response

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"Request timeout, retrying ({attempt + 1}/{self.retry_count})")
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))

            except httpx.RequestError as e:
                last_error = e
                logger.error(f"Request error: {e}")
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))

        record = RequestRecord(
            method=method,
            url=url,
            request_body=request_body,
            response_status=0,
            response_body=None,
            headers=dict(headers),
            duration_ms=0.0,
            error=str(last_error),
        )
        self.history.append(record)

        raise last_error or Exception("Request failed after retries")

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make an async GET request."""
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make an async POST request."""
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make an async PUT request."""
        return await self.request("PUT", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make an async PATCH request."""
        return await self.request("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        """Make an async DELETE request."""
        return await self.request("DELETE", path, **kwargs)

    def _safe_json(self, response: httpx.Response) -> Any:
        """Safely extract JSON from response."""
        try:
            return response.json()
        except Exception:
            return response.text

    def get_history(self) -> list[RequestRecord]:
        """Get all request history."""
        return self.history.copy()

    def clear_history(self) -> None:
        """Clear request history."""
        self.history.clear()

    def last_request(self) -> RequestRecord | None:
        """Get the most recent request record."""
        return self.history[-1] if self.history else None

    async def __aenter__(self) -> AsyncClient:
        """Enter async context manager, connecting to server."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager, disconnecting from server."""
        await self.disconnect()
