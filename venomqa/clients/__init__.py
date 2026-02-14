"""VenomQA Protocol Clients Module.

.. deprecated::
    This module is deprecated. Import from `venomqa.http` instead::

        # Old (still works for backward compatibility):
        from venomqa.clients import GraphQLClient, gRPCClient

        # New (preferred):
        from venomqa.http import GraphQLClient, GrpcClient

This module provides specialized clients for various protocols:

- GraphQLClient: GraphQL query and subscription support
- WebSocketClient: Real-time WebSocket communication
- gRPCClient: gRPC service method invocation

Example:
    >>> from venomqa.http import GraphQLClient, GrpcClient, AsyncWebSocketClient
    >>>
    >>> # GraphQL
    >>> gql = GraphQLClient("https://api.example.com/graphql")
    >>> gql.connect()
    >>> response = gql.query("{ users { id name } }")
    >>>
    >>> # gRPC
    >>> grpc = GrpcClient("localhost:50051")
    >>> grpc.connect()
    >>> response = grpc.call("MyService", "MyMethod", request)
"""

# Re-export from new location for backward compatibility
from venomqa.http.base import (
    AuthCredentials,
    BaseAsyncClient,
    BaseClient,
    ClientError,
    ClientRecord,
    ValidationError,
)
from venomqa.http.graphql import (
    AsyncGraphQLClient,
    GraphQLClient,
    GraphQLError,
    GraphQLResponse,
    GraphQLSchema,
)
from venomqa.http.grpc import (
    AsyncgRPCClient,
    GrpcClient,
    GrpcResponse,
    ProtoMethod,
    ProtoService,
    gRPCClient,
    gRPCResponse,
)
from venomqa.http.websocket import (
    AsyncWebSocketClient,
    ConnectionState,
    WebSocketClient,
    WebSocketMessage,
)

__all__ = [
    "BaseClient",
    "BaseAsyncClient",
    "ClientRecord",
    "ClientError",
    "AuthCredentials",
    "ValidationError",
    "GraphQLClient",
    "AsyncGraphQLClient",
    "GraphQLError",
    "GraphQLResponse",
    "GraphQLSchema",
    "WebSocketClient",
    "AsyncWebSocketClient",
    "WebSocketMessage",
    "ConnectionState",
    "gRPCClient",
    "GrpcClient",
    "AsyncgRPCClient",
    "gRPCResponse",
    "GrpcResponse",
    "ProtoMethod",
    "ProtoService",
]
