"""VenomQA Adapters.

This module provides adapters for external systems.

Main adapters (recommended):
    - HttpClient: HTTP client for API testing
    - PostgresAdapter: PostgreSQL with savepoint/rollback
    - SQLiteAdapter: SQLite with checkpoint/rollback
    - MySQLAdapter: MySQL adapter
    - RedisAdapter: Redis cache adapter
    - MockQueue, MockMail, MockStorage, MockTime: In-memory mocks

Legacy adapters (backwards compatibility):
    - MockCacheAdapter, MockMailAdapter, MockQueueAdapter, etc.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable

# =============================================================================
# Legacy adapters (backwards compatibility)
# =============================================================================
# Real adapters (for integration tests - may require optional dependencies)
from venomqa.adapters.asyncio_concurrency import AsyncConcurrencyAdapter

# Mock adapters (always available - in-memory, for unit tests)
from venomqa.adapters.cache import CacheEntry, MockCacheAdapter
from venomqa.adapters.concurrency import ThreadConcurrencyAdapter
from venomqa.adapters.controllable_time import ControllableTimeAdapter
from venomqa.adapters.local_storage import LocalStorageAdapter
from venomqa.adapters.mail import MockMailAdapter
from venomqa.adapters.queue import MockQueueAdapter
from venomqa.adapters.real_time import RealTimeAdapter
from venomqa.adapters.smtp_mock import SMTPMockAdapter
from venomqa.adapters.storage import LocalFileAdapter, MockStorageAdapter
from venomqa.adapters.threading_concurrency import ThreadingConcurrencyAdapter
from venomqa.adapters.time import MockTimeAdapter, SystemTimeAdapter

# =============================================================================
# Main adapters (from v1) - the recommended imports
# =============================================================================
from venomqa.v1.adapters.http import HttpClient
from venomqa.v1.adapters.mock_mail import Email, MockMail
from venomqa.v1.adapters.mock_queue import Message, MockQueue
from venomqa.v1.adapters.mock_storage import MockStorage, StoredFile
from venomqa.v1.adapters.mock_time import MockTime
from venomqa.v1.adapters.mysql import MySQLAdapter
from venomqa.v1.adapters.postgres import PostgresAdapter
from venomqa.v1.adapters.redis import RedisAdapter
from venomqa.v1.adapters.sqlite import SQLiteAdapter
from venomqa.v1.adapters.wiremock import WireMockAdapter as V1WireMockAdapter

# Redis-dependent adapters
try:
    from venomqa.adapters.redis_cache import RedisCacheAdapter
    _HAS_REDIS_CACHE = True
except ImportError:
    RedisCacheAdapter = None  # type: ignore
    _HAS_REDIS_CACHE = False

try:
    from venomqa.adapters.redis_queue import RedisQueueAdapter
    _HAS_REDIS_QUEUE = True
except ImportError:
    RedisQueueAdapter = None  # type: ignore
    _HAS_REDIS_QUEUE = False

# Celery-dependent adapters
try:
    from venomqa.adapters.celery_queue import CeleryQueueAdapter
    _HAS_CELERY = True
except ImportError:
    CeleryQueueAdapter = None  # type: ignore
    _HAS_CELERY = False

# Elasticsearch-dependent adapters
try:
    from venomqa.adapters.elasticsearch import ElasticsearchAdapter
    _HAS_ELASTICSEARCH = True
except ImportError:
    ElasticsearchAdapter = None  # type: ignore
    _HAS_ELASTICSEARCH = False

# Boto3-dependent adapters
try:
    from venomqa.adapters.s3_storage import S3StorageAdapter
    _HAS_BOTO3 = True
except ImportError:
    S3StorageAdapter = None  # type: ignore
    _HAS_BOTO3 = False

# Requests-dependent adapters
try:
    from venomqa.adapters.mailhog import MailhogAdapter
    from venomqa.adapters.mailpit import MailpitAdapter
    from venomqa.adapters.wiremock import WireMockAdapter
    _HAS_REQUESTS = True
except ImportError:
    MailhogAdapter = None  # type: ignore
    MailpitAdapter = None  # type: ignore
    WireMockAdapter = None  # type: ignore
    _HAS_REQUESTS = False

_adapters: dict[str, type] = {}


def register_adapter(name: str) -> Callable[[type], type]:
    """Decorator to register an adapter class."""

    def decorator(cls: type) -> type:
        _adapters[name] = cls
        return cls

    return decorator


def get_adapter(name: str) -> type | None:
    """Get an adapter class by name."""
    return _adapters.get(name)


def register_adapter_class(name: str, cls: type) -> None:
    """Register an adapter class directly."""
    _adapters[name] = cls


def list_adapters() -> list[str]:
    """List all registered adapter names."""
    return list(_adapters.keys())


# =============================================================================
# Submodule aliasing: allow `from venomqa.adapters.http import HttpClient` etc.
# This maps venomqa.adapters.{name} -> venomqa.v1.adapters.{name}
# for submodules that only exist under v1/adapters/.
# =============================================================================

_V1_ADAPTER_SUBMODULES = [
    "http", "postgres", "sqlite", "mysql", "redis",
    "mock_mail", "mock_queue", "mock_storage", "mock_time",
    "mock_http_server", "resource_graph", "asgi", "protocol",
]

for _submod in _V1_ADAPTER_SUBMODULES:
    _v1_name = f"venomqa.v1.adapters.{_submod}"
    _alias_name = f"venomqa.adapters.{_submod}"
    if _alias_name not in sys.modules:
        try:
            _mod = importlib.import_module(_v1_name)
            sys.modules[_alias_name] = _mod
        except ImportError:
            pass


# Lazy imports for optional adapters (v1)
_original_getattr = None


def __getattr__(name: str):
    if name in ("ASGIAdapter", "SharedPostgresAdapter", "ASGIResponse"):
        from venomqa.v1.adapters.asgi import ASGIAdapter, ASGIResponse, SharedPostgresAdapter
        return {"ASGIAdapter": ASGIAdapter, "SharedPostgresAdapter": SharedPostgresAdapter, "ASGIResponse": ASGIResponse}[name]
    if name == "ProtocolAdapter":
        from venomqa.v1.adapters.protocol import ProtocolAdapter
        return ProtocolAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Main adapters (recommended)
    "HttpClient",
    "PostgresAdapter",
    "MySQLAdapter",
    "SQLiteAdapter",
    "RedisAdapter",
    "V1WireMockAdapter",
    "MockQueue",
    "Message",
    "MockMail",
    "Email",
    "MockStorage",
    "StoredFile",
    "MockTime",
    "ASGIAdapter",
    "SharedPostgresAdapter",
    # Registry
    "register_adapter",
    "get_adapter",
    "register_adapter_class",
    "list_adapters",
    # Legacy adapters
    "MockCacheAdapter",
    "CacheEntry",
    "MockMailAdapter",
    "MockQueueAdapter",
    "MockStorageAdapter",
    "LocalFileAdapter",
    "MockTimeAdapter",
    "SystemTimeAdapter",
    "ThreadConcurrencyAdapter",
    "LocalStorageAdapter",
    "ThreadingConcurrencyAdapter",
    "AsyncConcurrencyAdapter",
    "ControllableTimeAdapter",
    "RealTimeAdapter",
    "SMTPMockAdapter",
]

# Add optional adapters if their dependencies are available
if _HAS_REDIS_CACHE:
    __all__.append("RedisCacheAdapter")
if _HAS_REDIS_QUEUE:
    __all__.append("RedisQueueAdapter")
if _HAS_CELERY:
    __all__.append("CeleryQueueAdapter")
if _HAS_ELASTICSEARCH:
    __all__.append("ElasticsearchAdapter")
if _HAS_BOTO3:
    __all__.append("S3StorageAdapter")
if _HAS_REQUESTS:
    __all__.extend(["MailhogAdapter", "MailpitAdapter", "WireMockAdapter"])
