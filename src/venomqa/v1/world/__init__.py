"""World module - the execution sandbox."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from venomqa.v1.core.action import Action, ActionResult
from venomqa.v1.core.context import Context
from venomqa.v1.core.state import Observation, State
from venomqa.v1.world.checkpoint import Checkpoint
from venomqa.v1.world.rollbackable import Rollbackable, SystemCheckpoint

if TYPE_CHECKING:
    from venomqa.v1.adapters.http import HttpClient as _HttpClientType


class World:
    """The execution sandbox that coordinates all systems.

    World is the central coordinator that:
    - Executes actions via the API client
    - Observes state from all registered systems
    - Creates checkpoints across all systems
    - Rolls back all systems to a checkpoint
    - Maintains shared context between actions

    The key insight: checkpoint and rollback are ATOMIC across all systems.
    When you checkpoint, every system saves its state at the same logical moment.
    When you rollback, every system restores together.

    Context: The World maintains a Context object that actions can use to
    share data. Context is checkpointed/restored along with system state.
    """

    def __init__(
        self,
        api: _HttpClientType,
        systems: dict[str, Rollbackable] | None = None,
        context: Context | None = None,
        setup: Callable[..., None] | None = None,
        clients: dict[str, _HttpClientType] | None = None,
        teardown: Callable[..., None] | None = None,
        state_from_context: list[str] | None = None,
        auth: Any | None = None,
    ) -> None:
        self.api = api
        self.systems: dict[str, Rollbackable] = systems or {}
        self.context = context or Context()
        self._setup_fn = setup
        self._checkpoints: dict[str, Checkpoint] = {}
        self._context_checkpoints: dict[str, dict[str, Any]] = {}
        self._current_state_id: str | None = None
        # Named clients for RBAC / multi-role testing.
        # Accessible as world.clients["viewer"] (invariants)
        # or context.get_client("viewer") (actions).
        # Never rolled back — they are test infrastructure, not state.
        self.clients: dict[str, _HttpClientType] = clients or {}
        for name, client in self.clients.items():
            self.context._register_client(name, client)
        self._teardown_fn = teardown
        # If auth= is provided, wrap api with AuthHttpClient so every request
        # gets the token injected automatically from context.
        if auth is not None:
            from venomqa.v1.auth import AuthHttpClient
            self.api = AuthHttpClient(api, auth, self.context)
        # Context keys whose values are included in state identity.
        # When these values change, VenomQA sees a new state — no DB adapter needed.
        self._state_from_context: list[str] = state_from_context or []

    def run_teardown(self) -> None:
        """Run the teardown function, if one was provided.

        Called by Agent.explore() after exploration completes (whether successful,
        truncated by max_steps, or stopped by a violation). Use this to delete
        test data created during the run.

        Receives the same (api, context) signature as setup.

        Example::

            def cleanup(api, context):
                conn_id = context.get("connection_id")
                if conn_id:
                    api.delete(f"/connections/{conn_id}")

            world = World(api=api, teardown=cleanup)
        """
        if self._teardown_fn is not None:
            self._teardown_fn(self.api, self.context)

    def run_setup(self) -> None:
        """Run the setup function, if one was provided.

        Called by Agent.explore() before taking the initial checkpoint.
        Use this to seed the database, create auth tokens, or perform any
        bootstrap that must happen before exploration begins.

        Example::

            def bootstrap(api, context):
                resp = api.post("/auth/token", json={"username": "admin", "password": "secret"})
                context.set("admin_token", resp.json()["token"])

            world = World(api=api, setup=bootstrap)
        """
        if self._setup_fn is not None:
            self._setup_fn(self.api, self.context)

    def register_system(self, name: str, system: Rollbackable) -> None:
        """Register a system for observation and rollback."""
        self.systems[name] = system

    def _context_observation(self) -> Observation | None:
        """Build a synthetic Observation from tracked context keys.

        Returns None if state_from_context was not configured.
        When returned, this observation is included in state identity —
        a change in any tracked key value produces a new state hash.
        """
        if not self._state_from_context:
            return None
        data = {key: self.context.get(key) for key in self._state_from_context}
        return Observation(system="_ctx", data=data)

    def act(self, action: Action) -> ActionResult:
        """Execute an action via the API.

        The action receives the API client and optionally the context.
        Actions can store/retrieve data via context for sharing.

        Uses Action.invoke() which auto-detects if the action accepts context.
        """
        return action.invoke(self.api, self.context)

    def observe(self) -> State:
        """Get current state from all systems.

        Note: The returned state has no checkpoint_id.
        Use observe_and_checkpoint() if you need to rollback to this state later.
        """
        observations: dict[str, Observation] = {}
        for name, system in self.systems.items():
            observations[name] = system.observe()
        ctx_obs = self._context_observation()
        if ctx_obs is not None:
            observations["_ctx"] = ctx_obs
        return State.create(observations=observations)

    def observe_and_checkpoint(self, checkpoint_name: str) -> State:
        """Atomically observe state and create a checkpoint.

        This is the primary method for exploration. It:
        1. Creates a checkpoint across all systems
        2. Observes current state from all systems
        3. Returns a State with checkpoint_id attached

        The returned State can be rolled back to via its checkpoint_id.

        Args:
            checkpoint_name: Human-readable name for the checkpoint.

        Returns:
            State with checkpoint_id set.
        """
        # First checkpoint, then observe (order matters for consistency)
        checkpoint_id = self.checkpoint(checkpoint_name)

        # Observe state
        observations: dict[str, Observation] = {}
        for name, system in self.systems.items():
            observations[name] = system.observe()
        ctx_obs = self._context_observation()
        if ctx_obs is not None:
            observations["_ctx"] = ctx_obs

        state = State.create(
            observations=observations,
            checkpoint_id=checkpoint_id,
        )
        self._current_state_id = state.id
        return state

    def checkpoint(self, name: str) -> str:
        """Create a checkpoint across all systems and context.

        Args:
            name: Human-readable name for the checkpoint.

        Returns:
            The checkpoint ID.
        """
        system_checkpoints: dict[str, SystemCheckpoint] = {}
        for system_name, system in self.systems.items():
            system_checkpoints[system_name] = system.checkpoint(name)

        cp = Checkpoint.create(name, system_checkpoints)
        self._checkpoints[cp.id] = cp

        # Also checkpoint context
        self._context_checkpoints[cp.id] = self.context.checkpoint()

        return cp.id

    def rollback(self, checkpoint_id: str) -> None:
        """Roll back all systems and context to a checkpoint.

        Args:
            checkpoint_id: The checkpoint to rollback to.

        Raises:
            ValueError: If checkpoint_id is unknown.
        """
        cp = self._checkpoints.get(checkpoint_id)
        if cp is None:
            raise ValueError(f"Unknown checkpoint: {checkpoint_id}")

        # Rollback systems
        for system_name, system in self.systems.items():
            system_cp = cp.get_system_checkpoint(system_name)
            if system_cp is not None:
                system.rollback(system_cp)

        # Rollback context
        context_cp = self._context_checkpoints.get(checkpoint_id)
        if context_cp is not None:
            self.context.restore(context_cp)

    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        """Get a checkpoint by ID."""
        return self._checkpoints.get(checkpoint_id)

    def has_checkpoint(self, checkpoint_id: str) -> bool:
        """Check if a checkpoint exists."""
        return checkpoint_id in self._checkpoints


__all__ = [
    "World",
    "Rollbackable",
    "Checkpoint",
    "SystemCheckpoint",
]
