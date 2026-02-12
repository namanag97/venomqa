"""In-memory state manager for fast testing without database dependency."""

from __future__ import annotations

import copy
import logging
from typing import Any

from venomqa.state.base import BaseStateManager

logger = logging.getLogger(__name__)


class InMemoryStateManager(BaseStateManager):
    """In-memory state manager using dict snapshots for fast testing.

    This backend stores data in memory and uses deep copies for snapshots,
    making it ideal for unit tests where database speed matters but actual
    persistence is not required.

    Note: This is NOT suitable for integration tests that need real SQL
    behavior or concurrent access testing.
    """

    def __init__(
        self,
        connection_url: str = "memory://default",
        initial_state: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(connection_url)
        self._data: dict[str, Any] = {}
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._initial_state = initial_state or {}

    def connect(self) -> None:
        """Initialize in-memory state."""
        self._data = copy.deepcopy(self._initial_state)
        self._snapshots = {}
        self._connected = True
        logger.info("Connected to in-memory state manager")

    def disconnect(self) -> None:
        """Clear in-memory state."""
        self._data = {}
        self._snapshots = {}
        self._connected = False
        self._checkpoints.clear()
        logger.info("Disconnected from in-memory state manager")

    def checkpoint(self, name: str) -> None:
        """Create a snapshot of current state."""
        self._ensure_connected()
        safe_name = self._sanitize_name(name)
        self._snapshots[safe_name] = copy.deepcopy(self._data)
        self._checkpoints.append(safe_name)
        logger.debug(f"Created snapshot: {safe_name}")

    def rollback(self, name: str) -> None:
        """Rollback to a previous snapshot."""
        self._ensure_connected()
        safe_name = self._sanitize_name(name)

        if safe_name not in self._snapshots:
            raise ValueError(f"Checkpoint '{name}' not found")

        self._data = copy.deepcopy(self._snapshots[safe_name])
        idx = self._checkpoints.index(safe_name)
        for checkpoint in self._checkpoints[idx + 1 :]:
            self._snapshots.pop(checkpoint, None)
        self._checkpoints = self._checkpoints[: idx + 1]
        logger.debug(f"Rolled back to snapshot: {safe_name}")

    def release(self, name: str) -> None:
        """Release a snapshot (free memory)."""
        self._ensure_connected()
        safe_name = self._sanitize_name(name)

        if safe_name in self._snapshots:
            del self._snapshots[safe_name]
        if safe_name in self._checkpoints:
            self._checkpoints.remove(safe_name)
        logger.debug(f"Released snapshot: {safe_name}")

    def reset(self) -> None:
        """Reset to initial state."""
        self._ensure_connected()
        self._data = copy.deepcopy(self._initial_state)
        self._snapshots = {}
        self._checkpoints.clear()
        logger.info("Reset in-memory state to initial state")

    def get_data(self) -> dict[str, Any]:
        """Get current data state (for testing assertions)."""
        self._ensure_connected()
        return copy.deepcopy(self._data)

    def set_data(self, data: dict[str, Any]) -> None:
        """Set data state directly (for test setup)."""
        self._ensure_connected()
        self._data = copy.deepcopy(data)

    def update_data(self, key: str, value: Any) -> None:
        """Update a specific key in data state."""
        self._ensure_connected()
        self._data[key] = value

    def get_value(self, key: str, default: Any = None) -> Any:
        """Get a specific value from data state."""
        self._ensure_connected()
        return self._data.get(key, default)

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitize checkpoint name."""
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
        if safe and safe[0].isdigit():
            safe = "sp_" + safe
        return f"mem_{safe}"
