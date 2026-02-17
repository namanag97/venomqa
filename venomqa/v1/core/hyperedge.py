"""Hyperedge: a multi-dimensional label for a state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from venomqa.v1.core.state import State, Observation


@dataclass(frozen=True)
class Hyperedge:
    """A tuple of (dimension → value) labels attached to a state.

    A Hyperedge captures *which combination of orthogonal concerns* a state
    belongs to.  For example::

        Hyperedge(dimensions={
            "auth": AuthStatus.AUTH,
            "role": UserRole.ADMIN,
            "count": CountClass.ZERO,
        })

    Two hyperedges are equal iff they share the same dimension map.

    The ``partial`` flag marks edges that were inferred automatically and
    may be missing some dimension values.
    """

    dimensions: dict[str, Any] = field(default_factory=dict)
    partial: bool = False  # True when some dimensions could not be inferred

    def __hash__(self) -> int:
        # Sort for determinism; values are Enums so .value is always hashable
        return hash(tuple(sorted((k, v) for k, v in self.dimensions.items())))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Hyperedge):
            return NotImplemented
        return self.dimensions == other.dimensions

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_observation(cls, observation: "Observation") -> "Hyperedge":
        """Infer dimensions from a single Observation's data dict.

        Looks for well-known keys in the observation data and maps them to
        the canonical dimension enums.  Unknown keys are ignored.

        Override this method (or pass a custom ``extractor`` to
        ``Hyperedge.from_state``) for application-specific mappings.
        """
        from venomqa.v1.core.dimensions import (
            AuthStatus, UserRole, EntityStatus, CountClass, UsageClass, PlanType,
        )
        dims: dict[str, Any] = {}
        data = observation.data

        # --- auth ---
        if "authenticated" in data:
            dims["auth"] = AuthStatus.AUTH if data["authenticated"] else AuthStatus.ANON
        elif "auth_status" in data:
            try:
                dims["auth"] = AuthStatus(data["auth_status"])
            except ValueError:
                pass

        # --- role ---
        if "role" in data:
            try:
                dims["role"] = UserRole(str(data["role"]).lower())
            except ValueError:
                pass

        # --- entity_status ---
        for key in ("status", "entity_status", "state"):
            if key in data:
                try:
                    dims["entity_status"] = EntityStatus(str(data[key]).lower())
                    break
                except ValueError:
                    pass

        # --- count ---
        for key in ("count", "total", "size", "length"):
            if key in data and isinstance(data[key], int):
                n = data[key]
                if n == 0:
                    dims["count"] = CountClass.ZERO
                elif n == 1:
                    dims["count"] = CountClass.ONE
                elif n <= 10:
                    dims["count"] = CountClass.FEW
                else:
                    dims["count"] = CountClass.MANY
                break

        # --- usage ---
        if "usage_percent" in data:
            pct = float(data["usage_percent"])
            if pct == 0:
                dims["usage"] = UsageClass.NONE
            elif pct < 25:
                dims["usage"] = UsageClass.LOW
            elif pct < 75:
                dims["usage"] = UsageClass.MEDIUM
            elif pct < 100:
                dims["usage"] = UsageClass.HIGH
            else:
                dims["usage"] = UsageClass.EXCEEDED

        # --- plan ---
        if "plan" in data:
            try:
                dims["plan"] = PlanType(str(data["plan"]).lower())
            except ValueError:
                pass

        return cls(dimensions=dims, partial=len(dims) == 0)

    @classmethod
    def from_state(cls, state: "State") -> "Hyperedge":
        """Merge dimension inferences from all observations in a state."""
        merged: dict[str, Any] = {}
        for obs in state.observations.values():
            inferred = cls.from_observation(obs)
            # Later observations override earlier ones for the same dimension key
            merged.update(inferred.dimensions)
        partial = len(merged) == 0
        return cls(dimensions=merged, partial=partial)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def get(self, dimension: str, default: Any = None) -> Any:
        return self.dimensions.get(dimension, default)

    def hamming_distance(self, other: "Hyperedge") -> int:
        """Count dimensions that differ between two hyperedges."""
        all_keys = set(self.dimensions) | set(other.dimensions)
        return sum(
            1 for k in all_keys
            if self.dimensions.get(k) != other.dimensions.get(k)
        )

    def to_dict(self) -> dict[str, str]:
        """Serialise to a plain string→string dict (for reporters)."""
        return {k: (v.value if isinstance(v, Enum) else str(v)) for k, v in self.dimensions.items()}

    def __repr__(self) -> str:
        items = ", ".join(f"{k}={v!r}" for k, v in sorted(self.dimensions.items()))
        return f"Hyperedge({items})"
