"""GraphQL client for VenomQA with query and subscription support.

This module provides GraphQL clients for testing GraphQL APIs, supporting
queries, mutations, and subscriptions over HTTP and WebSocket.

Classes:
    GraphQLError: Represents a GraphQL error from the server.
    GraphQLResponse: Represents a GraphQL response with data and errors.
    GraphQLSchema: Simplified schema information from introspection.
    GraphQLClient: Synchronous GraphQL client.
    AsyncGraphQLClient: Asynchronous GraphQL client with WebSocket subscriptions.

Example:
    >>> from venomqa.clients.graphql import GraphQLClient
    >>> client = GraphQLClient("https://api.example.com/graphql")
    >>> client.connect()
    >>> response = client.execute("{ users { id name } }")
    >>> print(response.data)
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator, Callable, Generator
from dataclasses import dataclass, field
from typing import Any

import httpx

from venomqa.http.base import (
    BaseAsyncClient,
    BaseClient,
    ValidationError,
    _validate_endpoint,
)
from venomqa.errors import ConnectionError, RequestFailedError, RequestTimeoutError

logger = logging.getLogger(__name__)


def _validate_graphql_query(query: str) -> str:
    """Validate a GraphQL query string.

    Args:
        query: The GraphQL query string.

    Returns:
        Validated query string.

    Raises:
        ValidationError: If query is empty or invalid.
    """
    if not query:
        raise ValidationError(
            "GraphQL query cannot be empty",
            field_name="query",
            value=query,
        )

    query = query.strip()
    if not query:
        raise ValidationError(
            "GraphQL query cannot be whitespace only",
            field_name="query",
            value=query,
        )

    return query


@dataclass
class GraphQLError:
    """Represents a GraphQL error from the server.

    GraphQL errors contain a message and optional location/path information
    for debugging.

    Attributes:
        message: The error message.
        locations: List of line/column locations in the query.
        path: Path to the field that caused the error.
        extensions: Additional error metadata from the server.

    Example:
        >>> error = GraphQLError(
        ...     message="Cannot query field 'invalid' on type 'Query'",
        ...     locations=[{"line": 1, "column": 3}],
        ... )
        >>> str(error)
        "Cannot query field 'invalid' on type 'Query' at line 1 col 3"
    """

    message: str
    locations: list[dict[str, int]] | None = None
    path: list[str | int] | None = None
    extensions: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphQLError:
        """Create GraphQLError from a dictionary.

        Args:
            data: Dictionary containing error data.

        Returns:
            GraphQLError instance.
        """
        return cls(
            message=data.get("message", "Unknown error"),
            locations=data.get("locations"),
            path=data.get("path"),
            extensions=data.get("extensions"),
        )

    def __str__(self) -> str:
        """Get formatted error string."""
        parts = [self.message]
        if self.locations:
            locs = ", ".join(
                f"line {loc.get('line')} col {loc.get('column')}" for loc in self.locations
            )
            parts.append(f"at {locs}")
        if self.path:
            parts.append(f"path: {'.'.join(str(p) for p in self.path)}")
        return " | ".join(parts)

    def __repr__(self) -> str:
        return f"GraphQLError(message={self.message!r})"


@dataclass
class GraphQLResponse:
    """Represents a GraphQL response with data and errors.

    Attributes:
        data: The response data (may be None if errors occurred).
        errors: List of GraphQL errors if any occurred.
        extensions: Response extensions from the server.
        status_code: HTTP status code.
        duration_ms: Response time in milliseconds.

    Example:
        >>> response = GraphQLResponse(
        ...     data={"users": [{"id": 1, "name": "Alice"}]},
        ...     status_code=200,
        ...     duration_ms=45.2,
        ... )
        >>> if response.successful:
        ...     print(response.get_data("users.0.name"))
        'Alice'
    """

    data: dict[str, Any] | None = None
    errors: list[GraphQLError] = field(default_factory=list)
    extensions: dict[str, Any] | None = None
    status_code: int = 200
    duration_ms: float = 0.0

    @property
    def has_errors(self) -> bool:
        """Check if response contains errors.

        Returns:
            True if errors list is non-empty.
        """
        return len(self.errors) > 0

    @property
    def successful(self) -> bool:
        """Check if response indicates success.

        Returns:
            True if no errors and data is present.
        """
        return not self.has_errors and self.data is not None

    def raise_for_errors(self) -> None:
        """Raise exception if response contains errors.

        Raises:
            RequestFailedError: If errors are present.
        """
        if self.has_errors:
            error_messages = [str(e) for e in self.errors]
            raise RequestFailedError(
                message=f"GraphQL errors: {'; '.join(error_messages)}",
                status_code=self.status_code,
            )

    def get_data(self, path: str | None = None) -> Any:
        """Get data optionally navigating a path.

        Args:
            path: Dot-separated path to navigate (e.g., "users.0.name").

        Returns:
            Data at the path, or None if path doesn't exist.

        Example:
            >>> response.get_data("users.0.id")
            1
        """
        if self.data is None:
            return None
        if path is None:
            return self.data
        result = self.data
        for key in path.split("."):
            if isinstance(result, dict):
                result = result.get(key)
            elif isinstance(result, list) and key.isdigit():
                idx = int(key)
                if 0 <= idx < len(result):
                    result = result[idx]
                else:
                    return None
            else:
                return None
        return result


@dataclass
class GraphQLSchema:
    """Simplified schema information from introspection.

    Attributes:
        types: Dictionary of type name to type information.
        query_type: Name of the Query type.
        mutation_type: Name of the Mutation type (optional).
        subscription_type: Name of the Subscription type (optional).
    """

    types: dict[str, dict[str, Any]] = field(default_factory=dict)
    query_type: str | None = None
    mutation_type: str | None = None
    subscription_type: str | None = None

    def get_type(self, type_name: str) -> dict[str, Any] | None:
        """Get type information by name.

        Args:
            type_name: Name of the GraphQL type.

        Returns:
            Type information dictionary or None.
        """
        return self.types.get(type_name)

    def get_field_names(self, type_name: str) -> list[str]:
        """Get field names for a type.

        Args:
            type_name: Name of the GraphQL type.

        Returns:
            List of field names.
        """
        type_info = self.types.get(type_name, {})
        fields = type_info.get("fields", [])
        return [f.get("name") for f in fields if f.get("name")]


INTROSPECTION_QUERY = """
query IntrospectionQuery {
    __schema {
        queryType { name }
        mutationType { name }
        subscriptionType { name }
        types {
            ...FullType
        }
    }
}
fragment FullType on __Type {
    kind
    name
    description
    fields(includeDeprecated: true) {
        name
        description
        args {
            ...InputValue
        }
        type {
            ...TypeRef
        }
        isDeprecated
        deprecationReason
    }
    inputFields {
        ...InputValue
    }
    interfaces {
        ...TypeRef
    }
    enumValues(includeDeprecated: true) {
        name
        description
        isDeprecated
        deprecationReason
    }
    possibleTypes {
        ...TypeRef
    }
}
fragment InputValue on __InputValue {
    name
    description
    type {
        ...TypeRef
    }
    defaultValue
}
fragment TypeRef on __Type {
    kind
    name
    ofType {
        kind
        name
        ofType {
            kind
            name
            ofType {
                kind
                name
            }
        }
    }
}
"""


class GraphQLClient(BaseClient[GraphQLResponse]):
    """Synchronous GraphQL client with query, mutation, and subscription support.

    Provides comprehensive GraphQL functionality including:
    - Query and mutation execution
    - Schema introspection
    - Request history tracking
    - Authentication support

    Example:
        >>> from venomqa.clients.graphql import GraphQLClient
        >>> client = GraphQLClient("https://api.example.com/graphql")
        >>> client.connect()
        >>> response = client.query("{ users { id name } }")
        >>> print(response.data)
        >>> client.disconnect()

    Attributes:
        _schema: Cached schema from introspection.
    """

    def __init__(
        self,
        endpoint: str,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """Initialize the GraphQL client.

        Args:
            endpoint: GraphQL endpoint URL.
            timeout: Request timeout in seconds (default: 30.0).
            default_headers: Headers for all requests (default: None).
            retry_count: Maximum retry attempts (default: 3).
            retry_delay: Base retry delay in seconds (default: 1.0).

        Raises:
            ValidationError: If parameters are invalid.
        """
        validated_endpoint = _validate_endpoint(endpoint, protocols=["http", "https"])
        super().__init__(validated_endpoint, timeout, default_headers, retry_count, retry_delay)
        self._client: httpx.Client | None = None
        self._ws_client: httpx.Client | None = None
        self._schema: GraphQLSchema | None = None

    def connect(self) -> None:
        """Initialize the HTTP client.

        Creates an httpx.Client configured for GraphQL requests.
        """
        headers = {"Content-Type": "application/json"}
        headers.update(self.default_headers)
        self._client = httpx.Client(
            base_url=self.endpoint,
            timeout=self.timeout,
            headers=headers,
        )
        self._connected = True
        logger.info(f"GraphQL client connected to {self.endpoint}")

    def disconnect(self) -> None:
        """Close the HTTP client and clean up resources."""
        if self._client:
            self._client.close()
            self._client = None
        if self._ws_client:
            self._ws_client.close()
            self._ws_client = None
        self._connected = False

    def is_connected(self) -> bool:
        """Check if client is connected.

        Returns:
            True if HTTP client is initialized.
        """
        return self._connected and self._client is not None

    def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL query or mutation.

        Args:
            query: The GraphQL query string.
            variables: Variables for the query (optional).
            operation_name: Name of the operation to execute (optional).
            headers: Additional headers for this request (optional).

        Returns:
            GraphQLResponse with data and any errors.

        Raises:
            ValidationError: If query is empty.
            RequestTimeoutError: If request times out.
            ConnectionError: If connection fails.
        """
        self._ensure_connected()

        validated_query = _validate_graphql_query(query)

        request_headers = self.get_auth_header()
        if headers:
            request_headers.update(headers)

        payload: dict[str, Any] = {"query": validated_query}
        if variables:
            if not isinstance(variables, dict):
                raise ValidationError(
                    "Variables must be a dictionary",
                    field_name="variables",
                    value=type(variables).__name__,
                )
            payload["variables"] = variables
        if operation_name:
            if not isinstance(operation_name, str) or not operation_name.strip():
                raise ValidationError(
                    "Operation name must be a non-empty string",
                    field_name="operation_name",
                    value=operation_name,
                )
            payload["operationName"] = operation_name.strip()

        start_time = time.perf_counter()

        try:
            response = self._client.post(
                "",
                json=payload,
                headers=request_headers,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000

            return self._parse_response(response, duration_ms, payload)

        except httpx.TimeoutException as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_request(
                operation="execute",
                request_data=payload,
                response_data=None,
                duration_ms=duration_ms,
                error=str(e),
            )
            raise RequestTimeoutError(
                message=f"GraphQL request timed out after {self.timeout}s"
            ) from None

        except httpx.RequestError as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_request(
                operation="execute",
                request_data=payload,
                response_data=None,
                duration_ms=duration_ms,
                error=str(e),
            )
            raise ConnectionError(message=f"GraphQL request failed: {e}") from None

    def _parse_response(
        self, response: httpx.Response, duration_ms: float, request_data: dict[str, Any]
    ) -> GraphQLResponse:
        """Parse HTTP response into GraphQL response.

        Args:
            response: The httpx response.
            duration_ms: Request duration in milliseconds.
            request_data: The original request payload.

        Returns:
            GraphQLResponse with parsed data.
        """
        errors: list[GraphQLError] = []
        data: dict[str, Any] | None = None
        extensions: dict[str, Any] | None = None
        body = None

        try:
            body = response.json()
            if isinstance(body, dict):
                data = body.get("data")
                if body.get("errors"):
                    errors = [GraphQLError.from_dict(e) for e in body["errors"]]
                extensions = body.get("extensions")
        except json.JSONDecodeError:
            pass

        graphql_response = GraphQLResponse(
            data=data,
            errors=errors,
            extensions=extensions,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        self._record_request(
            operation="execute",
            request_data=request_data,
            response_data=body,
            duration_ms=duration_ms,
            metadata={"status_code": response.status_code},
            error="; ".join(str(e) for e in errors) if errors else None,
        )

        return graphql_response

    def query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL query.

        Alias for execute() for semantic clarity.

        Args:
            query: The GraphQL query string.
            variables: Variables for the query (optional).
            operation_name: Name of the operation (optional).

        Returns:
            GraphQLResponse with data and any errors.
        """
        return self.execute(query, variables, operation_name)

    def mutate(
        self,
        mutation: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL mutation.

        Alias for execute() for semantic clarity.

        Args:
            mutation: The GraphQL mutation string.
            variables: Variables for the mutation (optional).
            operation_name: Name of the operation (optional).

        Returns:
            GraphQLResponse with data and any errors.
        """
        return self.execute(mutation, variables, operation_name)

    def subscribe(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
        callback: Callable[[GraphQLResponse], None] | None = None,
        max_iterations: int | None = None,
    ) -> Generator[GraphQLResponse, None, None]:
        """Subscribe to a GraphQL subscription over HTTP polling.

        Note: This is a simplified implementation using HTTP polling.
        For true WebSocket subscriptions, use AsyncGraphQLClient.

        Args:
            query: The GraphQL subscription string.
            variables: Variables for the subscription (optional).
            operation_name: Name of the operation (optional).
            callback: Optional callback for each response.
            max_iterations: Maximum number of polling iterations (optional).

        Yields:
            GraphQLResponse for each poll iteration.
        """
        import uuid

        subscription_id = str(uuid.uuid4())[:8]
        logger.warning(
            f"Subscription {subscription_id}: Using HTTP polling mode. "
            "Use AsyncGraphQLClient for WebSocket subscriptions."
        )

        iteration = 0
        while max_iterations is None or iteration < max_iterations:
            response = self.execute(query, variables, operation_name)
            if callback:
                try:
                    callback(response)
                except Exception as e:
                    logger.error(f"Subscription callback error: {e}")
            yield response
            iteration += 1

    def introspect(self) -> GraphQLSchema:
        """Perform schema introspection.

        Queries the server's __schema to get type information.

        Returns:
            GraphQLSchema with type information.

        Raises:
            RequestFailedError: If introspection fails.
        """
        response = self.execute(INTROSPECTION_QUERY)
        response.raise_for_errors()

        schema_data = response.get_data("__schema")
        self._schema = GraphQLSchema()

        if schema_data:
            self._schema.query_type = schema_data.get("queryType", {}).get("name")
            self._schema.mutation_type = schema_data.get("mutationType", {}).get("name")
            self._schema.subscription_type = schema_data.get("subscriptionType", {}).get("name")

            for type_info in schema_data.get("types", []):
                type_name = type_info.get("name")
                if type_name:
                    self._schema.types[type_name] = type_info

        return self._schema

    def get_type(self, type_name: str) -> dict[str, Any] | None:
        """Get type information from schema.

        Performs introspection if schema is not cached.

        Args:
            type_name: Name of the GraphQL type.

        Returns:
            Type information dictionary or None.
        """
        if self._schema is None:
            self.introspect()
        return self._schema.types.get(type_name) if self._schema else None

    def get_query_fields(self) -> list[str]:
        """Get available query fields from schema.

        Returns:
            List of query field names.
        """
        if self._schema is None:
            self.introspect()
        if self._schema and self._schema.query_type:
            query_type = self._schema.types.get(self._schema.query_type, {})
            return [f.get("name") for f in query_type.get("fields", []) if f.get("name")]
        return []


class AsyncGraphQLClient(BaseAsyncClient[GraphQLResponse]):
    """Asynchronous GraphQL client with WebSocket subscription support.

    Provides the same functionality as GraphQLClient but with async/await
    support and true WebSocket-based subscriptions.

    Example:
        >>> from venomqa.clients.graphql import AsyncGraphQLClient
        >>> client = AsyncGraphQLClient("https://api.example.com/graphql")
        >>> await client.connect()
        >>> response = await client.query("{ users { id name } }")
        >>> print(response.data)
        >>> async for sub_response in client.subscribe("subscription { userCreated { id } }"):
        ...     print(sub_response.data)
    """

    def __init__(
        self,
        endpoint: str,
        ws_endpoint: str | None = None,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """Initialize the async GraphQL client.

        Args:
            endpoint: GraphQL HTTP endpoint URL.
            ws_endpoint: WebSocket endpoint for subscriptions (optional).
            timeout: Request timeout in seconds (default: 30.0).
            default_headers: Headers for all requests (default: None).
            retry_count: Maximum retry attempts (default: 3).
            retry_delay: Base retry delay in seconds (default: 1.0).

        Raises:
            ValidationError: If parameters are invalid.
        """
        validated_endpoint = _validate_endpoint(endpoint, protocols=["http", "https"])
        super().__init__(validated_endpoint, timeout, default_headers, retry_count, retry_delay)

        if ws_endpoint is not None:
            if not ws_endpoint.startswith(("ws://", "wss://")):
                raise ValidationError(
                    "WebSocket endpoint must start with ws:// or wss://",
                    field_name="ws_endpoint",
                    value=ws_endpoint,
                )

        self.ws_endpoint = ws_endpoint
        self._client: httpx.AsyncClient | None = None
        self._schema: GraphQLSchema | None = None

    async def connect(self) -> None:
        """Initialize the async HTTP client."""
        headers = {"Content-Type": "application/json"}
        headers.update(self.default_headers)
        self._client = httpx.AsyncClient(
            base_url=self.endpoint,
            timeout=self.timeout,
            headers=headers,
        )
        self._connected = True
        logger.info(f"Async GraphQL client connected to {self.endpoint}")

    async def disconnect(self) -> None:
        """Close the async HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False

    async def is_connected(self) -> bool:
        """Check if client is connected.

        Returns:
            True if HTTP client is initialized.
        """
        return self._connected and self._client is not None

    async def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL query or mutation asynchronously.

        Args:
            query: The GraphQL query string.
            variables: Variables for the query (optional).
            operation_name: Name of the operation to execute (optional).
            headers: Additional headers for this request (optional).

        Returns:
            GraphQLResponse with data and any errors.
        """
        if not self._connected:
            await self.connect()

        validated_query = _validate_graphql_query(query)

        request_headers = await self.get_auth_header()
        if headers:
            request_headers.update(headers)

        payload: dict[str, Any] = {"query": validated_query}
        if variables:
            if not isinstance(variables, dict):
                raise ValidationError(
                    "Variables must be a dictionary",
                    field_name="variables",
                    value=type(variables).__name__,
                )
            payload["variables"] = variables
        if operation_name:
            if not isinstance(operation_name, str) or not operation_name.strip():
                raise ValidationError(
                    "Operation name must be a non-empty string",
                    field_name="operation_name",
                    value=operation_name,
                )
            payload["operationName"] = operation_name.strip()

        start_time = time.perf_counter()

        try:
            response = await self._client.post(
                "",
                json=payload,
                headers=request_headers,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000

            return self._parse_response(response, duration_ms, payload)

        except httpx.TimeoutException as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_request(
                operation="execute",
                request_data=payload,
                response_data=None,
                duration_ms=duration_ms,
                error=str(e),
            )
            raise RequestTimeoutError(
                message=f"GraphQL request timed out after {self.timeout}s"
            ) from None

        except httpx.RequestError as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_request(
                operation="execute",
                request_data=payload,
                response_data=None,
                duration_ms=duration_ms,
                error=str(e),
            )
            raise ConnectionError(message=f"GraphQL request failed: {e}") from None

    def _parse_response(
        self, response: httpx.Response, duration_ms: float, request_data: dict[str, Any]
    ) -> GraphQLResponse:
        """Parse HTTP response into GraphQL response."""
        errors: list[GraphQLError] = []
        data: dict[str, Any] | None = None
        extensions: dict[str, Any] | None = None
        body = None

        try:
            body = response.json()
            if isinstance(body, dict):
                data = body.get("data")
                if body.get("errors"):
                    errors = [GraphQLError.from_dict(e) for e in body["errors"]]
                extensions = body.get("extensions")
        except json.JSONDecodeError:
            pass

        graphql_response = GraphQLResponse(
            data=data,
            errors=errors,
            extensions=extensions,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        self._record_request(
            operation="execute",
            request_data=request_data,
            response_data=body,
            duration_ms=duration_ms,
            metadata={"status_code": response.status_code},
            error="; ".join(str(e) for e in errors) if errors else None,
        )

        return graphql_response

    async def query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL query asynchronously.

        Args:
            query: The GraphQL query string.
            variables: Variables for the query (optional).
            operation_name: Name of the operation (optional).

        Returns:
            GraphQLResponse with data and any errors.
        """
        return await self.execute(query, variables, operation_name)

    async def mutate(
        self,
        mutation: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL mutation asynchronously.

        Args:
            mutation: The GraphQL mutation string.
            variables: Variables for the mutation (optional).
            operation_name: Name of the operation (optional).

        Returns:
            GraphQLResponse with data and any errors.
        """
        return await self.execute(mutation, variables, operation_name)

    async def subscribe(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> AsyncGenerator[GraphQLResponse, None]:
        """Subscribe to a GraphQL subscription over WebSocket.

        Establishes a WebSocket connection and yields responses as they arrive.

        Args:
            query: The GraphQL subscription string.
            variables: Variables for the subscription (optional).
            operation_name: Name of the operation (optional).

        Yields:
            GraphQLResponse for each subscription event.
        """
        import websockets

        validated_query = _validate_graphql_query(query)

        ws_url = self.ws_endpoint or self.endpoint.replace("http://", "ws://").replace(
            "https://", "wss://"
        )
        auth_header = await self.get_auth_header()
        headers = auth_header if auth_header else None

        connection_init = {"type": "connection_init", "payload": {}}
        subscribe_payload: dict[str, Any] = {"query": validated_query}
        if variables:
            subscribe_payload["variables"] = variables
        if operation_name:
            subscribe_payload["operationName"] = operation_name

        async with websockets.connect(ws_url, additional_headers=headers) as ws:
            await ws.send(json.dumps(connection_init))
            init_response = json.loads(await ws.recv())

            if init_response.get("type") != "connection_ack":
                raise ConnectionError(
                    message=f"Failed to establish WebSocket connection: {init_response}"
                )

            subscribe_msg = {
                "id": "1",
                "type": "start",
                "payload": subscribe_payload,
            }
            await ws.send(json.dumps(subscribe_msg))

            while True:
                message = json.loads(await ws.recv())
                msg_type = message.get("type")

                if msg_type == "data":
                    payload = message.get("payload", {})
                    response = GraphQLResponse(
                        data=payload.get("data"),
                        errors=[GraphQLError.from_dict(e) for e in payload.get("errors", [])],
                    )
                    self._record_request(
                        operation="subscribe",
                        request_data=subscribe_payload,
                        response_data=payload,
                        duration_ms=0,
                    )
                    yield response

                elif msg_type == "complete":
                    break

                elif msg_type == "error":
                    errors = [
                        GraphQLError.from_dict(e)
                        for e in message.get("payload", {}).get("errors", [])
                    ]
                    raise RequestFailedError(
                        message=f"Subscription error: {'; '.join(str(e) for e in errors)}"
                    )

    async def introspect(self) -> GraphQLSchema:
        """Perform schema introspection asynchronously.

        Returns:
            GraphQLSchema with type information.
        """
        response = await self.execute(INTROSPECTION_QUERY)
        response.raise_for_errors()

        schema_data = response.get_data("__schema")
        self._schema = GraphQLSchema()

        if schema_data:
            self._schema.query_type = schema_data.get("queryType", {}).get("name")
            self._schema.mutation_type = schema_data.get("mutationType", {}).get("name")
            self._schema.subscription_type = schema_data.get("subscriptionType", {}).get("name")

            for type_info in schema_data.get("types", []):
                type_name = type_info.get("name")
                if type_name:
                    self._schema.types[type_name] = type_info

        return self._schema

    async def get_type(self, type_name: str) -> dict[str, Any] | None:
        """Get type information from schema asynchronously.

        Args:
            type_name: Name of the GraphQL type.

        Returns:
            Type information dictionary or None.
        """
        if self._schema is None:
            await self.introspect()
        return self._schema.types.get(type_name) if self._schema else None

    async def get_query_fields(self) -> list[str]:
        """Get available query fields from schema.

        Returns:
            List of query field names.
        """
        if self._schema is None:
            await self.introspect()
        if self._schema and self._schema.query_type:
            query_type = self._schema.types.get(self._schema.query_type, {})
            return [f.get("name") for f in query_type.get("fields", []) if f.get("name")]
        return []
