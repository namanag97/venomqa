"""Redis Cache adapter for caching in testing.

Redis is an in-memory data structure store that can be used as a
cache, message broker, and more.

Installation:
    pip install redis

Example:
    >>> from venomqa.adapters import RedisCacheAdapter
    >>> adapter = RedisCacheAdapter(host="localhost", port=6379)
    >>> adapter.set("key", {"data": "value"}, ttl=60)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from redis import Redis

from venomqa.ports.cache import CachePort, CacheStats


@dataclass
class RedisCacheConfig:
    """Configuration for Redis Cache adapter."""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    prefix: str = "venomqa:"
    serializer: str = "json"
    default_ttl: int = 3600


class RedisCacheAdapter(CachePort):
    """Adapter for Redis cache.

    This adapter provides integration with Redis for caching
    in test environments.

    Attributes:
        config: Configuration for the Redis connection.

    Example:
        >>> adapter = RedisCacheAdapter()
        >>> adapter.set("user:123", {"name": "John"})
        >>> user = adapter.get("user:123")
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        prefix: str = "venomqa:",
        default_ttl: int = 3600,
    ) -> None:
        """Initialize the Redis Cache adapter.

        Args:
            host: Redis server hostname.
            port: Redis server port.
            db: Redis database number.
            password: Redis password if required.
            prefix: Key prefix for namespacing.
            default_ttl: Default TTL in seconds.
        """
        self.config = RedisCacheConfig(
            host=host,
            port=port,
            db=db,
            password=password,
            prefix=prefix,
            default_ttl=default_ttl,
        )
        self._redis = Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
        )
        self._redis_binary = Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=False,
        )

    def _make_key(self, key: str) -> str:
        """Create a prefixed key."""
        return f"{self.config.prefix}{key}"

    def _serialize(self, value: Any) -> str:
        """Serialize a value for storage."""
        return json.dumps(value)

    def _deserialize(self, value: str | None) -> Any:
        """Deserialize a value from storage."""
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Args:
            key: Cache key.

        Returns:
            Cached value or None if not found.
        """
        full_key = self._make_key(key)
        value = self._redis.get(full_key)
        return self._deserialize(value)

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set a value in the cache.

        Args:
            key: Cache key.
            value: Value to cache.
            ttl: Time to live in seconds.

        Returns:
            True if successful.
        """
        full_key = self._make_key(key)
        serialized = self._serialize(value)
        ttl = ttl or self.config.default_ttl

        if ttl > 0:
            return self._redis.setex(full_key, ttl, serialized)
        return self._redis.set(full_key, serialized)

    def delete(self, key: str) -> bool:
        """Delete a value from the cache.

        Args:
            key: Cache key.

        Returns:
            True if deleted, False if not found.
        """
        full_key = self._make_key(key)
        return bool(self._redis.delete(full_key))

    def exists(self, key: str) -> bool:
        """Check if a key exists in the cache.

        Args:
            key: Cache key.

        Returns:
            True if exists, False otherwise.
        """
        full_key = self._make_key(key)
        return bool(self._redis.exists(full_key))

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from the cache.

        Args:
            keys: List of cache keys.

        Returns:
            Dictionary of key-value pairs found.
        """
        if not keys:
            return {}

        full_keys = [self._make_key(k) for k in keys]
        values = self._redis.mget(full_keys)

        result = {}
        for key, value in zip(keys, values, strict=False):
            if value is not None:
                result[key] = self._deserialize(value)

        return result

    def set_many(self, mapping: dict[str, Any], ttl: int | None = None) -> bool:
        """Set multiple values in the cache.

        Args:
            mapping: Dictionary of key-value pairs.
            ttl: Time to live in seconds for all keys.

        Returns:
            True if all successful.
        """
        if not mapping:
            return True

        pipe = self._redis.pipeline()
        for key, value in mapping.items():
            full_key = self._make_key(key)
            serialized = self._serialize(value)
            if ttl and ttl > 0:
                pipe.setex(full_key, ttl, serialized)
            else:
                pipe.set(full_key, serialized)

        pipe.execute()
        return True

    def delete_many(self, keys: list[str]) -> int:
        """Delete multiple values from the cache.

        Args:
            keys: List of cache keys.

        Returns:
            Number of keys deleted.
        """
        if not keys:
            return 0

        full_keys = [self._make_key(k) for k in keys]
        return self._redis.delete(*full_keys)

    def clear(self) -> bool:
        """Clear all values from the cache.

        This only clears keys with the configured prefix.

        Returns:
            True if successful.
        """
        pattern = f"{self.config.prefix}*"
        keys = list(self._redis.scan_iter(pattern))
        if keys:
            self._redis.delete(*keys)
        return True

    def get_ttl(self, key: str) -> int | None:
        """Get the remaining TTL of a key.

        Args:
            key: Cache key.

        Returns:
            Remaining TTL in seconds, -1 if no expiry, None if not found.
        """
        full_key = self._make_key(key)
        ttl = self._redis.ttl(full_key)
        if ttl == -2:
            return None
        return ttl

    def set_ttl(self, key: str, ttl: int) -> bool:
        """Set the TTL for an existing key.

        Args:
            key: Cache key.
            ttl: Time to live in seconds.

        Returns:
            True if successful.
        """
        full_key = self._make_key(key)
        return bool(self._redis.expire(full_key, ttl))

    def get_stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            Cache statistics.
        """
        info = self._redis.info("memory")
        stats_info = self._redis.info("stats")

        hits = stats_info.get("keyspace_hits", 0)
        misses = stats_info.get("keyspace_misses", 0)
        total = hits + misses
        hit_rate = (hits / total * 100) if total > 0 else 0.0

        pattern = f"{self.config.prefix}*"
        keys_count = len(list(self._redis.scan_iter(pattern)))

        return CacheStats(
            hits=hits,
            misses=misses,
            hit_rate=hit_rate,
            size=0,
            memory_usage=info.get("used_memory", 0),
            keys_count=keys_count,
        )

    def health_check(self) -> bool:
        """Check if the cache service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            return self._redis.ping()
        except Exception:
            return False

    def increment(self, key: str, amount: int = 1) -> int:
        """Increment a counter.

        Args:
            key: Cache key.
            amount: Amount to increment by.

        Returns:
            New value after increment.
        """
        full_key = self._make_key(key)
        return self._redis.incrby(full_key, amount)

    def decrement(self, key: str, amount: int = 1) -> int:
        """Decrement a counter.

        Args:
            key: Cache key.
            amount: Amount to decrement by.

        Returns:
            New value after decrement.
        """
        full_key = self._make_key(key)
        return self._redis.decrby(full_key, amount)

    def get_or_set(self, key: str, default: Any, ttl: int | None = None) -> Any:
        """Get a value, or set and return a default.

        Args:
            key: Cache key.
            default: Default value if key doesn't exist.
            ttl: Time to live in seconds.

        Returns:
            Cached or default value.
        """
        value = self.get(key)
        if value is not None:
            return value

        self.set(key, default, ttl)
        return default

    def add_to_set(self, key: str, *values: Any) -> int:
        """Add values to a set.

        Args:
            key: Cache key.
            *values: Values to add.

        Returns:
            Number of values added.
        """
        full_key = self._make_key(key)
        serialized = [self._serialize(v) for v in values]
        return self._redis.sadd(full_key, *serialized)

    def get_set(self, key: str) -> set[Any]:
        """Get all members of a set.

        Args:
            key: Cache key.

        Returns:
            Set of values.
        """
        full_key = self._make_key(key)
        values = self._redis.smembers(full_key)
        return {self._deserialize(v) for v in values}

    def push_to_list(self, key: str, *values: Any) -> int:
        """Push values to a list.

        Args:
            key: Cache key.
            *values: Values to push.

        Returns:
            Length of the list after push.
        """
        full_key = self._make_key(key)
        serialized = [self._serialize(v) for v in values]
        return self._redis.rpush(full_key, *serialized)

    def get_list(self, key: str, start: int = 0, end: int = -1) -> list[Any]:
        """Get a range of values from a list.

        Args:
            key: Cache key.
            start: Start index.
            end: End index (-1 for all).

        Returns:
            List of values.
        """
        full_key = self._make_key(key)
        values = self._redis.lrange(full_key, start, end)
        return [self._deserialize(v) for v in values]

    def set_hash(self, key: str, field: str, value: Any) -> int:
        """Set a field in a hash.

        Args:
            key: Cache key.
            field: Hash field.
            value: Value to set.

        Returns:
            1 if new field, 0 if updated.
        """
        full_key = self._make_key(key)
        return self._redis.hset(full_key, field, self._serialize(value))

    def get_hash(self, key: str, field: str) -> Any | None:
        """Get a field from a hash.

        Args:
            key: Cache key.
            field: Hash field.

        Returns:
            Field value or None.
        """
        full_key = self._make_key(key)
        value = self._redis.hget(full_key, field)
        return self._deserialize(value)

    def get_all_hash(self, key: str) -> dict[str, Any]:
        """Get all fields from a hash.

        Args:
            key: Cache key.

        Returns:
            Dictionary of field-value pairs.
        """
        full_key = self._make_key(key)
        data = self._redis.hgetall(full_key)
        return {k: self._deserialize(v) for k, v in data.items()}
