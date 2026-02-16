"""World module - the execution sandbox."""

from __future__ import annotations

from typing import TYPE_CHECKING

from venomqa.v1.core.state import State, Observation
from venomqa.v1.core.action import Action, ActionResult
from venomqa.v1.world.rollbackable import Rollbackable, SystemCheckpoint
from venomqa.v1.world.checkpoint import Checkpoint

if TYPE_CHECKING:
    from venomqa.v1.adapters.http import HttpClient


class World:
    """The execution sandbox that coordinates all systems.

    World is the central coordinator that:
    - Executes actions via the API client
    - Observes state from all registered systems
    - Creates checkpoints across all systems
    - Rolls back all systems to a checkpoint
    """

    def __init__(
        self,
        api: "HttpClient",
        systems: dict[str, Rollbackable] | None = None,
    ) -> None:
        self.api = api
        self.systems: dict[str, Rollbackable] = systems or {}
        self._checkpoints: dict[str, Checkpoint] = {}

    def register_system(self, name: str, system: Rollbackable) -> None:
        """Register a system for observation and rollback."""
        self.systems[name] = system

    def act(self, action: Action) -> ActionResult:
        """Execute an action via the API."""
        return action.execute(self.api)

    def observe(self) -> State:
        """Get current state from all systems."""
        observations: dict[str, Observation] = {}
        for name, system in self.systems.items():
            observations[name] = system.observe()
        return State.create(observations=observations)

    def checkpoint(self, name: str) -> str:
        """Create a checkpoint across all systems.

        Returns:
            The checkpoint ID.
        """
        system_checkpoints: dict[str, SystemCheckpoint] = {}
        for system_name, system in self.systems.items():
            system_checkpoints[system_name] = system.checkpoint(name)

        cp = Checkpoint.create(name, system_checkpoints)
        self._checkpoints[cp.id] = cp
        return cp.id

    def rollback(self, checkpoint_id: str) -> None:
        """Roll back all systems to a checkpoint."""
        cp = self._checkpoints.get(checkpoint_id)
        if cp is None:
            raise ValueError(f"Unknown checkpoint: {checkpoint_id}")

        for system_name, system in self.systems.items():
            system_cp = cp.get_system_checkpoint(system_name)
            if system_cp is not None:
                system.rollback(system_cp)

    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        """Get a checkpoint by ID."""
        return self._checkpoints.get(checkpoint_id)


__all__ = [
    "World",
    "Rollbackable",
    "Checkpoint",
    "SystemCheckpoint",
]
