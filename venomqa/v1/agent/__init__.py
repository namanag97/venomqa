"""Agent module - the explorer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from venomqa.v1.core.state import State
from venomqa.v1.core.action import Action
from venomqa.v1.core.transition import Transition
from venomqa.v1.core.graph import Graph
from venomqa.v1.core.invariant import Invariant, Violation
from venomqa.v1.core.result import ExplorationResult
from venomqa.v1.agent.strategies import Strategy, BFS, DFS, Random

if TYPE_CHECKING:
    from venomqa.v1.world import World


class Agent:
    """The state space explorer.

    The agent explores by:
    1. Observing current state
    2. Picking next action via Strategy
    3. Executing action via World
    4. Recording transition in Graph
    5. Checking invariants
    6. Rolling back if needed
    7. Repeating until done
    """

    def __init__(
        self,
        world: "World",
        actions: list[Action],
        invariants: list[Invariant] | None = None,
        strategy: Strategy | None = None,
        max_steps: int = 1000,
    ) -> None:
        self.world = world
        self.graph = Graph(actions)
        self.invariants = invariants or []
        self.strategy = strategy or BFS()
        self.max_steps = max_steps
        self._violations: list[Violation] = []

    def explore(self) -> ExplorationResult:
        """Run full exploration and return results."""
        result = ExplorationResult(graph=self.graph)

        # Get initial state
        initial_state = self.world.observe()
        self.graph.add_state(initial_state)

        # Create initial checkpoint
        initial_cp = self.world.checkpoint("initial")

        steps = 0
        while steps < self.max_steps:
            step_result = self._step()
            if step_result is None:
                break
            steps += 1

        result.violations = list(self._violations)
        result.finish()
        return result

    def _step(self) -> Transition | None:
        """Execute one exploration step."""
        # Pick next (state, action) pair
        pick = self.strategy.pick(self.graph)
        if pick is None:
            return None

        from_state, action = pick

        # Navigate to the from_state if needed
        self._navigate_to(from_state)

        # Execute action
        action_result = self.world.act(action)

        # Observe new state
        to_state = self.world.observe()
        self.graph.add_state(to_state)

        # Record transition
        transition = Transition.create(
            from_state_id=from_state.id,
            action_name=action.name,
            to_state_id=to_state.id,
            result=action_result,
        )
        self.graph.add_transition(transition)

        # Check invariants
        self._check_invariants(to_state, action, transition)

        # Update strategy with new state
        if hasattr(self.strategy, "enqueue"):
            self.strategy.enqueue(to_state, self.graph.get_valid_actions(to_state))
        elif hasattr(self.strategy, "push"):
            self.strategy.push(to_state, self.graph.get_valid_actions(to_state))

        return transition

    def _navigate_to(self, target_state: State) -> None:
        """Navigate to a state by rolling back and replaying."""
        # Find checkpoint closest to target
        if target_state.checkpoint_id:
            self.world.rollback(target_state.checkpoint_id)
            return

        # Otherwise, roll back to initial and replay path
        path = self.graph.get_path_to(target_state.id)
        if not path:
            return  # Already at initial state

        # Find the nearest checkpoint in the path
        last_checkpoint_id = None
        replay_from = 0

        for i, transition in enumerate(path):
            state = self.graph.get_state(transition.to_state_id)
            if state and state.checkpoint_id:
                last_checkpoint_id = state.checkpoint_id
                replay_from = i + 1

        if last_checkpoint_id:
            self.world.rollback(last_checkpoint_id)
        else:
            # Roll back to initial
            initial = self.graph.get_state(self.graph.initial_state_id or "")
            if initial and initial.checkpoint_id:
                self.world.rollback(initial.checkpoint_id)

        # Replay remaining actions
        for transition in path[replay_from:]:
            action = self.graph.get_action(transition.action_name)
            if action:
                self.world.act(action)

    def _check_invariants(
        self,
        state: State,
        action: Action,
        transition: Transition,
    ) -> None:
        """Check all invariants and record violations."""
        for inv in self.invariants:
            try:
                if not inv.check(self.world):
                    path = self.graph.get_path_to(state.id)
                    violation = Violation.create(
                        invariant=inv,
                        state=state,
                        action=action,
                        reproduction_path=path + [transition],
                    )
                    self._violations.append(violation)
            except Exception as e:
                # Invariant check itself failed
                violation = Violation.create(
                    invariant=inv,
                    state=state,
                    action=action,
                )
                violation.message = f"Invariant check failed: {e}"
                self._violations.append(violation)


__all__ = [
    "Agent",
    "Strategy",
    "BFS",
    "DFS",
    "Random",
]
