"""Adapters for external systems."""

from venomqa.v1.adapters.http import HttpClient
from venomqa.v1.adapters.mock_mail import Email, MockMail
from venomqa.v1.adapters.mock_queue import Message, MockQueue
from venomqa.v1.adapters.mock_storage import MockStorage, StoredFile
from venomqa.v1.adapters.mock_time import MockTime
from venomqa.v1.adapters.mysql import MySQLAdapter
from venomqa.v1.adapters.postgres import PostgresAdapter
from venomqa.v1.adapters.redis import RedisAdapter
from venomqa.v1.adapters.sqlite import SQLiteAdapter
from venomqa.v1.adapters.wiremock import WireMockAdapter


# Lazy imports for optional adapters
def __getattr__(name: str):
    if name in ("ASGIAdapter", "SharedPostgresAdapter", "ASGIResponse"):
        from venomqa.v1.adapters.asgi import ASGIAdapter, ASGIResponse, SharedPostgresAdapter
        return {"ASGIAdapter": ASGIAdapter, "SharedPostgresAdapter": SharedPostgresAdapter, "ASGIResponse": ASGIResponse}[name]
    if name == "ProtocolAdapter":
        from venomqa.v1.adapters.protocol import ProtocolAdapter
        return ProtocolAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # HTTP
    "HttpClient",
    # ASGI (in-process, for shared DB connection)
    "ASGIAdapter",
    "SharedPostgresAdapter",
    # Databases
    "PostgresAdapter",
    "MySQLAdapter",
    "SQLiteAdapter",
    # Cache
    "RedisAdapter",
    # External API mocking
    "WireMockAdapter",
    # Mock adapters
    "MockQueue",
    "Message",
    "MockMail",
    "Email",
    "MockStorage",
    "StoredFile",
    "MockTime",
]
