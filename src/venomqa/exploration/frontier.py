"""Frontier - Manages unexplored (state, action) pairs.

The Frontier is the key abstraction for exploration strategies.
It holds the pairs that have been discovered but not yet explored.

Different frontier implementations give different exploration behaviors:
- QueueFrontier (FIFO): BFS - explores breadth-first, guarantees shortest paths
- StackFrontier (LIFO): DFS - explores depth-first, uses less memory
- PriorityFrontier: Guided search - explores based on heuristics
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from venomqa.exploration.graph import Graph
    from venomqa.sandbox import State
    from venomqa.v1.core.action import Action


@runtime_checkable
class Frontier(Protocol):
    """Protocol for frontier implementations.

    A Frontier manages the set of unexplored (state, action) pairs.
    Strategies use frontiers to decide what to explore next.
    """

    def add(self, state_id: str, action_name: str) -> None:
        """Add a (state, action) pair to the frontier.

        Args:
            state_id: The state ID to explore from.
            action_name: The action to try from that state.
        """
        ...

    def add_many(self, state_id: str, action_names: list[str]) -> None:
        """Add multiple actions from a single state.

        Args:
            state_id: The state ID to explore from.
            action_names: Actions to try from that state.
        """
        ...

    def pop(self) -> tuple[str, str] | None:
        """Remove and return the next (state_id, action_name) pair.

        Returns:
            A tuple of (state_id, action_name), or None if empty.
        """
        ...

    def is_empty(self) -> bool:
        """Check if the frontier is empty."""
        ...

    def __len__(self) -> int:
        """Return the number of pairs in the frontier."""
        ...


class BaseFrontier(ABC):
    """Base class for frontier implementations."""

    @abstractmethod
    def add(self, state_id: str, action_name: str) -> None:
        """Add a (state, action) pair to the frontier."""
        ...

    def add_many(self, state_id: str, action_names: list[str]) -> None:
        """Add multiple actions from a single state."""
        for action_name in action_names:
            self.add(state_id, action_name)

    @abstractmethod
    def pop(self) -> tuple[str, str] | None:
        """Remove and return the next (state_id, action_name) pair."""
        ...

    @abstractmethod
    def is_empty(self) -> bool:
        """Check if the frontier is empty."""
        ...

    @abstractmethod
    def __len__(self) -> int:
        """Return the number of pairs in the frontier."""
        ...


class QueueFrontier(BaseFrontier):
    """FIFO frontier for breadth-first exploration.

    Pairs are explored in the order they were added.
    This guarantees shortest paths to each state.
    """

    def __init__(self) -> None:
        self._queue: deque[tuple[str, str]] = deque()

    def add(self, state_id: str, action_name: str) -> None:
        self._queue.append((state_id, action_name))

    def add_many(self, state_id: str, action_names: list[str]) -> None:
        for action_name in action_names:
            self._queue.append((state_id, action_name))

    def pop(self) -> tuple[str, str] | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def is_empty(self) -> bool:
        return len(self._queue) == 0

    def __len__(self) -> int:
        return len(self._queue)


class StackFrontier(BaseFrontier):
    """LIFO frontier for depth-first exploration.

    Most recently added pairs are explored first.
    This explores deeply before backtracking.
    """

    def __init__(self) -> None:
        self._stack: list[tuple[str, str]] = []

    def add(self, state_id: str, action_name: str) -> None:
        self._stack.append((state_id, action_name))

    def add_many(self, state_id: str, action_names: list[str]) -> None:
        # Add in reverse order so first action is on top
        for action_name in reversed(action_names):
            self._stack.append((state_id, action_name))

    def pop(self) -> tuple[str, str] | None:
        if not self._stack:
            return None
        return self._stack.pop()

    def is_empty(self) -> bool:
        return len(self._stack) == 0

    def __len__(self) -> int:
        return len(self._stack)


__all__ = [
    "Frontier",
    "BaseFrontier",
    "QueueFrontier",
    "StackFrontier",
]
