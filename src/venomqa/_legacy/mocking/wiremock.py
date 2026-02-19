"""WireMock Integration for VenomQA.

This module provides integration with WireMock for complex HTTP mocking scenarios:
- Docker-based WireMock setup
- Stub management
- Request matching and verification
- Scenarios and stateful behavior

Example:
    >>> from venomqa.mocking import WireMockManager
    >>>
    >>> # Use with existing WireMock instance
    >>> wiremock = WireMockManager(host="localhost", port=8080)
    >>>
    >>> # Create stub
    >>> wiremock.stub(
    ...     method="GET",
    ...     url="/api/users",
    ...     response={"users": []},
    ...     status=200
    ... )
    >>>
    >>> # Or use Docker container
    >>> from venomqa.mocking import WireMockContainer
    >>> with WireMockContainer() as wiremock:
    ...     wiremock.stub(...)
    ...     # Tests here
"""

from __future__ import annotations

import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx


class WireMockError(Exception):
    """Base exception for WireMock errors."""

    pass


class WireMockConnectionError(WireMockError):
    """Raised when unable to connect to WireMock."""

    pass


@dataclass
class WireMockStub:
    """A WireMock stub definition.

    Attributes:
        id: Stub ID assigned by WireMock
        method: HTTP method to match
        url: URL pattern to match
        url_pattern: Regex pattern for URL matching
        status: Response status code
        body: Response body
        headers: Response headers
        delay_ms: Response delay in milliseconds
        priority: Stub priority (higher = checked first)
        scenario: Scenario name for stateful behavior
        required_state: Required scenario state
        new_state: New scenario state after match
    """

    id: str = ""
    method: str = "GET"
    url: str | None = None
    url_pattern: str | None = None
    url_path: str | None = None
    url_path_pattern: str | None = None
    status: int = 200
    body: str | dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    delay_ms: int = 0
    priority: int = 5
    scenario: str | None = None
    required_state: str | None = None
    new_state: str | None = None
    query_params: dict[str, str] = field(default_factory=dict)
    body_patterns: list[dict[str, Any]] = field(default_factory=list)

    def to_wiremock_json(self) -> dict[str, Any]:
        """Convert to WireMock JSON format."""
        request: dict[str, Any] = {"method": self.method}

        if self.url:
            request["url"] = self.url
        elif self.url_pattern:
            request["urlPattern"] = self.url_pattern
        elif self.url_path:
            request["urlPath"] = self.url_path
        elif self.url_path_pattern:
            request["urlPathPattern"] = self.url_path_pattern

        if self.query_params:
            request["queryParameters"] = {
                k: {"equalTo": v} for k, v in self.query_params.items()
            }

        if self.body_patterns:
            request["bodyPatterns"] = self.body_patterns

        response: dict[str, Any] = {"status": self.status}

        if self.body is not None:
            if isinstance(self.body, dict):
                response["jsonBody"] = self.body
                response["headers"] = {"Content-Type": "application/json", **self.headers}
            else:
                response["body"] = str(self.body)
                if self.headers:
                    response["headers"] = self.headers
        elif self.headers:
            response["headers"] = self.headers

        if self.delay_ms > 0:
            response["fixedDelayMilliseconds"] = self.delay_ms

        mapping: dict[str, Any] = {
            "request": request,
            "response": response,
            "priority": self.priority,
        }

        if self.scenario:
            mapping["scenarioName"] = self.scenario
            if self.required_state:
                mapping["requiredScenarioState"] = self.required_state
            if self.new_state:
                mapping["newScenarioState"] = self.new_state

        return mapping


@dataclass
class WireMockRequest:
    """A recorded WireMock request.

    Attributes:
        id: Request ID
        method: HTTP method
        url: Request URL
        headers: Request headers
        body: Request body
        timestamp: When request was received
        matched: Whether request matched a stub
        stub_id: ID of matched stub (if any)
    """

    id: str
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    matched: bool = False
    stub_id: str | None = None


