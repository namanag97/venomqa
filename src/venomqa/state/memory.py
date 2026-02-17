"""In-memory state manager for fast testing without database dependency.

This module provides an in-memory state management backend that simulates
database savepoints using deep copies of Python dictionaries. It's ideal
for unit tests where speed is important but actual SQL behavior is not required.

Example:
    >>> from venomqa.state import InMemoryStateManager
    >>> with InMemoryStateManager("memory://test") as state:
    ...     state.set_data({"users": [{"id": 1, "name": "Alice"}]})
    ...     state.checkpoint("initial")
    ...     state.update_data("users", [{"id": 1, "name": "Bob"}])
    ...     state.rollback("initial")
    ...     assert state.get_value("users")[0]["name"] == "Alice"

Warning:
    This backend does NOT simulate actual database constraints, transactions,
    or concurrent access. For integration tests, use SQLite or PostgreSQL.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from venomqa.errors import CheckpointError, RollbackError
from venomqa.state.base import BaseStateManager

logger = logging.getLogger(__name__)


class InMemoryStateManager(BaseStateManager):
    """In-memory state manager using dict snapshots for fast testing.

    This backend stores data in memory and uses deep copies for snapshots,
    making it ideal for unit tests where database speed matters but actual
    persistence is not required.

    The state is stored as a dictionary that can be manipulated directly
    through the provided methods. Snapshots are created using copy.deepcopy()
    to ensure complete isolation between checkpoints.

    Attributes:
        _data: Current state dictionary.
        _snapshots: Dictionary mapping checkpoint names to state snapshots.
        _initial_state: Initial state to use on connect/reset.

    Example:
        >>> manager = InMemoryStateManager("memory://test", initial_state={"count": 0})
        >>> manager.connect()
        >>> manager.update_data("count", 5)
        >>> manager.checkpoint("after_increment")
        >>> manager.update_data("count", 10)
        >>> manager.rollback("after_increment")
        >>> manager.get_value("count")
        5

    Note:
        This is NOT suitable for integration tests that need:
        - Real SQL behavior and constraints
        - Concurrent access testing
        - Transaction isolation levels
        - Database-specific features
    """

    def __init__(
        self,
        connection_url: str = "memory://default",
        initial_state: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the in-memory state manager.

        Args:
            connection_url: Identifier for this state manager. Not used for
                actual connections but useful for logging and debugging.
                Defaults to "memory://default".
            initial_state: Optional initial state dictionary. This will be
                deep-copied on connect() and reset(). Defaults to empty dict.

        Example:
            >>> manager = InMemoryStateManager(
            ...     "memory://user_tests",
            ...     initial_state={"users": [], "settings": {}}
            ... )
        """
        super().__init__(connection_url)
        self._data: dict[str, Any] = {}
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._initial_state: dict[str, Any] = initial_state or {}

    def connect(self) -> None:
        """Initialize in-memory state by copying initial state.

        Sets up the internal data structures and marks the manager as connected.
        Safe to call multiple times - each call resets to initial state.
        """
        self._data = copy.deepcopy(self._initial_state)
        self._snapshots = {}
        self._connected = True
        self._checkpoints = []
        logger.info(f"Connected to in-memory state manager: {self.connection_url}")

    def disconnect(self) -> None:
        """Clear in-memory state and disconnect.

        Removes all data, snapshots, and checkpoints. Safe to call multiple
        times or when already disconnected.
        """
        self._data = {}
        self._snapshots = {}
        self._connected = False
        self._checkpoints = []
        logger.info(f"Disconnected from in-memory state manager: {self.connection_url}")

    def checkpoint(self, name: str) -> None:
        """Create a snapshot of current state.

        Creates a deep copy of the current state and stores it under the
        given checkpoint name. The checkpoint can later be used to restore
        the state via rollback().

        Args:
            name: Unique identifier for this checkpoint. Will be validated
                and sanitized.

        Raises:
            StateNotConnectedError: If not connected.
            ValueError: If checkpoint name is empty or invalid.
            CheckpointError: If checkpoint already exists.
        """
        self._ensure_connected()
        self._validate_checkpoint_name(name)

        safe_name = self._sanitize_checkpoint_name(name, prefix="mem")

        if safe_name in self._snapshots:
            raise CheckpointError(
                message=f"Checkpoint '{name}' already exists",
                context={"checkpoint_name": name, "safe_name": safe_name},
            )

        self._snapshots[safe_name] = copy.deepcopy(self._data)
        self._checkpoints.append(safe_name)
        logger.debug(f"Created in-memory snapshot: {safe_name}")

    def rollback(self, name: str) -> None:
        """Rollback to a previous snapshot.

        Restores the state to the snapshot taken at checkpoint() time.
        Any checkpoints created after this one will be removed.

        Args:
            name: Name of the checkpoint to rollback to.

        Raises:
            StateNotConnectedError: If not connected.
            RollbackError: If checkpoint doesn't exist.
        """
        self._ensure_connected()
        safe_name = self._sanitize_checkpoint_name(name, prefix="mem")

        if safe_name not in self._snapshots:
            raise RollbackError(
                message=f"Checkpoint '{name}' not found",
                context={
                    "checkpoint_name": name,
                    "available_checkpoints": self._checkpoints,
                },
            )

        self._data = copy.deepcopy(self._snapshots[safe_name])

        if safe_name in self._checkpoints:
            idx = self._checkpoints.index(safe_name)
            for cp in self._checkpoints[idx + 1 :]:
                self._snapshots.pop(cp, None)
            self._checkpoints = self._checkpoints[: idx + 1]

        logger.debug(f"Rolled back to in-memory snapshot: {safe_name}")

    def release(self, name: str) -> None:
        """Release a snapshot to free memory.

        Removes the snapshot from memory. The checkpoint can no longer be
        used for rollback after release.

        Args:
            name: Name of the checkpoint to release.

        Note:
            This operation is silent if the checkpoint doesn't exist,
            making it safe to call speculatively.
        """
        self._ensure_connected()
        safe_name = self._sanitize_checkpoint_name(name, prefix="mem")

        self._snapshots.pop(safe_name, None)
        if safe_name in self._checkpoints:
            self._checkpoints.remove(safe_name)

        logger.debug(f"Released in-memory snapshot: {safe_name}")

    def reset(self) -> None:
        """Reset state to initial state.

        Clears all data and snapshots, restoring to the initial_state
        provided at construction time.
        """
        self._ensure_connected()
        self._data = copy.deepcopy(self._initial_state)
        self._snapshots = {}
        self._checkpoints = []
        logger.info(f"Reset in-memory state to initial state: {self.connection_url}")

    def get_data(self) -> dict[str, Any]:
        """Get a deep copy of current data state.

        Returns a copy to prevent external modification of internal state.

        Returns:
            Deep copy of the current state dictionary.

        Raises:
            StateNotConnectedError: If not connected.
        """
        self._ensure_connected()
        return copy.deepcopy(self._data)

    def set_data(self, data: dict[str, Any]) -> None:
        """Set data state directly by replacing current state.

        Args:
            data: New state dictionary. Will be deep-copied to prevent
                external modification.

        Raises:
            StateNotConnectedError: If not connected.
        """
        self._ensure_connected()
        self._data = copy.deepcopy(data)

    def update_data(self, key: str, value: Any) -> None:
        """Update a specific key in the data state.

        Args:
            key: Dictionary key to update.
            value: New value for the key. Note: not deep-copied for
                performance; caller should copy if needed.

        Raises:
            StateNotConnectedError: If not connected.

        Example:
            >>> manager.update_data("users", [{"id": 1}])
        """
        self._ensure_connected()
        self._data[key] = value

    def get_value(self, key: str, default: Any = None) -> Any:
        """Get a specific value from data state.

        Args:
            key: Dictionary key to retrieve.
            default: Value to return if key doesn't exist. Defaults to None.

        Returns:
            Value for the key, or default if not found.

        Raises:
            StateNotConnectedError: If not connected.

        Note:
            Returns the actual value, not a copy. Modify at your own risk.
        """
        self._ensure_connected()
        return self._data.get(key, default)

    def delete_key(self, key: str) -> bool:
        """Delete a key from the data state.

        Args:
            key: Dictionary key to delete.

        Returns:
            True if key existed and was deleted, False if key didn't exist.

        Raises:
            StateNotConnectedError: If not connected.
        """
        self._ensure_connected()
        if key in self._data:
            del self._data[key]
            return True
        return False

    def clear_data(self) -> None:
        """Clear all data without affecting checkpoints.

        Useful for testing scenarios where you want to reset data
        but keep checkpoint snapshots available.
        """
        self._ensure_connected()
        self._data = {}

    def get_snapshot_names(self) -> list[str]:
        """Get list of all snapshot names.

        Returns:
            List of checkpoint names that have snapshots.
        """
        return list(self._snapshots.keys())

    def get_snapshot_size(self, name: str) -> int:
        """Get approximate size of a snapshot in bytes.

        Args:
            name: Checkpoint name.

        Returns:
            Approximate size in bytes, or 0 if snapshot doesn't exist.
        """
        safe_name = self._sanitize_checkpoint_name(name, prefix="mem")
        if safe_name in self._snapshots:
            import sys

            return sys.getsizeof(self._snapshots[safe_name])
        return 0
