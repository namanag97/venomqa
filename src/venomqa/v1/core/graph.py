"""Graph class for state space exploration."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator

from venomqa.v1.core.action import Action
from venomqa.v1.core.context import Context
from venomqa.v1.core.state import State
from venomqa.v1.core.transition import Transition


class Graph:
    """Holds all states and transitions during exploration.

    The graph tracks:
    - All visited states
    - All transitions between states
    - Which (state, action) pairs have been explored
    """

    def __init__(self, actions: list[Action] | None = None) -> None:
        self._states: dict[str, State] = {}
        self._transitions: list[Transition] = []
        self._actions: dict[str, Action] = {a.name: a for a in (actions or [])}
        self._explored: set[tuple[str, str]] = set()  # (state_id, action_name)
        self._transition_keys: set[tuple[str, str, str]] = set()  # (from_id, action, to_id)
        self._initial_state_id: str | None = None
        self._action_call_counts: dict[str, int] = {}  # action_name -> call count

    @property
    def states(self) -> dict[str, State]:
        return self._states

    @property
    def transitions(self) -> list[Transition]:
        return self._transitions

    @property
    def actions(self) -> dict[str, Action]:
        return self._actions

    @property
    def initial_state_id(self) -> str | None:
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
                # Create updated state with checkpoint (frozen dataclass)
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
            # Duplicate transition - already recorded
            return False

        self._transition_keys.add(key)
        self._transitions.append(transition)
        self._explored.add((transition.from_state_id, transition.action_name))
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

    def get_valid_actions(
        self,
        state: State,
        context: Context | None = None,
        executed_actions: set[str] | None = None,
    ) -> list[Action]:
        """Get actions whose preconditions are satisfied in this state.

        If context is provided, preconditions created with precondition_has_context()
        are evaluated against the live Context.

        If executed_actions is provided, preconditions created with
        precondition_action_ran() are evaluated against the set of already-fired
        action names.

        Without these optional arguments, all preconditions pass (backward-compatible).
        """
        if context is not None:
            return [
                a for a in self._actions.values()
                if a.can_execute_with_context(state, context, executed_actions)
            ]
        return [a for a in self._actions.values() if a.can_execute(state)]

    def get_unexplored(self) -> list[tuple[State, Action]]:
        """Get all unexplored (state, action) pairs."""
        result = []
        for state in self._states.values():
            for action in self.get_valid_actions(state):
                if not self.is_explored(state.id, action.name):
                    result.append((state, action))
        return result

    def get_path_to(self, state_id: str) -> list[Transition]:
        """Get the path from initial state to the given state."""
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
        return len(self._states)

    @property
    def transition_count(self) -> int:
        return len(self._transitions)

    @property
    def action_count(self) -> int:
        return len(self._actions)

    @property
    def used_action_names(self) -> set[str]:
        """Set of action names that have been executed at least once."""
        return {t.action_name for t in self._transitions}

    @property
    def used_action_count(self) -> int:
        """Number of unique actions that have been executed at least once."""
        return len(self.used_action_names)

    @property
    def unused_action_names(self) -> list[str]:
        """List of action names that have never been executed.

        Useful for debugging coverage issues - shows which actions DFS/BFS
        never reached, even after many steps.
        """
        all_names = set(self._actions.keys())
        used = self.used_action_names
        return sorted(all_names - used)

    @property
    def explored_count(self) -> int:
        return len(self._explored)

    @property
    def unique_transition_count(self) -> int:
        """Number of unique transitions (deduplicated)."""
        return len(self._transition_keys)