class WireMockManager:
    """Manager for WireMock mock server.

    Provides a Python interface for WireMock's admin API.

    Example:
        >>> wiremock = WireMockManager(host="localhost", port=8080)
        >>>
        >>> # Create a stub
        >>> stub_id = wiremock.stub(
        ...     method="GET",
        ...     url="/api/users",
        ...     response={"users": [{"id": 1}]},
        ...     status=200
        ... )
        >>>
        >>> # Verify request was made
        >>> assert wiremock.verify("GET", "/api/users")
        >>>
        >>> # Clean up
        >>> wiremock.reset()
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8080,
        https: bool = False,
        timeout: float = 10.0,
    ) -> None:
        """Initialize WireMock manager.

        Args:
            host: WireMock server host
            port: WireMock server port
            https: Use HTTPS
            timeout: Request timeout
        """
        self._host = host
        self._port = port
        self._https = https
        self._timeout = timeout
        scheme = "https" if https else "http"
        self._base_url = f"{scheme}://{host}:{port}"
        self._admin_url = f"{self._base_url}/__admin"
        self._client = httpx.Client(timeout=timeout)

    @property
    def base_url(self) -> str:
        """Get the base URL for making requests to WireMock."""
        return self._base_url

    def health_check(self) -> bool:
        """Check if WireMock is running and healthy.

        Returns:
            True if healthy
        """
        try:
            response = self._client.get(f"{self._admin_url}/health")
            return response.status_code == 200
        except httpx.RequestError:
            return False

    def wait_until_ready(self, timeout: float = 30.0, poll_interval: float = 0.5) -> bool:
        """Wait for WireMock to become ready.

        Args:
            timeout: Maximum wait time in seconds
            poll_interval: Time between health checks

        Returns:
            True if ready, False if timeout
        """
        start = time.time()
        while time.time() - start < timeout:
            if self.health_check():
                return True
            time.sleep(poll_interval)
        return False

    def stub(
        self,
        method: str = "GET",
        url: str | None = None,
        url_pattern: str | None = None,
        url_path: str | None = None,
        response: dict[str, Any] | str | None = None,
        status: int = 200,
        headers: dict[str, str] | None = None,
        delay_ms: int = 0,
        priority: int = 5,
        scenario: str | None = None,
        required_state: str | None = None,
        new_state: str | None = None,
    ) -> str:
        """Create a stub.

        Args:
            method: HTTP method
            url: Exact URL to match
            url_pattern: Regex pattern for URL
            url_path: URL path to match
            response: Response body (dict for JSON, str for text)
            status: Response status code
            headers: Response headers
            delay_ms: Response delay
            priority: Stub priority
            scenario: Scenario name for stateful behavior
            required_state: Required scenario state
            new_state: New state after match

        Returns:
            Stub ID

        Raises:
            WireMockError: If stub creation fails
        """
        stub = WireMockStub(
            method=method.upper(),
            url=url,
            url_pattern=url_pattern,
            url_path=url_path,
            status=status,
            body=response,
            headers=headers or {},
            delay_ms=delay_ms,
            priority=priority,
            scenario=scenario,
            required_state=required_state,
            new_state=new_state,
        )

        try:
            resp = self._client.post(
                f"{self._admin_url}/mappings",
                json=stub.to_wiremock_json(),
            )
            resp.raise_for_status()
            result = resp.json()
            return result.get("id", str(uuid.uuid4()))
        except httpx.HTTPError as e:
            raise WireMockError(f"Failed to create stub: {e}") from e

    def stub_sequence(
        self,
        method: str,
        url: str,
        responses: list[dict[str, Any]],
    ) -> str:
        """Create a sequence of stubs using scenarios.

        Each request returns the next response in the sequence.

        Args:
            method: HTTP method
            url: URL to match
            responses: List of response configs (status, body, headers, delay_ms)

        Returns:
            Scenario name

        Example:
            >>> wiremock.stub_sequence("POST", "/api/retry", [
            ...     {"status": 500, "body": {"error": "Temporary error"}},
            ...     {"status": 500, "body": {"error": "Still failing"}},
            ...     {"status": 200, "body": {"success": True}},
            ... ])
        """
        scenario_name = f"seq_{uuid.uuid4().hex[:8]}"

        for i, resp_config in enumerate(responses):
            state = "Started" if i == 0 else f"state_{i}"
            next_state = f"state_{i + 1}" if i < len(responses) - 1 else "done"

            self.stub(
                method=method,
                url=url,
                status=resp_config.get("status", 200),
                response=resp_config.get("body"),
                headers=resp_config.get("headers"),
                delay_ms=resp_config.get("delay_ms", 0),
                scenario=scenario_name,
                required_state=state,
                new_state=next_state,
            )

        return scenario_name

    def remove_stub(self, stub_id: str) -> bool:
        """Remove a stub by ID.

        Args:
            stub_id: Stub ID to remove

        Returns:
            True if removed
        """
        try:
            resp = self._client.delete(f"{self._admin_url}/mappings/{stub_id}")
            return resp.status_code in (200, 204)
        except httpx.RequestError:
            return False

    def clear_stubs(self) -> None:
        """Clear all stubs."""
        try:
            self._client.delete(f"{self._admin_url}/mappings")
        except httpx.RequestError:
            pass

    def get_stubs(self) -> list[dict[str, Any]]:
        """Get all stubs.

        Returns:
            List of stub mappings
        """
        try:
            resp = self._client.get(f"{self._admin_url}/mappings")
            resp.raise_for_status()
            return resp.json().get("mappings", [])
        except httpx.RequestError:
            return []

    def get_requests(
        self,
        method: str | None = None,
        url: str | None = None,
        limit: int = 100,
    ) -> list[WireMockRequest]:
        """Get recorded requests.

        Args:
            method: Filter by HTTP method
            url: Filter by URL (contains)
            limit: Maximum requests to return

        Returns:
            List of recorded requests
        """
        try:
            resp = self._client.get(f"{self._admin_url}/requests")
            resp.raise_for_status()
            requests_data = resp.json().get("requests", [])

            results = []
            for item in requests_data[:limit]:
                req = item.get("request", {})
                req_url = req.get("url", "")

                if method and req.get("method", "").upper() != method.upper():
                    continue
                if url and url not in req_url:
                    continue

                results.append(
                    WireMockRequest(
                        id=item.get("id", str(uuid.uuid4())),
                        method=req.get("method", ""),
                        url=req_url,
                        headers=req.get("headers", {}),
                        body=req.get("body", ""),
                        matched=item.get("wasMatched", False),
                        stub_id=item.get("stubMapping", {}).get("id"),
                    )
                )

            return results
        except httpx.RequestError:
            return []

    def count_requests(self, method: str | None = None, url: str | None = None) -> int:
        """Count recorded requests.

        Args:
            method: Filter by method
            url: Filter by URL

        Returns:
            Number of matching requests
        """
        return len(self.get_requests(method=method, url=url))

    def verify(
        self,
        method: str,
        url: str,
        times: int | None = None,
        at_least: int | None = None,
        at_most: int | None = None,
    ) -> bool:
        """Verify requests were made.

        Args:
            method: HTTP method
            url: URL (contains match)
            times: Exact expected count
            at_least: Minimum count
            at_most: Maximum count

        Returns:
            True if verification passes
        """
        count = self.count_requests(method=method, url=url)

        if times is not None and count != times:
            return False
        if at_least is not None and count < at_least:
            return False
        if at_most is not None and count > at_most:
            return False

        return True

    def clear_requests(self) -> None:
        """Clear all recorded requests."""
        try:
            self._client.delete(f"{self._admin_url}/requests")
        except httpx.RequestError:
            pass

    def reset(self) -> None:
        """Reset all stubs and requests."""
        try:
            self._client.post(f"{self._admin_url}/reset")
        except httpx.RequestError:
            # Fall back to manual reset
            self.clear_stubs()
            self.clear_requests()

    def reset_scenarios(self) -> None:
        """Reset all scenarios to initial state."""
        try:
            self._client.post(f"{self._admin_url}/scenarios/reset")
        except httpx.RequestError:
            pass

    def set_global_delay(self, delay_ms: int) -> None:
        """Set global fixed delay for all responses.

        Args:
            delay_ms: Delay in milliseconds
        """
        try:
            self._client.post(
                f"{self._admin_url}/settings",
                json={"fixedDelay": delay_ms},
            )
        except httpx.RequestError:
            pass

    def simulate_fault(
        self,
        method: str,
        url: str,
        fault_type: str = "CONNECTION_RESET_BY_PEER",
    ) -> str:
        """Create a stub that simulates a network fault.

        Args:
            method: HTTP method
            url: URL to match
            fault_type: Type of fault (CONNECTION_RESET_BY_PEER, EMPTY_RESPONSE, MALFORMED_RESPONSE_CHUNK, RANDOM_DATA_THEN_CLOSE)

        Returns:
            Stub ID
        """
        mapping = {
            "request": {"method": method, "url": url},
            "response": {"fault": fault_type},
        }

        try:
            resp = self._client.post(f"{self._admin_url}/mappings", json=mapping)
            resp.raise_for_status()
            return resp.json().get("id", str(uuid.uuid4()))
        except httpx.HTTPError as e:
            raise WireMockError(f"Failed to create fault stub: {e}") from e

    def __enter__(self) -> WireMockManager:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - reset WireMock."""
        self.reset()
        self._client.close()


