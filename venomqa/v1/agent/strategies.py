"""Exploration strategies."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections import deque
from typing import Protocol, runtime_checkable

from venomqa.v1.core.state import State
from venomqa.v1.core.action import Action
from venomqa.v1.core.graph import Graph


@runtime_checkable
class Strategy(Protocol):
    """Protocol for exploration strategies.

    A strategy decides which (state, action) pair to explore next.
    """

    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        """Pick the next (state, action) pair to explore.

        Args:
            graph: The current exploration graph.

        Returns:
            A (state, action) tuple to explore, or None if done.
        """
        ...


class BaseStrategy(ABC):
    """Base class for strategy implementations."""

    @abstractmethod
    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        """Pick the next (state, action) pair to explore."""
        ...


class BFS(BaseStrategy):
    """Breadth-first search strategy.

    Explores states in the order they were discovered.
    Guarantees shortest paths to each state.
    """

    def __init__(self) -> None:
        self._queue: deque[tuple[str, str]] = deque()
        self._initialized = False

    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        # Initialize queue with initial state actions
        if not self._initialized:
            self._initialized = True
            if graph.initial_state_id:
                initial = graph.get_state(graph.initial_state_id)
                if initial:
                    for action in graph.get_valid_actions(initial):
                        self._queue.append((initial.id, action.name))

        # Process queue
        while self._queue:
            state_id, action_name = self._queue.popleft()
            if graph.is_explored(state_id, action_name):
                continue

            state = graph.get_state(state_id)
            action = graph.get_action(action_name)
            if state and action and action.can_execute(state):
                return (state, action)

        # Queue empty, look for any unexplored pairs
        unexplored = graph.get_unexplored()
        if unexplored:
            return unexplored[0]

        return None

    def enqueue(self, state: State, actions: list[Action]) -> None:
        """Add new state's actions to the queue."""
        for action in actions:
            self._queue.append((state.id, action.name))


class DFS(BaseStrategy):
    """Depth-first search strategy.

    Explores as deep as possible before backtracking.
    """

    def __init__(self) -> None:
        self._stack: list[tuple[str, str]] = []
        self._initialized = False

    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        # Initialize stack with initial state actions
        if not self._initialized:
            self._initialized = True
            if graph.initial_state_id:
                initial = graph.get_state(graph.initial_state_id)
                if initial:
                    for action in reversed(graph.get_valid_actions(initial)):
                        self._stack.append((initial.id, action.name))

        # Process stack
        while self._stack:
            state_id, action_name = self._stack.pop()
            if graph.is_explored(state_id, action_name):
                continue

            state = graph.get_state(state_id)
            action = graph.get_action(action_name)
            if state and action and action.can_execute(state):
                return (state, action)

        # Stack empty, look for any unexplored pairs
        unexplored = graph.get_unexplored()
        if unexplored:
            return unexplored[0]

        return None

    def push(self, state: State, actions: list[Action]) -> None:
        """Add new state's actions to the stack."""
        for action in reversed(actions):
            self._stack.append((state.id, action.name))


class Random(BaseStrategy):
    """Random exploration strategy.

    Picks randomly from unexplored (state, action) pairs.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        unexplored = graph.get_unexplored()
        if not unexplored:
            return None
        return self._rng.choice(unexplored)
