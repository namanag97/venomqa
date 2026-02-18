"""Exploration strategies - Algorithms for traversing state space."""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections import Counter
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from venomqa.exploration.frontier import QueueFrontier, StackFrontier
from venomqa.sandbox import State

if TYPE_CHECKING:
    from venomqa.exploration.graph import Graph
    from venomqa.v1.core.action import Action


@runtime_checkable
class ExplorationStrategy(Protocol):
    """Protocol for exploration strategies.

    A strategy decides which (state, action) pair to explore next.
    Different strategies give different exploration behaviors:

    - BFS: Breadth-first, guarantees shortest paths to bugs
    - DFS: Depth-first, explores deeply before backtracking
    - Random: Random selection, good for fuzzing
    - CoverageGuided: Prioritizes least-explored actions
    - MCTS: Monte Carlo Tree Search (coming soon)

    Example::

        class MyStrategy:
            def pick(self, graph: Graph) -> tuple[State, Action] | None:
                # Return the next pair to explore, or None if done
                unexplored = graph.get_unexplored()
                return unexplored[0] if unexplored else None

            def notify(self, state: State, actions: list[Action]) -> None:
                # Called when a new state is discovered
                pass
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


# Backward compatibility alias
Strategy = ExplorationStrategy


class BaseStrategy(ABC):
    """Base class for strategy implementations."""

    @abstractmethod
    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        """Pick the next (state, action) pair to explore."""
        ...

    def notify(self, state: State, actions: list[Action]) -> None:
        """Notify strategy of a new state and its valid actions.

        Default implementation does nothing. Override in subclasses
        that maintain internal state (queues, stacks, etc.).
        """
        pass


class BFS(BaseStrategy):
    """Breadth-first search strategy.

    Explores states in the order they were discovered.
    Guarantees shortest paths to each state (and thus shortest
    reproduction paths for bugs).

    Uses a queue-based frontier internally.
    """

    def __init__(self) -> None:
        self._frontier = QueueFrontier()
        self._initialized = False

    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        # Initialize frontier with initial state actions
        if not self._initialized:
            self._initialized = True
            if graph.initial_state_id:
                initial = graph.get_state(graph.initial_state_id)
                if initial:
                    for action in graph.get_valid_actions(initial):
                        self._frontier.add(initial.id, action.name)

        # Process frontier
        while not self._frontier.is_empty():
            pair = self._frontier.pop()
            if pair is None:
                break

            state_id, action_name = pair
            if graph.is_explored(state_id, action_name):
                continue

            state = graph.get_state(state_id)
            action = graph.get_action(action_name)
            if state and action and action.can_execute(state):
                return (state, action)

        # Frontier empty, look for any unexplored pairs
        unexplored = graph.get_unexplored()
        if unexplored:
            return unexplored[0]

        return None

    def notify(self, state: State, actions: list[Action]) -> None:
        """Add new state's actions to the frontier."""
        for action in actions:
            self._frontier.add(state.id, action.name)


class DFS(BaseStrategy):
    """Depth-first search strategy.

    Explores as deep as possible before backtracking.
    Uses less memory than BFS but doesn't guarantee shortest paths.

    Uses a stack-based frontier internally.
    """

    def __init__(self) -> None:
        self._frontier = StackFrontier()
        self._initialized = False

    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        # Initialize frontier with initial state actions
        if not self._initialized:
            self._initialized = True
            if graph.initial_state_id:
                initial = graph.get_state(graph.initial_state_id)
                if initial:
                    for action in reversed(graph.get_valid_actions(initial)):
                        self._frontier.add(initial.id, action.name)

        # Process frontier
        while not self._frontier.is_empty():
            pair = self._frontier.pop()
            if pair is None:
                break

            state_id, action_name = pair
            if graph.is_explored(state_id, action_name):
                continue

            state = graph.get_state(state_id)
            action = graph.get_action(action_name)
            if state and action and action.can_execute(state):
                return (state, action)

        # Frontier empty, look for any unexplored pairs
        unexplored = graph.get_unexplored()
        if unexplored:
            return unexplored[0]

        return None

    def notify(self, state: State, actions: list[Action]) -> None:
        """Add new state's actions to the frontier."""
        # Add in reverse order so first action is on top
        for action in reversed(actions):
            self._frontier.add(state.id, action.name)


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
        self._action_counts.clear()
        for transition in graph.iter_transitions():
            self._action_counts[transition.action_name] += 1

        # Sort unexplored pairs by action exploration count (ascending)
        def score(pair: tuple[State, Action]) -> int:
            return self._action_counts[pair[1].name]

        unexplored.sort(key=score)
        return unexplored[0]


class Weighted(BaseStrategy):
    """Weighted random exploration strategy.

    Allows assigning weights to actions to control exploration priority.
    Higher weight = more likely to be picked.

    Example::

        strategy = Weighted(weights={"login": 1.0, "create_order": 2.0})
        # create_order is twice as likely to be picked as login
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


__all__ = [
    "ExplorationStrategy",
    "Strategy",  # Backward compat alias
    "BaseStrategy",
    "BFS",
    "DFS",
    "Random",
    "CoverageGuided",
    "Weighted",
]