class WireMockContainer:
    """Docker-based WireMock container for testing.

    Automatically starts and stops a WireMock Docker container.

    Example:
        >>> with WireMockContainer() as wiremock:
        ...     wiremock.stub(method="GET", url="/api/test", response={"ok": True})
        ...     # Run tests
        ...     # Container is automatically stopped
    """

    def __init__(
        self,
        image: str = "wiremock/wiremock:latest",
        port: int = 8080,
        https_port: int = 8443,
        verbose: bool = False,
        extensions: list[str] | None = None,
    ) -> None:
        """Initialize WireMock container.

        Args:
            image: Docker image to use
            port: HTTP port
            https_port: HTTPS port
            verbose: Enable verbose logging
            extensions: List of WireMock extensions to enable
        """
        self._image = image
        self._port = port
        self._https_port = https_port
        self._verbose = verbose
        self._extensions = extensions or []
        self._container_id: str | None = None
        self._manager: WireMockManager | None = None

    def start(self) -> WireMockManager:
        """Start the WireMock container.

        Returns:
            WireMockManager for the container

        Raises:
            WireMockError: If container fails to start
        """
        cmd = [
            "docker",
            "run",
            "-d",
            "--rm",
            "-p",
            f"{self._port}:8080",
            "-p",
            f"{self._https_port}:8443",
        ]

        if self._verbose:
            cmd.extend(["--env", "WIREMOCK_OPTIONS=--verbose"])

        cmd.append(self._image)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self._container_id = result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise WireMockError(f"Failed to start WireMock container: {e.stderr}") from e

        # Create manager
        self._manager = WireMockManager(host="localhost", port=self._port)

        # Wait for container to be ready
        if not self._manager.wait_until_ready(timeout=30):
            self.stop()
            raise WireMockError("WireMock container failed to become ready")

        return self._manager

    def stop(self) -> None:
        """Stop the WireMock container."""
        if self._container_id:
            try:
                subprocess.run(
                    ["docker", "stop", self._container_id],
                    capture_output=True,
                    check=False,
                )
            except subprocess.CalledProcessError:
                pass
            self._container_id = None

        if self._manager:
            self._manager._client.close()
            self._manager = None

    @property
    def manager(self) -> WireMockManager | None:
        """Get the WireMock manager."""
        return self._manager

    def __enter__(self) -> WireMockManager:
        """Context manager entry - start container."""
        return self.start()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - stop container."""
        self.stop()


class WireMockBuilder:
    """Fluent builder for WireMock stubs.

    Example:
        >>> WireMockBuilder(manager).get("/api/users").with_query("page", "1").returns(
        ...     status=200,
        ...     json={"users": []}
        ... )
    """

    def __init__(self, manager: WireMockManager) -> None:
        """Initialize builder.

        Args:
            manager: WireMock manager
        """
        self._manager = manager
        self._method = "GET"
        self._url: str | None = None
        self._url_pattern: str | None = None
        self._url_path: str | None = None
        self._headers: dict[str, str] = {}
        self._query_params: dict[str, str] = {}
        self._body_patterns: list[dict[str, Any]] = []
        self._priority = 5
        self._scenario: str | None = None
        self._required_state: str | None = None
        self._new_state: str | None = None

    def get(self, url: str) -> WireMockBuilder:
        """Configure GET request matcher."""
        self._method = "GET"
        self._url = url
        return self

    def post(self, url: str) -> WireMockBuilder:
        """Configure POST request matcher."""
        self._method = "POST"
        self._url = url
        return self

    def put(self, url: str) -> WireMockBuilder:
        """Configure PUT request matcher."""
        self._method = "PUT"
        self._url = url
        return self

    def delete(self, url: str) -> WireMockBuilder:
        """Configure DELETE request matcher."""
        self._method = "DELETE"
        self._url = url
        return self

    def with_url_pattern(self, pattern: str) -> WireMockBuilder:
        """Match URL with regex pattern."""
        self._url = None
        self._url_pattern = pattern
        return self

    def with_url_path(self, path: str) -> WireMockBuilder:
        """Match URL path exactly."""
        self._url = None
        self._url_path = path
        return self

    def with_header(self, key: str, value: str) -> WireMockBuilder:
        """Require header in request."""
        self._headers[key] = value
        return self

    def with_query(self, key: str, value: str) -> WireMockBuilder:
        """Require query parameter."""
        self._query_params[key] = value
        return self

    def with_body_containing(self, text: str) -> WireMockBuilder:
        """Require body to contain text."""
        self._body_patterns.append({"contains": text})
        return self

    def with_body_json(self, json_path: str, value: Any) -> WireMockBuilder:
        """Require body JSON field to match."""
        self._body_patterns.append({"matchesJsonPath": f"$[?(@.{json_path} == '{value}')]"})
        return self

    def with_priority(self, priority: int) -> WireMockBuilder:
        """Set stub priority."""
        self._priority = priority
        return self

    def in_scenario(
        self,
        scenario: str,
        required_state: str | None = None,
        new_state: str | None = None,
    ) -> WireMockBuilder:
        """Configure scenario-based matching."""
        self._scenario = scenario
        self._required_state = required_state
        self._new_state = new_state
        return self

    def returns(
        self,
        status: int = 200,
        json: dict[str, Any] | None = None,
        body: str | None = None,
        headers: dict[str, str] | None = None,
        delay_ms: int = 0,
    ) -> str:
        """Set response and create stub.

        Returns:
            Stub ID
        """
        stub = WireMockStub(
            method=self._method,
            url=self._url,
            url_pattern=self._url_pattern,
            url_path=self._url_path,
            status=status,
            body=json or body,
            headers=headers or {},
            delay_ms=delay_ms,
            priority=self._priority,
            scenario=self._scenario,
            required_state=self._required_state,
            new_state=self._new_state,
            query_params=self._query_params,
            body_patterns=self._body_patterns,
        )

        try:
            resp = self._manager._client.post(
                f"{self._manager._admin_url}/mappings",
                json=stub.to_wiremock_json(),
            )
            resp.raise_for_status()
            return resp.json().get("id", str(uuid.uuid4()))
        except httpx.HTTPError as e:
            raise WireMockError(f"Failed to create stub: {e}") from e

    def returns_fault(self, fault_type: str = "CONNECTION_RESET_BY_PEER") -> str:
        """Return a network fault.

        Args:
            fault_type: Type of fault

        Returns:
            Stub ID
        """
        mapping = {
            "request": {"method": self._method},
            "response": {"fault": fault_type},
        }

        if self._url:
            mapping["request"]["url"] = self._url
        elif self._url_pattern:
            mapping["request"]["urlPattern"] = self._url_pattern
        elif self._url_path:
            mapping["request"]["urlPath"] = self._url_path

        try:
            resp = self._manager._client.post(
                f"{self._manager._admin_url}/mappings",
                json=mapping,
            )
            resp.raise_for_status()
            return resp.json().get("id", str(uuid.uuid4()))
        except httpx.HTTPError as e:
            raise WireMockError(f"Failed to create fault stub: {e}") from e
