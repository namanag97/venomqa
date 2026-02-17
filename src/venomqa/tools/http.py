"""Advanced HTTP actions for REST, GraphQL, and WebSocket testing.

This module provides reusable HTTP action functions that work with
VenomQA's client and context system.

Example:
    >>> from venomqa.tools import get, post, graphql_query
    >>>
    >>> # REST GET request
    >>> response = get(client, context, "/api/users/1")
    >>>
    >>> # REST POST request
    >>> response = post(client, context, "/api/users", json={"name": "John"})
    >>>
    >>> # GraphQL query
    >>> result = graphql_query(client, context, "{ user(id: 1) { name } }")
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import httpx

from venomqa.errors import VenomQAError

if TYPE_CHECKING:
    from venomqa.http import Client
    from venomqa.state.context import Context


class HTTPError(VenomQAError):
    """Raised when an HTTP request fails."""

    pass


class WebSocketError(VenomQAError):
    """Raised when a WebSocket operation fails."""

    pass


class GraphQLError(VenomQAError):
    """Raised when a GraphQL query fails."""


GraphQL_Error = GraphQLError  # noqa: N801


def _get_base_url(client: Client, context: Context) -> str:
    """Get base URL from client or context."""
    if hasattr(client, "base_url") and client.base_url:
        return client.base_url.rstrip("/")
    if hasattr(context, "config") and hasattr(context.config, "base_url"):
        return context.config.base_url.rstrip("/")
    return ""


def _build_url(base_url: str, path: str) -> str:
    """Build full URL from base URL and path."""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith("ws://") or path.startswith("wss://"):
        return path
    return f"{base_url}/{path.lstrip('/')}"


def _get_headers(client: Client, context: Context) -> dict[str, str]:
    """Get headers from client and context."""
    headers = {}
    if hasattr(client, "headers"):
        headers.update(client.headers)
    if hasattr(context, "headers"):
        headers.update(context.headers)
    if hasattr(context, "get_auth_headers"):
        headers.update(context.get_auth_headers())
    return headers


def get(
    client: Client,
    context: Context,
    path: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    **kwargs: Any,
) -> httpx.Response:
    """Perform an HTTP GET request.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        params: Query parameters.
        headers: Additional headers for this request.
        timeout: Request timeout in seconds.
        **kwargs: Additional arguments passed to httpx.

    Returns:
        httpx.Response: The HTTP response.

    Raises:
        HTTPError: If the request fails.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> assert response.status_code == 200
        >>> users = response.json()
    """
    base_url = _get_base_url(client, context)
    url = _build_url(base_url, path)
    request_headers = _get_headers(client, context)
    if headers:
        request_headers.update(headers)

    http_client = getattr(client, "http_client", None) or httpx.Client(timeout=timeout)

    try:
        response = http_client.get(url, params=params, headers=request_headers, **kwargs)
        context.last_response = response
        return response
    except httpx.HTTPError as e:
        raise HTTPError(f"GET request failed: {url}") from e


def post(
    client: Client,
    context: Context,
    path: str,
    json: Any = None,
    data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    **kwargs: Any,
) -> httpx.Response:
    """Perform an HTTP POST request.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        json: JSON body for the request.
        data: Form data for the request.
        params: Query parameters.
        headers: Additional headers for this request.
        timeout: Request timeout in seconds.
        **kwargs: Additional arguments passed to httpx.

    Returns:
        httpx.Response: The HTTP response.

    Raises:
        HTTPError: If the request fails.

    Example:
        >>> response = post(
        ...     client, context, "/api/users",
        ...     json={"name": "John", "email": "john@example.com"}
        ... )
        >>> assert response.status_code == 201
    """
    base_url = _get_base_url(client, context)
    url = _build_url(base_url, path)
    request_headers = _get_headers(client, context)
    if headers:
        request_headers.update(headers)

    http_client = getattr(client, "http_client", None) or httpx.Client(timeout=timeout)

    try:
        response = http_client.post(
            url, json=json, data=data, params=params, headers=request_headers, **kwargs
        )
        context.last_response = response
        return response
    except httpx.HTTPError as e:
        raise HTTPError(f"POST request failed: {url}") from e


def put(
    client: Client,
    context: Context,
    path: str,
    json: Any = None,
    data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    **kwargs: Any,
) -> httpx.Response:
    """Perform an HTTP PUT request.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        json: JSON body for the request.
        data: Form data for the request.
        params: Query parameters.
        headers: Additional headers for this request.
        timeout: Request timeout in seconds.
        **kwargs: Additional arguments passed to httpx.

    Returns:
        httpx.Response: The HTTP response.

    Raises:
        HTTPError: If the request fails.

    Example:
        >>> response = put(
        ...     client, context, "/api/users/1",
        ...     json={"name": "Jane"}
        ... )
        >>> assert response.status_code == 200
    """
    base_url = _get_base_url(client, context)
    url = _build_url(base_url, path)
    request_headers = _get_headers(client, context)
    if headers:
        request_headers.update(headers)

    http_client = getattr(client, "http_client", None) or httpx.Client(timeout=timeout)

    try:
        response = http_client.put(
            url, json=json, data=data, params=params, headers=request_headers, **kwargs
        )
        context.last_response = response
        return response
    except httpx.HTTPError as e:
        raise HTTPError(f"PUT request failed: {url}") from e


def patch(
    client: Client,
    context: Context,
    path: str,
    json: Any = None,
    data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    **kwargs: Any,
) -> httpx.Response:
    """Perform an HTTP PATCH request.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        json: JSON body for the request.
        data: Form data for the request.
        params: Query parameters.
        headers: Additional headers for this request.
        timeout: Request timeout in seconds.
        **kwargs: Additional arguments passed to httpx.

    Returns:
        httpx.Response: The HTTP response.

    Raises:
        HTTPError: If the request fails.

    Example:
        >>> response = patch(
        ...     client, context, "/api/users/1",
        ...     json={"status": "active"}
        ... )
        >>> assert response.status_code == 200
    """
    base_url = _get_base_url(client, context)
    url = _build_url(base_url, path)
    request_headers = _get_headers(client, context)
    if headers:
        request_headers.update(headers)

    http_client = getattr(client, "http_client", None) or httpx.Client(timeout=timeout)

    try:
        response = http_client.patch(
            url, json=json, data=data, params=params, headers=request_headers, **kwargs
        )
        context.last_response = response
        return response
    except httpx.HTTPError as e:
        raise HTTPError(f"PATCH request failed: {url}") from e


def delete(
    client: Client,
    context: Context,
    path: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    **kwargs: Any,
) -> httpx.Response:
    """Perform an HTTP DELETE request.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        params: Query parameters.
        headers: Additional headers for this request.
        timeout: Request timeout in seconds.
        **kwargs: Additional arguments passed to httpx.

    Returns:
        httpx.Response: The HTTP response.

    Raises:
        HTTPError: If the request fails.

    Example:
        >>> response = delete(client, context, "/api/users/1")
        >>> assert response.status_code == 204
    """
    base_url = _get_base_url(client, context)
    url = _build_url(base_url, path)
    request_headers = _get_headers(client, context)
    if headers:
        request_headers.update(headers)

    http_client = getattr(client, "http_client", None) or httpx.Client(timeout=timeout)

    try:
        response = http_client.delete(url, params=params, headers=request_headers, **kwargs)
        context.last_response = response
        return response
    except httpx.HTTPError as e:
        raise HTTPError(f"DELETE request failed: {url}") from e


def head(
    client: Client,
    context: Context,
    path: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    **kwargs: Any,
) -> httpx.Response:
    """Perform an HTTP HEAD request.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        params: Query parameters.
        headers: Additional headers for this request.
        timeout: Request timeout in seconds.
        **kwargs: Additional arguments passed to httpx.

    Returns:
        httpx.Response: The HTTP response.

    Raises:
        HTTPError: If the request fails.

    Example:
        >>> response = head(client, context, "/api/users/1")
        >>> assert "content-length" in response.headers
    """
    base_url = _get_base_url(client, context)
    url = _build_url(base_url, path)
    request_headers = _get_headers(client, context)
    if headers:
        request_headers.update(headers)

    http_client = getattr(client, "http_client", None) or httpx.Client(timeout=timeout)

    try:
        response = http_client.head(url, params=params, headers=request_headers, **kwargs)
        context.last_response = response
        return response
    except httpx.HTTPError as e:
        raise HTTPError(f"HEAD request failed: {url}") from e


def options(
    client: Client,
    context: Context,
    path: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    **kwargs: Any,
) -> httpx.Response:
    """Perform an HTTP OPTIONS request.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        params: Query parameters.
        headers: Additional headers for this request.
        timeout: Request timeout in seconds.
        **kwargs: Additional arguments passed to httpx.

    Returns:
        httpx.Response: The HTTP response.

    Raises:
        HTTPError: If the request fails.

    Example:
        >>> response = options(client, context, "/api/users")
        >>> allowed = response.headers.get("allow", "").split(", ")
    """
    base_url = _get_base_url(client, context)
    url = _build_url(base_url, path)
    request_headers = _get_headers(client, context)
    if headers:
        request_headers.update(headers)

    http_client = getattr(client, "http_client", None) or httpx.Client(timeout=timeout)

    try:
        response = http_client.options(url, params=params, headers=request_headers, **kwargs)
        context.last_response = response
        return response
    except httpx.HTTPError as e:
        raise HTTPError(f"OPTIONS request failed: {url}") from e


def graphql_query(
    client: Client,
    context: Context,
    query: str,
    variables: dict[str, Any] | None = None,
    operation_name: str | None = None,
    endpoint: str = "/graphql",
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Execute a GraphQL query.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        query: GraphQL query string.
        variables: Variables for the GraphQL query.
        operation_name: Name of the operation to execute.
        endpoint: GraphQL endpoint path.
        headers: Additional headers for this request.
        timeout: Request timeout in seconds.

    Returns:
        dict: GraphQL response data.

    Raises:
        GraphQL_Error: If the query fails or contains errors.

    Example:
        >>> result = graphql_query(
        ...     client, context,
        ...     query='''
        ...         query GetUser($id: ID!) {
        ...             user(id: $id) { name email }
        ...         }
        ...     ''',
        ...     variables={"id": "1"}
        ... )
        >>> assert result["user"]["name"] == "John"
    """
    base_url = _get_base_url(client, context)
    url = _build_url(base_url, endpoint)
    request_headers = _get_headers(client, context)
    request_headers.setdefault("Content-Type", "application/json")
    if headers:
        request_headers.update(headers)

    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables
    if operation_name:
        payload["operationName"] = operation_name

    http_client = getattr(client, "http_client", None) or httpx.Client(timeout=timeout)

    try:
        response = http_client.post(url, json=payload, headers=request_headers)
        context.last_response = response
        result = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as e:
        raise GraphQL_Error(f"GraphQL request failed: {url}") from e

    if "errors" in result:
        errors = result["errors"]
        raise GraphQL_Error(f"GraphQL query returned errors: {errors}")

    return result.get("data", {})


