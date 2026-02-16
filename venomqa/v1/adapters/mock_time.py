"""Mock time adapter for testing."""

from __future__ import annotations

from datetime import datetime, timedelta

from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import SystemCheckpoint


class MockTime:
    """Controllable time for testing.

    Implements Rollbackable protocol for checkpoint/restore.
    """

    def __init__(self, start: datetime | None = None) -> None:
        self._current = start or datetime.now()
        self._frozen = False

    @property
    def now(self) -> datetime:
        """Get current time."""
        if self._frozen:
            return self._current
        return datetime.now()

    def freeze(self, at: datetime | None = None) -> None:
        """Freeze time at the given moment (or now)."""
        self._current = at or datetime.now()
        self._frozen = True

    def unfreeze(self) -> None:
        """Unfreeze time."""
        self._frozen = False

    def advance(self, **kwargs: int) -> datetime:
        """Advance frozen time by the given delta.

        Args:
            **kwargs: Arguments passed to timedelta (days, hours, minutes, seconds, etc.)

        Returns:
            The new current time.
        """
        if not self._frozen:
            raise RuntimeError("Cannot advance time when not frozen")
        self._current += timedelta(**kwargs)
        return self._current

    def set(self, time: datetime) -> None:
        """Set the current time (automatically freezes)."""
        self._current = time
        self._frozen = True

    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Save current time state."""
        return {
            "current": self._current,
            "frozen": self._frozen,
        }

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Restore time state."""
        self._current = checkpoint["current"]
        self._frozen = checkpoint["frozen"]

    def observe(self) -> Observation:
        """Get current time state."""
        return Observation(
            system="time",
            data={
                "current": self._current.isoformat(),
                "frozen": self._frozen,
            },
            observed_at=datetime.now(),
        )
