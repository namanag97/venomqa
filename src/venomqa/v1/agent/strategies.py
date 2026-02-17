"""Exploration strategies."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections import Counter, deque
from typing import Protocol, runtime_checkable

from venomqa.v1.core.action import Action
from venomqa.v1.core.graph import Graph
from venomqa.v1.core.state import State


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

    def notify(self, state: State, actions: list[Action]) -> None:
        """Notify strategy of a new state and its valid actions.

        Called by Agent after each transition to inform the strategy
        about newly discovered states. Strategies use this to update
        their internal queues/stacks.

        Args:
            state: The newly observed state.
            actions: Actions valid from this state.
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
    Good for fuzzing and finding unexpected bugs.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        unexplored = graph.get_unexplored()
        if not unexplored:
            return None
        return self._rng.choice(unexplored)


class CoverageGuided(BaseStrategy):
    """Coverage-guided exploration strategy.

    Prioritizes actions that are least explored across all states.
    The goal is to maximize action diversity - ensuring all actions
    are tried from multiple states rather than focusing on a few.

    This is useful for finding edge cases where an action behaves
    differently depending on the state it's executed from.
    """

    def __init__(self) -> None:
        self._action_counts: Counter[str] = Counter()

    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        unexplored = graph.get_unexplored()
        if not unexplored:
            return None

        # Count how many times each action has been explored
        for transition in graph.iter_transitions():
            self._action_counts[transition.action_name] += 1

        # Sort unexplored pairs by action exploration count (ascending)
        # This prioritizes least-explored actions
        def score(pair: tuple[State, Action]) -> int:
            return self._action_counts[pair[1].name]

        unexplored.sort(key=score)
        return unexplored[0]

    def enqueue(self, state: State, actions: list[Action]) -> None:
        """No-op for coverage guided (it recalculates each pick)."""
        pass

    def push(self, state: State, actions: list[Action]) -> None:
        """No-op for coverage guided (it recalculates each pick)."""
        pass


class Weighted(BaseStrategy):
    """Weighted random exploration strategy.

    Allows assigning weights to actions to control exploration priority.
    Higher weight = more likely to be picked.
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        seed: int | None = None,
    ) -> None:
        self._weights = weights or {}
        self._rng = random.Random(seed)
        self._default_weight = 1.0

    def set_weight(self, action_name: str, weight: float) -> None:
        """Set the weight for an action."""
        self._weights[action_name] = weight

    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        unexplored = graph.get_unexplored()
        if not unexplored:
            return None

        # Calculate weights
        weights = [
            self._weights.get(pair[1].name, self._default_weight)
            for pair in unexplored
        ]

        # Weighted random selection
        total = sum(weights)
        if total == 0:
            return self._rng.choice(unexplored)

        r = self._rng.random() * total
        cumulative = 0.0
        for pair, weight in zip(unexplored, weights, strict=False):
            cumulative += weight
            if r <= cumulative:
                return pair

        return unexplored[-1]  # Fallback


# Import DimensionNoveltyStrategy so it is available from this module
from venomqa.v1.agent.dimension_strategy import DimensionNoveltyStrategy  # noqa: E402

__all__ = [
    "Strategy",
    "BFS",
    "DFS",
    "Random",
    "CoverageGuided",
    "Weighted",
    "DimensionNoveltyStrategy",
]
