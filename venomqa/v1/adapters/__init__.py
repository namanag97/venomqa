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

__all__ = [
    # HTTP
    "HttpClient",
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
