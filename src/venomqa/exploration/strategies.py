"""Exploration strategies - Algorithms for traversing state space."""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from collections import Counter, deque
from dataclasses import dataclass, field
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
    - MCTS: Monte Carlo Tree Search, balances exploration/exploitation

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

    @property
    def _queue(self) -> deque:
        """Backward compatibility: expose internal queue."""
        return self._frontier._queue

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

    def enqueue(self, state: State, actions: list[Action]) -> None:
        """Backward compatibility alias for notify."""
        self.notify(state, actions)


class DFS(BaseStrategy):
    """Depth-first search strategy.

    Explores as deep as possible before backtracking.
    Uses less memory than BFS but doesn't guarantee shortest paths.

    Uses a stack-based frontier internally.
    """

    def __init__(self) -> None:
        self._frontier = StackFrontier()
        self._initialized = False

    @property
    def _stack(self) -> list:
        """Backward compatibility: expose internal stack."""
        return self._frontier._stack

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

    def push(self, state: State, actions: list[Action]) -> None:
        """Backward compatibility alias for notify."""
        self.notify(state, actions)


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


@dataclass
class _MCTSNode:
    """Internal node for Monte Carlo Tree Search.

    Each node represents a (state_id, action_name) pair with statistics
    about how many times it was visited and how much reward it accumulated.
    """

    state_id: str
    action_name: str
    visits: int = 0
    reward: float = 0.0
    children: list[_MCTSNode] = field(default_factory=list)
    parent: _MCTSNode | None = field(default=None, repr=False)

    @property
    def value(self) -> float:
        """Average reward per visit."""
        if self.visits == 0:
            return 0.0
        return self.reward / self.visits


