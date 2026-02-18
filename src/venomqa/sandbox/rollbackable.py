"""Rollbackable protocol - Interface for systems that support checkpoint/rollback."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from venomqa.sandbox.state import Observation

# SystemCheckpoint is implementation-specific:
# - PostgreSQL: savepoint name string
# - Redis: dict of key->value dumps
# - MockQueue: list of messages
# - MockMail: list of sent emails
# - MockStorage: dict of files
# - MockTime: frozen datetime
SystemCheckpoint = Any


@runtime_checkable
class Rollbackable(Protocol):
    """Protocol for systems that can checkpoint and rollback.

    This is the core abstraction that enables VenomQA's state exploration.
    Any system that implements this protocol can be registered with World
    and will participate in atomic checkpoint/rollback operations.

    Implementations:
        - PostgresAdapter: uses database savepoints
        - SQLiteAdapter: copies database file or uses backup API
        - RedisAdapter: uses dump/restore for each key
        - MockQueue: copies message list
        - MockMail: copies sent mail list
        - MockStorage: copies file dict
        - MockTime: saves current frozen time
        - ResourceGraph: copies resource instances dict

    Example implementation::

        class MySystemAdapter:
            def __init__(self):
                self._state = {}
                self._snapshots = {}

            def checkpoint(self, name: str) -> dict:
                snapshot = copy.deepcopy(self._state)
                self._snapshots[name] = snapshot
                return {"name": name}

            def rollback(self, checkpoint: dict) -> None:
                name = checkpoint["name"]
                self._state = copy.deepcopy(self._snapshots[name])

            def observe(self) -> Observation:
                return Observation(
                    system="my_system",
                    data={"key_count": len(self._state)},
                )
    """

    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Save current state and return checkpoint data.

        Args:
            name: Human-readable name for the checkpoint.

        Returns:
            Implementation-specific checkpoint data that can be
            passed to rollback() to restore this state.
        """
        ...

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Restore state to a previous checkpoint.

        Args:
            checkpoint: Data returned from a previous checkpoint() call.
        """
        ...

    def observe(self) -> Observation:
        """Get current state as an Observation.

        Returns:
            Observation containing relevant system state data.
            The data dict should include fields that represent
            the "shape" of the system's state for deduplication.
        """
        ...
