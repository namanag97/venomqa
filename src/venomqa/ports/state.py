from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class StateEntry:
    key: str
    value: Any
    created_at: datetime
    updated_at: datetime
    ttl_seconds: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        elapsed = (datetime.now() - self.updated_at).total_seconds()
        return elapsed > self.ttl_seconds


@dataclass
class StateQuery:
    key_prefix: str | None = None
    key_pattern: str | None = None
    metadata_filter: dict[str, Any] = field(default_factory=dict)
    limit: int = 100
    offset: int = 0
    include_expired: bool = False


class StatePort(ABC):
    @abstractmethod
    def get(self, key: str) -> StateEntry | None:
        """
        Get a state entry by key.

        Args:
            key: The key to look up.

        Returns:
            StateEntry if found and not expired, None otherwise.
        """
        ...

    @abstractmethod
    def get_value(self, key: str, default: Any = None) -> Any:
        """
        Get just the value for a key.

        Args:
            key: The key to look up.
            default: Default value if key not found.

        Returns:
            The value or default.
        """
        ...

    @abstractmethod
    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StateEntry:
        """
        Set a state entry.

        Args:
            key: The key to set.
            value: The value to store.
            ttl_seconds: Optional TTL in seconds.
            metadata: Optional metadata dictionary.

        Returns:
            The created StateEntry.
        """
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        Delete a state entry.

        Args:
            key: The key to delete.

        Returns:
            True if deleted, False if not found.
        """
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        Check if a key exists and is not expired.

        Args:
            key: The key to check.

        Returns:
            True if exists and valid, False otherwise.
        """
        ...

    @abstractmethod
    def keys(self, pattern: str = "*") -> list[str]:
        """
        Get all keys matching a pattern.

        Args:
            pattern: Glob pattern to match keys.

        Returns:
            List of matching keys.
        """
        ...

    @abstractmethod
    def query(self, query: StateQuery) -> list[StateEntry]:
        """
        Query state entries with filters.

        Args:
            query: Query parameters.

        Returns:
            List of matching StateEntry objects.
        """
        ...

    @abstractmethod
    def increment(self, key: str, amount: int = 1) -> int:
        """
        Atomically increment a numeric value.

        Args:
            key: The key to increment.
            amount: Amount to increment by.

        Returns:
            The new value.
        """
        ...

    @abstractmethod
    def decrement(self, key: str, amount: int = 1) -> int:
        """
        Atomically decrement a numeric value.

        Args:
            key: The key to decrement.
            amount: Amount to decrement by.

        Returns:
            The new value.
        """
        ...

    @abstractmethod
    def append(self, key: str, value: Any) -> list[Any]:
        """
        Append to a list value.

        Args:
            key: The key of the list.
            value: Value to append.

        Returns:
            The updated list.
        """
        ...

    @abstractmethod
    def extend(self, key: str, values: list[Any]) -> list[Any]:
        """
        Extend a list with multiple values.

        Args:
            key: The key of the list.
            values: Values to extend with.

        Returns:
            The updated list.
        """
        ...

    @abstractmethod
    def get_list(self, key: str) -> list[Any]:
        """
        Get a list value.

        Args:
            key: The key of the list.

        Returns:
            The list or empty list if not found.
        """
        ...

    @abstractmethod
    def add_to_set(self, key: str, value: Any) -> set[Any]:
        """
        Add a value to a set.

        Args:
            key: The key of the set.
            value: Value to add.

        Returns:
            The updated set.
        """
        ...

    @abstractmethod
    def remove_from_set(self, key: str, value: Any) -> set[Any]:
        """
        Remove a value from a set.

        Args:
            key: The key of the set.
            value: Value to remove.

        Returns:
            The updated set.
        """
        ...

    @abstractmethod
    def get_set(self, key: str) -> set[Any]:
        """
        Get a set value.

        Args:
            key: The key of the set.

        Returns:
            The set or empty set if not found.
        """
        ...

    @abstractmethod
    def set_dict_field(self, key: str, field: str, value: Any) -> dict[str, Any]:
        """
        Set a field in a dictionary value.

        Args:
            key: The key of the dictionary.
            field: The field name.
            value: The value to set.

        Returns:
            The updated dictionary.
        """
        ...

    @abstractmethod
    def get_dict_field(self, key: str, field: str, default: Any = None) -> Any:
        """
        Get a field from a dictionary value.

        Args:
            key: The key of the dictionary.
            field: The field name.
            default: Default value if field not found.

        Returns:
            The field value or default.
        """
        ...

    @abstractmethod
    def get_dict(self, key: str) -> dict[str, Any]:
        """
        Get a dictionary value.

        Args:
            key: The key of the dictionary.

        Returns:
            The dictionary or empty dict if not found.
        """
        ...

    @abstractmethod
    def expire(self, key: str, ttl_seconds: int) -> bool:
        """
        Set TTL on an existing key.

        Args:
            key: The key to set TTL on.
            ttl_seconds: TTL in seconds.

        Returns:
            True if TTL was set, False if key not found.
        """
        ...

    @abstractmethod
    def ttl(self, key: str) -> int | None:
        """
        Get remaining TTL for a key.

        Args:
            key: The key to check.

        Returns:
            Remaining TTL in seconds, or None if no TTL.
        """
        ...

    @abstractmethod
    def persist(self, key: str) -> bool:
        """
        Remove TTL from a key, making it persistent.

        Args:
            key: The key to persist.

        Returns:
            True if TTL was removed, False if key not found.
        """
        ...

    @abstractmethod
    def clear(self, pattern: str = "*") -> int:
        """
        Clear all keys matching a pattern.

        Args:
            pattern: Glob pattern for keys to clear.

        Returns:
            Number of keys cleared.
        """
        ...

    @abstractmethod
    def watch(self, key: str, callback: Callable[[StateEntry | None], None]) -> str:
        """
        Watch a key for changes.

        Args:
            key: The key to watch.
            callback: Function called on change with the new entry.

        Returns:
            Watcher ID for unwatching.
        """
        ...

    @abstractmethod
    def unwatch(self, watcher_id: str) -> None:
        """
        Stop watching a key.

        Args:
            watcher_id: The watcher ID to remove.
        """
        ...

    @abstractmethod
    def transaction(self, operations: list[tuple[str, tuple[Any, ...]]]) -> list[Any]:
        """
        Execute multiple operations atomically.

        Args:
            operations: List of (method_name, args) tuples.

        Returns:
            List of results from each operation.
        """
        ...
