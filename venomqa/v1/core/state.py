"""State and Observation dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import uuid


@dataclass(frozen=True)
class Observation:
    """Data observed from one system at a point in time."""

    system: str
    data: dict[str, Any]
    observed_at: datetime = field(default_factory=datetime.now)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the observation data."""
        return self.data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]


@dataclass(frozen=True)
class State:
    """Snapshot of the world at a moment in time."""

    id: str
    observations: dict[str, Observation]
    created_at: datetime = field(default_factory=datetime.now)
    checkpoint_id: str | None = None
    parent_transition_id: str | None = None

    @classmethod
    def create(
        cls,
        observations: dict[str, Observation],
        checkpoint_id: str | None = None,
        parent_transition_id: str | None = None,
    ) -> State:
        """Create a new state with auto-generated ID."""
        return cls(
            id=f"s_{uuid.uuid4().hex[:12]}",
            observations=observations,
            checkpoint_id=checkpoint_id,
            parent_transition_id=parent_transition_id,
        )

    def get_observation(self, system: str) -> Observation | None:
        """Get observation for a specific system."""
        return self.observations.get(system)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, State):
            return NotImplemented
        return self.id == other.id
