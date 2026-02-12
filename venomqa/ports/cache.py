"""Cache Port interface for VenomQA."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CacheEntry:
    """Represents a cache entry."""

    key: str
    value: Any
    ttl: int | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    tags: set[str] = field(default_factory=set)


@dataclass
class CacheStats:
    """Statistics for cache operations."""

    hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    size: int = 0
    memory_usage: int = 0
    keys_count: int = 0


class CachePort(ABC):
    """Abstract port for cache operations in QA testing.

    This port defines the interface for caching systems like
    Redis, Memcached, etc. Implementations should support
    basic cache operations with TTL and tagging.
    """

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Args:
            key: Cache key.

        Returns:
            Cached value or None if not found.
        """
        ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set a value in the cache.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Time to live in seconds.

        Returns:
            True if successful.
        """
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a value from the cache.

        Args:
            key: Cache key.

        Returns:
            True if deleted, False if not found.
        """
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if a key exists in the cache.

        Args:
            key: Cache key.

        Returns:
            True if exists, False otherwise.
        """
        ...

    @abstractmethod
    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from the cache.

        Args:
            keys: List of cache keys.

        Returns:
            Dictionary of key-value pairs found.
        """
        ...

    @abstractmethod
    def set_many(self, mapping: dict[str, Any], ttl: int | None = None) -> bool:
        """Set multiple values in the cache.

        Args:
            mapping: Dictionary of key-value pairs.
            ttl: Time to live in seconds for all keys.

        Returns:
            True if all successful.
        """
        ...

    @abstractmethod
    def delete_many(self, keys: list[str]) -> int:
        """Delete multiple values from the cache.

        Args:
            keys: List of cache keys.

        Returns:
            Number of keys deleted.
        """
        ...

    @abstractmethod
    def clear(self) -> bool:
        """Clear all values from the cache.

        Returns:
            True if successful.
        """
        ...

    @abstractmethod
    def get_ttl(self, key: str) -> int | None:
        """Get the remaining TTL of a key.

        Args:
            key: Cache key.

        Returns:
            Remaining TTL in seconds, -1 if no expiry, None if not found.
        """
        ...

    @abstractmethod
    def set_ttl(self, key: str, ttl: int) -> bool:
        """Set the TTL for an existing key.

        Args:
            key: Cache key.
            ttl: Time to live in seconds.

        Returns:
            True if successful.
        """
        ...

    @abstractmethod
    def get_stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            Cache statistics.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the cache service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        ...
