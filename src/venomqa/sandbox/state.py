"""State and Observation - Immutable snapshots of the world."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Hyperedge is part of the exploration context (hypergraph system)
    # Import only for type checking to avoid circular deps
    from venomqa.v1.core.hyperedge import Hyperedge


@dataclass(frozen=True)
class Observation:
    """Data observed from one system at a point in time.

    Observations have two types of data:
    - data: The actual state (used for identity/deduplication)
    - metadata: Additional info not part of state (timing, counters, etc.)

    Only data is used when computing state identity. This allows
    proper deduplication while still capturing useful metadata.

    Attributes:
        system: Name of the system this observation came from
        data: State data used for identity computation
        metadata: Additional metadata not used for identity
        observed_at: When this observation was taken
    """

    system: str
    data: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    observed_at: datetime = field(default_factory=datetime.now)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the state data."""
        return self.data.get(key, default)

    def get_meta(self, key: str, default: Any = None) -> Any:
        """Get a value from metadata."""
        return self.metadata.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def content_hash(self) -> str:
        """Generate deterministic hash of state data (excluding metadata/timestamp)."""
        content = {"system": self.system, "data": self.data}
        return hashlib.sha256(
            json.dumps(content, sort_keys=True, default=str).encode()
        ).hexdigest()

    @classmethod
    def create(
        cls,
        system: str,
        data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> Observation:
        """Create an observation with optional metadata."""
        return cls(
            system=system,
            data=data,
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class State:
    """Snapshot of the world at a moment in time.

    State identity is based on observation CONTENT, not UUID.
    Two states with identical observations will have the same ID.
    This enables state deduplication and prevents exponential state explosion.

    Attributes:
        id: Content-based identifier (same observations = same ID)
        observations: Map of system name to observation
        created_at: When this state was created
        checkpoint_id: Associated checkpoint for rollback (if any)
        parent_transition_id: Transition that led to this state (if any)
        hyperedge: Multi-dimensional coordinates (for hypergraph exploration)
    """

    id: str
    observations: dict[str, Observation]
    created_at: datetime = field(default_factory=datetime.now)
    checkpoint_id: str | None = None
    parent_transition_id: str | None = None
    hyperedge: Hyperedge | None = None

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
        - Same observations -> same hash -> same state ID
        - Different observations -> different hash -> different state ID
        """
        # Build sorted content dict (excludes timestamps for determinism)
        content = {}
        for system_name in sorted(observations.keys()):
            obs = observations[system_name]
            content[system_name] = {
                "system": obs.system,
                "data": obs.data,
            }

        # Hash the content (16 hex chars = 64 bits, birthday collision at ~4B states)
        json_str = json.dumps(content, sort_keys=True, default=str)
        content_hash = hashlib.sha256(json_str.encode()).hexdigest()[:16]
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
