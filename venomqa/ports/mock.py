"""Mock Port interface for VenomQA."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MockResponse:
    """Represents a mock HTTP response."""

    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    delay: float = 0.0


@dataclass
class MockEndpoint:
    """Represents a mock HTTP endpoint."""

    method: str
    path: str
    response: MockResponse | None = None
    responses: list[MockResponse] = field(default_factory=list)
    response_index: int = 0
    priority: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)


@dataclass
class RecordedRequest:
    """Represents a recorded HTTP request."""

    id: str
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    body: Any = None
    timestamp: datetime | None = None
    matched_endpoint: str | None = None
    response_status: int = 0


class MockPort(ABC):
    """Abstract port for mock server operations in QA testing.

    This port defines the interface for mock servers like
    WireMock, MockServer, etc. Implementations should support
    endpoint stubbing, request recording, and verification.
    """

    @abstractmethod
    def stub(
        self,
        method: str,
        path: str,
        response: MockResponse | None = None,
        status_code: int = 200,
        body: Any = None,
        headers: dict[str, str] | None = None,
        delay: float = 0.0,
    ) -> str:
        """Create a stub endpoint.

        Args:
            method: HTTP method.
            path: URL path pattern.
            response: Complete response object.
            status_code: Response status code.
            body: Response body.
            headers: Response headers.
            delay: Response delay in seconds.

        Returns:
            Stub ID.
        """
        ...

    @abstractmethod
    def stub_sequence(
        self,
        method: str,
        path: str,
        responses: list[MockResponse],
    ) -> str:
        """Create a stub that returns different responses in sequence.

        Args:
            method: HTTP method.
            path: URL path pattern.
            responses: List of responses to return in order.

        Returns:
            Stub ID.
        """
        ...

    @abstractmethod
    def stub_with_callback(
        self,
        method: str,
        path: str,
        callback: Callable[[RecordedRequest], MockResponse],
    ) -> str:
        """Create a stub that uses a callback to generate responses.

        Args:
            method: HTTP method.
            path: URL path pattern.
            callback: Function to generate responses.

        Returns:
            Stub ID.
        """
        ...

    @abstractmethod
    def remove_stub(self, stub_id: str) -> bool:
        """Remove a stub.

        Args:
            stub_id: Stub ID to remove.

        Returns:
            True if removed, False if not found.
        """
        ...

    @abstractmethod
    def clear_stubs(self) -> None:
        """Clear all stubs."""
        ...

    @abstractmethod
    def get_requests(
        self,
        method: str | None = None,
        path: str | None = None,
        limit: int | None = None,
    ) -> list[RecordedRequest]:
        """Get recorded requests.

        Args:
            method: Filter by HTTP method.
            path: Filter by path pattern.
            limit: Maximum requests to return.

        Returns:
            List of recorded requests.
        """
        ...

    @abstractmethod
    def get_request(self, request_id: str) -> RecordedRequest | None:
        """Get a specific recorded request.

        Args:
            request_id: Request ID.

        Returns:
            Request or None if not found.
        """
        ...

    @abstractmethod
    def count_requests(
        self,
        method: str | None = None,
        path: str | None = None,
    ) -> int:
        """Count recorded requests.

        Args:
            method: Filter by HTTP method.
            path: Filter by path pattern.

        Returns:
            Number of matching requests.
        """
        ...

    @abstractmethod
    def verify(
        self,
        method: str,
        path: str,
        count: int | None = None,
        at_least: int | None = None,
        at_most: int | None = None,
    ) -> bool:
        """Verify that requests were made.

        Args:
            method: HTTP method.
            path: URL path pattern.
            count: Exact count expected.
            at_least: Minimum count expected.
            at_most: Maximum count expected.

        Returns:
            True if verification passes.
        """
        ...

    @abstractmethod
    def clear_requests(self) -> None:
        """Clear all recorded requests."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset all stubs and recorded requests."""
        ...

    @abstractmethod
    def get_base_url(self) -> str:
        """Get the base URL of the mock server.

        Returns:
            Base URL string.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the mock server is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        ...
