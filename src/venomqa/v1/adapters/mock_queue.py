"""Mock queue adapter for testing."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import SystemCheckpoint


@dataclass
class Message:
    """A message in the queue."""

    id: str
    payload: Any
    created_at: datetime = field(default_factory=datetime.now)
    processed: bool = False


class MockQueue:
    """In-memory queue for testing.

    Implements Rollbackable protocol for checkpoint/restore.
    """

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._messages: list[Message] = []
        self._message_counter = 0

    def push(self, payload: Any) -> Message:
        """Add a message to the queue."""
        self._message_counter += 1
        msg = Message(
            id=f"msg_{self._message_counter}",
            payload=payload,
        )
        self._messages.append(msg)
        return msg

    def pop(self) -> Message | None:
        """Get and remove the next unprocessed message."""
        for msg in self._messages:
            if not msg.processed:
                msg.processed = True
                return msg
        return None

    def peek(self) -> Message | None:
        """Get the next unprocessed message without removing it."""
        for msg in self._messages:
            if not msg.processed:
                return msg
        return None

    @property
    def pending_count(self) -> int:
        """Count of unprocessed messages."""
        return sum(1 for m in self._messages if not m.processed)

    @property
    def processed_count(self) -> int:
        """Count of processed messages."""
        return sum(1 for m in self._messages if m.processed)

    def clear(self) -> None:
        """Clear all messages."""
        self._messages.clear()

    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Save current queue state."""
        return copy.deepcopy(self._messages)

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Restore queue state."""
        self._messages = copy.deepcopy(checkpoint)

    def observe(self) -> Observation:
        """Get current queue state."""
        return Observation(
            system=f"queue:{self.name}",
            data={
                "pending": self.pending_count,
                "processed": self.processed_count,
                "total": len(self._messages),
            },
            observed_at=datetime.now(),
        )
