"""Agent module - the explorer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from venomqa.v1.core.state import State
from venomqa.v1.core.action import Action
from venomqa.v1.core.transition import Transition
from venomqa.v1.core.graph import Graph
from venomqa.v1.core.invariant import Invariant, Violation, InvariantTiming, Severity
from venomqa.v1.core.result import ExplorationResult
from venomqa.v1.agent.strategies import Strategy, BFS, DFS, Random, CoverageGuided, Weighted
from venomqa.v1.agent.scheduler import Scheduler, ScheduledRun, RunResult

if TYPE_CHECKING:
    from venomqa.v1.world import World


class Agent:
    """The state space explorer.

    The Agent explores the state graph by:
    1. Observing current state (with checkpoint for rollback)
    2. Picking an unexplored (state, action) pair via Strategy
    3. Rolling back to that state if needed
    4. Executing the action via World
    5. Observing the new state (with checkpoint)
    6. Checking all invariants
    7. Recording the transition in the Graph
    8. Repeating until no unexplored pairs remain

    The key innovation is ROLLBACK. By checkpointing each state, we can:
    - Try action A from state S, observe result
    - Roll back to S
    - Try action B from state S, observe result
    - And so on...

    This enables exhaustive exploration of the state graph.
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
        self._step_count = 0

    def explore(self) -> ExplorationResult:
        """Run full exploration and return results.

        The exploration algorithm:
        1. Observe initial state with checkpoint
        2. While unexplored (state, action) pairs exist:
           a. Pick next pair via strategy
           b. Rollback to that state
           c. Execute action
           d. Observe new state with checkpoint
           e. Check invariants
           f. Record transition
        3. Return results with graph and violations

        State deduplication: States with identical observations share the same ID.
        This prevents exponential state explosion from exploring the same
        logical state via different paths.
        """
        result = ExplorationResult(graph=self.graph)

        # Observe initial state WITH checkpoint (critical for rollback)
        initial_state = self.world.observe_and_checkpoint("initial")
        # add_state returns canonical state (may be deduplicated)
        initial_state = self.graph.add_state(initial_state)

        # Initialize strategy with initial state's valid actions
        valid_actions = self.graph.get_valid_actions(initial_state)
        if hasattr(self.strategy, "enqueue"):
            self.strategy.enqueue(initial_state, valid_actions)
        elif hasattr(self.strategy, "push"):
            self.strategy.push(initial_state, valid_actions)

        # Exploration loop
        self._step_count = 0
        while self._step_count < self.max_steps:
            transition = self._step()
            if transition is None:
                break  # No more unexplored pairs
            self._step_count += 1

        result.violations = list(self._violations)
        result.finish()
        return result

    def _step(self) -> Transition | None:
        """Execute one exploration step.

        Returns:
            The transition taken, or None if exploration is complete.
        """
        # Pick next unexplored (state, action) pair
        pick = self.strategy.pick(self.graph)
        if pick is None:
            return None

        from_state, action = pick

        # CRITICAL: Roll back to the from_state before executing
        self._rollback_to(from_state)

        # Check PRE-ACTION invariants
        self._check_invariants_with_timing(
            from_state, action, None, InvariantTiming.PRE_ACTION
        )

        # Execute action
        action_result = self.world.act(action)

        # Check response assertions
        self._check_response_assertions(from_state, action, action_result)

        # Observe new state WITH checkpoint (enables future rollback to this state)
        checkpoint_name = f"after_{action.name}_{self._step_count}"
        to_state = self.world.observe_and_checkpoint(checkpoint_name)
        # add_state returns canonical state (deduplicates if same observations)
        to_state = self.graph.add_state(to_state)

        # Record transition
        transition = Transition.create(
            from_state_id=from_state.id,
            action_name=action.name,
            to_state_id=to_state.id,
            result=action_result,
        )
        self.graph.add_transition(transition)

        # Check POST-ACTION invariants
        self._check_invariants_with_timing(
            to_state, action, transition, InvariantTiming.POST_ACTION
        )

        # Tell strategy about the new state's valid actions
        valid_actions = self.graph.get_valid_actions(to_state)
        if hasattr(self.strategy, "enqueue"):
            self.strategy.enqueue(to_state, valid_actions)
        elif hasattr(self.strategy, "push"):
            self.strategy.push(to_state, valid_actions)

        return transition

    def _rollback_to(self, target_state: State) -> None:
        """Roll back the world to a target state.

        If the target state has a checkpoint_id, we roll back directly.
        Otherwise, we must replay actions from the nearest checkpoint.
        """
        if target_state.checkpoint_id is None:
            # This shouldn't happen if we're using observe_and_checkpoint correctly
            # But handle it gracefully by replaying from initial
            self._replay_to(target_state)
            return

        # Roll back directly to the checkpoint
        self.world.rollback(target_state.checkpoint_id)

    def _replay_to(self, target_state: State) -> None:
        """Replay actions to reach target state (fallback when no checkpoint)."""
        path = self.graph.get_path_to(target_state.id)
        if not path:
            return  # Already at initial state

        # Find nearest checkpoint in path
        last_checkpoint_id = None
        replay_from = 0

        # Check initial state
        initial = self.graph.get_state(self.graph.initial_state_id or "")
        if initial and initial.checkpoint_id:
            last_checkpoint_id = initial.checkpoint_id

        for i, transition in enumerate(path):
            state = self.graph.get_state(transition.to_state_id)
            if state and state.checkpoint_id:
                last_checkpoint_id = state.checkpoint_id
                replay_from = i + 1

        # Roll back to nearest checkpoint
        if last_checkpoint_id:
            self.world.rollback(last_checkpoint_id)

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
                    # Get reproduction path (how to reach this state)
                    path = self.graph.get_path_to(state.id)
                    violation = Violation.create(
                        invariant=inv,
                        state=state,
                        action=action,
                        reproduction_path=path + [transition],
                    )
                    self._violations.append(violation)
            except Exception as e:
                # Invariant check itself failed - treat as violation
                violation = Violation.create(
                    invariant=inv,
                    state=state,
                    action=action,
                )
                # Can't modify frozen dataclass, create with error message
                self._violations.append(Violation(
                    id=violation.id,
                    invariant_name=violation.invariant_name,
                    state=violation.state,
                    message=f"Invariant check raised exception: {e}",
                    severity=violation.severity,
                    action=violation.action,
                    reproduction_path=violation.reproduction_path,
                    timestamp=violation.timestamp,
                ))

    @property
    def violations(self) -> list[Violation]:
        """Get all violations found so far."""
        return list(self._violations)

    @property
    def step_count(self) -> int:
        """Get number of exploration steps taken."""
        return self._step_count


__all__ = [
    "Agent",
    "Strategy",
    "BFS",
    "DFS",
    "Random",
    "CoverageGuided",
    "Weighted",
    "Scheduler",
    "ScheduledRun",
    "RunResult",
]
