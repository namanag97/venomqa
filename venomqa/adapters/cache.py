"""Mock Cache adapter for testing.

This adapter provides an in-memory cache for testing purposes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from venomqa.ports.cache import CachePort, CacheStats


@dataclass
class MockCacheConfig:
    """Configuration for Mock Cache adapter."""

    default_ttl: int = 3600


class MockCacheAdapter(CachePort):
    """In-memory mock cache adapter for testing.

    Attributes:
        config: Configuration for the mock cache.
    """

    def __init__(self, default_ttl: int = 3600) -> None:
        self.config = MockCacheConfig(default_ttl=default_ttl)
        self._cache: dict[str, tuple[Any, float | None]] = {}
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            self._misses += 1
            return None
        value, expiry = self._cache[key]
        if expiry and time.time() > expiry:
            del self._cache[key]
            self._misses += 1
            return None
        self._hits += 1
        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        expiry = None
        if ttl:
            expiry = time.time() + ttl
        self._cache[key] = (value, expiry)
        return True

    def delete(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def exists(self, key: str) -> bool:
        if key not in self._cache:
            return False
        _, expiry = self._cache[key]
        if expiry and time.time() > expiry:
            del self._cache[key]
            return False
        return True

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        result = {}
        for key in keys:
            value = self.get(key)
            if value is not None:
                result[key] = value
        return result

    def set_many(self, mapping: dict[str, Any], ttl: int | None = None) -> bool:
        for key, value in mapping.items():
            self.set(key, value, ttl)
        return True

    def delete_many(self, keys: list[str]) -> int:
        count = 0
        for key in keys:
            if self.delete(key):
                count += 1
        return count

    def clear(self) -> bool:
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        return True

    def get_ttl(self, key: str) -> int | None:
        if key not in self._cache:
            return None
        _, expiry = self._cache[key]
        if expiry is None:
            return -1
        remaining = int(expiry - time.time())
        return max(0, remaining)

    def set_ttl(self, key: str, ttl: int) -> bool:
        if key not in self._cache:
            return False
        value, _ = self._cache[key]
        self._cache[key] = (value, time.time() + ttl if ttl else None)
        return True

    def get_stats(self) -> CacheStats:
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            hit_rate=hit_rate,
            size=len(self._cache),
            memory_usage=0,
            keys_count=len(self._cache),
        )

    def health_check(self) -> bool:
        return True
