"""Execution context for sharing state between steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionContext:
    """Typed context for sharing state between steps in a journey.

    Provides type-safe access to step results and shared data.
    """

    _data: dict[str, Any] = field(default_factory=dict)
    _step_results: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        """Store a value in context."""
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from context."""
        return self._data.get(key, default)

    def get_required(self, key: str) -> Any:
        """Retrieve a value, raising if not found."""
        if key not in self._data:
            raise KeyError(f"Required context key not found: {key}")
        return self._data[key]

    def store_step_result(self, step_name: str, result: Any) -> None:
        """Store result of a step for later access."""
        self._step_results[step_name] = result
        self._data[step_name] = result

    def get_step_result(self, step_name: str) -> Any:
        """Get result from a previous step."""
        return self._step_results.get(step_name)

    def clear(self) -> None:
        """Clear all context data."""
        self._data.clear()
        self._step_results.clear()

    def snapshot(self) -> dict[str, Any]:
        """Create a snapshot of current context."""
        return {
            "data": self._data.copy(),
            "step_results": self._step_results.copy(),
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore context from a snapshot."""
        self._data = snapshot.get("data", {}).copy()
        self._step_results = snapshot.get("step_results", {}).copy()

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def to_dict(self) -> dict[str, Any]:
        """Export context as dictionary."""
        return self.snapshot()
