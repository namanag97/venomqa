"""GraphQL client for VenomQA with query and subscription support."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx

from venomqa.clients.base import BaseAsyncClient, BaseClient
from venomqa.errors import ConnectionError, RequestFailedError, RequestTimeoutError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


@dataclass
class GraphQLError:
    """Represents a GraphQL error."""

    message: str
    locations: list[dict[str, int]] | None = None
    path: list[str | int] | None = None
    extensions: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphQLError:
        return cls(
            message=data.get("message", "Unknown error"),
            locations=data.get("locations"),
            path=data.get("path"),
            extensions=data.get("extensions"),
        )

    def __str__(self) -> str:
        parts = [self.message]
        if self.locations:
            locs = ", ".join(
                f"line {loc.get('line')} col {loc.get('column')}" for loc in self.locations
            )
            parts.append(f"at {locs}")
        if self.path:
            parts.append(f"path: {'.'.join(str(p) for p in self.path)}")
        return " | ".join(parts)


@dataclass
class GraphQLResponse:
    """Represents a GraphQL response."""

    data: dict[str, Any] | None = None
    errors: list[GraphQLError] = field(default_factory=list)
    extensions: dict[str, Any] | None = None
    status_code: int = 200
    duration_ms: float = 0.0

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def successful(self) -> bool:
        return not self.has_errors and self.data is not None

    def raise_for_errors(self) -> None:
        """Raise exception if response contains errors."""
        if self.has_errors:
            error_messages = [str(e) for e in self.errors]
            raise RequestFailedError(
                message=f"GraphQL errors: {'; '.join(error_messages)}",
                status_code=self.status_code,
            )

    def get_data(self, path: str | None = None) -> Any:
        """Get data optionally navigating a path."""
        if self.data is None:
            return None
        if path is None:
            return self.data
        result = self.data
        for key in path.split("."):
            if isinstance(result, dict):
                result = result.get(key)
            else:
                return None
        return result


@dataclass
class GraphQLSchema:
    """Simplified schema information."""

    types: dict[str, dict[str, Any]] = field(default_factory=dict)
    query_type: str | None = None
    mutation_type: str | None = None
    subscription_type: str | None = None


class GraphQLClient(BaseClient[GraphQLResponse]):
    """GraphQL client with query, mutation, and subscription support."""

    def __init__(
        self,
        endpoint: str,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        super().__init__(endpoint, timeout, default_headers, retry_count, retry_delay)
        self._client: httpx.Client | None = None
        self._ws_client: httpx.Client | None = None
        self._schema: GraphQLSchema | None = None

    def connect(self) -> None:
        """Initialize the HTTP client."""
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
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None
        if self._ws_client:
            self._ws_client.close()
            self._ws_client = None
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL query or mutation."""
        self._ensure_connected()

        request_headers = self.get_auth_header()
        if headers:
            request_headers.update(headers)

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name

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
            raise RequestTimeoutError(message=f"GraphQL request timed out: {e}") from None

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

    def query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL query (alias for execute)."""
        return self.execute(query, variables, operation_name)

    def mutate(
        self,
        mutation: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL mutation (alias for execute)."""
        return self.execute(mutation, variables, operation_name)

    def subscribe(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
        callback: Callable[[GraphQLResponse], None] | None = None,
    ) -> Generator[GraphQLResponse, None, None]:
        """Subscribe to a GraphQL subscription over WebSocket.

        Note: This is a simplified implementation using HTTP polling.
        For true WebSocket subscriptions, use AsyncGraphQLClient.
        """
        import uuid

        subscription_id = str(uuid.uuid4())[:8]
        logger.warning(
            f"Subscription {subscription_id}: Using polling mode. "
            "Use AsyncGraphQLClient for WebSocket subscriptions."
        )

        while True:
            response = self.execute(query, variables, operation_name)
            if callback:
                callback(response)
            yield response

    def introspect(self) -> GraphQLSchema:
        """Perform schema introspection."""
        introspection_query = """
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

        response = self.execute(introspection_query)
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
        """Get type information from schema."""
        if self._schema is None:
            self.introspect()
        return self._schema.types.get(type_name) if self._schema else None

    def get_query_fields(self) -> list[str]:
        """Get available query fields from schema."""
        if self._schema is None:
            self.introspect()
        if self._schema and self._schema.query_type:
            query_type = self._schema.types.get(self._schema.query_type, {})
            return [f.get("name") for f in query_type.get("fields", [])]
        return []


class AsyncGraphQLClient(BaseAsyncClient[GraphQLResponse]):
    """Async GraphQL client with WebSocket subscription support."""

    def __init__(
        self,
        endpoint: str,
        ws_endpoint: str | None = None,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        super().__init__(endpoint, timeout, default_headers, retry_count, retry_delay)
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
        return self._connected and self._client is not None

    async def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL query or mutation."""
        if not self._connected:
            await self.connect()

        request_headers = self.get_auth_header()
        if headers:
            request_headers.update(headers)

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name

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
            raise RequestTimeoutError(message=f"GraphQL request timed out: {e}") from None

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
        """Execute a GraphQL query."""
        return await self.execute(query, variables, operation_name)

    async def mutate(
        self,
        mutation: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> GraphQLResponse:
        """Execute a GraphQL mutation."""
        return await self.execute(mutation, variables, operation_name)

    async def subscribe(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> AsyncGenerator[GraphQLResponse, None]:
        """Subscribe to a GraphQL subscription over WebSocket."""
        import websockets

        ws_url = self.ws_endpoint or self.endpoint.replace("http", "ws")
        headers = self.get_auth_header()

        connection_init = {"type": "connection_init", "payload": {}}
        subscribe_payload: dict[str, Any] = {"query": query}
        if variables:
            subscribe_payload["variables"] = variables
        if operation_name:
            subscribe_payload["operationName"] = operation_name

        async with websockets.connect(ws_url, extra_headers=headers) as ws:
            await ws.send(json.dumps(connection_init))
            init_response = json.loads(await ws.recv())

            if init_response.get("type") != "connection_ack":
                raise ConnectionError(message="Failed to establish WebSocket connection")

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
        """Perform schema introspection."""
        introspection_query = """
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

        response = await self.execute(introspection_query)
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
