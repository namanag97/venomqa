"""VenomQA HTTP Module - Unified HTTP and Protocol Clients.

This module consolidates all HTTP and protocol clients into a single import location:

- REST: Client, AsyncClient for HTTP/REST APIs
- GraphQL: GraphQLClient, AsyncGraphQLClient for GraphQL APIs
- gRPC: GrpcClient, AsyncgRPCClient for gRPC services
- WebSocket: WebSocketClient, AsyncWebSocketClient for real-time communication

Example:
    >>> from venomqa.http import Client, GraphQLClient
    >>>
    >>> # REST API
    >>> with Client("https://api.example.com") as client:
    ...     response = client.get("/users")
    >>>
    >>> # GraphQL API
    >>> with GraphQLClient("https://api.example.com/graphql") as gql:
    ...     response = gql.query("{ users { id name } }")
"""

# REST HTTP Client
# Base client classes
from venomqa.http.base import (
    AuthCredentials,
    BaseAsyncClient,
    BaseClient,
    ClientError,
    ClientRecord,
    ValidationError,
)

# GraphQL Client
from venomqa.http.graphql import (
    AsyncGraphQLClient,
    GraphQLClient,
    GraphQLError,
    GraphQLResponse,
    GraphQLSchema,
)

# gRPC Client
from venomqa.http.grpc import (
    AsyncgRPCClient,
    GrpcClient,
    GrpcResponse,
    ProtoMethod,
    ProtoService,
    gRPCClient,
    gRPCResponse,
)
from venomqa.http.rest import (
    AsyncClient,
    Client,
    ClientValidationError,
    RequestRecord,
    SecureCredentials,
)

# WebSocket Client
from venomqa.http.websocket import (
    AsyncWebSocketClient,
    ConnectionState,
    WebSocketClient,
    WebSocketMessage,
)

__all__ = [
    # REST
    "Client",
    "AsyncClient",
    "RequestRecord",
    "SecureCredentials",
    "ClientValidationError",
    # Base
    "BaseClient",
    "BaseAsyncClient",
    "ClientRecord",
    "ClientError",
    "AuthCredentials",
    "ValidationError",
    # GraphQL
    "GraphQLClient",
    "AsyncGraphQLClient",
    "GraphQLError",
    "GraphQLResponse",
    "GraphQLSchema",
    # gRPC
    "GrpcClient",
    "gRPCClient",
    "AsyncgRPCClient",
    "GrpcResponse",
    "gRPCResponse",
    "ProtoMethod",
    "ProtoService",
    # WebSocket
    "WebSocketClient",
    "AsyncWebSocketClient",
    "WebSocketMessage",
    "ConnectionState",
]
