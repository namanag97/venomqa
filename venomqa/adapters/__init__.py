"""Adapters for VenomQA Ports.

This module provides concrete implementations of the Port interfaces
for various backend services commonly used in testing environments.

Mock Adapters (for testing):
    - MockCacheAdapter: In-memory cache for unit tests
    - MockMailAdapter: In-memory email capture
    - MockQueueAdapter: In-memory job queue
    - MockStorageAdapter: In-memory object storage
    - MockTimeAdapter: Controllable time for deterministic tests
    - ThreadConcurrencyAdapter: Thread-based task execution

Real Adapters (for integration):
    - MailhogAdapter: MailHog email catcher integration
    - MailpitAdapter: Mailpit email catcher integration
    - RedisQueueAdapter: Redis-based job queue
    - CeleryQueueAdapter: Celery task queue integration
    - RedisCacheAdapter: Redis cache backend
    - ElasticsearchAdapter: Elasticsearch search engine
    - S3StorageAdapter: AWS S3 object storage
    - LocalStorageAdapter: Local filesystem storage
    - AsyncConcurrencyAdapter: Asyncio-based concurrency
    - ControllableTimeAdapter: Controllable time for testing
    - RealTimeAdapter: Real system time
    - WireMockAdapter: WireMock mock server
    - SMTPMockAdapter: SMTP mock server
"""

from __future__ import annotations

from collections.abc import Callable

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


# Build __all__ dynamically based on available adapters
__all__ = [
    "register_adapter",
    "get_adapter",
    "register_adapter_class",
    "list_adapters",
    # Mock adapters (always available)
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
