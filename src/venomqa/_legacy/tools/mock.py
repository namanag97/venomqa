"""Mock server integration for QA testing.

This module provides reusable mock server action functions supporting:
- MockServer integration
- WireMock integration
- Generic mock server support

Example:
    >>> from venomqa.tools import setup_mock, verify_mock_called, clear_mocks
    >>>
    >>> # Setup a mock response
    >>> setup_mock(client, context, "/api/users", {"status": 200, "body": {"users": []}})
    >>>
    >>> # Verify mock was called
    >>> verify_mock_called(client, context, "/api/users", times=1)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx

from venomqa.errors import VenomQAError

if TYPE_CHECKING:
    from venomqa.http import Client
    from venomqa.state.context import Context


class MockError(VenomQAError):
    """Raised when a mock operation fails."""

    pass


def _get_mock_config(client: Client, context: Context) -> dict[str, Any]:
    """Get mock server configuration from client or context."""
    config = {}

    if hasattr(context, "config") and hasattr(context.config, "mock"):
        config = context.config.mock or {}
    elif hasattr(client, "mock_config"):
        config = client.mock_config or {}

    if hasattr(context, "_mock_config"):
        config = {**config, **context._mock_config}

    return config


def _get_mockserver_url(client: Client, context: Context) -> str:
    """Get MockServer API URL from configuration."""
    config = _get_mock_config(client, context)
    return config.get("mockserver_url", "http://localhost:1080")


def _get_wiremock_url(client: Client, context: Context) -> str:
    """Get WireMock API URL from configuration."""
    config = _get_mock_config(client, context)
    return config.get("wiremock_url", "http://localhost:8080")


def setup_mock(
    client: Client,
    context: Context,
    path: str,
    response: dict[str, Any],
    method: str = "GET",
    mock_service: str = "mockserver",
    priority: int = 0,
    delay_ms: int = 0,
) -> dict[str, Any]:
    """Setup a mock response for a specific endpoint.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API path to mock (e.g., "/api/users").
        response: Response configuration with 'status' and 'body'.
        method: HTTP method to match (default: GET).
        mock_service: Mock service to use ('mockserver' or 'wiremock').
        priority: Priority for matching (higher = more important).
        delay_ms: Delay before responding in milliseconds.

    Returns:
        dict: Mock configuration that was created.

    Raises:
        MockError: If setup fails.

    Example:
        >>> setup_mock(
        ...     client, context,
        ...     path="/api/users",
        ...     response={"status": 200, "body": {"users": [{"id": 1, "name": "John"}]}},
        ...     method="GET"
        ... )
    """
    if mock_service == "mockserver":
        return _setup_mockserver(client, context, path, response, method, priority, delay_ms)
    elif mock_service == "wiremock":
        return _setup_wiremock(client, context, path, response, method, priority, delay_ms)
    else:
        raise MockError(f"Unsupported mock service: {mock_service}")


def _setup_mockserver(
    client: Client,
    context: Context,
    path: str,
    response: dict[str, Any],
    method: str,
    priority: int,
    delay_ms: int,
) -> dict[str, Any]:
    """Setup mock in MockServer."""
    base_url = _get_mockserver_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    mock_config = {
        "httpRequest": {
            "method": method,
            "path": path,
        },
        "httpResponse": {
            "statusCode": response.get("status", 200),
            "body": json.dumps(response.get("body", {})),
            "headers": response.get("headers", {"Content-Type": "application/json"}),
        },
        "priority": priority,
    }

    if delay_ms > 0:
        mock_config["httpResponse"]["delay"] = {"timeUnit": "MILLISECONDS", "value": delay_ms}

    try:
        resp = http_client.put(
            f"{base_url}/mockserver/expectation",
            json=mock_config,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise MockError(f"Failed to setup mock in MockServer: {e}") from e

    mock_id = f"{method}:{path}"
    if not hasattr(context, "_mocks"):
        context._mocks = {}
    context._mocks[mock_id] = {"path": path, "method": method, "config": mock_config}

    return {"mock_id": mock_id, "config": mock_config}


def _setup_wiremock(
    client: Client,
    context: Context,
    path: str,
    response: dict[str, Any],
    method: str,
    priority: int,
    delay_ms: int,
) -> dict[str, Any]:
    """Setup mock in WireMock."""
    base_url = _get_wiremock_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    mock_config = {
        "request": {
            "method": method,
            "urlPath": path,
        },
        "response": {
            "status": response.get("status", 200),
            "jsonBody": response.get("body", {}),
            "headers": response.get("headers", {"Content-Type": "application/json"}),
        },
        "priority": priority,
    }

    if delay_ms > 0:
        mock_config["response"]["fixedDelayMilliseconds"] = delay_ms

    try:
        resp = http_client.post(
            f"{base_url}/__admin/mappings",
            json=mock_config,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        result = resp.json()
    except httpx.HTTPError as e:
        raise MockError(f"Failed to setup mock in WireMock: {e}") from e

    mock_id = result.get("id", f"{method}:{path}")
    if not hasattr(context, "_mocks"):
        context._mocks = {}
    context._mocks[mock_id] = {"path": path, "method": method, "config": mock_config}

    return {"mock_id": mock_id, "config": mock_config}


def setup_mock_sequence(
    client: Client,
    context: Context,
    path: str,
    responses: list[dict[str, Any]],
    method: str = "GET",
    mock_service: str = "mockserver",
) -> list[dict[str, Any]]:
    """Setup a sequence of mock responses for the same endpoint.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API path to mock.
        responses: List of response configurations.
        method: HTTP method to match.
        mock_service: Mock service to use.

    Returns:
        list: List of mock configurations created.

    Example:
        >>> setup_mock_sequence(
        ...     client, context,
        ...     path="/api/poll",
        ...     responses=[
        ...         {"status": 200, "body": {"status": "pending"}},
        ...         {"status": 200, "body": {"status": "pending"}},
        ...         {"status": 200, "body": {"status": "completed"}},
        ...     ]
        ... )
    """
    if mock_service == "mockserver":
        return _setup_mockserver_sequence(client, context, path, responses, method)
    elif mock_service == "wiremock":
        return _setup_wiremock_sequence(client, context, path, responses, method)
    else:
        raise MockError(f"Unsupported mock service: {mock_service}")


def _setup_mockserver_sequence(
    client: Client,
    context: Context,
    path: str,
    responses: list[dict[str, Any]],
    method: str,
) -> list[dict[str, Any]]:
    """Setup response sequence in MockServer."""
    base_url = _get_mockserver_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    mock_ids = []

    for i, response in enumerate(responses):
        mock_config = {
            "httpRequest": {
                "method": method,
                "path": path,
            },
            "httpResponse": {
                "statusCode": response.get("status", 200),
                "body": json.dumps(response.get("body", {})),
                "headers": response.get("headers", {"Content-Type": "application/json"}),
            },
            "times": {"remainingTimes": 1, "unlimited": False},
            "priority": len(responses) - i,
        }

        try:
            resp = http_client.put(
                f"{base_url}/mockserver/expectation",
                json=mock_config,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise MockError(f"Failed to setup mock sequence in MockServer: {e}") from e

        mock_id = f"{method}:{path}:{i}"
        mock_ids.append({"mock_id": mock_id, "config": mock_config})

    if not hasattr(context, "_mock_sequences"):
        context._mock_sequences = {}
    context._mock_sequences[f"{method}:{path}"] = mock_ids

    return mock_ids


def _setup_wiremock_sequence(
    client: Client,
    context: Context,
    path: str,
    responses: list[dict[str, Any]],
    method: str,
) -> list[dict[str, Any]]:
    """Setup response sequence in WireMock."""
    base_url = _get_wiremock_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    scenario_name = f"scenario_{path.replace('/', '_')}_{method}"
    mock_ids = []

    for i, response in enumerate(responses):
        _state_name = f"state_{i}"
        del _state_name
        next_state = f"state_{i + 1}" if i < len(responses) - 1 else "done"

        mock_config = {
            "request": {
                "method": method,
                "urlPath": path,
                "scenarioName": scenario_name,
            },
            "response": {
                "status": response.get("status", 200),
                "jsonBody": response.get("body", {}),
            },
        }

        if i == 0:
            mock_config["request"]["requiredScenarioState"] = "Started"
        else:
            mock_config["request"]["requiredScenarioState"] = f"state_{i}"

        if i < len(responses) - 1:
            mock_config["newScenarioState"] = next_state

        try:
            resp = http_client.post(
                f"{base_url}/__admin/mappings",
                json=mock_config,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            result = resp.json()
        except httpx.HTTPError as e:
            raise MockError(f"Failed to setup mock sequence in WireMock: {e}") from e

        mock_id = result.get("id", f"{method}:{path}:{i}")
        mock_ids.append({"mock_id": mock_id, "config": mock_config})

    if not hasattr(context, "_mock_sequences"):
        context._mock_sequences = {}
    context._mock_sequences[f"{method}:{path}"] = mock_ids

    return mock_ids


def remove_mock(
    client: Client,
    context: Context,
    mock_id: str,
    mock_service: str = "mockserver",
) -> bool:
    """Remove a specific mock.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        mock_id: ID of the mock to remove.
        mock_service: Mock service to use.

    Returns:
        bool: True if mock was removed.

    Raises:
        MockError: If removal fails.

    Example:
        >>> remove_mock(client, context, "GET:/api/users")
    """
    if mock_service == "mockserver":
        return _remove_mockserver_mock(client, context, mock_id)
    elif mock_service == "wiremock":
        return _remove_wiremock_mock(client, context, mock_id)
    else:
        raise MockError(f"Unsupported mock service: {mock_service}")


def _remove_mockserver_mock(client: Client, context: Context, mock_id: str) -> bool:
    """Remove mock from MockServer."""
    base_url = _get_mockserver_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    stored_mock = getattr(context, "_mocks", {}).get(mock_id, {})
    mock_config = stored_mock.get("config", {})

    try:
        resp = http_client.put(
            f"{base_url}/mockserver/clear",
            json={"httpRequest": mock_config.get("httpRequest", {})},
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise MockError(f"Failed to remove mock from MockServer: {e}") from e

    if hasattr(context, "_mocks") and mock_id in context._mocks:
        del context._mocks[mock_id]

    return True


def _remove_wiremock_mock(client: Client, context: Context, mock_id: str) -> bool:
    """Remove mock from WireMock."""
    base_url = _get_wiremock_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    try:
        resp = http_client.delete(f"{base_url}/__admin/mappings/{mock_id}")
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise MockError(f"Failed to remove mock from WireMock: {e}") from e

    if hasattr(context, "_mocks") and mock_id in context._mocks:
        del context._mocks[mock_id]

    return True


def clear_mocks(
    client: Client,
    context: Context,
    mock_service: str = "mockserver",
) -> int:
    """Clear all mocks from the mock server.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        mock_service: Mock service to use.

    Returns:
        int: Number of mocks cleared.

    Raises:
        MockError: If clearing fails.

    Example:
        >>> count = clear_mocks(client, context)
        >>> print(f"Cleared {count} mocks")
    """
    if mock_service == "mockserver":
        return _clear_mockserver_mocks(client, context)
    elif mock_service == "wiremock":
        return _clear_wiremock_mocks(client, context)
    else:
        raise MockError(f"Unsupported mock service: {mock_service}")


def _clear_mockserver_mocks(client: Client, context: Context) -> int:
    """Clear all mocks from MockServer."""
    base_url = _get_mockserver_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    count = len(getattr(context, "_mocks", {}))

    try:
        resp = http_client.put(
            f"{base_url}/mockserver/reset",
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise MockError(f"Failed to clear mocks from MockServer: {e}") from e

    if hasattr(context, "_mocks"):
        context._mocks = {}
    if hasattr(context, "_mock_sequences"):
        context._mock_sequences = {}

    return count


def _clear_wiremock_mocks(client: Client, context: Context) -> int:
    """Clear all mocks from WireMock."""
    base_url = _get_wiremock_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    try:
        resp = http_client.delete(f"{base_url}/__admin/mappings")
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise MockError(f"Failed to clear mocks from WireMock: {e}") from e

    count = len(getattr(context, "_mocks", {}))

    if hasattr(context, "_mocks"):
        context._mocks = {}
    if hasattr(context, "_mock_sequences"):
        context._mock_sequences = {}

    return count


def verify_mock_called(
    client: Client,
    context: Context,
    path: str,
    times: int | None = None,
    method: str = "GET",
    mock_service: str = "mockserver",
) -> dict[str, Any]:
    """Verify that a mock endpoint was called.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API path to verify.
        times: Expected number of calls. If None, just checks it was called.
        method: HTTP method to match.
        mock_service: Mock service to use.

    Returns:
        dict: Verification result with 'called' and 'count' keys.

    Raises:
        MockError: If verification fails.

    Example:
        >>> result = verify_mock_called(client, context, "/api/users", times=2)
        >>> print(f"Called {result['count']} times")
    """
    if mock_service == "mockserver":
        return _verify_mockserver_called(client, context, path, times, method)
    elif mock_service == "wiremock":
        return _verify_wiremock_called(client, context, path, times, method)
    else:
        raise MockError(f"Unsupported mock service: {mock_service}")


def _verify_mockserver_called(
    client: Client,
    context: Context,
    path: str,
    times: int | None,
    method: str,
) -> dict[str, Any]:
    """Verify mock was called in MockServer."""
    base_url = _get_mockserver_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    verify_request = {
        "httpRequest": {
            "method": method,
            "path": path,
        },
    }

    if times is not None:
        verify_request["times"] = {"atLeast": times, "atMost": times}

    try:
        resp = http_client.put(
            f"{base_url}/mockserver/verify",
            json=verify_request,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise MockError(f"Mock verification failed for {method} {path}: {e}") from e

    try:
        count_resp = http_client.put(
            f"{base_url}/mockserver/retrieve",
            json={
                "httpRequest": {"method": method, "path": path},
                "retrieveType": "REQUESTS",
            },
            headers={"Content-Type": "application/json"},
        )
        count_resp.raise_for_status()
        requests = count_resp.json()
        call_count = len(requests) if isinstance(requests, list) else 0
    except Exception:
        call_count = times if times is not None else 1

    return {"called": True, "count": call_count, "expected": times}


def _verify_wiremock_called(
    client: Client,
    context: Context,
    path: str,
    times: int | None,
    method: str,
) -> dict[str, Any]:
    """Verify mock was called in WireMock."""
    base_url = _get_wiremock_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    try:
        resp = http_client.get(f"{base_url}/__admin/requests")
        resp.raise_for_status()
        requests = resp.json().get("requests", [])
    except httpx.HTTPError as e:
        raise MockError(f"Failed to retrieve requests from WireMock: {e}") from e

    call_count = sum(
        1
        for r in requests
        if r.get("request", {}).get("url", "").endswith(path)
        and r.get("request", {}).get("method") == method
    )

    if times is not None and call_count != times:
        raise MockError(
            f"Expected {method} {path} to be called {times} times, "
            f"but was called {call_count} times"
        )

    return {"called": call_count > 0, "count": call_count, "expected": times}


def get_mock_requests(
    client: Client,
    context: Context,
    path: str | None = None,
    method: str | None = None,
    mock_service: str = "mockserver",
) -> list[dict[str, Any]]:
    """Get all requests received by the mock server.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: Filter by path (optional).
        method: Filter by HTTP method (optional).
        mock_service: Mock service to use.

    Returns:
        list: List of request records.

    Raises:
        MockError: If retrieval fails.

    Example:
        >>> requests = get_mock_requests(client, context, path="/api/users")
        >>> for req in requests:
        ...     print(f"{req['method']} {req['path']}")
    """
    if mock_service == "mockserver":
        return _get_mockserver_requests(client, context, path, method)
    elif mock_service == "wiremock":
        return _get_wiremock_requests(client, context, path, method)
    else:
        raise MockError(f"Unsupported mock service: {mock_service}")


def _get_mockserver_requests(
    client: Client,
    context: Context,
    path: str | None,
    method: str | None,
) -> list[dict[str, Any]]:
    """Get requests from MockServer."""
    base_url = _get_mockserver_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    retrieve_request = {"retrieveType": "REQUESTS"}

    if path or method:
        retrieve_request["httpRequest"] = {}
        if path:
            retrieve_request["httpRequest"]["path"] = path
        if method:
            retrieve_request["httpRequest"]["method"] = method

    try:
        resp = http_client.put(
            f"{base_url}/mockserver/retrieve",
            json=retrieve_request,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        requests = resp.json()
    except httpx.HTTPError as e:
        raise MockError(f"Failed to retrieve requests from MockServer: {e}") from e

    result = []
    for req in requests if isinstance(requests, list) else []:
        result.append(
            {
                "method": req.get("method", ""),
                "path": req.get("path", ""),
                "headers": req.get("headers", {}),
                "body": req.get("body", {}),
                "timestamp": req.get("timestamp"),
            }
        )

    return result


def _get_wiremock_requests(
    client: Client,
    context: Context,
    path: str | None,
    method: str | None,
) -> list[dict[str, Any]]:
    """Get requests from WireMock."""
    base_url = _get_wiremock_url(client, context)
    http_client = getattr(client, "http_client", None) or httpx.Client()

    try:
        resp = http_client.get(f"{base_url}/__admin/requests")
        resp.raise_for_status()
        requests = resp.json().get("requests", [])
    except httpx.HTTPError as e:
        raise MockError(f"Failed to retrieve requests from WireMock: {e}") from e

    result = []
    for req in requests:
        req_data = req.get("request", {})
        req_path = req_data.get("url", "")

        if path and not req_path.endswith(path):
            continue
        if method and req_data.get("method") != method:
            continue

        result.append(
            {
                "method": req_data.get("method", ""),
                "path": req_path,
                "headers": req_data.get("headers", {}),
                "body": req_data.get("body", ""),
                "timestamp": req.get("loggedDate"),
            }
        )

    return result


def configure_mock(
    context: Context,
    mockserver_url: str | None = None,
    wiremock_url: str | None = None,
) -> None:
    """Configure mock server settings in context.

    Args:
        context: Test context to configure.
        mockserver_url: MockServer API URL.
        wiremock_url: WireMock API URL.

    Example:
        >>> configure_mock(
        ...     context,
        ...     mockserver_url="http://localhost:1080"
        ... )
    """
    if not hasattr(context, "_mock_config"):
        context._mock_config = {}

    if mockserver_url:
        context._mock_config["mockserver_url"] = mockserver_url
    if wiremock_url:
        context._mock_config["wiremock_url"] = wiremock_url


def reset_mock_requests(
    client: Client,
    context: Context,
    mock_service: str = "mockserver",
) -> bool:
    """Reset recorded requests (clear request log but keep mocks).

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        mock_service: Mock service to use.

    Returns:
        bool: True if reset was successful.

    Example:
        >>> reset_mock_requests(client, context)
    """
    if mock_service == "mockserver":
        base_url = _get_mockserver_url(client, context)
        http_client = getattr(client, "http_client", None) or httpx.Client()

        try:
            resp = http_client.put(
                f"{base_url}/mockserver/clear",
                json={"httpRequest": {}, "type": "LOG"},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            raise MockError(f"Failed to reset MockServer request log: {e}") from e
    elif mock_service == "wiremock":
        base_url = _get_wiremock_url(client, context)
        http_client = getattr(client, "http_client", None) or httpx.Client()

        try:
            resp = http_client.delete(f"{base_url}/__admin/requests")
            resp.raise_for_status()
            return True
        except httpx.HTTPError as e:
            raise MockError(f"Failed to reset WireMock request log: {e}") from e
    else:
        raise MockError(f"Unsupported mock service: {mock_service}")


class MockResponseBuilder:
    """Builder pattern for creating mock responses.

    Provides a fluent interface for configuring mock responses.

    Example:
        >>> mock = (
        ...     MockResponseBuilder()
        ...     .with_path("/api/users")
        ...     .with_method("GET")
        ...     .with_status(200)
        ...     .with_json_body({"users": [{"id": 1, "name": "John"}]})
        ...     .with_delay(100)
        ...     .build()
        ... )
        >>> setup_mock(client, context, mock["path"], mock["response"], mock["method"])
    """

    def __init__(self) -> None:
        self._path: str = "/"
        self._method: str = "GET"
        self._status: int = 200
        self._body: Any = {}
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        self._delay_ms: int = 0
        self._priority: int = 0

    def with_path(self, path: str) -> MockResponseBuilder:
        """Set the path for the mock."""
        self._path = path
        return self

    def with_method(self, method: str) -> MockResponseBuilder:
        """Set the HTTP method for the mock."""
        self._method = method.upper()
        return self

    def with_status(self, status: int) -> MockResponseBuilder:
        """Set the response status code."""
        self._status = status
        return self

    def with_body(self, body: Any) -> MockResponseBuilder:
        """Set the response body (any JSON-serializable value)."""
        self._body = body
        return self

    def with_json_body(self, data: dict[str, Any]) -> MockResponseBuilder:
        """Set the response body as JSON."""
        self._body = data
        self._headers["Content-Type"] = "application/json"
        return self

    def with_text_body(self, text: str) -> MockResponseBuilder:
        """Set the response body as plain text."""
        self._body = text
        self._headers["Content-Type"] = "text/plain"
        return self

    def with_headers(self, headers: dict[str, str]) -> MockResponseBuilder:
        """Add response headers."""
        self._headers.update(headers)
        return self

    def with_delay(self, delay_ms: int) -> MockResponseBuilder:
        """Set response delay in milliseconds."""
        self._delay_ms = delay_ms
        return self

    def with_priority(self, priority: int) -> MockResponseBuilder:
        """Set mock priority (higher = more important)."""
        self._priority = priority
        return self

    def build(self) -> dict[str, Any]:
        """Build the mock configuration.

        Returns:
            dict: Configuration with path, method, and response.
        """
        return {
            "path": self._path,
            "method": self._method,
            "response": {
                "status": self._status,
                "body": self._body,
                "headers": self._headers,
            },
            "delay_ms": self._delay_ms,
            "priority": self._priority,
        }

    def setup(
        self,
        client: Client,
        context: Context,
        mock_service: str = "mockserver",
    ) -> dict[str, Any]:
        """Build and setup the mock in one step.

        Args:
            client: VenomQA client instance.
            context: Test context.
            mock_service: Mock service to use.

        Returns:
            dict: Mock configuration that was created.
        """
        config = self.build()
        return setup_mock(
            client=client,
            context=context,
            path=config["path"],
            response=config["response"],
            method=config["method"],
            mock_service=mock_service,
            priority=config["priority"],
            delay_ms=config["delay_ms"],
        )


def mock_success_response(
    path: str,
    data: Any,
    method: str = "GET",
) -> dict[str, Any]:
    """Create a standard success mock response.

    Args:
        path: API path to mock.
        data: Response data.
        method: HTTP method.

    Returns:
        dict: Mock configuration.

    Example:
        >>> config = mock_success_response("/api/users", {"users": []})
        >>> setup_mock(client, context, config["path"], config["response"])
    """
    return {
        "path": path,
        "method": method,
        "response": {
            "status": 200,
            "body": {"success": True, "data": data},
            "headers": {"Content-Type": "application/json"},
        },
    }


def mock_error_response(
    path: str,
    error_message: str,
    status: int = 400,
    error_code: str | None = None,
    method: str = "GET",
) -> dict[str, Any]:
    """Create a standard error mock response.

    Args:
        path: API path to mock.
        error_message: Error message.
        status: HTTP status code (default: 400).
        error_code: Optional error code.
        method: HTTP method.

    Returns:
        dict: Mock configuration.

    Example:
        >>> config = mock_error_response("/api/users", "User not found", status=404)
        >>> setup_mock(client, context, config["path"], config["response"])
    """
    body: dict[str, Any] = {
        "success": False,
        "error": {"message": error_message},
    }
    if error_code:
        body["error"]["code"] = error_code

    return {
        "path": path,
        "method": method,
        "response": {
            "status": status,
            "body": body,
            "headers": {"Content-Type": "application/json"},
        },
    }


def mock_paginated_response(
    path: str,
    items: list[Any],
    page: int = 1,
    per_page: int = 10,
    total: int | None = None,
    method: str = "GET",
) -> dict[str, Any]:
    """Create a paginated mock response.

    Args:
        path: API path to mock.
        items: List of items for current page.
        page: Current page number.
        per_page: Items per page.
        total: Total items (default: len(items)).
        method: HTTP method.

    Returns:
        dict: Mock configuration.

    Example:
        >>> config = mock_paginated_response(
        ...     "/api/users",
        ...     items=[{"id": 1}, {"id": 2}],
        ...     page=1,
        ...     per_page=10,
        ...     total=25
        ... )
        >>> setup_mock(client, context, config["path"], config["response"])
    """
    total = total if total is not None else len(items)
    total_pages = (total + per_page - 1) // per_page

    return {
        "path": path,
        "method": method,
        "response": {
            "status": 200,
            "body": {
                "success": True,
                "data": {
                    "items": items,
                    "pagination": {
                        "page": page,
                        "per_page": per_page,
                        "total": total,
                        "total_pages": total_pages,
                        "has_next": page < total_pages,
                        "has_prev": page > 1,
                    },
                },
            },
            "headers": {"Content-Type": "application/json"},
        },
    }


def mock_auth_required_response(
    path: str,
    method: str = "GET",
) -> dict[str, Any]:
    """Create an authentication required (401) mock response.

    Args:
        path: API path to mock.
        method: HTTP method.

    Returns:
        dict: Mock configuration.

    Example:
        >>> config = mock_auth_required_response("/api/protected")
        >>> setup_mock(client, context, config["path"], config["response"])
    """
    return mock_error_response(
        path=path,
        error_message="Authentication required",
        status=401,
        error_code="AUTH_REQUIRED",
        method=method,
    )


def mock_rate_limited_response(
    path: str,
    retry_after: int = 60,
    method: str = "GET",
) -> dict[str, Any]:
    """Create a rate limited (429) mock response.

    Args:
        path: API path to mock.
        retry_after: Seconds until rate limit resets.
        method: HTTP method.

    Returns:
        dict: Mock configuration.

    Example:
        >>> config = mock_rate_limited_response("/api/data", retry_after=30)
        >>> setup_mock(client, context, config["path"], config["response"])
    """
    return {
        "path": path,
        "method": method,
        "response": {
            "status": 429,
            "body": {
                "success": False,
                "error": {
                    "message": "Rate limit exceeded",
                    "code": "RATE_LIMITED",
                    "retry_after": retry_after,
                },
            },
            "headers": {
                "Content-Type": "application/json",
                "Retry-After": str(retry_after),
            },
        },
    }


def mock_server_error_response(
    path: str,
    message: str = "Internal server error",
    method: str = "GET",
) -> dict[str, Any]:
    """Create a server error (500) mock response.

    Args:
        path: API path to mock.
        message: Error message.
        method: HTTP method.

    Returns:
        dict: Mock configuration.

    Example:
        >>> config = mock_server_error_response("/api/flaky")
        >>> setup_mock(client, context, config["path"], config["response"])
    """
    return mock_error_response(
        path=path,
        error_message=message,
        status=500,
        error_code="INTERNAL_ERROR",
        method=method,
    )
