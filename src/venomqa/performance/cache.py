"""Response caching layer with TTL and LRU eviction.

This module provides a thread-safe, high-performance caching system for HTTP
responses with the following features:

- Time-to-live (TTL) based expiration
- Least Recently Used (LRU) eviction
- Memory-based eviction limits
- Comprehensive cache statistics
- Request key computation with header normalization

The cache is designed for use in API testing scenarios where identical requests
may be repeated frequently, allowing response reuse to speed up test execution.

Example:
    >>> cache = ResponseCache(max_size=1000, default_ttl=300.0)
    >>> key = cache.compute_key("GET", "https://api.example.com/users/1")
    >>> cache.set(key, {"id": 1, "name": "Alice"})
    >>> response = cache.get(key)
    >>> stats = cache.get_stats()
    >>> print(f"Hit rate: {stats.hit_rate:.1%}")
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached response entry with metadata.

    Represents a single cached item with its value, creation timestamp,
    TTL configuration, and access statistics.

    Attributes:
        key: Unique identifier for this cache entry.
        value: The cached data.
        created_at: Unix timestamp when entry was created.
        ttl_seconds: Time-to-live in seconds from creation.
        hits: Number of times this entry has been accessed.
        size_bytes: Estimated memory size in bytes.
        last_accessed: Unix timestamp of most recent access.
    """

    key: str
    value: Any
    created_at: float
    ttl_seconds: float
    hits: int = 0
    size_bytes: int = 0
    last_accessed: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if this entry has exceeded its TTL.

        Returns:
            True if current time exceeds created_at + ttl_seconds.
        """
        return time.time() > self.created_at + self.ttl_seconds

    @property
    def remaining_ttl(self) -> float:
        """Get remaining time-to-live in seconds.

        Returns:
            Seconds until expiration, or 0 if already expired.
        """
        remaining = (self.created_at + self.ttl_seconds) - time.time()
        return max(0.0, remaining)

    @property
    def age_seconds(self) -> float:
        """Get the age of this entry in seconds.

        Returns:
            Seconds since the entry was created.
        """
        return time.time() - self.created_at


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring.

    Tracks cache operations, memory usage, and hit rates for
    performance analysis and tuning.

    Attributes:
        hits: Number of successful cache lookups.
        misses: Number of failed cache lookups.
        sets: Number of entries stored.
        evictions: Number of entries removed due to size limits.
        expirations: Number of entries removed due to TTL.
        entries: Current number of cached entries.
        memory_bytes: Estimated memory usage in bytes.
        hit_rate: Ratio of hits to total lookups (0.0 to 1.0).
        total_wait_time_ms: Total time spent waiting for cache lock.
    """

    hits: int = 0
    misses: int = 0
    sets: int = 0
    evictions: int = 0
    expirations: int = 0
    entries: int = 0
    memory_bytes: int = 0
    hit_rate: float = 0.0
    total_wait_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to a dictionary for serialization.

        Returns:
            Dictionary with all statistics formatted for display.
        """
        return {
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "entries": self.entries,
            "memory_mb": round(self.memory_bytes / (1024 * 1024), 2),
            "hit_rate": f"{self.hit_rate:.1%}",
            "avg_wait_ms": round(self.total_wait_time_ms / max(1, self.hits + self.misses), 3),
        }


class ResponseCache:
    """Thread-safe LRU cache with TTL-based expiration.

    A production-ready cache implementation optimized for HTTP response caching
    with configurable size limits, memory limits, and TTL support.

    The cache uses OrderedDict for O(1) LRU eviction and RLock for thread safety.
    Entries are automatically evicted when size or memory limits are exceeded,
    or when they exceed their configured TTL.

    Attributes:
        max_size: Maximum number of entries to cache.
        default_ttl: Default TTL in seconds for entries without explicit TTL.
        max_memory_bytes: Maximum memory usage in bytes.

    Example:
        >>> cache = ResponseCache(max_size=500, default_ttl=60.0)
        >>> key = cache.compute_key("GET", "/api/users", {"Accept": "application/json"})
        >>> cache.set(key, {"users": []}, ttl=120.0)
        >>> data = cache.get(key)
        >>> if data is None:
        ...     # Cache miss - fetch fresh data
        ...     pass
        >>> cache.cleanup_expired()  # Manual cleanup
    """

    SKIP_HEADERS: frozenset[str] = frozenset(
        {
            "authorization",
            "cookie",
            "user-agent",
            "date",
            "host",
            "x-request-id",
            "x-correlation-id",
        }
    )

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: float = 300.0,
        max_memory_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        """Initialize the response cache.

        Args:
            max_size: Maximum number of entries. Defaults to 1000.
            default_ttl: Default TTL in seconds. Defaults to 300 (5 minutes).
            max_memory_bytes: Maximum memory in bytes. Defaults to 100MB.

        Raises:
            ValueError: If max_size or max_memory_bytes is <= 0.
        """
        if max_size <= 0:
            raise ValueError(f"max_size must be positive, got {max_size}")
        if max_memory_bytes <= 0:
            raise ValueError(f"max_memory_bytes must be positive, got {max_memory_bytes}")

        self.max_size = max_size
        self.default_ttl = default_ttl
        self.max_memory_bytes = max_memory_bytes
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = CacheStats()

    def compute_key(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: Any = None,
    ) -> str:
        """Compute a deterministic cache key from request components.

        Creates a SHA-256 hash of the normalized request data for use as
        a cache key. Headers are normalized (filtered, lowercased) to ensure
        equivalent requests produce identical keys.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Request URL.
            headers: Optional request headers.
            body: Optional request body.

        Returns:
            64-character hexadecimal SHA-256 hash string.

        Example:
            >>> key1 = cache.compute_key("GET", "https://api.example.com/users")
            >>> key2 = cache.compute_key("GET", "https://api.example.com/users")
            >>> assert key1 == key2
        """
        key_data = {
            "method": method.upper(),
            "url": url,
            "headers": self._normalize_headers(headers),
            "body": self._serialize_body(body),
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        """Get a cached value by key.

        Retrieves the cached value if it exists and hasn't expired.
        Updates access statistics and moves the entry to the end of
        the LRU order.

        Args:
            key: The cache key to look up.

        Returns:
            The cached value, or None if not found or expired.
        """
        start_time = time.perf_counter()

        with self._lock:
            wait_time = (time.perf_counter() - start_time) * 1000
            self._stats.total_wait_time_ms += wait_time

            if key not in self._cache:
                self._stats.misses += 1
                return None

            entry = self._cache[key]

            if entry.is_expired():
                self._remove_entry(key)
                self._stats.expirations += 1
                self._stats.misses += 1
                logger.debug("Cache entry expired: %s", key[:16])
                return None

            self._cache.move_to_end(key)
            entry.hits += 1
            entry.last_accessed = time.time()
            self._stats.hits += 1
            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
    ) -> None:
        """Store a value in the cache.

        If the key already exists, the old entry is replaced.
        Evicts entries if size or memory limits would be exceeded.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl: Optional TTL in seconds. Uses default_ttl if not specified.

        Example:
            >>> cache.set("user:1", {"id": 1, "name": "Alice"}, ttl=60.0)
        """
        effective_ttl = ttl if ttl is not None else self.default_ttl

        with self._lock:
            if key in self._cache:
                self._remove_entry(key)

            entry = CacheEntry(
                key=key,
                value=value,
                created_at=time.time(),
                ttl_seconds=effective_ttl,
                size_bytes=self._estimate_size(value),
            )

            self._cache[key] = entry
            self._stats.memory_bytes += entry.size_bytes
            self._stats.sets += 1

            self._evict_if_needed()

    def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: float | None = None,
    ) -> Any:
        """Get a cached value, or compute and cache it if missing.

        Atomic get-or-compute operation that avoids the thundering herd
        problem by computing values within the cache lock.

        Args:
            key: The cache key.
            factory: Callable that produces the value if not cached.
            ttl: Optional TTL in seconds.

        Returns:
            The cached or newly computed value.

        Example:
            >>> data = cache.get_or_set(
            ...     "users:list",
            ...     lambda: fetch_users_from_api(),
            ...     ttl=60.0
            ... )
        """
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if not entry.is_expired():
                    self._cache.move_to_end(key)
                    entry.hits += 1
                    self._stats.hits += 1
                    return entry.value

            value = factory()
            self.set(key, value, ttl)
            return value

    def delete(self, key: str) -> bool:
        """Delete a key from the cache.

        Args:
            key: The cache key to delete.

        Returns:
            True if the key existed and was deleted, False otherwise.
        """
        with self._lock:
            if key in self._cache:
                self._remove_entry(key)
                return True
            return False

    def clear(self) -> None:
        """Clear all cached entries.

        Removes all entries and resets memory tracking.
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats.memory_bytes = 0
            logger.info("Cache cleared (%d entries removed)", count)

    def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Scans the cache for entries past their TTL and removes them.

        Returns:
            Number of entries removed.
        """
        with self._lock:
            expired_keys = [key for key, entry in self._cache.items() if entry.is_expired()]
            for key in expired_keys:
                self._remove_entry(key)
                self._stats.expirations += 1

            if expired_keys:
                logger.debug("Cleaned up %d expired entries", len(expired_keys))
            return len(expired_keys)

    def get_stats(self) -> CacheStats:
        """Get cache performance statistics.

        Returns a snapshot of current cache metrics including hit rate,
        memory usage, and operation counts.

        Returns:
            CacheStats with current statistics.
        """
        with self._lock:
            self._stats.entries = len(self._cache)
            total_requests = self._stats.hits + self._stats.misses
            self._stats.hit_rate = self._stats.hits / total_requests if total_requests > 0 else 0.0
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                sets=self._stats.sets,
                evictions=self._stats.evictions,
                expirations=self._stats.expirations,
                entries=self._stats.entries,
                memory_bytes=self._stats.memory_bytes,
                hit_rate=self._stats.hit_rate,
                total_wait_time_ms=self._stats.total_wait_time_ms,
            )

    def get_entry_metadata(self, key: str) -> dict[str, Any] | None:
        """Get metadata about a cached entry without retrieving its value.

        Args:
            key: The cache key.

        Returns:
            Dictionary with entry metadata, or None if not found.
        """
        with self._lock:
            if key not in self._cache:
                return None
            entry = self._cache[key]
            return {
                "key": key,
                "ttl_seconds": entry.ttl_seconds,
                "remaining_ttl": entry.remaining_ttl,
                "age_seconds": entry.age_seconds,
                "hits": entry.hits,
                "size_bytes": entry.size_bytes,
                "is_expired": entry.is_expired(),
            }

    def _remove_entry(self, key: str) -> None:
        """Remove an entry and update memory stats.

        Args:
            key: The key of the entry to remove.
        """
        entry = self._cache.pop(key, None)
        if entry:
            self._stats.memory_bytes -= entry.size_bytes

    def _evict_if_needed(self) -> None:
        """Evict entries if limits are exceeded.

        First evicts by count (LRU), then by memory if still over limit.
        """
        while len(self._cache) > self.max_size:
            self._evict_oldest()

        while self._stats.memory_bytes > self.max_memory_bytes and self._cache:
            self._evict_oldest()

    def _evict_oldest(self) -> None:
        """Evict the oldest (least recently used) entry."""
        if not self._cache:
            return
        oldest_key = next(iter(self._cache))
        self._remove_entry(oldest_key)
        self._stats.evictions += 1
        logger.debug("Evicted LRU entry: %s", oldest_key[:16])

    def _normalize_headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        """Normalize headers for consistent cache keys.

        Filters out headers that vary per-request (like auth tokens)
        and lowercases remaining header names.

        Args:
            headers: Raw request headers.

        Returns:
            Normalized header dictionary.
        """
        if not headers:
            return {}
        return {k.lower(): v for k, v in headers.items() if k.lower() not in self.SKIP_HEADERS}

    def _serialize_body(self, body: Any) -> str:
        """Serialize request body for key computation.

        Converts body to a deterministic string representation.

        Args:
            body: Request body (any type).

        Returns:
            String representation of the body.
        """
        if body is None:
            return ""
        if isinstance(body, (str, bytes)):
            return body.decode() if isinstance(body, bytes) else body
        try:
            return json.dumps(body, sort_keys=True, default=str)
        except (TypeError, ValueError):
            return str(body)

    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of a value in bytes.

        Uses JSON serialization length as an approximation.
        For exact memory usage, consider using pympler or similar.

        Args:
            value: The value to estimate.

        Returns:
            Estimated size in bytes.
        """
        try:
            return len(json.dumps(value, default=str))
        except Exception:
            return len(str(value))

    def __len__(self) -> int:
        """Get the number of cached entries."""
        return len(self._cache)

    def __contains__(self, key: str) -> bool:
        """Check if a key exists in the cache (without checking expiration)."""
        return key in self._cache


