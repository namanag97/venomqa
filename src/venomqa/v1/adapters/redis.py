"""Redis adapter with dump/restore-based rollback."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import SystemCheckpoint


class RedisAdapter:
    """Redis adapter using key dump/restore for checkpoint/rollback.

    This adapter wraps a Redis connection and provides:
    - checkpoint(): Dumps all tracked keys
    - rollback(): Restores keys from dump
    - observe(): Gets values of tracked keys
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        track_keys: list[str] | None = None,
        track_patterns: list[str] | None = None,
    ) -> None:
        self.url = url
        self.track_keys = track_keys or []
        self.track_patterns = track_patterns or ["*"]
        self._client: Any = None

    def connect(self) -> None:
        """Connect to Redis."""
        try:
            import redis
            self._client = redis.from_url(self.url)
        except ImportError:
            raise ImportError("redis is required for RedisAdapter")

    def close(self) -> None:
        """Close the connection."""
        if self._client:
            self._client.close()
            self._client = None

    def _get_tracked_keys(self) -> list[str]:
        """Get all keys matching tracked patterns."""
        keys = set(self.track_keys)
        for pattern in self.track_patterns:
            keys.update(self._client.keys(pattern))
        return list(keys)

    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Dump all tracked keys."""
        if not self._client:
            self.connect()

        dump: dict[str, tuple[bytes, int]] = {}
        for key in self._get_tracked_keys():
            if isinstance(key, bytes):
                key = key.decode()
            data = self._client.dump(key)
            if data:
                ttl = self._client.pttl(key)
                dump[key] = (data, ttl if ttl > 0 else 0)

        return dump

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Restore keys from dump."""
        if not self._client:
            self.connect()

        dump: dict[str, tuple[bytes, int]] = checkpoint

        # Delete current keys
        current_keys = self._get_tracked_keys()
        if current_keys:
            self._client.delete(*current_keys)

        # Restore from dump
        for key, (data, ttl) in dump.items():
            self._client.restore(key, ttl, data, replace=True)

    def observe(self) -> Observation:
        """Get current state of tracked keys."""
        if not self._client:
            self.connect()

        data: dict[str, Any] = {}
        for key in self._get_tracked_keys():
            if isinstance(key, bytes):
                key = key.decode()
            key_type = self._client.type(key)
            if isinstance(key_type, bytes):
                key_type = key_type.decode()

            if key_type == "string":
                data[key] = self._client.get(key)
            elif key_type == "list":
                data[key] = self._client.lrange(key, 0, -1)
            elif key_type == "set":
                data[key] = list(self._client.smembers(key))
            elif key_type == "hash":
                data[key] = self._client.hgetall(key)

        return Observation(
            system="cache",
            data=data,
            observed_at=datetime.now(),
        )

    def __enter__(self) -> RedisAdapter:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
