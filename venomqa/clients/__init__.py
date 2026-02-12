"""VenomQA Protocol Clients Module.

This module provides specialized clients for various protocols:

- GraphQLClient: GraphQL query and subscription support
- WebSocketClient: Real-time WebSocket communication
- gRPCClient: gRPC service method invocation

All clients extend the BaseClient interface with common features:
- Request/response history tracking
- Authentication support
- Retry logic
- Proper type hints
"""

from venomqa.clients.base import (
    AuthCredentials,
    BaseAsyncClient,
    BaseClient,
    ClientRecord,
)
from venomqa.clients.graphql import (
    AsyncGraphQLClient,
    GraphQLClient,
    GraphQLError,
    GraphQLResponse,
    GraphQLSchema,
)
from venomqa.clients.grpc import (
    AsyncgRPCClient,
    ProtoMethod,
    ProtoService,
    gRPCClient,
    gRPCResponse,
)
from venomqa.clients.websocket import (
    AsyncWebSocketClient,
    ConnectionState,
    WebSocketClient,
    WebSocketMessage,
)

__all__ = [
    "BaseClient",
    "BaseAsyncClient",
    "ClientRecord",
    "AuthCredentials",
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
    "AsyncgRPCClient",
    "gRPCResponse",
    "ProtoMethod",
    "ProtoService",
]
