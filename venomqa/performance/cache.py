"""Response caching layer with TTL and LRU eviction."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached response entry."""

    key: str
    value: Any
    created_at: float
    ttl_seconds: float
    hits: int = 0
    size_bytes: int = 0

    def is_expired(self) -> bool:
        return time.time() > self.created_at + self.ttl_seconds


class ResponseCache:
    """Thread-safe LRU cache with TTL-based expiration."""

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: float = 300.0,
        max_memory_bytes: int = 100 * 1024 * 1024,
    ) -> None:
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
        """Compute a cache key from request components."""
        key_data = {
            "method": method.upper(),
            "url": url,
            "headers": self._normalize_headers(headers),
            "body": self._serialize_body(body),
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        """Get a cached value by key."""
        with self._lock:
            if key not in self._cache:
                self._stats.misses += 1
                return None

            entry = self._cache[key]

            if entry.is_expired():
                self._remove_entry(key)
                self._stats.expirations += 1
                self._stats.misses += 1
                return None

            self._cache.move_to_end(key)
            entry.hits += 1
            self._stats.hits += 1
            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
    ) -> None:
        """Set a value in the cache."""
        with self._lock:
            if key in self._cache:
                self._remove_entry(key)

            entry = CacheEntry(
                key=key,
                value=value,
                created_at=time.time(),
                ttl_seconds=ttl if ttl is not None else self.default_ttl,
                size_bytes=self._estimate_size(value),
            )

            self._cache[key] = entry
            self._stats.memory_bytes += entry.size_bytes
            self._stats.sets += 1

            self._evict_if_needed()

    def delete(self, key: str) -> bool:
        """Delete a key from the cache."""
        with self._lock:
            if key in self._cache:
                self._remove_entry(key)
                return True
            return False

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._stats.memory_bytes = 0
            logger.info("Cache cleared")

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of removed entries."""
        with self._lock:
            expired_keys = [key for key, entry in self._cache.items() if entry.is_expired()]
            for key in expired_keys:
                self._remove_entry(key)
                self._stats.expirations += 1
            return len(expired_keys)

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        with self._lock:
            self._stats.entries = len(self._cache)
            self._stats.hit_rate = (
                self._stats.hits / (self._stats.hits + self._stats.misses)
                if (self._stats.hits + self._stats.misses) > 0
                else 0.0
            )
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                sets=self._stats.sets,
                evictions=self._stats.evictions,
                expirations=self._stats.expirations,
                entries=self._stats.entries,
                memory_bytes=self._stats.memory_bytes,
                hit_rate=self._stats.hit_rate,
            )

    def _remove_entry(self, key: str) -> None:
        """Remove an entry and update stats."""
        entry = self._cache.pop(key, None)
        if entry:
            self._stats.memory_bytes -= entry.size_bytes

    def _evict_if_needed(self) -> None:
        """Evict entries if limits exceeded."""
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

    def _normalize_headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        """Normalize headers for consistent caching."""
        if not headers:
            return {}
        skip_headers = {"authorization", "cookie", "user-agent", "date", "host"}
        return {k.lower(): v for k, v in headers.items() if k.lower() not in skip_headers}

    def _serialize_body(self, body: Any) -> str:
        """Serialize body for key computation."""
        if body is None:
            return ""
        if isinstance(body, (str, bytes)):
            return body.decode() if isinstance(body, bytes) else body
        try:
            return json.dumps(body, sort_keys=True, default=str)
        except (TypeError, ValueError):
            return str(body)

    def _estimate_size(self, value: Any) -> int:
        """Estimate memory size of a value in bytes."""
        try:
            return len(json.dumps(value, default=str))
        except Exception:
            return len(str(value))


@dataclass
class CacheStats:
    """Cache statistics."""

    hits: int = 0
    misses: int = 0
    sets: int = 0
    evictions: int = 0
    expirations: int = 0
    entries: int = 0
    memory_bytes: int = 0
    hit_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "entries": self.entries,
            "memory_mb": round(self.memory_bytes / (1024 * 1024), 2),
            "hit_rate": f"{self.hit_rate:.1%}",
        }


class CachedResponse:
    """Wrapper for cached HTTP responses."""

    def __init__(
        self,
        status_code: int,
        headers: dict[str, str],
        body: Any,
        from_cache: bool = True,
    ) -> None:
        self.status_code = status_code
        self.headers = headers
        self._body = body
        self.from_cache = from_cache
        self.is_error = status_code >= 400

    def json(self) -> Any:
        if isinstance(self._body, (dict, list)):
            return self._body
        if isinstance(self._body, str):
            return json.loads(self._body)
        return self._body

    @property
    def text(self) -> str:
        if isinstance(self._body, str):
            return self._body
        return json.dumps(self._body)

    def __repr__(self) -> str:
        return f"CachedResponse(status_code={self.status_code}, from_cache={self.from_cache})"