class MCTS(BaseStrategy):
    """Monte Carlo Tree Search strategy.

    Uses UCB1 (Upper Confidence Bound) to balance exploration vs exploitation.
    Nodes that led to violations (bugs) get higher reward, encouraging the
    search to focus on bug-producing regions of the state space while still
    exploring new areas.

    The MCTS loop:
    1. **Selection**: Walk the tree using UCB1 to pick the most promising node.
    2. **Expansion**: If the selected node has unexplored children, pick one.
    3. **Simulation**: (Lightweight) Evaluate the node by checking if it led
       to new states or violations.
    4. **Backpropagation**: Update visit counts and rewards up the tree.

    Args:
        exploration_weight: Controls exploration vs exploitation tradeoff.
            Higher values explore more. Default sqrt(2) is theoretically optimal.
        violation_reward: Reward given when a violation is found. Default 10.0.
        new_state_reward: Reward for discovering a previously unseen state.
            Default 1.0.
        seed: Random seed for reproducibility.

    Example::

        strategy = MCTS(exploration_weight=1.5)
        agent = Agent(
            world=world,
            actions=actions,
            invariants=invariants,
            strategy=strategy,
        )
        result = agent.explore()
    """

    def __init__(
        self,
        exploration_weight: float = math.sqrt(2),
        violation_reward: float = 10.0,
        new_state_reward: float = 1.0,
        seed: int | None = None,
    ) -> None:
        self._exploration_weight = exploration_weight
        self._violation_reward = violation_reward
        self._new_state_reward = new_state_reward
        self._rng = random.Random(seed)
        # Tree: state_id -> list of child nodes
        self._nodes: dict[str, list[_MCTSNode]] = {}
        # Track all nodes for backpropagation
        self._all_nodes: dict[tuple[str, str], _MCTSNode] = {}
        self._last_picked: _MCTSNode | None = None
        self._known_states: set[str] = set()
        self._initialized = False

    def pick(self, graph: Graph) -> tuple[State, Action] | None:
        """Pick the next (state, action) pair using UCB1 selection.

        Args:
            graph: The current exploration graph.

        Returns:
            A (state, action) tuple to explore, or None if done.
        """
        # Initialize tree on first call
        if not self._initialized:
            self._initialized = True
            if graph.initial_state_id:
                initial = graph.get_state(graph.initial_state_id)
                if initial:
                    self._known_states.add(initial.id)
                    self._expand_node(graph, initial.id)

        # Get all unexplored pairs first
        unexplored = graph.get_unexplored()
        if not unexplored:
            return None

        # Build a set for fast lookup
        unexplored_set = {(s.id, a.name) for s, a in unexplored}

        # Selection: find best node via UCB1
        best_node = self._select(graph, unexplored_set)

        if best_node is None:
            # Fallback to random unexplored
            choice = self._rng.choice(unexplored)
            state, action = choice
            # Create node if needed
            key = (state.id, action.name)
            if key not in self._all_nodes:
                node = _MCTSNode(state_id=state.id, action_name=action.name)
                self._all_nodes[key] = node
                self._nodes.setdefault(state.id, []).append(node)
            self._last_picked = self._all_nodes[key]
            return choice

        # Resolve to actual state and action
        state = graph.get_state(best_node.state_id)
        action = graph.get_action(best_node.action_name)

        if state and action:
            self._last_picked = best_node
            return (state, action)

        # Shouldn't happen, but fall back
        if unexplored:
            return self._rng.choice(unexplored)
        return None

    def notify(self, state: State, actions: list[Action]) -> None:
        """Notify MCTS of a new state, triggering backpropagation and expansion.

        Args:
            state: The newly observed state.
            actions: Actions valid from this state.
        """
        is_new = state.id not in self._known_states
        self._known_states.add(state.id)

        # Expand this new state's children
        if is_new:
            for action in actions:
                key = (state.id, action.name)
                if key not in self._all_nodes:
                    node = _MCTSNode(
                        state_id=state.id,
                        action_name=action.name,
                        parent=self._last_picked,
                    )
                    self._all_nodes[key] = node
                    self._nodes.setdefault(state.id, []).append(node)
                    if self._last_picked:
                        self._last_picked.children.append(node)

        # Backpropagate reward for new state discovery
        if self._last_picked and is_new:
            self._backpropagate(self._last_picked, self._new_state_reward)

    def record_violation(self) -> None:
        """Record that the last picked action led to a violation.

        Called externally (by Agent) when a violation is found, so MCTS
        can reward the path that led to the bug.
        """
        if self._last_picked:
            self._backpropagate(self._last_picked, self._violation_reward)

    def _expand_node(self, graph: Graph, state_id: str) -> None:
        """Expand a state node, creating child nodes for valid actions."""
        state = graph.get_state(state_id)
        if not state:
            return

        for action in graph.get_valid_actions(state):
            key = (state_id, action.name)
            if key not in self._all_nodes:
                node = _MCTSNode(state_id=state_id, action_name=action.name)
                self._all_nodes[key] = node
                self._nodes.setdefault(state_id, []).append(node)

    def _select(
        self,
        graph: Graph,
        unexplored_set: set[tuple[str, str]],
    ) -> _MCTSNode | None:
        """Select the best unexplored node using UCB1.

        Args:
            graph: The exploration graph.
            unexplored_set: Set of (state_id, action_name) pairs not yet explored.

        Returns:
            The best node to explore, or None if no valid node found.
        """
        best_node: _MCTSNode | None = None
        best_ucb: float = -float("inf")

        # Total visits across all nodes for UCB1 denominator
        total_visits = sum(n.visits for n in self._all_nodes.values())
        if total_visits == 0:
            total_visits = 1

        for key, node in self._all_nodes.items():
            if key not in unexplored_set:
                continue

            ucb = self._ucb1(node, total_visits)
            if ucb > best_ucb:
                best_ucb = ucb
                best_node = node

        return best_node

    def _ucb1(self, node: _MCTSNode, total_visits: int) -> float:
        """Compute UCB1 score for a node.

        UCB1 = (reward / visits) + C * sqrt(ln(total) / visits)

        Unvisited nodes get infinite score (always explored first).

        Args:
            node: The node to score.
            total_visits: Total visits across all nodes.

        Returns:
            UCB1 score.
        """
        if node.visits == 0:
            return float("inf")

        exploitation = node.value
        exploration = self._exploration_weight * math.sqrt(
            math.log(total_visits) / node.visits
        )
        return exploitation + exploration

    def _backpropagate(self, node: _MCTSNode, reward: float) -> None:
        """Propagate reward up the tree from node to root.

        Args:
            node: The leaf node where the reward originated.
            reward: The reward value to propagate.
        """
        current: _MCTSNode | None = node
        while current is not None:
            current.visits += 1
            current.reward += reward
            current = current.parent


__all__ = [
    "ExplorationStrategy",
    "Strategy",  # Backward compat alias
    "BaseStrategy",
    "BFS",
    "DFS",
    "Random",
    "CoverageGuided",
    "Weighted",
    "MCTS",
]
