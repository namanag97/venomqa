"""World module - the execution sandbox."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from venomqa.v1.core.action import Action, ActionResult
from venomqa.v1.core.context import Context
from venomqa.v1.core.state import Observation, State
from venomqa.v1.world.checkpoint import Checkpoint
from venomqa.v1.world.rollbackable import Rollbackable, SystemCheckpoint

if TYPE_CHECKING:
    from venomqa.v1.adapters.http import HttpClient


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
        api: HttpClient,
        systems: dict[str, Rollbackable] | None = None,
        context: Context | None = None,
    ) -> None:
        self.api = api
        self.systems: dict[str, Rollbackable] = systems or {}
        self.context = context or Context()
        self._checkpoints: dict[str, Checkpoint] = {}
        self._context_checkpoints: dict[str, dict[str, Any]] = {}
        self._current_state_id: str | None = None

    def register_system(self, name: str, system: Rollbackable) -> None:
        """Register a system for observation and rollback."""
        self.systems[name] = system

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
