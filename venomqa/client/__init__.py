"""HTTP Client with history tracking and retry logic."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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


class Client:
    """HTTP client that captures request history and handles retries."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        retry_count: int = 3,
        retry_delay: float = 1.0,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.default_headers = default_headers or {}
        self.history: list[RequestRecord] = []
        self._auth_token: str | None = None
        self._client: httpx.Client | None = None

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

    def clear_auth(self) -> None:
        """Clear authentication token."""
        self._auth_token = None

    def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an HTTP request with retry logic and history tracking."""
        if not self._client:
            self.connect()

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
    """Async HTTP client with history tracking."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        retry_count: int = 3,
        retry_delay: float = 1.0,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.default_headers = default_headers or {}
        self.history: list[RequestRecord] = []
        self._auth_token: str | None = None
        self._client: httpx.AsyncClient | None = None

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
        self._auth_token = f"{scheme} {token}"

    def clear_auth(self) -> None:
        self._auth_token = None

    async def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an async HTTP request with retry logic."""
        if not self._client:
            await self.connect()

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
