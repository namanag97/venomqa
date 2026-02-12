"""Adapters for VenomQA Ports.

This module provides concrete implementations of the Port interfaces
for various backend services commonly used in testing environments.

Available Adapters:
    - MailhogAdapter: MailHog email catcher integration
    - MailpitAdapter: Mailpit email catcher integration
    - RedisQueueAdapter: Redis-based job queue
    - CeleryQueueAdapter: Celery task queue integration
    - RedisCacheAdapter: Redis cache backend
    - ElasticsearchAdapter: Elasticsearch search engine
    - S3StorageAdapter: AWS S3 object storage
    - LocalStorageAdapter: Local filesystem storage
    - ThreadingConcurrencyAdapter: Thread-based concurrency
    - AsyncConcurrencyAdapter: Asyncio-based concurrency
    - ControllableTimeAdapter: Controllable time for testing
    - RealTimeAdapter: Real system time
    - WireMockAdapter: WireMock mock server
    - SMTPMockAdapter: SMTP mock server
"""

from __future__ import annotations

from collections.abc import Callable

from venomqa.adapters.asyncio_concurrency import AsyncConcurrencyAdapter
from venomqa.adapters.celery_queue import CeleryQueueAdapter
from venomqa.adapters.controllable_time import ControllableTimeAdapter
from venomqa.adapters.elasticsearch import ElasticsearchAdapter
from venomqa.adapters.local_storage import LocalStorageAdapter
from venomqa.adapters.mailhog import MailhogAdapter
from venomqa.adapters.mailpit import MailpitAdapter
from venomqa.adapters.real_time import RealTimeAdapter
from venomqa.adapters.redis_cache import RedisCacheAdapter
from venomqa.adapters.redis_queue import RedisQueueAdapter
from venomqa.adapters.s3_storage import S3StorageAdapter
from venomqa.adapters.smtp_mock import SMTPMockAdapter
from venomqa.adapters.threading_concurrency import ThreadingConcurrencyAdapter
from venomqa.adapters.wiremock import WireMockAdapter

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


__all__ = [
    "register_adapter",
    "get_adapter",
    "register_adapter_class",
    "list_adapters",
    "MailhogAdapter",
    "MailpitAdapter",
    "RedisQueueAdapter",
    "CeleryQueueAdapter",
    "RedisCacheAdapter",
    "ElasticsearchAdapter",
    "S3StorageAdapter",
    "LocalStorageAdapter",
    "ThreadingConcurrencyAdapter",
    "AsyncConcurrencyAdapter",
    "ControllableTimeAdapter",
    "RealTimeAdapter",
    "WireMockAdapter",
    "SMTPMockAdapter",
]
