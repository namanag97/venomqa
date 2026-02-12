"""WireMock adapter for HTTP mocking.

WireMock is a popular HTTP mock server for testing.

Installation:
    Run WireMock via Docker:
    docker run -d -p 8080:8080 -p 8443:8443 wiremock/wiremock

Example:
    >>> from venomqa.adapters import WireMockAdapter
    >>> adapter = WireMockAdapter(host="localhost", port=8080)
    >>> adapter.stub("GET", "/api/users", body={"users": []})
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

from venomqa.ports.mock import MockPort, MockResponse, RecordedRequest


@dataclass
class WireMockConfig:
    """Configuration for WireMock adapter."""

    host: str = "localhost"
    port: int = 8080
    timeout: float = 10.0
    poll_interval: float = 0.5


class WireMockAdapter(MockPort):
    """Adapter for WireMock mock server.

    This adapter provides integration with WireMock for HTTP
    mocking in test environments.

    Attributes:
        config: Configuration for WireMock connection.

    Example:
        >>> adapter = WireMockAdapter()
        >>> adapter.stub("GET", "/api/users", body=[{"id": 1}])
        >>> response = requests.get(adapter.get_base_url() + "/api/users")
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8080,
        timeout: float = 10.0,
    ) -> None:
        """Initialize the WireMock adapter.

        Args:
            host: WireMock server hostname.
            port: WireMock server port.
            timeout: Request timeout in seconds.
        """
        self.config = WireMockConfig(
            host=host,
            port=port,
            timeout=timeout,
        )
        self._base_url = f"http://{host}:{port}"
        self._admin_url = f"{self._base_url}/__admin"

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
        if response:
            status_code = response.status_code
            body = response.body
            headers = response.headers or {}
            delay = response.delay

        mapping = {
            "request": {
                "method": method.upper(),
                "urlPath": path,
            },
            "response": {
                "status": status_code,
            },
        }

        if body is not None:
            if isinstance(body, (dict, list)):
                mapping["response"]["jsonBody"] = body
                mapping["response"]["headers"] = {"Content-Type": "application/json"}
            else:
                mapping["response"]["body"] = str(body)

        if headers:
            mapping["response"]["headers"] = {
                **mapping["response"].get("headers", {}),
                **headers,
            }

        if delay > 0:
            mapping["response"]["fixedDelayMilliseconds"] = int(delay * 1000)

        response = requests.post(
            f"{self._admin_url}/mappings",
            json=mapping,
            timeout=self.config.timeout,
        )
        response.raise_for_status()

        result = response.json()
        return result.get("id", str(uuid.uuid4()))

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
        scenarios = []
        scenario_name = f"seq_{uuid.uuid4().hex[:8]}"

        for i, resp in enumerate(responses):
            state_name = f"state_{i}"
            next_state = f"state_{i + 1}" if i < len(responses) - 1 else "done"

            mapping = {
                "scenarioName": scenario_name,
                "requiredScenarioState": state_name if i > 0 else "Started",
                "newScenarioState": next_state,
                "request": {
                    "method": method.upper(),
                    "urlPath": path,
                },
                "response": {
                    "status": resp.status_code,
                },
            }

            if resp.body is not None:
                if isinstance(resp.body, (dict, list)):
                    mapping["response"]["jsonBody"] = resp.body
                else:
                    mapping["response"]["body"] = str(resp.body)

            if resp.delay > 0:
                mapping["response"]["fixedDelayMilliseconds"] = int(resp.delay * 1000)

            r = requests.post(
                f"{self._admin_url}/mappings",
                json=mapping,
                timeout=self.config.timeout,
            )
            r.raise_for_status()
            scenarios.append(r.json().get("id", ""))

        return scenarios[0] if scenarios else ""

    def stub_with_callback(
        self,
        method: str,
        path: str,
        callback: Callable[[RecordedRequest], MockResponse],
    ) -> str:
        """Create a stub that uses a callback to generate responses.

        Note: WireMock doesn't support Python callbacks directly.
        This creates a default response instead.

        Args:
            method: HTTP method.
            path: URL path pattern.
            callback: Function to generate responses.

        Returns:
            Stub ID.
        """
        return self.stub(method, path, status_code=200, body="Callback not supported")

    def remove_stub(self, stub_id: str) -> bool:
        """Remove a stub.

        Args:
            stub_id: Stub ID to remove.

        Returns:
            True if removed, False if not found.
        """
        try:
            response = requests.delete(
                f"{self._admin_url}/mappings/{stub_id}",
                timeout=self.config.timeout,
            )
            return response.status_code in (200, 204, 404)
        except requests.RequestException:
            return False

    def clear_stubs(self) -> None:
        """Clear all stubs."""
        requests.delete(
            f"{self._admin_url}/mappings",
            timeout=self.config.timeout,
        )

    def _parse_request(self, item: dict[str, Any]) -> RecordedRequest:
        """Parse a WireMock request log entry."""
        request = item.get("request", {})
        return RecordedRequest(
            id=item.get("id", str(uuid.uuid4())),
            method=request.get("method", ""),
            path=request.get("url", ""),
            headers=request.get("headers", {}),
            query_params={},
            body=request.get("body"),
            timestamp=None,
            matched_endpoint=item.get("mappingId"),
            response_status=item.get("response", {}).get("status", 0),
        )

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
        try:
            response = requests.get(
                f"{self._admin_url}/requests",
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            requests_data = response.json().get("requests", [])

            results = []
            for item in requests_data:
                req = self._parse_request(item)

                if method and req.method.upper() != method.upper():
                    continue
                if path and path not in req.path:
                    continue

                results.append(req)

                if limit and len(results) >= limit:
                    break

            return results
        except requests.RequestException:
            return []

    def get_request(self, request_id: str) -> RecordedRequest | None:
        """Get a specific recorded request.

        Args:
            request_id: Request ID.

        Returns:
            Request or None if not found.
        """
        try:
            response = requests.get(
                f"{self._admin_url}/requests/{request_id}",
                timeout=self.config.timeout,
            )
            if response.status_code == 200:
                return self._parse_request(response.json())
            return None
        except requests.RequestException:
            return None

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
        return len(self.get_requests(method=method, path=path))

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
        actual = self.count_requests(method=method, path=path)

        if count is not None and actual != count:
            return False
        if at_least is not None and actual < at_least:
            return False
        if at_most is not None and actual > at_most:
            return False

        return True

    def clear_requests(self) -> None:
        """Clear all recorded requests."""
        requests.delete(
            f"{self._admin_url}/requests",
            timeout=self.config.timeout,
        )

    def reset(self) -> None:
        """Reset all stubs and recorded requests."""
        self.clear_stubs()
        self.clear_requests()

    def get_base_url(self) -> str:
        """Get the base URL of the mock server.

        Returns:
            Base URL string.
        """
        return self._base_url

    def health_check(self) -> bool:
        """Check if the mock server is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            response = requests.get(
                f"{self._admin_url}/health",
                timeout=2.0,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_all_mappings(self) -> list[dict[str, Any]]:
        """Get all stub mappings.

        Returns:
            List of mapping definitions.
        """
        try:
            response = requests.get(
                f"{self._admin_url}/mappings",
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            return response.json().get("mappings", [])
        except requests.RequestException:
            return []

    def set_global_delay(self, delay: float) -> bool:
        """Set a global response delay.

        Args:
            delay: Delay in seconds.

        Returns:
            True if successful.
        """
        try:
            response = requests.post(
                f"{self._admin_url}/settings",
                json={"fixedDelay": int(delay * 1000)},
                timeout=self.config.timeout,
            )
            return response.status_code == 200
        except requests.RequestException:
            return False

    def reset_global_delay(self) -> bool:
        """Reset global response delay.

        Returns:
            True if successful.
        """
        return self.set_global_delay(0)
