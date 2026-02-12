"""Abstract base client class for VenomQA protocol clients."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class ClientRecord:
    """Record of a client request/response."""

    operation: str
    request_data: Any | None
    response_data: Any | None
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.now)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthCredentials:
    """Authentication credentials with optional refresh capability."""

    token: str
    token_type: str = "Bearer"
    expires_at: datetime | None = None
    refresh_token: str | None = None
    _buffer_seconds: int = 60

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        buffer = timedelta(seconds=self._buffer_seconds)
        return datetime.now() >= (self.expires_at - buffer)

    def needs_refresh(self) -> bool:
        return self.refresh_token is not None and self.is_expired()

    @property
    def authorization_header(self) -> str:
        return f"{self.token_type} {self.token}"


class BaseClient(ABC, Generic[T]):
    """Abstract base class for all protocol clients."""

    def __init__(
        self,
        endpoint: str,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
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
        """Establish connection to the service."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the service."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if client is connected."""
        pass

    def set_auth_token(self, token: str, token_type: str = "Bearer") -> None:
        """Set authentication token for subsequent requests."""
        self._credentials = AuthCredentials(token=token, token_type=token_type)

    def set_credentials(
        self,
        token: str,
        token_type: str = "Bearer",
        expires_in_seconds: int | None = None,
        refresh_token: str | None = None,
    ) -> None:
        """Set credentials with optional expiration and refresh."""
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
        """Set callback for automatic token refresh."""
        self._token_refresh_callback = callback

    def _refresh_token_if_needed(self) -> None:
        """Refresh token if expired and callback is available."""
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
        """Clear authentication credentials."""
        self._credentials = None

    def get_auth_header(self) -> dict[str, str]:
        """Get authorization header if credentials are set."""
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
        """Record a request/response to history."""
        record = ClientRecord(
            operation=operation,
            request_data=request_data,
            response_data=response_data,
            duration_ms=duration_ms,
            error=error,
            metadata=metadata or {},
        )
        self.history.append(record)
        return record

    def get_history(self) -> list[ClientRecord]:
        """Get all request history."""
        return self.history.copy()

    def clear_history(self) -> None:
        """Clear request history."""
        self.history.clear()

    def last_request(self) -> ClientRecord | None:
        """Get the most recent request record."""
        return self.history[-1] if self.history else None

    def _ensure_connected(self) -> None:
        """Ensure client is connected before operations."""
        if not self._connected:
            self.connect()

    def _retry_with_backoff(
        self, operation: Callable[[], T], is_retryable: Callable[[Exception], bool]
    ) -> T:
        """Execute operation with retry and exponential backoff."""
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
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.disconnect()


class BaseAsyncClient(ABC, Generic[T]):
    """Abstract base class for async protocol clients."""

    def __init__(
        self,
        endpoint: str,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.default_headers = default_headers or {}
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.history: list[ClientRecord] = []
        self._credentials: AuthCredentials | None = None
        self._token_refresh_callback: Callable[[], AuthCredentials] | None = None
        self._connected = False

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the service."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the service."""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if client is connected."""
        pass

    def set_auth_token(self, token: str, token_type: str = "Bearer") -> None:
        """Set authentication token for subsequent requests."""
        self._credentials = AuthCredentials(token=token, token_type=token_type)

    def set_credentials(
        self,
        token: str,
        token_type: str = "Bearer",
        expires_in_seconds: int | None = None,
        refresh_token: str | None = None,
    ) -> None:
        """Set credentials with optional expiration and refresh."""
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
        """Set callback for automatic token refresh."""
        self._token_refresh_callback = callback

    def _refresh_token_if_needed(self) -> None:
        """Refresh token if expired and callback is available."""
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
        """Clear authentication credentials."""
        self._credentials = None

    def get_auth_header(self) -> dict[str, str]:
        """Get authorization header if credentials are set."""
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
        """Record a request/response to history."""
        record = ClientRecord(
            operation=operation,
            request_data=request_data,
            response_data=response_data,
            duration_ms=duration_ms,
            error=error,
            metadata=metadata or {},
        )
        self.history.append(record)
        return record

    def get_history(self) -> list[ClientRecord]:
        """Get all request history."""
        return self.history.copy()

    def clear_history(self) -> None:
        """Clear request history."""
        self.history.clear()

    def last_request(self) -> ClientRecord | None:
        """Get the most recent request record."""
        return self.history[-1] if self.history else None

    async def __aenter__(self) -> BaseAsyncClient[T]:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()
