"""Mock Cache adapter for testing.

This adapter provides an in-memory cache for testing purposes.
It implements the CachePort interface with full TTL support and
statistics tracking.

Example:
    >>> from venomqa.adapters.cache import MockCacheAdapter
    >>> cache = MockCacheAdapter(default_ttl=3600)
    >>> cache.set("key", {"data": "value"}, ttl=60)
    >>> value = cache.get("key")
    >>> stats = cache.get_stats()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from venomqa.ports.cache import CachePort, CacheStats


class CacheKeyError(Exception):
    """Raised when cache key validation fails."""

    pass


class CacheValueError(Exception):
    """Raised when cache value validation fails."""

    pass


@dataclass
class MockCacheConfig:
    """Configuration for Mock Cache adapter.

    Attributes:
        default_ttl: Default time-to-live in seconds for cache entries.
        max_size: Maximum number of entries in the cache (0 = unlimited).
        validate_keys: Whether to validate key format.
    """

    default_ttl: int = 3600
    max_size: int = 0
    validate_keys: bool = True


@dataclass
class CacheEntry:
    """A cache entry with value, expiry, and metadata.

    Attributes:
        value: The cached value.
        expiry: Unix timestamp when the entry expires (None = no expiry).
        created_at: Unix timestamp when the entry was created.
        access_count: Number of times this entry has been accessed.
    """

    value: Any
    expiry: float | None = None
    created_at: float = field(default_factory=time.time)
    access_count: int = 0


class MockCacheAdapter(CachePort):
    """In-memory mock cache adapter for testing.

    This adapter provides a fully functional in-memory cache implementation
    for testing purposes. It supports TTL, statistics tracking, and can
    simulate unhealthy states for error handling tests.

    Attributes:
        config: Configuration for the mock cache.

    Example:
        >>> cache = MockCacheAdapter(default_ttl=3600)
        >>> cache.set("user:123", {"name": "John"})
        >>> user = cache.get("user:123")
        >>> print(user["name"])  # "John"
    """

    def __init__(
        self,
        default_ttl: int = 3600,
        max_size: int = 0,
        validate_keys: bool = True,
    ) -> None:
        """Initialize the Mock Cache adapter.

        Args:
            default_ttl: Default time-to-live in seconds for cache entries.
                Defaults to 3600 (1 hour).
            max_size: Maximum number of entries in the cache. 0 means unlimited.
                Defaults to 0.
            validate_keys: Whether to validate key format. Defaults to True.

        Raises:
            ValueError: If default_ttl is negative or max_size is negative.
        """
        if default_ttl < 0:
            raise ValueError("default_ttl must be non-negative")
        if max_size < 0:
            raise ValueError("max_size must be non-negative")

        self.config = MockCacheConfig(
            default_ttl=default_ttl,
            max_size=max_size,
            validate_keys=validate_keys,
        )
        self._cache: dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0
        self._healthy = True
        self._evictions = 0

    def _validate_key(self, key: str) -> None:
        """Validate a cache key.

        Args:
            key: The cache key to validate.

        Raises:
            CacheKeyError: If the key is empty or contains invalid characters.
        """
        if not self.config.validate_keys:
            return
        if not key:
            raise CacheKeyError("Cache key cannot be empty")
        if len(key) > 250:
            raise CacheKeyError("Cache key cannot exceed 250 characters")

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if a cache entry has expired.

        Args:
            entry: The cache entry to check.

        Returns:
            True if the entry has expired, False otherwise.
        """
        if entry.expiry is None:
            return False
        return time.time() > entry.expiry

    def _evict_if_needed(self) -> None:
        """Evict expired entries if max size is reached."""
        if self.config.max_size == 0:
            return
        if len(self._cache) < self.config.max_size:
            return

        expired_keys = [k for k, v in self._cache.items() if self._is_expired(v)]
        for key in expired_keys:
            del self._cache[key]
            self._evictions += 1

    def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Args:
            key: Cache key to retrieve.

        Returns:
            The cached value, or None if the key doesn't exist or has expired.

        Raises:
            CacheKeyError: If the key is invalid and validation is enabled.
        """
        self._validate_key(key)

        if key not in self._cache:
            self._misses += 1
            return None

        entry = self._cache[key]
        if self._is_expired(entry):
            del self._cache[key]
            self._misses += 1
            return None

        entry.access_count += 1
        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set a value in the cache.

        Args:
            key: Cache key to set.
            value: Value to cache.
            ttl: Time-to-live in seconds. If None, no expiry is set.
                A negative ttl means immediate expiration.
                A ttl of 0 means no expiry.

        Returns:
            True if the value was set successfully.

        Raises:
            CacheKeyError: If the key is invalid and validation is enabled.
        """
        self._validate_key(key)
        self._evict_if_needed()

        expiry = None
        if ttl is not None:
            if ttl < 0:
                expiry = time.time() - 1
            elif ttl > 0:
                expiry = time.time() + ttl

        self._cache[key] = CacheEntry(value=value, expiry=expiry)
        return True

    def delete(self, key: str) -> bool:
        """Delete a value from the cache.

        Args:
            key: Cache key to delete.

        Returns:
            True if the key was deleted, False if it didn't exist.

        Raises:
            CacheKeyError: If the key is invalid and validation is enabled.
        """
        self._validate_key(key)

        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def exists(self, key: str) -> bool:
        """Check if a key exists in the cache.

        Args:
            key: Cache key to check.

        Returns:
            True if the key exists and hasn't expired, False otherwise.

        Raises:
            CacheKeyError: If the key is invalid and validation is enabled.
        """
        self._validate_key(key)

        if key not in self._cache:
            return False

        entry = self._cache[key]
        if self._is_expired(entry):
            del self._cache[key]
            return False
        return True

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from the cache.

        Args:
            keys: List of cache keys to retrieve.

        Returns:
            Dictionary mapping found keys to their values.
            Keys that don't exist or have expired are not included.
        """
        result = {}
        for key in keys:
            value = self.get(key)
            if value is not None:
                result[key] = value
        return result

    def set_many(self, mapping: dict[str, Any], ttl: int | None = None) -> bool:
        """Set multiple values in the cache.

        Args:
            mapping: Dictionary of key-value pairs to set.
            ttl: Time-to-live in seconds for all keys.

        Returns:
            True if all values were set successfully.
        """
        for key, value in mapping.items():
            self.set(key, value, ttl)
        return True

    def delete_many(self, keys: list[str]) -> int:
        """Delete multiple values from the cache.

        Args:
            keys: List of cache keys to delete.

        Returns:
            Number of keys that were actually deleted.
        """
        count = 0
        for key in keys:
            if self.delete(key):
                count += 1
        return count

    def clear(self) -> bool:
        """Clear all values from the cache.

        This also resets hit/miss statistics.

        Returns:
            True if the cache was cleared successfully.
        """
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        return True

    def get_ttl(self, key: str) -> int | None:
        """Get the remaining TTL of a key.

        Args:
            key: Cache key to check.

        Returns:
            Remaining TTL in seconds, -1 if the key has no expiry,
            or None if the key doesn't exist.

        Raises:
            CacheKeyError: If the key is invalid and validation is enabled.
        """
        self._validate_key(key)

        if key not in self._cache:
            return None

        entry = self._cache[key]
        if entry.expiry is None:
            return -1

        if self._is_expired(entry):
            del self._cache[key]
            return None

        remaining = int(entry.expiry - time.time())
        return max(0, remaining)

    def set_ttl(self, key: str, ttl: int) -> bool:
        """Set the TTL for an existing key.

        Args:
            key: Cache key to update.
            ttl: New time-to-live in seconds. A ttl of 0 or negative
                removes the expiry.

        Returns:
            True if the TTL was updated, False if the key doesn't exist.

        Raises:
            CacheKeyError: If the key is invalid and validation is enabled.
        """
        self._validate_key(key)

        if key not in self._cache:
            return False

        entry = self._cache[key]
        if self._is_expired(entry):
            del self._cache[key]
            return False

        new_expiry = None
        if ttl > 0:
            new_expiry = time.time() + ttl

        self._cache[key] = CacheEntry(
            value=entry.value,
            expiry=new_expiry,
            created_at=entry.created_at,
            access_count=entry.access_count,
        )
        return True

    def get_stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            CacheStats object with hits, misses, hit_rate, size,
            memory_usage (always 0 for mock), and keys_count.
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total) if total > 0 else 0.0
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            hit_rate=hit_rate,
            size=len(self._cache),
            memory_usage=0,
            keys_count=len(self._cache),
        )

    def health_check(self) -> bool:
        """Check if the cache service is healthy.

        Returns:
            True if healthy, False if set_healthy(False) was called.
        """
        return self._healthy

    def set_healthy(self, healthy: bool) -> None:
        """Set the health status of the cache.

        Use this to simulate unhealthy cache states in tests.

        Args:
            healthy: True for healthy, False for unhealthy.
        """
        self._healthy = healthy

    def reset_stats(self) -> None:
        """Reset hit/miss statistics without clearing the cache."""
        self._hits = 0
        self._misses = 0

    def get_keys(self) -> list[str]:
        """Get all non-expired cache keys.

        Returns:
            List of all keys currently in the cache (excluding expired).
        """
        keys = []
        for key, entry in list(self._cache.items()):
            if self._is_expired(entry):
                del self._cache[key]
            else:
                keys.append(key)
        return keys

    def get_entry_count(self) -> int:
        """Get the number of entries in the cache.

        Returns:
            Number of non-expired entries.
        """
        return len(self.get_keys())

    def get_evictions(self) -> int:
        """Get the number of cache evictions.

        Returns:
            Number of entries that have been evicted due to expiry.
        """
        return self._evictions

    def increment(self, key: str, amount: int = 1) -> int:
        """Increment a numeric value in the cache.

        If the key doesn't exist, it's initialized to 0 before incrementing.

        Args:
            key: Cache key to increment.
            amount: Amount to increment by. Defaults to 1.

        Returns:
            The new value after incrementing.

        Raises:
            CacheKeyError: If the key is invalid and validation is enabled.
            CacheValueError: If the current value is not numeric.
        """
        self._validate_key(key)

        current = self.get(key)
        if current is None:
            current = 0
        elif not isinstance(current, (int, float)):
            raise CacheValueError(f"Cannot increment non-numeric value: {type(current)}")

        new_value = int(current) + amount
        self.set(key, new_value)
        return new_value

    def decrement(self, key: str, amount: int = 1) -> int:
        """Decrement a numeric value in the cache.

        If the key doesn't exist, it's initialized to 0 before decrementing.

        Args:
            key: Cache key to decrement.
            amount: Amount to decrement by. Defaults to 1.

        Returns:
            The new value after decrementing.

        Raises:
            CacheKeyError: If the key is invalid and validation is enabled.
            CacheValueError: If the current value is not numeric.
        """
        return self.increment(key, -amount)