class CachedResponse:
    """Wrapper for cached HTTP responses.

    Provides a response-like interface for cached data, mimicking
    common HTTP response attributes for transparent cache integration.

    Attributes:
        status_code: HTTP status code of the original response.
        headers: Response headers.
        from_cache: Always True for cached responses.
        is_error: True if status_code >= 400.

    Example:
        >>> cached = CachedResponse(200, {"Content-Type": "application/json"}, {"id": 1})
        >>> data = cached.json()
        >>> text = cached.text
    """

    def __init__(
        self,
        status_code: int,
        headers: dict[str, str],
        body: Any,
        from_cache: bool = True,
        cached_at: float | None = None,
    ) -> None:
        """Initialize a cached response wrapper.

        Args:
            status_code: HTTP status code.
            headers: Response headers dictionary.
            body: Response body (string, dict, or list).
            from_cache: Whether this response came from cache.
            cached_at: Unix timestamp when response was cached.
        """
        self.status_code = status_code
        self.headers = headers
        self._body = body
        self.from_cache = from_cache
        self.cached_at = cached_at or time.time()
        self.is_error = status_code >= 400

    def json(self) -> Any:
        """Parse the response body as JSON.

        Returns:
            Parsed JSON data (dict or list).

        Raises:
            json.JSONDecodeError: If body is not valid JSON.
        """
        if isinstance(self._body, (dict, list)):
            return self._body
        if isinstance(self._body, str):
            return json.loads(self._body)
        return self._body

    @property
    def text(self) -> str:
        """Get the response body as text.

        Returns:
            String representation of the body.
        """
        if isinstance(self._body, str):
            return self._body
        return json.dumps(self._body)

    @property
    def age_seconds(self) -> float:
        """Get the age of this cached response.

        Returns:
            Seconds since the response was cached.
        """
        return time.time() - self.cached_at

    def __repr__(self) -> str:
        """String representation of the cached response."""
        return (
            f"CachedResponse(status_code={self.status_code}, "
            f"from_cache={self.from_cache}, age={self.age_seconds:.1f}s)"
        )
