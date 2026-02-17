"""Bridge: StateManager to Rollbackable adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import Rollbackable, SystemCheckpoint


@runtime_checkable
class LegacyStateManager(Protocol):
    """Protocol for the old StateManager interface."""

    def save_state(self) -> Any:
        """Save current state."""
        ...

    def restore_state(self, state: Any) -> None:
        """Restore to a saved state."""
        ...

    def get_state(self) -> dict[str, Any]:
        """Get current state as dict."""
        ...


class StateManagerAdapter:
    """Wraps a legacy StateManager as a Rollbackable."""

    def __init__(
        self,
        state_manager: LegacyStateManager,
        system_name: str = "legacy",
    ) -> None:
        self._manager = state_manager
        self._system_name = system_name

    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Save state using the legacy interface."""
        return self._manager.save_state()

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Restore state using the legacy interface."""
        self._manager.restore_state(checkpoint)

    def observe(self) -> Observation:
        """Get observation from the legacy interface."""
        return Observation(
            system=self._system_name,
            data=self._manager.get_state(),
            observed_at=datetime.now(),
        )


def adapt_state_manager(
    state_manager: LegacyStateManager,
    system_name: str = "legacy",
) -> Rollbackable:
    """Convert a legacy StateManager to a Rollbackable.

    Args:
        state_manager: The old StateManager instance.
        system_name: Name to use for observations.

    Returns:
        A Rollbackable adapter wrapping the StateManager.

    Example:
        from venomqa.v1.bridge import adapt_state_manager

        old_manager = SomeLegacyStateManager()
        rollbackable = adapt_state_manager(old_manager, "db")
        world = World(api=http_client, systems={"db": rollbackable})
    """
    return StateManagerAdapter(state_manager, system_name)
