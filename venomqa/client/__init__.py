"""HTTP Client with history tracking and retry logic."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
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
from venomqa.errors import (
    ErrorContext as ErrorContext,
)
from venomqa.errors import (
    RateLimitedError as RateLimitedError,
)
from venomqa.errors import (
    RequestFailedError as RequestFailedError,
)
from venomqa.errors import (
    RetryExhaustedError as RetryExhaustedError,
)
from venomqa.errors.retry import BackoffStrategy, RetryConfig
from venomqa.security.sanitization import Sanitizer, SensitiveDataFilter
from venomqa.security.secrets import SecretsManager

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

for handler in logging.root.handlers:
    handler.addFilter(SensitiveDataFilter())


@dataclass
class RequestRecord:
    """Record of an HTTP request/response."""

    method: str
    url: str
    request_body: Any | None
    response_status: int
    response_body: Any | None
    headers: dict[str, str]
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    error: str | None = None


@dataclass
class SecureCredentials:
    """Secure credential storage with auto-refresh capability."""

    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None
    token_type: str = "Bearer"
    _token_buffer_seconds: int = 60

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        buffer = timedelta(seconds=self._token_buffer_seconds)
        return datetime.now() >= (self.expires_at - buffer)

    def needs_refresh(self) -> bool:
        return self.refresh_token is not None and self.is_expired()

    @property
    def authorization_header(self) -> str:
        return f"{self.token_type} {self.access_token}"


class Client:
    """HTTP client that captures request history and handles retries."""

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
        self.base_url = base_url.rstrip("/")
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
        """Initialize the HTTP client."""
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=self.default_headers,
        )
        logger.info(f"HTTP client connected to {self.base_url}")

    def disconnect(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def set_auth_token(self, token: str, scheme: str = "Bearer") -> None:
        """Set authentication token for subsequent requests."""
        self._auth_token = f"{scheme} {token}"

    def set_secure_credentials(
        self,
        access_token: str,
        refresh_token: str | None = None,
        expires_in_seconds: int | None = None,
        token_type: str = "Bearer",
    ) -> None:
        """Set secure credentials with optional auto-refresh capability."""
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
        """Set callback for automatic token refresh."""
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

    def _refresh_token_if_needed(self) -> None:
        """Refresh token if expired and refresh callback is available."""
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

    def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with retry logic and history tracking."""
        if not self._client:
            self.connect()

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
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", path, **kwargs)

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


class AsyncClient:
    """Async HTTP client with history tracking and secure credential handling."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        retry_count: int = 3,
        retry_delay: float = 1.0,
        default_headers: dict[str, str] | None = None,
        secrets_manager: SecretsManager | None = None,
        token_refresh_callback: Callable[[], SecureCredentials] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
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
        """Set authentication token for subsequent requests."""
        self._auth_token = f"{scheme} {token}"

    def set_secure_credentials(
        self,
        access_token: str,
        refresh_token: str | None = None,
        expires_in_seconds: int | None = None,
        token_type: str = "Bearer",
    ) -> None:
        """Set secure credentials with optional auto-refresh capability."""
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
        """Set callback for automatic token refresh."""
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

    def _refresh_token_if_needed(self) -> None:
        """Refresh token if expired and refresh callback is available."""
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
        """Make an async HTTP request with retry logic."""
        if not self._client:
            await self.connect()

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
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PATCH", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", path, **kwargs)

    def _safe_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except Exception:
            return response.text

    def get_history(self) -> list[RequestRecord]:
        return self.history.copy()

    def clear_history(self) -> None:
        self.history.clear()

    def last_request(self) -> RequestRecord | None:
        return self.history[-1] if self.history else None
