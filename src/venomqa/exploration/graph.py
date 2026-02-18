"""Graph - State space representation for exploration."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from typing import TYPE_CHECKING

from venomqa.exploration.transition import Transition
from venomqa.sandbox import Context, State

if TYPE_CHECKING:
    from venomqa.v1.core.action import Action


class Graph:
    """Holds all states and transitions during exploration.

    The Graph is the central data structure for exploration. It tracks:
    - All visited states (deduplicated by content hash)
    - All transitions between states
    - Which (state, action) pairs have been explored
    - Action call counts for max_calls limiting

    Key property: States are deduplicated by content. Two states with
    identical observations have the same ID and are stored once.
    This prevents exponential state explosion.

    Example::

        graph = Graph(actions=[login, create_order, cancel_order])

        # Add initial state
        initial = graph.add_state(world.observe())

        # Record a transition
        transition = Transition.create(
            from_state_id=initial.id,
            action_name="login",
            to_state_id=new_state.id,
            result=result,
        )
        graph.add_transition(transition)
    """

    def __init__(self, actions: list[Action] | None = None) -> None:
        """Initialize an empty graph.

        Args:
            actions: List of available actions for this exploration.
        """
        self._states: dict[str, State] = {}
        self._transitions: list[Transition] = []
        self._actions: dict[str, Action] = {a.name: a for a in (actions or [])}
        self._explored: set[tuple[str, str]] = set()  # (state_id, action_name)
        self._transition_keys: set[tuple[str, str, str]] = set()  # (from_id, action, to_id)
        self._initial_state_id: str | None = None
        self._action_call_counts: dict[str, int] = {}  # action_name -> call count

    @property
    def states(self) -> dict[str, State]:
        """All states in the graph, keyed by ID."""
        return self._states

    @property
    def transitions(self) -> list[Transition]:
        """All transitions in the graph."""
        return self._transitions

    @property
    def actions(self) -> dict[str, Action]:
        """All registered actions, keyed by name."""
        return self._actions

    @property
    def initial_state_id(self) -> str | None:
        """ID of the first state added to the graph."""
        return self._initial_state_id

    def add_state(self, state: State) -> State:
        """Add a state to the graph, deduplicating by content.

        If a state with the same ID (same observation content) already exists:
        - Return the existing state
        - Update checkpoint_id if the new state has one and existing doesn't

        This is key to preventing exponential state explosion.

        Returns:
            The canonical state (existing or newly added).
        """
        if self._initial_state_id is None:
            self._initial_state_id = state.id

        if state.id in self._states:
            existing = self._states[state.id]
            # If new state has checkpoint but existing doesn't, update
            if state.checkpoint_id and not existing.checkpoint_id:
                from dataclasses import replace
                updated = replace(existing, checkpoint_id=state.checkpoint_id)
                self._states[state.id] = updated
                return updated
            return existing

        self._states[state.id] = state
        return state

    def add_transition(self, transition: Transition) -> bool:
        """Add a transition and mark as explored.

        With state deduplication, the same logical transition may be attempted
        multiple times. This method deduplicates transitions.

        Returns:
            True if transition was added, False if it was a duplicate.
        """
        key = (transition.from_state_id, transition.action_name, transition.to_state_id)
        if key in self._transition_keys:
            return False

        self._transition_keys.add(key)
        self._transitions.append(transition)
        self._explored.add((transition.from_state_id, transition.action_name))

        # Track action call count (for max_calls limiting)
        action_name = transition.action_name
        self._action_call_counts[action_name] = self._action_call_counts.get(action_name, 0) + 1

        return True

    def add_action(self, action: Action) -> None:
        """Register an action."""
        self._actions[action.name] = action

    def get_state(self, state_id: str) -> State | None:
        """Get a state by ID."""
        return self._states.get(state_id)

    def get_action(self, action_name: str) -> Action | None:
        """Get an action by name."""
        return self._actions.get(action_name)

    def is_explored(self, state_id: str, action_name: str) -> bool:
        """Check if a (state, action) pair has been explored."""
        return (state_id, action_name) in self._explored

    def mark_explored(self, state_id: str, action_name: str) -> None:
        """Mark a (state, action) pair as explored without adding a transition.

        Used by the parallel exploration engine to reserve a pair before
        submitting it to a worker thread, preventing duplicate work.
        """
        self._explored.add((state_id, action_name))

    def mark_noop(self, state_id: str, action_name: str) -> None:
        """Mark a (state, action) pair as a no-op loop.

        This is called when an action from a state has been executed multiple
        times without changing the state. Future strategy picks will skip this
        pair since it's already marked as explored.
        """
        self._explored.add((state_id, action_name))

    def get_valid_actions(
        self,
        state: State,
        context: Context | None = None,
        executed_actions: set[str] | None = None,
    ) -> list[Action]:
        """Get actions whose preconditions are satisfied in this state.

        If context is provided, preconditions are evaluated against the live Context.
        If executed_actions is provided, preconditions that check for prior actions
        are evaluated against the set of already-fired action names.

        Actions with max_calls set are excluded once they've reached their limit.

        Args:
            state: The current state.
            context: Optional context for precondition evaluation.
            executed_actions: Optional set of already-executed action names.

        Returns:
            List of actions that can be executed from this state.
        """
        result = []
        for a in self._actions.values():
            # Check max_calls limit
            if a.max_calls is not None:
                call_count = self._action_call_counts.get(a.name, 0)
                if call_count >= a.max_calls:
                    continue

            # Check preconditions
            if context is not None:
                if a.can_execute_with_context(state, context, executed_actions):
                    result.append(a)
            elif a.can_execute(state):
                result.append(a)

        return result

    def get_action_call_count(self, action_name: str) -> int:
        """Get how many times an action has been called."""
        return self._action_call_counts.get(action_name, 0)

    def get_unexplored(self) -> list[tuple[State, Action]]:
        """Get all unexplored (state, action) pairs."""
        result = []
        for state in self._states.values():
            for action in self.get_valid_actions(state):
                if not self.is_explored(state.id, action.name):
                    result.append((state, action))
        return result

    def get_path_to(self, state_id: str) -> list[Transition]:
        """Get the path from initial state to the given state.

        Uses BFS to find the shortest path.

        Args:
            state_id: Target state ID.

        Returns:
            List of transitions forming the shortest path, or empty if unreachable.
        """
        if self._initial_state_id is None:
            return []

        if state_id == self._initial_state_id:
            return []

        # BFS to find shortest path
        visited = {self._initial_state_id}
        queue: deque[tuple[str, list[Transition]]] = deque([(self._initial_state_id, [])])

        # Build adjacency from transitions
        outgoing: dict[str, list[Transition]] = {}
        for t in self._transitions:
            outgoing.setdefault(t.from_state_id, []).append(t)

        while queue:
            current_id, path = queue.popleft()
            if current_id == state_id:
                return path

            for t in outgoing.get(current_id, []):
                if t.to_state_id not in visited:
                    visited.add(t.to_state_id)
                    queue.append((t.to_state_id, path + [t]))

        return []

    def iter_states(self) -> Iterator[State]:
        """Iterate over all states."""
        return iter(self._states.values())

    def iter_transitions(self) -> Iterator[Transition]:
        """Iterate over all transitions."""
        return iter(self._transitions)

    @property
    def state_count(self) -> int:
        """Number of unique states."""
        return len(self._states)

    @property
    def transition_count(self) -> int:
        """Number of transitions."""
        return len(self._transitions)

    @property
    def action_count(self) -> int:
        """Number of registered actions."""
        return len(self._actions)

    @property
    def used_action_names(self) -> set[str]:
        """Set of action names that have been executed at least once."""
        return {t.action_name for t in self._transitions}

    @property
    def used_action_count(self) -> int:
        """Number of unique actions that have been executed."""
        return len(self.used_action_names)

    @property
    def unused_action_names(self) -> list[str]:
        """List of action names that have never been executed."""
        all_names = set(self._actions.keys())
        used = self.used_action_names
        return sorted(all_names - used)

    @property
    def explored_count(self) -> int:
        """Number of explored (state, action) pairs."""
        return len(self._explored)

    @property
    def unique_transition_count(self) -> int:
        """Number of unique transitions (deduplicated)."""
        return len(self._transition_keys)


__all__ = ["Graph"]
