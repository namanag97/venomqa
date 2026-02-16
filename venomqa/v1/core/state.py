"""State and Observation dataclasses."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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

    def content_hash(self) -> str:
        """Generate deterministic hash of observation content (excluding timestamp)."""
        data = {"system": self.system, "data": self.data}
        content = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()


@dataclass(frozen=True)
class State:
    """Snapshot of the world at a moment in time.

    State identity is based on observation CONTENT, not UUID.
    Two states with identical observations will have the same ID.
    This enables state deduplication and prevents exponential state explosion.
    """

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
        """Create a new state with content-based ID.

        The ID is derived from the hash of observation content.
        Same observations = same state ID = deduplication.
        """
        state_id = cls._compute_content_id(observations)
        return cls(
            id=state_id,
            observations=observations,
            checkpoint_id=checkpoint_id,
            parent_transition_id=parent_transition_id,
        )

    @staticmethod
    def _compute_content_id(observations: dict[str, Observation]) -> str:
        """Compute deterministic state ID from observation content.

        This is the key to state deduplication:
        - Same observations → same hash → same state ID
        - Different observations → different hash → different state ID
        """
        # Build sorted content dict (excludes timestamps for determinism)
        content = {}
        for system_name in sorted(observations.keys()):
            obs = observations[system_name]
            content[system_name] = {
                "system": obs.system,
                "data": obs.data,
            }

        # Hash the content
        json_str = json.dumps(content, sort_keys=True, default=str)
        content_hash = hashlib.sha256(json_str.encode()).hexdigest()[:12]
        return f"s_{content_hash}"

    def content_hash(self) -> str:
        """Get the content hash portion of the state ID."""
        return self.id[2:] if self.id.startswith("s_") else self.id

    def get_observation(self, system: str) -> Observation | None:
        """Get observation for a specific system."""
        return self.observations.get(system)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, State):
            return NotImplemented
        return self.id == other.id
