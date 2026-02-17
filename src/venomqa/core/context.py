"""Execution context for sharing state between steps.

The ExecutionContext provides a type-safe way to share data between steps
in a journey, supporting snapshots for rollback scenarios.

Also re-exports the v1 Context class for convenience.

Example:
    >>> from venomqa.core.context import Context  # v1 exploration context
    >>> from venomqa.core.context import ExecutionContext  # v0 step context
"""

from __future__ import annotations

# Re-export the v1 Context for new-style imports
from venomqa.v1.core.context import Context

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from venomqa.state import StateManager

T = TypeVar("T")


@dataclass
class ExecutionContext:
    """Typed context for sharing state between steps in a journey.

    Provides type-safe access to step results and shared data with
    support for snapshots (used by checkpoints) and restoration.

    Attributes:
        _data: General-purpose key-value storage.
        _step_results: Results indexed by step name.
        _state_manager: Optional state manager for database operations.

    Example:
        >>> ctx = ExecutionContext()
        >>> ctx["user_id"] = 123  # Dictionary-style access
        >>> ctx.set("token", "abc123")  # Method-style access
        >>>
        >>> # Create snapshot before risky operation
        >>> snapshot = ctx.snapshot()
        >>> try:
        ...     ctx.set("result", risky_operation())
        ... except Exception:
        ...     ctx.restore(snapshot)  # Rollback on failure
    """

    _data: dict[str, Any] = field(default_factory=dict)
    _step_results: dict[str, Any] = field(default_factory=dict)
    _created_at: datetime = field(default_factory=datetime.now)
    _state_manager: StateManager | None = field(default=None, repr=False)

    def set(self, key: str, value: Any) -> None:
        """Store a value in context.

        Args:
            key: The key to store the value under.
            value: The value to store. Can be any type.

        Example:
            >>> ctx.set("user_id", 123)
            >>> ctx.set("config", {"timeout": 30})
        """
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from context.

        Args:
            key: The key to retrieve.
            default: Value to return if key not found.

        Returns:
            The stored value or default if not found.

        Example:
            >>> ctx.set("user_id", 123)
            >>> ctx.get("user_id")  # Returns 123
            >>> ctx.get("missing", "default")  # Returns "default"
        """
        return self._data.get(key, default)

    def get_required(self, key: str) -> Any:
        """Retrieve a value, raising KeyError if not found.

        Args:
            key: The key to retrieve.

        Returns:
            The stored value.

        Raises:
            KeyError: If the key does not exist.

        Example:
            >>> ctx.set("user_id", 123)
            >>> ctx.get_required("user_id")  # Returns 123
            >>> ctx.get_required("missing")  # Raises KeyError
        """
        if key not in self._data:
            raise KeyError(f"Required context key not found: {key}")
        return self._data[key]

    def get_typed(self, key: str, expected_type: type[T], default: T | None = None) -> T:
        """Retrieve a value with type validation.

        Args:
            key: The key to retrieve.
            expected_type: The expected type of the value.
            default: Default value if key not found.

        Returns:
            The stored value (validated type).

        Raises:
            TypeError: If value is not of expected type.

        Example:
            >>> ctx.set("count", 42)
            >>> count = ctx.get_typed("count", int)  # Returns 42
            >>> name = ctx.get_typed("missing", str, "unknown")  # Returns "unknown"
        """
        value = self._data.get(key, default)
        if value is not None and not isinstance(value, expected_type):
            raise TypeError(
                f"Context key '{key}' has type {type(value).__name__}, "
                f"expected {expected_type.__name__}"
            )
        return value  # type: ignore[return-value]

    def store_step_result(self, step_name: str, result: Any) -> None:
        """Store result of a step for later access.

        Results are stored both in _step_results and _data for flexible
        access patterns.

        Args:
            step_name: Name of the step.
            result: The result to store.

        Example:
            >>> ctx.store_step_result("create_user", {"id": 123})
            >>> ctx.get_step_result("create_user")  # Returns {"id": 123}
            >>> ctx.get("create_user")  # Also returns {"id": 123}
        """
        self._step_results[step_name] = result
        self._data[step_name] = result

    def get_step_result(self, step_name: str) -> Any:
        """Get result from a previous step.

        Args:
            step_name: Name of the step.

        Returns:
            The stored result or None if not found.

        Example:
            >>> result = ctx.get_step_result("create_user")
            >>> if result:
            ...     user_id = result.get("id")
        """
        return self._step_results.get(step_name)

    def get_step_result_required(self, step_name: str) -> Any:
        """Get result from a previous step, raising if not found.

        Args:
            step_name: Name of the step.

        Returns:
            The stored result.

        Raises:
            KeyError: If no result exists for the step.

        Example:
            >>> result = ctx.get_step_result_required("create_user")
            >>> user_id = result["id"]
        """
        if step_name not in self._step_results:
            raise KeyError(f"No result stored for step: {step_name}")
        return self._step_results[step_name]

    def has_step_result(self, step_name: str) -> bool:
        """Check if a step result exists.

        Args:
            step_name: Name of the step.

        Returns:
            True if result exists, False otherwise.
        """
        return step_name in self._step_results

    def clear(self) -> None:
        """Clear all context data.

        Removes all data and step results. Use with caution.

        Example:
            >>> ctx.clear()
            >>> len(ctx)  # Returns 0
        """
        self._data.clear()
        self._step_results.clear()

    def snapshot(self) -> dict[str, Any]:
        """Create a snapshot of current context.

        Snapshots are used by checkpoints to enable rollback.

        Performance Note:
            This method creates a shallow copy for efficiency. The deep copy
            is deferred to restore() time. This means if you modify mutable
            objects in the context AFTER taking a snapshot (but before
            restoring), those changes may affect the snapshot. The runner
            avoids this by creating new contexts for each path.

        Returns:
            Dictionary containing complete context state.

        Example:
            >>> snapshot = ctx.snapshot()
            >>> # ... perform operations ...
            >>> ctx.restore(snapshot)  # Rollback to snapshot
        """
        # Shallow copy - deep copy is deferred to restore() for efficiency
        # This is O(1) for dict structure, actual data copy happens on restore
        return {
            "data": dict(self._data),
            "step_results": dict(self._step_results),
            "created_at": self._created_at.isoformat(),
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore context from a snapshot.

        This method performs a deep copy of the snapshot data to ensure
        the restored context is fully independent. This pattern defers
        the O(n) deep copy cost from snapshot creation to restore time,
        improving performance when snapshots are created more often than
        they are restored.

        Args:
            snapshot: A snapshot created by snapshot().

        Example:
            >>> snapshot = ctx.snapshot()
            >>> ctx.set("new_key", "value")
            >>> ctx.restore(snapshot)
            >>> ctx.get("new_key")  # Returns None
        """
        # Deepcopy on restore ensures each restored context is independent
        # This is where the O(n) copy cost is paid
        self._data = deepcopy(snapshot.get("data", {}))
        self._step_results = deepcopy(snapshot.get("step_results", {}))

    def merge(self, other: ExecutionContext, overwrite: bool = False) -> None:
        """Merge another context into this one.

        Args:
            other: Another ExecutionContext to merge.
            overwrite: If True, overwrite existing keys.

        Example:
            >>> ctx1 = ExecutionContext()
            >>> ctx1.set("a", 1)
            >>> ctx2 = ExecutionContext()
            >>> ctx2.set("b", 2)
            >>> ctx1.merge(ctx2)
            >>> ctx1.get("b")  # Returns 2
        """
        for key, value in other._data.items():
            if overwrite or key not in self._data:
                self._data[key] = deepcopy(value)
        for key, value in other._step_results.items():
            if overwrite or key not in self._step_results:
                self._step_results[key] = deepcopy(value)

    def keys(self) -> list[str]:
        """Get all keys in the context."""
        return list(self._data.keys())

    def step_names(self) -> list[str]:
        """Get all step names with stored results."""
        return list(self._step_results.keys())

    def __contains__(self, key: str) -> bool:
        """Check if a key exists in context."""
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        """Dictionary-style get access."""
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Dictionary-style set access."""
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        """Dictionary-style delete access."""
        del self._data[key]

    def pop(self, key: str, default: Any = None) -> Any:
        """Remove and return a value from context.

        Args:
            key: The key to remove.
            default: Value to return if key not found.

        Returns:
            The removed value or default if not found.

        Example:
            >>> ctx.set("user_id", 123)
            >>> ctx.pop("user_id")  # Returns 123
            >>> ctx.get("user_id")  # Returns None
        """
        return self._data.pop(key, default)

    def __len__(self) -> int:
        """Number of items in context."""
        return len(self._data)

    def __bool__(self) -> bool:
        """Context is truthy if it has data."""
        return bool(self._data or self._step_results)

    @property
    def state_manager(self) -> StateManager | None:
        """Get the state manager for database operations.

        Returns:
            The state manager instance or None if not set.

        Example:
            >>> if ctx.state_manager:
            ...     ctx.state_manager.execute("UPDATE users SET active = 1")
        """
        return self._state_manager

    @state_manager.setter
    def state_manager(self, value: StateManager | None) -> None:
        """Set the state manager.

        Args:
            value: The state manager instance or None to clear.
        """
        self._state_manager = value

    def to_dict(self) -> dict[str, Any]:
        """Export context as dictionary for serialization.

        Returns:
            Complete context state as dictionary.

        Example:
            >>> data = ctx.to_dict()
            >>> json.dumps(data)  # Can be JSON serialized
        """
        return self.snapshot()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionContext:
        """Create context from a dictionary.

        Args:
            data: Dictionary with 'data' and 'step_results' keys.

        Returns:
            New ExecutionContext instance.

        Example:
            >>> ctx = ExecutionContext.from_dict({
            ...     "data": {"user_id": 123},
            ...     "step_results": {"create_user": {"id": 123}}
            ... })
        """
        return cls(
            _data=deepcopy(data.get("data", {})),
            _step_results=deepcopy(data.get("step_results", {})),
        )

    def copy(self) -> ExecutionContext:
        """Create a deep copy of this context.

        Note: The state_manager reference is preserved (not copied).

        Returns:
            A new ExecutionContext with copied data.

        Example:
            >>> ctx_copy = ctx.copy()
            >>> ctx_copy.set("new", "value")
            >>> ctx.get("new")  # Returns None (original unchanged)
        """
        return ExecutionContext(
            _data=deepcopy(self._data),
            _step_results=deepcopy(self._step_results),
            _state_manager=self._state_manager,
        )
