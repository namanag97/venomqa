"""HTTP Mocking for VenomQA.

This module provides HTTP endpoint mocking capabilities including:
- Mock specific endpoints with predefined responses
- Simulate delays and timeouts
- Return error responses (500, 503, etc.)
- Response sequences for stateful testing

Example:
    >>> from venomqa.mocking import HTTPMock, MockedResponse
    >>>
    >>> # Create HTTP mock
    >>> mock = HTTPMock()
    >>>
    >>> # Mock a GET endpoint
    >>> mock.get("/api/users").returns(
    ...     status=200,
    ...     json={"users": [{"id": 1, "name": "John"}]}
    ... )
    >>>
    >>> # Mock with delay
    >>> mock.post("/api/slow").returns(
    ...     status=200,
    ...     delay_ms=5000
    ... )
    >>>
    >>> # Mock error response
    >>> mock.get("/api/error").returns(status=500, json={"error": "Server error"})
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Any, Pattern
from urllib.parse import parse_qs, urlparse

import httpx


class MockError(Exception):
    """Base exception for mock errors."""

    pass


class MockNotFoundError(MockError):
    """Raised when no mock matches a request."""

    pass


class MockTimeoutError(MockError):
    """Raised when a mock timeout is triggered."""

    pass


class MatchType(Enum):
    """How to match request attributes."""

    EXACT = "exact"
    PATTERN = "pattern"
    CONTAINS = "contains"
    ANY = "any"


@dataclass
class RequestMatcher:
    """Matches incoming requests against criteria.

    Attributes:
        method: HTTP method to match (GET, POST, etc.)
        path: URL path pattern to match
        path_pattern: Regex pattern for path matching
        headers: Headers that must be present
        query_params: Query parameters to match
        body_contains: Body must contain this string
        body_json: Body must match this JSON (or callable)
        priority: Higher priority matchers are checked first
    """

    method: str = "GET"
    path: str = "/"
    path_pattern: Pattern[str] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    header_patterns: dict[str, Pattern[str]] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    body_contains: str | None = None
    body_json: dict[str, Any] | Callable[[dict], bool] | None = None
    priority: int = 0

    def matches(self, request: httpx.Request) -> bool:
        """Check if request matches this matcher."""
        # Check method
        if self.method.upper() != request.method.upper():
            return False

        # Check path
        parsed_url = urlparse(str(request.url))
        path = parsed_url.path

        if self.path_pattern:
            if not self.path_pattern.match(path):
                return False
        elif self.path != path:
            # Try prefix matching for paths with query strings
            if not path.startswith(self.path.rstrip("/")):
                return False

        # Check headers
        for key, value in self.headers.items():
            req_value = request.headers.get(key.lower())
            if req_value is None or req_value != value:
                return False

        # Check header patterns
        for key, pattern in self.header_patterns.items():
            req_value = request.headers.get(key.lower())
            if req_value is None or not pattern.match(req_value):
                return False

        # Check query params
        query_string = parsed_url.query
        actual_params = parse_qs(query_string)
        for key, value in self.query_params.items():
            actual_values = actual_params.get(key, [])
            if value not in actual_values:
                return False

        # Check body
        if self.body_contains is not None:
            body_text = request.content.decode("utf-8", errors="ignore")
            if self.body_contains not in body_text:
                return False

        if self.body_json is not None:
            try:
                body_text = request.content.decode("utf-8")
                body_data = json.loads(body_text) if body_text else {}
                if callable(self.body_json):
                    if not self.body_json(body_data):
                        return False
                else:
                    for key, value in self.body_json.items():
                        if body_data.get(key) != value:
                            return False
            except (json.JSONDecodeError, UnicodeDecodeError):
                return False

        return True


@dataclass
class MockedResponse:
    """A mocked HTTP response.

    Attributes:
        status: HTTP status code
        headers: Response headers
        body: Raw response body
        json_body: JSON response body (takes precedence over body)
        text_body: Text response body
        delay_ms: Delay before returning response (milliseconds)
        raise_error: Exception to raise instead of returning response
        timeout: Simulate a timeout
    """

    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None
    json_body: dict[str, Any] | list[Any] | None = None
    text_body: str | None = None
    delay_ms: float = 0
    raise_error: Exception | None = None
    timeout: bool = False

    def __post_init__(self) -> None:
        """Set default Content-Type header based on body type."""
        if "content-type" not in {k.lower() for k in self.headers}:
            if self.json_body is not None:
                self.headers["Content-Type"] = "application/json"
            elif self.text_body is not None:
                self.headers["Content-Type"] = "text/plain"

    def get_body(self) -> bytes:
        """Get the response body as bytes."""
        if self.body is not None:
            return self.body
        if self.json_body is not None:
            return json.dumps(self.json_body).encode("utf-8")
        if self.text_body is not None:
            return self.text_body.encode("utf-8")
        return b""

    def to_httpx_response(self, request: httpx.Request) -> httpx.Response:
        """Convert to httpx.Response."""
        return httpx.Response(
            status_code=self.status,
            headers=self.headers,
            content=self.get_body(),
            request=request,
        )


@dataclass
class DelayedResponse(MockedResponse):
    """A response with built-in delay."""

    def __init__(self, delay_ms: float, **kwargs: Any) -> None:
        super().__init__(delay_ms=delay_ms, **kwargs)


@dataclass
class ErrorResponse(MockedResponse):
    """A predefined error response."""

    def __init__(
        self,
        status: int = 500,
        error_message: str = "Internal Server Error",
        error_code: str | None = None,
        **kwargs: Any,
    ) -> None:
        error_body: dict[str, Any] = {
            "error": {"message": error_message},
        }
        if error_code:
            error_body["error"]["code"] = error_code
        super().__init__(status=status, json_body=error_body, **kwargs)


@dataclass
class TimeoutResponse(MockedResponse):
    """A response that simulates a timeout."""

    def __init__(self, timeout_after_ms: float = 30000, **kwargs: Any) -> None:
        super().__init__(timeout=True, delay_ms=timeout_after_ms, **kwargs)


class ResponseSequence:
    """A sequence of responses to return in order.

    Useful for testing retry logic or state transitions.

    Example:
        >>> sequence = ResponseSequence([
        ...     MockedResponse(status=500),  # First call fails
        ...     MockedResponse(status=500),  # Second call fails
        ...     MockedResponse(status=200, json_body={"ok": True}),  # Third succeeds
        ... ])
    """

    def __init__(
        self,
        responses: list[MockedResponse],
        repeat_last: bool = True,
    ) -> None:
        """Initialize response sequence.

        Args:
            responses: List of responses to return in order
            repeat_last: Whether to repeat the last response after exhausting the list
        """
        if not responses:
            raise ValueError("Response sequence cannot be empty")
        self._responses = responses
        self._repeat_last = repeat_last
        self._index = 0
        self._lock = Lock()

    def next(self) -> MockedResponse:
        """Get the next response in the sequence."""
        with self._lock:
            if self._index >= len(self._responses):
                if self._repeat_last:
                    return self._responses[-1]
                raise MockError("Response sequence exhausted")
            response = self._responses[self._index]
            self._index += 1
            return response

    def reset(self) -> None:
        """Reset the sequence to the beginning."""
        with self._lock:
            self._index = 0

    @property
    def remaining(self) -> int:
        """Number of responses remaining before repetition."""
        return max(0, len(self._responses) - self._index)


@dataclass
class MockedEndpoint:
    """A mocked HTTP endpoint.

    Combines a request matcher with a response or response sequence.

    Attributes:
        id: Unique identifier for this endpoint
        matcher: Request matcher criteria
        response: Single response or sequence
        call_count: Number of times this endpoint was called
        calls: Record of all calls to this endpoint
        created_at: When this endpoint was created
        enabled: Whether this endpoint is active
    """

    id: str
    matcher: RequestMatcher
    response: MockedResponse | ResponseSequence
    call_count: int = 0
    calls: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    enabled: bool = True

    def get_response(self) -> MockedResponse:
        """Get the next response for this endpoint."""
        if isinstance(self.response, ResponseSequence):
            return self.response.next()
        return self.response

    def record_call(self, request: httpx.Request) -> None:
        """Record a call to this endpoint."""
        self.call_count += 1
        self.calls.append(
            {
                "timestamp": datetime.now().isoformat(),
                "method": request.method,
                "url": str(request.url),
                "headers": dict(request.headers),
                "body": request.content.decode("utf-8", errors="ignore"),
            }
        )


class EndpointBuilder:
    """Fluent builder for mocked endpoints.

    Example:
        >>> mock = HTTPMock()
        >>> mock.get("/api/users").with_header("X-API-Key", "secret").returns(
        ...     status=200,
        ...     json={"users": []}
        ... )
    """

    def __init__(
        self,
        mock: HTTPMock,
        method: str,
        path: str,
    ) -> None:
        self._mock = mock
        self._method = method
        self._path = path
        self._path_pattern: Pattern[str] | None = None
        self._headers: dict[str, str] = {}
        self._header_patterns: dict[str, Pattern[str]] = {}
        self._query_params: dict[str, str] = {}
        self._body_contains: str | None = None
        self._body_json: dict[str, Any] | Callable[[dict], bool] | None = None
        self._priority = 0

    def with_path_pattern(self, pattern: str) -> EndpointBuilder:
        """Match path using regex pattern."""
        self._path_pattern = re.compile(pattern)
        return self

    def with_header(self, key: str, value: str) -> EndpointBuilder:
        """Require specific header value."""
        self._headers[key] = value
        return self

    def with_header_pattern(self, key: str, pattern: str) -> EndpointBuilder:
        """Require header matching pattern."""
        self._header_patterns[key] = re.compile(pattern)
        return self

    def with_query_param(self, key: str, value: str) -> EndpointBuilder:
        """Require specific query parameter."""
        self._query_params[key] = value
        return self

    def with_body_containing(self, text: str) -> EndpointBuilder:
        """Require body to contain text."""
        self._body_contains = text
        return self

    def with_body_json(
        self, matcher: dict[str, Any] | Callable[[dict], bool]
    ) -> EndpointBuilder:
        """Require body JSON to match."""
        self._body_json = matcher
        return self

    def with_priority(self, priority: int) -> EndpointBuilder:
        """Set matcher priority (higher is checked first)."""
        self._priority = priority
        return self

    def returns(
        self,
        status: int = 200,
        json: dict[str, Any] | list[Any] | None = None,
        body: bytes | None = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        delay_ms: float = 0,
    ) -> MockedEndpoint:
        """Set the response for this endpoint."""
        response = MockedResponse(
            status=status,
            json_body=json,
            body=body,
            text_body=text,
            headers=headers or {},
            delay_ms=delay_ms,
        )
        return self._create_endpoint(response)

    def returns_sequence(
        self,
        responses: list[MockedResponse],
        repeat_last: bool = True,
    ) -> MockedEndpoint:
        """Set a sequence of responses."""
        sequence = ResponseSequence(responses, repeat_last=repeat_last)
        return self._create_endpoint(sequence)

    def returns_error(
        self,
        status: int = 500,
        message: str = "Internal Server Error",
        code: str | None = None,
    ) -> MockedEndpoint:
        """Return an error response."""
        response = ErrorResponse(status=status, error_message=message, error_code=code)
        return self._create_endpoint(response)

    def times_out(self, after_ms: float = 30000) -> MockedEndpoint:
        """Simulate a timeout."""
        response = TimeoutResponse(timeout_after_ms=after_ms)
        return self._create_endpoint(response)

    def raises(self, error: Exception) -> MockedEndpoint:
        """Raise an exception when called."""
        response = MockedResponse(raise_error=error)
        return self._create_endpoint(response)

    def _create_endpoint(
        self, response: MockedResponse | ResponseSequence
    ) -> MockedEndpoint:
        """Create and register the endpoint."""
        matcher = RequestMatcher(
            method=self._method,
            path=self._path,
            path_pattern=self._path_pattern,
            headers=self._headers,
            header_patterns=self._header_patterns,
            query_params=self._query_params,
            body_contains=self._body_contains,
            body_json=self._body_json,
            priority=self._priority,
        )
        endpoint = MockedEndpoint(
            id=str(uuid.uuid4()),
            matcher=matcher,
            response=response,
        )
        self._mock.add_endpoint(endpoint)
        return endpoint


class HTTPMock:
    """HTTP endpoint mocking for testing.

    Provides a fluent API for mocking HTTP endpoints with:
    - Exact and pattern-based URL matching
    - Header and query parameter matching
    - Request body matching
    - Response delays and timeouts
    - Error simulation
    - Call recording and verification

    Example:
        >>> mock = HTTPMock()
        >>>
        >>> # Mock a simple GET endpoint
        >>> mock.get("/api/users").returns(
        ...     status=200,
        ...     json={"users": [{"id": 1, "name": "John"}]}
        ... )
        >>>
        >>> # Mock with header requirement
        >>> mock.get("/api/protected").with_header("Authorization", "Bearer token").returns(
        ...     status=200,
        ...     json={"secret": "data"}
        ... )
        >>>
        >>> # Mock POST with body matching
        >>> mock.post("/api/users").with_body_json({"name": "John"}).returns(
        ...     status=201,
        ...     json={"id": 1, "name": "John"}
        ... )
        >>>
        >>> # Install as httpx transport
        >>> client = httpx.Client(transport=mock.transport())
    """

    def __init__(self, base_url: str = "") -> None:
        """Initialize HTTP mock.

        Args:
            base_url: Base URL to prepend to all paths
        """
        self._base_url = base_url.rstrip("/")
        self._endpoints: list[MockedEndpoint] = []
        self._unmatched_requests: list[dict[str, Any]] = []
        self._lock = Lock()
        self._passthrough = False

    @property
    def base_url(self) -> str:
        """Get the base URL."""
        return self._base_url

    def get(self, path: str) -> EndpointBuilder:
        """Start building a GET endpoint mock."""
        return EndpointBuilder(self, "GET", path)

    def post(self, path: str) -> EndpointBuilder:
        """Start building a POST endpoint mock."""
        return EndpointBuilder(self, "POST", path)

    def put(self, path: str) -> EndpointBuilder:
        """Start building a PUT endpoint mock."""
        return EndpointBuilder(self, "PUT", path)

    def patch(self, path: str) -> EndpointBuilder:
        """Start building a PATCH endpoint mock."""
        return EndpointBuilder(self, "PATCH", path)

    def delete(self, path: str) -> EndpointBuilder:
        """Start building a DELETE endpoint mock."""
        return EndpointBuilder(self, "DELETE", path)

    def any(self, path: str) -> EndpointBuilder:
        """Start building a mock for any HTTP method."""
        builder = EndpointBuilder(self, "GET", path)
        # Override method matching to accept any
        builder._method = "*"
        return builder

    def add_endpoint(self, endpoint: MockedEndpoint) -> None:
        """Add a mocked endpoint."""
        with self._lock:
            self._endpoints.append(endpoint)
            # Sort by priority (highest first)
            self._endpoints.sort(key=lambda e: e.matcher.priority, reverse=True)

    def remove_endpoint(self, endpoint_id: str) -> bool:
        """Remove an endpoint by ID."""
        with self._lock:
            for i, endpoint in enumerate(self._endpoints):
                if endpoint.id == endpoint_id:
                    del self._endpoints[i]
                    return True
            return False

    def clear(self) -> None:
        """Clear all mocked endpoints and recorded calls."""
        with self._lock:
            self._endpoints.clear()
            self._unmatched_requests.clear()

    def reset_calls(self) -> None:
        """Reset call counts and recordings for all endpoints."""
        with self._lock:
            for endpoint in self._endpoints:
                endpoint.call_count = 0
                endpoint.calls.clear()
            self._unmatched_requests.clear()

    def enable_passthrough(self) -> None:
        """Enable passthrough for unmatched requests."""
        self._passthrough = True

    def disable_passthrough(self) -> None:
        """Disable passthrough for unmatched requests."""
        self._passthrough = False

    def find_endpoint(self, request: httpx.Request) -> MockedEndpoint | None:
        """Find the first matching endpoint for a request."""
        with self._lock:
            for endpoint in self._endpoints:
                if endpoint.enabled and endpoint.matcher.matches(request):
                    return endpoint
            return None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Handle an incoming request.

        Args:
            request: The incoming HTTP request

        Returns:
            The mocked response

        Raises:
            MockNotFoundError: If no endpoint matches and passthrough is disabled
            MockTimeoutError: If the endpoint simulates a timeout
        """
        endpoint = self.find_endpoint(request)

        if endpoint is None:
            self._unmatched_requests.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "method": request.method,
                    "url": str(request.url),
                    "headers": dict(request.headers),
                }
            )
            if self._passthrough:
                # Return a placeholder that indicates passthrough
                raise MockNotFoundError(
                    f"No mock found for {request.method} {request.url}"
                )
            raise MockNotFoundError(f"No mock found for {request.method} {request.url}")

        # Record the call
        endpoint.record_call(request)

        # Get the response
        response = endpoint.get_response()

        # Handle special response types
        if response.raise_error is not None:
            raise response.raise_error

        if response.timeout:
            raise MockTimeoutError(
                f"Mock timeout after {response.delay_ms}ms for {request.method} {request.url}"
            )

        # Apply delay
        if response.delay_ms > 0:
            time.sleep(response.delay_ms / 1000)

        return response.to_httpx_response(request)

    async def handle_request_async(self, request: httpx.Request) -> httpx.Response:
        """Handle an incoming request asynchronously."""
        endpoint = self.find_endpoint(request)

        if endpoint is None:
            self._unmatched_requests.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "method": request.method,
                    "url": str(request.url),
                    "headers": dict(request.headers),
                }
            )
            raise MockNotFoundError(f"No mock found for {request.method} {request.url}")

        endpoint.record_call(request)
        response = endpoint.get_response()

        if response.raise_error is not None:
            raise response.raise_error

        if response.timeout:
            raise MockTimeoutError(
                f"Mock timeout after {response.delay_ms}ms for {request.method} {request.url}"
            )

        if response.delay_ms > 0:
            await asyncio.sleep(response.delay_ms / 1000)

        return response.to_httpx_response(request)

    def transport(self) -> httpx.MockTransport:
        """Create an httpx transport for this mock.

        Example:
            >>> mock = HTTPMock()
            >>> mock.get("/api/test").returns(status=200, json={"ok": True})
            >>> client = httpx.Client(transport=mock.transport())
            >>> response = client.get("http://test.local/api/test")
        """
        return httpx.MockTransport(self.handle_request)

    def async_transport(self) -> httpx.MockTransport:
        """Create an async httpx transport for this mock."""
        return httpx.MockTransport(self.handle_request_async)

    # Verification methods

    def was_called(self, method: str, path: str) -> bool:
        """Check if an endpoint was called."""
        for endpoint in self._endpoints:
            if endpoint.matcher.method == method and endpoint.matcher.path == path:
                return endpoint.call_count > 0
        return False

    def call_count(self, method: str, path: str) -> int:
        """Get the number of calls to an endpoint."""
        for endpoint in self._endpoints:
            if endpoint.matcher.method == method and endpoint.matcher.path == path:
                return endpoint.call_count
        return 0

    def get_calls(self, method: str, path: str) -> list[dict[str, Any]]:
        """Get all calls to an endpoint."""
        for endpoint in self._endpoints:
            if endpoint.matcher.method == method and endpoint.matcher.path == path:
                return endpoint.calls.copy()
        return []

    def get_last_call(self, method: str, path: str) -> dict[str, Any] | None:
        """Get the last call to an endpoint."""
        calls = self.get_calls(method, path)
        return calls[-1] if calls else None

    def get_unmatched_requests(self) -> list[dict[str, Any]]:
        """Get all unmatched requests."""
        return self._unmatched_requests.copy()

    def verify(
        self,
        method: str,
        path: str,
        times: int | None = None,
        at_least: int | None = None,
        at_most: int | None = None,
    ) -> bool:
        """Verify endpoint was called expected number of times.

        Args:
            method: HTTP method
            path: URL path
            times: Exact number of expected calls
            at_least: Minimum number of calls
            at_most: Maximum number of calls

        Returns:
            True if verification passes
        """
        count = self.call_count(method, path)

        if times is not None and count != times:
            return False
        if at_least is not None and count < at_least:
            return False
        if at_most is not None and count > at_most:
            return False

        return True

    def assert_called(self, method: str, path: str, times: int | None = None) -> None:
        """Assert endpoint was called.

        Raises:
            AssertionError: If verification fails
        """
        count = self.call_count(method, path)
        if times is not None:
            assert count == times, f"Expected {times} calls to {method} {path}, got {count}"
        else:
            assert count > 0, f"Expected at least one call to {method} {path}, got none"

    def assert_not_called(self, method: str, path: str) -> None:
        """Assert endpoint was not called."""
        count = self.call_count(method, path)
        assert count == 0, f"Expected no calls to {method} {path}, got {count}"

    def assert_called_with(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> None:
        """Assert endpoint was called with specific parameters."""
        calls = self.get_calls(method, path)
        assert calls, f"No calls to {method} {path}"

        last_call = calls[-1]

        if headers:
            for key, value in headers.items():
                assert (
                    last_call["headers"].get(key.lower()) == value
                ), f"Header {key} not found or doesn't match"

        if json_body:
            body = json.loads(last_call["body"]) if last_call["body"] else {}
            for key, value in json_body.items():
                assert body.get(key) == value, f"Body key {key} not found or doesn't match"

    @property
    def endpoints(self) -> list[MockedEndpoint]:
        """Get all mocked endpoints."""
        return self._endpoints.copy()

    def __enter__(self) -> HTTPMock:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.clear()
