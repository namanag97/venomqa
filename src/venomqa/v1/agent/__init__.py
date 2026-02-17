"""Agent module - the explorer."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from venomqa.v1.agent.scheduler import RunResult, ScheduledRun, Scheduler
from venomqa.v1.agent.strategies import BFS, DFS, CoverageGuided, Random, Strategy, Weighted
from venomqa.v1.core.action import Action, ActionResult
from venomqa.v1.core.graph import Graph
from venomqa.v1.core.invariant import Invariant, InvariantTiming, Severity, Violation
from venomqa.v1.core.result import ExplorationResult
from venomqa.v1.core.state import State
from venomqa.v1.core.transition import Transition

if TYPE_CHECKING:
    from venomqa.v1.adapters.resource_graph import ResourceGraph
    from venomqa.v1.core.hypergraph import Hypergraph
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
        world: World,
        actions: list[Action],
        invariants: list[Invariant] | None = None,
        strategy: Strategy | None = None,
        max_steps: int = 1000,
        hypergraph: bool = False,
        coverage_target: float | None = None,
        progress_every: int = 0,
        shrink: bool = False,
    ) -> None:
        self.world = world
        self.graph = Graph(actions)
        self.invariants = invariants or []
        self.strategy = strategy or BFS()
        self.max_steps = max_steps
        self.coverage_target = coverage_target  # 0.0–1.0; stop when action coverage >= this
        self.progress_every = progress_every    # print progress line every N steps (0 = off)
        self.shrink = shrink                    # if True, shrink violation paths after finding them
        self._violations: list[Violation] = []
        self._step_count = 0

        # Loop detection: track (state_id, action_name) -> count of times it led to same state
        # If the same action from the same state repeatedly produces no state change, it's a loop.
        self._noop_counts: dict[tuple[str, str], int] = {}
        self._max_noop_per_action = 3  # Skip action after this many no-ops from same state

        # ── Guard: PostgresAdapter + BFS/CoverageGuided crash mid-run ───────
        # PostgreSQL SAVEPOINTs are destroyed when you ROLLBACK TO an earlier
        # one. BFS and CoverageGuided need arbitrary rollback, so they'll crash
        # with "savepoint does not exist" after the first multi-hop rollback.
        # DFS only ever rolls back to the most recent savepoint — safe.
        self._check_strategy_adapter_compatibility()

        # Hypergraph support (opt-in)
        self._use_hypergraph = hypergraph
        self._hypergraph: Hypergraph | None = None
        if hypergraph:
            from venomqa.v1.core.hypergraph import Hypergraph
            self._hypergraph = Hypergraph()

    def _check_strategy_adapter_compatibility(self) -> None:
        """Fail fast if PostgresAdapter is paired with a non-DFS strategy.

        PostgreSQL SAVEPOINTs are stack-based: ROLLBACK TO S1 destroys all
        savepoints created after S1. BFS and similar strategies need to roll
        back to arbitrary earlier states, which silently destroys intermediate
        savepoints and then crashes when those savepoints are later referenced.

        DFS is safe because it always rolls back to the most recently created
        savepoint (LIFO order).
        """
        from venomqa.v1.agent.strategies import BFS, CoverageGuided, Weighted

        non_dfs_types = (BFS, CoverageGuided, Weighted)
        if not isinstance(self.strategy, non_dfs_types):
            return  # DFS, Random, DimensionNovelty — all fine

        # Check if any registered system is a PostgresAdapter
        for name, system in self.world.systems.items():
            # Avoid importing postgres here to keep the check lightweight
            type_name = type(system).__name__
            if type_name == "PostgresAdapter":
                strategy_name = type(self.strategy).__name__
                raise ValueError(
                    f"Incompatible strategy + adapter: {strategy_name} + PostgresAdapter ('{name}').\n"
                    "\n"
                    "PostgreSQL SAVEPOINTs are stack-based — ROLLBACK TO an earlier savepoint\n"
                    "destroys all later savepoints. BFS/CoverageGuided/Weighted need arbitrary\n"
                    "rollback and will crash mid-run with 'savepoint does not exist'.\n"
                    "\n"
                    "Solutions:\n"
                    "  1. Use DFS() strategy (safe with PostgresAdapter — rolls back in LIFO order):\n"
                    "         Agent(world=world, actions=actions, strategy=DFS())\n"
                    "  2. Use SQLiteAdapter for local testing (supports arbitrary rollback).\n"
                    "  3. Use MockHTTPServer for in-process mock APIs (zero DB dependency).\n"
                    "  4. Use Random() strategy with a low max_steps (each run is independent).\n"
                )

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
        _exhausted = False  # Set True when strategy returns None (exploration complete)

        try:
            # Run user-defined setup (DB seeding, auth bootstrap, etc.)
            self.world.run_setup()

            # ── CRITICAL: No systems = no state exploration ──────────────────
            # Without a database/system to rollback, VenomQA cannot explore
            # different branches. Every state hashes identically.
            # Allow bypass if state_from_context was explicitly set (even to []).
            if not self.world.systems and not self.world._state_from_context_explicit:
                raise ValueError(
                    "\n"
                    "=" * 70 + "\n"
                    "CRITICAL: No database/systems registered in World\n"
                    "=" * 70 + "\n"
                    "\n"
                    "VenomQA explores state graphs by ROLLING BACK the database.\n"
                    "Without a database connection, it cannot:\n"
                    "  - Checkpoint state after each action\n"
                    "  - Rollback to explore different branches\n"
                    "  - Distinguish different states (all states look identical)\n"
                    "\n"
                    "Choose ONE of these options:\n"
                    "\n"
                    "  # Option 1: PostgreSQL (full exploration with DB rollback)\n"
                    "  from venomqa import World\n"
                    "  from venomqa.adapters.http import HttpClient\n"
                    "  from venomqa.adapters.postgres import PostgresAdapter\n"
                    "  \n"
                    "  api = HttpClient('http://localhost:8000')\n"
                    "  db = PostgresAdapter('postgresql://user:pass@localhost/mydb')\n"
                    "  world = World(api=api, systems={'db': db})\n"
                    "\n"
                    "  # Option 2: Context-based state (no DB required)\n"
                    "  # VenomQA tracks these context keys to distinguish states.\n"
                    "  # When values change, it sees a new state.\n"
                    "  from venomqa.v1 import World\n"
                    "  from venomqa.v1.adapters.http import HttpClient\n"
                    "  \n"
                    "  world = World(\n"
                    "      api=HttpClient('http://localhost:8000'),\n"
                    "      state_from_context=['connection_id', 'user_id', 'item_count'],\n"
                    "  )\n"
                    "\n"
                    "  # Option 3: SQLite (works with BFS, DFS, all strategies)\n"
                    "  from venomqa.v1 import World\n"
                    "  from venomqa.v1.adapters.http import HttpClient\n"
                    "  from venomqa.v1.adapters.sqlite import SQLiteAdapter\n"
                    "  \n"
                    "  world = World(api=api, systems={'db': SQLiteAdapter('/path/to/api.db')})\n"
                    "\n"
                    "=" * 70
                )

            # Observe initial state WITH checkpoint (critical for rollback)
            initial_state = self.world.observe_and_checkpoint("initial")
            # add_state returns canonical state (may be deduplicated)
            initial_state = self.graph.add_state(initial_state)

            # Register initial state in hypergraph if enabled
            if self._hypergraph is not None:
                self._register_hyperedge(initial_state)

            # Initialize strategy with initial state's valid actions
            valid_actions = self._get_valid_actions(initial_state)

            # ── Sanity check #2: warn if all actions are valid from step 0 ──
            # This usually means context IDs were pre-seeded in setup() so
            # every precondition passes immediately, making exploration shallow.
            _action_count = len(self.graph.actions)
            if _action_count > 5 and len(valid_actions) == _action_count:
                warnings.warn(
                    f"All {_action_count} actions are valid from the initial state. "
                    "This often means you pre-seeded IDs (e.g. connection_id, user_id) "
                    "in World.setup() or in context before exploration. "
                    "Set those values inside action functions instead so VenomQA can "
                    "discover which actions are actually reachable from each state.",
                    stacklevel=3,
                )

            if hasattr(self.strategy, "enqueue"):
                self.strategy.enqueue(initial_state, valid_actions)
            elif hasattr(self.strategy, "push"):
                self.strategy.push(initial_state, valid_actions)

            # Exploration loop
            self._step_count = 0
            _exhausted = False
            while self._step_count < self.max_steps:
                # Check coverage_target early-exit
                if self.coverage_target is not None and len(self.graph.actions) > 0:
                    used = self.graph.used_action_count
                    total = len(self.graph.actions)
                    if used / total >= self.coverage_target:
                        _exhausted = True
                        break

                transition = self._step()
                if transition is None:
                    _exhausted = True
                    break  # No more unexplored pairs
                self._step_count += 1

                # Real-time progress output (opt-in via progress_every > 0)
                if self.progress_every > 0 and self._step_count % self.progress_every == 0:
                    _cov = 0.0
                    if len(self.graph.actions) > 0:
                        _cov = self.graph.used_action_count / len(self.graph.actions) * 100
                    print(
                        f"  step {self._step_count}/{self.max_steps} | "
                        f"states {len(self.graph.states)} | "
                        f"coverage {_cov:.0f}% | "
                        f"violations {len(self._violations)}",
                        flush=True,
                    )

        finally:
            # Close registered systems (DB connections, etc.) even if exploration crashes
            for _, system in self.world.systems.items():
                if hasattr(system, "close"):
                    try:
                        system.close()
                    except Exception:
                        pass  # Best-effort cleanup; don't mask the original error

            # Run user-defined teardown (delete test data, revoke tokens, etc.)
            try:
                self.world.run_teardown()
            except Exception:
                pass  # Best-effort; don't mask exploration errors

        result.violations = list(self._violations)
        result.truncated_by_max_steps = not _exhausted
        result.finish()

        # Attach dimension coverage if hypergraph was used
        if self._hypergraph is not None:
            from venomqa.v1.core.coverage import DimensionCoverage
            result.dimension_coverage = DimensionCoverage.from_hypergraph(self._hypergraph)

        # ── CRITICAL: Warn about unused actions ──────────────────────────────
        # If exploration was truncated AND actions were never executed,
        # this is a silent coverage failure that users need to know about.
        unused = result.unused_actions
        if result.truncated_by_max_steps and unused:
            used_count = len(self.graph.actions) - len(unused)
            total_count = len(self.graph.actions)
            coverage_pct = (used_count / total_count * 100) if total_count else 100

            # Print loud warning to stderr
            import sys
            print("\n" + "=" * 70, file=sys.stderr)
            print("COVERAGE WARNING: Actions never executed", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            print(f"  {len(unused)}/{total_count} actions ({100 - coverage_pct:.0f}%) were NEVER run:", file=sys.stderr)
            # Show first 10 unused actions
            for name in unused[:10]:
                print(f"    - {name}", file=sys.stderr)
            if len(unused) > 10:
                print(f"    ... and {len(unused) - 10} more", file=sys.stderr)
            print(file=sys.stderr)
            print("Possible fixes:", file=sys.stderr)
            print("  1. Use CoverageGuided() strategy instead of DFS()", file=sys.stderr)
            print("  2. Add state_from_context=['connection_id', ...] to World", file=sys.stderr)
            print("     (When these context keys change, VenomQA sees new states)", file=sys.stderr)
            print("  3. Add preconditions to chain actions: Action(preconditions=['create_x'])", file=sys.stderr)
            print("=" * 70 + "\n", file=sys.stderr)

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

        # Check PRE-ACTION invariants (no action_result yet)
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

        # Register in hypergraph if enabled
        if self._hypergraph is not None:
            self._register_hyperedge(to_state)

        # Record transition
        transition = Transition.create(
            from_state_id=from_state.id,
            action_name=action.name,
            to_state_id=to_state.id,
            result=action_result,
        )
        self.graph.add_transition(transition)

        # ── LOOP DETECTION ─────────────────────────────────────────────────
        # If this action didn't change state (from_state == to_state), track it.
        # After N repetitions, warn and mark this (state, action) as a loop.
        if from_state.id == to_state.id:
            key = (from_state.id, action.name)
            self._noop_counts[key] = self._noop_counts.get(key, 0) + 1
            count = self._noop_counts[key]
            if count == self._max_noop_per_action:
                warnings.warn(
                    f"Loop detected: '{action.name}' from state {from_state.id[:8]} "
                    f"has been called {count} times without changing state. "
                    "This action likely needs a precondition= guard to prevent "
                    "re-execution when it has no effect. The action will be "
                    "skipped from this state in future picks.",
                    stacklevel=3,
                )
                # Mark this (state, action) as explored to prevent future picks
                self.graph.mark_noop(from_state.id, action.name)

        # Check POST-ACTION invariants (pass action_result for richer violation info)
        self._check_invariants_with_timing(
            to_state, action, transition, InvariantTiming.POST_ACTION,
            action_result=action_result,
        )

        # Tell strategy about the new state's valid actions (context, action-dependency, and resource-aware)
        valid_actions = self._get_valid_actions(to_state)
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
        """Check all POST_ACTION invariants and record violations.

        Deprecated: Use _check_invariants_with_timing instead.
        """
        self._check_invariants_with_timing(
            state, action, transition, InvariantTiming.POST_ACTION
        )

    def _check_invariants_with_timing(
        self,
        state: State,
        action: Action,
        transition: Transition | None,
        timing: InvariantTiming,
        action_result: ActionResult | None = None,
    ) -> None:
        """Check invariants with specified timing and record violations."""
        for inv in self.invariants:
            # Check if this invariant should be checked at this timing
            should_check = (
                inv.timing == timing or
                inv.timing == InvariantTiming.BOTH
            )
            if not should_check:
                continue

            try:
                if not inv.check(self.world):
                    # Get reproduction path (how to reach this state)
                    path = self.graph.get_path_to(state.id)
                    repro_path = path + [transition] if transition else path
                    violation = Violation.create(
                        invariant=inv,
                        state=state,
                        action=action,
                        reproduction_path=repro_path,
                        action_result=action_result,
                    )
                    # Optionally shrink the reproduction path to its minimum
                    if self.shrink and len(repro_path) > 1:
                        violation = self._shrink_violation(violation)
                    self._violations.append(violation)
            except Exception as e:
                # Invariant check itself failed - treat as violation
                self._violations.append(Violation(
                    id=f"v_{state.id[:8]}_{inv.name}",
                    invariant_name=inv.name,
                    state=state,
                    message=f"Invariant check raised exception: {e}",
                    severity=inv.severity,
                    action=action,
                    reproduction_path=[],
                    timestamp=state.created_at,
                ))

    def _check_response_assertions(
        self,
        state: State,
        action: Action,
        result: ActionResult,
    ) -> None:
        """Check action's response assertions and record violations."""
        from venomqa.v1.core.action import ActionResult

        passed, message = action.validate_result(result)
        if not passed:
            # Create a synthetic invariant for the violation
            self._violations.append(Violation(
                id=f"v_{state.id[:8]}_{action.name}_response",
                invariant_name=f"{action.name}_response_assertion",
                state=state,
                message=message,
                severity=Severity.HIGH,
                action=action,
                reproduction_path=self.graph.get_path_to(state.id),
                timestamp=result.timestamp,
            ))

    def _shrink_violation(self, violation: Violation) -> Violation:
        """Delta-debug the violation's reproduction path to find the minimal sequence.

        Iteratively removes steps from the path and re-tests whether the same
        invariant still fires. Repeats until no further reduction is possible.

        The world is saved/restored around the entire shrink process so that
        exploration can resume from exactly where it left off.

        Returns the original violation if shrinking is impossible or fails.
        """
        original_path = list(violation.reproduction_path)
        if len(original_path) <= 1:
            return violation

        # Save world state so we can restore after shrinking
        try:
            save_cp = self.world.checkpoint("_shrink_save")
        except Exception:
            return violation  # can't checkpoint → skip shrinking

        try:
            path = original_path
            changed = True
            while changed and len(path) > 1:
                changed = False
                for i in range(len(path)):
                    candidate = path[:i] + path[i + 1:]
                    if candidate and self._test_path_fires(candidate, violation.invariant_name):
                        path = candidate
                        changed = True
                        break  # restart inner loop with shorter path

            if len(path) == len(original_path):
                return violation  # no reduction achieved

            # Rebuild violation with shorter path
            from dataclasses import replace
            shrunk = replace(
                violation,
                reproduction_path=path,
                message=(
                    violation.message
                    + f"  [Path shrunk from {len(original_path)} → {len(path)} step(s)]"
                ),
            )
            return shrunk

        except Exception:
            return violation  # shrinking failed — return original

        finally:
            # Always restore world so exploration can continue
            try:
                self.world.rollback(save_cp)
            except Exception:
                pass

    def _test_path_fires(self, transitions: list[Transition], inv_name: str) -> bool:
        """Execute a sequence of transitions and check if the named invariant fires.

        Rolls back to the initial state before replaying. Used by _shrink_violation.

        Returns True if the invariant returns False (i.e. violation triggered).
        """
        # Roll back to initial state
        initial = self.graph.get_state(self.graph.initial_state_id or "")
        if initial is None or initial.checkpoint_id is None:
            return False
        try:
            self.world.rollback(initial.checkpoint_id)
        except Exception:
            return False

        # Replay each action in the candidate path
        for t in transitions:
            action = self.graph.get_action(t.action_name)
            if action is None:
                return False
            try:
                self.world.act(action)
            except Exception:
                return False

        # Check if the named invariant fires
        for inv in self.invariants:
            if inv.name == inv_name:
                try:
                    return not inv.check(self.world)
                except Exception:
                    return False

        return False

    def _register_hyperedge(self, state: State) -> None:
        """Infer and register a state's hyperedge in the Hypergraph."""
        if self._hypergraph is None:
            return
        from venomqa.v1.core.hyperedge import Hyperedge
        edge = Hyperedge.from_state(state)
        self._hypergraph.add(state.id, edge)

    def _get_valid_actions(self, state: State) -> list[Action]:
        """Get actions valid in this state, including ResourceGraph checks.

        This combines:
        1. Graph's precondition filtering (max_calls, action dependencies, context)
        2. ResourceGraph existence checks (if configured)

        Returns:
            List of actions that can be executed from this state.
        """
        # Get actions that pass preconditions
        valid = self.graph.get_valid_actions(
            state, self.world.context, self.graph.used_action_names
        )

        # If ResourceGraph is configured, also filter by resource requirements
        resource_graph = self.world.resources
        if resource_graph is not None:
            bindings = self.world.context.to_dict()
            valid = [
                a for a in valid
                if not getattr(a, "requires", None)  # No requirements = always valid
                or resource_graph.can_execute(a.requires, bindings)
            ]

        return valid

    @property
    def hypergraph(self) -> Hypergraph | None:
        """The Hypergraph instance, if hypergraph mode is enabled."""
        return self._hypergraph

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
    "DimensionNoveltyStrategy",
    "Scheduler",
    "ScheduledRun",
    "RunResult",
]
