"""Checkpoint and SystemCheckpoint dataclasses."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# SystemCheckpoint is implementation-specific:
# - PostgreSQL: savepoint name string
# - Redis: dict of key->value dumps
# - MockQueue: list of messages
# - etc.
SystemCheckpoint = Any


@dataclass
class Checkpoint:
    """A saved state of the entire world."""

    id: str
    name: str
    system_checkpoints: dict[str, SystemCheckpoint]
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        name: str,
        system_checkpoints: dict[str, SystemCheckpoint],
    ) -> Checkpoint:
        """Create a new checkpoint with auto-generated ID."""
        return cls(
            id=f"cp_{uuid.uuid4().hex[:12]}",
            name=name,
            system_checkpoints=system_checkpoints,
        )

    def get_system_checkpoint(self, system: str) -> SystemCheckpoint | None:
        """Get checkpoint data for a specific system."""
        return self.system_checkpoints.get(system)
