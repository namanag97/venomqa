"""Rollbackable protocol."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from venomqa.v1.core.state import Observation

# SystemCheckpoint is implementation-specific
# PostgreSQL: savepoint name string
# Redis: dict of key->value dumps
# MockQueue: list of messages
SystemCheckpoint = Any


@runtime_checkable
class Rollbackable(Protocol):
    """Protocol for systems that can checkpoint and rollback.

    Implementations:
        - PostgresAdapter: uses savepoints
        - RedisAdapter: uses dump/restore
        - MockQueue: copies message list
        - MockMail: copies sent mail list
        - MockStorage: copies file dict
        - MockTime: saves current time
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
        """
        ...