def graphql_mutation(
    client: Client,
    context: Context,
    mutation: str,
    variables: dict[str, Any] | None = None,
    operation_name: str | None = None,
    endpoint: str = "/graphql",
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Execute a GraphQL mutation.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        mutation: GraphQL mutation string.
        variables: Variables for the GraphQL mutation.
        operation_name: Name of the operation to execute.
        endpoint: GraphQL endpoint path.
        headers: Additional headers for this request.
        timeout: Request timeout in seconds.

    Returns:
        dict: GraphQL response data.

    Raises:
        GraphQL_Error: If the mutation fails or contains errors.

    Example:
        >>> result = graphql_mutation(
        ...     client, context,
        ...     mutation='''
        ...         mutation CreateUser($input: CreateUserInput!) {
        ...             createUser(input: $input) { id name }
        ...         }
        ...     ''',
        ...     variables={"input": {"name": "John", "email": "john@example.com"}}
        ... )
    """
    return graphql_query(
        client=client,
        context=context,
        query=mutation,
        variables=variables,
        operation_name=operation_name,
        endpoint=endpoint,
        headers=headers,
        timeout=timeout,
    )


class WebSocketConnection:
    """WebSocket connection wrapper for testing."""

    def __init__(self, url: str, headers: dict[str, str] | None = None):
        self.url = url
        self.headers = headers or {}
        self._ws: Any = None
        self._messages: list[str | bytes] = []
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def messages(self) -> list[str | bytes]:
        return self._messages.copy()

    async def connect_async(self) -> None:
        """Connect to WebSocket asynchronously."""
        try:
            import websockets

            self._ws = await websockets.connect(self.url, extra_headers=self.headers)
            self._connected = True
        except ImportError:
            raise WebSocketError(
                "websockets library not installed. Install with: pip install websockets"
            ) from None
        except Exception as e:
            raise WebSocketError(f"Failed to connect to WebSocket: {self.url}") from e

    async def send_async(self, message: str | dict) -> None:
        """Send a message asynchronously."""
        if not self._ws or not self._connected:
            raise WebSocketError("WebSocket not connected")

        try:
            if isinstance(message, dict):
                message = json.dumps(message)
            await self._ws.send(message)
        except Exception as e:
            raise WebSocketError("Failed to send WebSocket message") from e

    async def receive_async(self, timeout: float = 10.0) -> str | bytes:
        """Receive a message asynchronously."""
        if not self._ws or not self._connected:
            raise WebSocketError("WebSocket not connected")

        try:
            import asyncio

            message = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            self._messages.append(message)
            return message
        except asyncio.TimeoutError:
            raise WebSocketError(f"WebSocket receive timeout after {timeout}s") from None
        except Exception as e:
            raise WebSocketError("Failed to receive WebSocket message") from e

    async def close_async(self) -> None:
        """Close the WebSocket connection."""
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._connected = False
        self._ws = None


def websocket_connect(
    client: Client,
    context: Context,
    url: str,
    headers: dict[str, str] | None = None,
) -> WebSocketConnection:
    """Connect to a WebSocket endpoint.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        url: WebSocket URL (ws:// or wss://).
        headers: Additional headers for the connection.

    Returns:
        WebSocketConnection: The WebSocket connection wrapper.

    Raises:
        WebSocketError: If connection fails.

    Example:
        >>> ws = websocket_connect(client, context, "wss://api.example.com/ws")
        >>> ws.send({"type": "subscribe", "channel": "updates"})
    """
    base_url = _get_base_url(client, context)

    if not url.startswith("ws://") and not url.startswith("wss://"):
        if base_url.startswith("https://"):
            url = f"wss://{base_url[8:]}/{url.lstrip('/')}"
        elif base_url.startswith("http://"):
            url = f"ws://{base_url[7:]}/{url.lstrip('/')}"
        else:
            url = (
                _build_url(base_url, url).replace("http://", "ws://").replace("https://", "wss://")
            )

    request_headers = _get_headers(client, context)
    if headers:
        request_headers.update(headers)

    connection = WebSocketConnection(url, request_headers)

    if not hasattr(context, "_websocket_connections"):
        context._websocket_connections = []
    context._websocket_connections.append(connection)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(connection.connect_async())
        else:
            loop.run_until_complete(connection.connect_async())
    except RuntimeError:
        asyncio.run(connection.connect_async())

    return connection


def websocket_send(
    client: Client,
    context: Context,
    connection: WebSocketConnection | None,
    message: str | dict,
) -> None:
    """Send a message through a WebSocket connection.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        connection: WebSocket connection to use. If None, uses the last connection from context.
        message: Message to send (string or dict).

    Raises:
        WebSocketError: If send fails.

    Example:
        >>> ws = websocket_connect(client, context, "wss://api.example.com/ws")
        >>> websocket_send(client, context, ws, {"type": "ping"})
    """
    if connection is None:
        connections = getattr(context, "_websocket_connections", [])
        if not connections:
            raise WebSocketError("No WebSocket connections available")
        connection = connections[-1]

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(connection.send_async(message))
        else:
            loop.run_until_complete(connection.send_async(message))
    except RuntimeError:
        asyncio.run(connection.send_async(message))


def websocket_receive(
    client: Client,
    context: Context,
    connection: WebSocketConnection | None = None,
    timeout: float = 10.0,
) -> str | bytes:
    """Receive a message from a WebSocket connection.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        connection: WebSocket connection to use. If None, uses the last connection from context.
        timeout: Maximum time to wait for a message.

    Returns:
        str | bytes: The received message.

    Raises:
        WebSocketError: If receive fails or times out.

    Example:
        >>> ws = websocket_connect(client, context, "wss://api.example.com/ws")
        >>> response = websocket_receive(client, context, ws)
    """
    if connection is None:
        connections = getattr(context, "_websocket_connections", [])
        if not connections:
            raise WebSocketError("No WebSocket connections available")
        connection = connections[-1]

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            future = asyncio.ensure_future(connection.receive_async(timeout))
            return loop.run_until_complete(future)
        else:
            return loop.run_until_complete(connection.receive_async(timeout))
    except RuntimeError:
        return asyncio.run(connection.receive_async(timeout))


def websocket_close(
    client: Client,
    context: Context,
    connection: WebSocketConnection | None = None,
) -> None:
    """Close a WebSocket connection.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        connection: WebSocket connection to close. If None, closes the last connection from context.

    Example:
        >>> ws = websocket_connect(client, context, "wss://api.example.com/ws")
        >>> websocket_close(client, context, ws)
    """
    if connection is None:
        connections = getattr(context, "_websocket_connections", [])
        if connections:
            connection = connections.pop()
        else:
            return

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(connection.close_async())
        else:
            loop.run_until_complete(connection.close_async())
    except RuntimeError:
        asyncio.run(connection.close_async())


def request(
    client: Client,
    context: Context,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    json: Any = None,
    data: dict[str, Any] | bytes | None = None,
    timeout: float = 30.0,
    **kwargs: Any,
) -> httpx.Response:
    """Perform an HTTP request with any method.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        method: HTTP method (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, etc.).
        path: API endpoint path or full URL.
        params: Query parameters.
        headers: Additional headers for this request.
        json: JSON body for the request.
        data: Form data or raw body for the request.
        timeout: Request timeout in seconds.
        **kwargs: Additional arguments passed to httpx.

    Returns:
        httpx.Response: The HTTP response.

    Raises:
        HTTPError: If the request fails.

    Example:
        >>> response = request(client, context, "GET", "/api/users")
        >>> response = request(client, context, "CUSTOM_METHOD", "/api/action")
    """
    base_url = _get_base_url(client, context)
    url = _build_url(base_url, path)
    request_headers = _get_headers(client, context)
    if headers:
        request_headers.update(headers)

    http_client = getattr(client, "http_client", None) or httpx.Client(timeout=timeout)

    try:
        response = http_client.request(
            method=method.upper(),
            url=url,
            params=params,
            headers=request_headers,
            json=json,
            data=data,
            **kwargs,
        )
        context.last_response = response
        return response
    except httpx.HTTPError as e:
        raise HTTPError(f"{method.upper()} request failed: {url}") from e


def upload_file(
    client: Client,
    context: Context,
    path: str,
    file_path: str | None = None,
    file_content: bytes | None = None,
    file_name: str | None = None,
    field_name: str = "file",
    additional_data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    method: str = "POST",
) -> httpx.Response:
    """Upload a file via multipart/form-data.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        file_path: Path to file to upload (mutually exclusive with file_content).
        file_content: File content as bytes (mutually exclusive with file_path).
        file_name: Name of the file (required if using file_content).
        field_name: Form field name for the file (default: 'file').
        additional_data: Additional form fields to include.
        headers: Additional headers for this request.
        timeout: Request timeout in seconds.
        method: HTTP method (default: POST).

    Returns:
        httpx.Response: The HTTP response.

    Raises:
        HTTPError: If the request fails.
        ValueError: If neither file_path nor file_content is provided.

    Example:
        >>> # Upload from file path
        >>> response = upload_file(
        ...     client, context,
        ...     path="/api/upload",
        ...     file_path="/path/to/document.pdf"
        ... )
        >>>
        >>> # Upload from bytes
        >>> response = upload_file(
        ...     client, context,
        ...     path="/api/upload",
        ...     file_content=b"file content here",
        ...     file_name="data.txt"
        ... )
    """
    if file_path is None and file_content is None:
        raise ValueError("Either file_path or file_content must be provided")

    if file_path is not None:
        with open(file_path, "rb") as f:
            file_content = f.read()
        if file_name is None:
            file_name = file_path.split("/")[-1].split("\\")[-1]

    if file_content is None or file_name is None:
        raise ValueError("file_name is required when using file_content")

    base_url = _get_base_url(client, context)
    url = _build_url(base_url, path)
    request_headers = _get_headers(client, context)
    if headers:
        request_headers.update(headers)

    if "Content-Type" in request_headers:
        del request_headers["Content-Type"]

    files = {field_name: (file_name, file_content)}
    data = additional_data or {}

    http_client = getattr(client, "http_client", None) or httpx.Client(timeout=timeout)

    try:
        response = http_client.request(
            method=method,
            url=url,
            files=files,
            data=data,
            headers=request_headers,
        )
        context.last_response = response
        return response
    except httpx.HTTPError as e:
        raise HTTPError(f"File upload failed: {url}") from e


def download_file(
    client: Client,
    context: Context,
    path: str,
    output_path: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    chunk_size: int = 8192,
) -> dict[str, Any]:
    """Download a file from an endpoint.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        output_path: Path where the file should be saved.
        params: Query parameters.
        headers: Additional headers for this request.
        timeout: Request timeout in seconds.
        chunk_size: Size of chunks to read/write.

    Returns:
        dict: Download information with 'size', 'path', and 'content_type' keys.

    Raises:
        HTTPError: If the request fails.

    Example:
        >>> result = download_file(
        ...     client, context,
        ...     path="/api/reports/123/download",
        ...     output_path="/tmp/report.pdf"
        ... )
        >>> print(f"Downloaded {result['size']} bytes")
    """
    base_url = _get_base_url(client, context)
    url = _build_url(base_url, path)
    request_headers = _get_headers(client, context)
    if headers:
        request_headers.update(headers)

    http_client = getattr(client, "http_client", None) or httpx.Client(timeout=timeout)

    try:
        with http_client.stream("GET", url, params=params, headers=request_headers) as response:
            response.raise_for_status()
            context.last_response = response

            content_type = response.headers.get("Content-Type", "application/octet-stream")
            total_size = 0

            with open(output_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=chunk_size):
                    f.write(chunk)
                    total_size += len(chunk)

            return {
                "size": total_size,
                "path": output_path,
                "content_type": content_type,
            }
    except httpx.HTTPError as e:
        raise HTTPError(f"File download failed: {url}") from e


def follow_redirects(
    client: Client,
    context: Context,
    path: str,
    max_redirects: int = 10,
    **kwargs: Any,
) -> list[httpx.Response]:
    """Follow redirect chain and return all responses.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        max_redirects: Maximum number of redirects to follow.
        **kwargs: Additional arguments passed to GET request.

    Returns:
        list: List of responses in redirect chain.

    Raises:
        HTTPError: If the request fails.

    Example:
        >>> responses = follow_redirects(client, context, "/old-url")
        >>> for i, resp in enumerate(responses):
        ...     print(f"Step {i}: {resp.status_code} -> {resp.headers.get('Location', 'final')}")
    """
    base_url = _get_base_url(client, context)
    url = _build_url(base_url, path)
    request_headers = _get_headers(client, context)

    http_client = getattr(client, "http_client", None) or httpx.Client(
        timeout=kwargs.pop("timeout", 30.0),
        follow_redirects=False,
    )

    responses: list[httpx.Response] = []
    current_url = url
    redirect_count = 0

    while redirect_count <= max_redirects:
        try:
            response = http_client.get(current_url, headers=request_headers, **kwargs)
            responses.append(response)

            if 300 <= response.status_code < 400:
                location = response.headers.get("Location")
                if not location:
                    break

                if location.startswith("/"):
                    from urllib.parse import urlparse

                    parsed = urlparse(current_url)
                    current_url = f"{parsed.scheme}://{parsed.netloc}{location}"
                elif not location.startswith("http"):
                    from urllib.parse import urljoin

                    current_url = urljoin(current_url, location)
                else:
                    current_url = location

                redirect_count += 1
            else:
                break
        except httpx.HTTPError as e:
            raise HTTPError(f"Request failed during redirect chain: {current_url}") from e

    if responses:
        context.last_response = responses[-1]

    return responses


def get_response_size(response: httpx.Response) -> int:
    """Get the size of a response in bytes.

    Args:
        response: HTTP response.

    Returns:
        int: Size in bytes.

    Example:
        >>> response = get(client, context, "/api/data")
        >>> size = get_response_size(response)
        >>> print(f"Response size: {size} bytes")
    """
    content_length = response.headers.get("Content-Length")
    if content_length:
        return int(content_length)
    return len(response.content)


def is_json_response(response: httpx.Response) -> bool:
    """Check if response is JSON.

    Args:
        response: HTTP response.

    Returns:
        bool: True if response appears to be JSON.

    Example:
        >>> response = get(client, context, "/api/users")
        >>> if is_json_response(response):
        ...     data = response.json()
    """
    content_type = response.headers.get("Content-Type", "")
    return "json" in content_type.lower()


def get_json_or_none(response: httpx.Response) -> Any:
    """Safely get JSON from response, returning None on failure.

    Args:
        response: HTTP response.

    Returns:
        Any: Parsed JSON or None if parsing fails.

    Example:
        >>> response = get(client, context, "/api/data")
        >>> data = get_json_or_none(response)
        >>> if data:
        ...     print(data.get("status"))
    """
    try:
        return response.json()
    except (json.JSONDecodeError, Exception):
        return None
