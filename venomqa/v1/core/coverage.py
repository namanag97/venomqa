"""DimensionCoverage: per-axis coverage statistics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from venomqa.v1.core.hypergraph import Hypergraph


@dataclass
class DimensionAxisCoverage:
    """Coverage statistics for a single dimension axis."""

    dimension: str
    observed_values: set[Any] = field(default_factory=set)
    total_possible: int = 0  # 0 = unknown

    @property
    def observed_count(self) -> int:
        return len(self.observed_values)

    @property
    def coverage_percent(self) -> float:
        if self.total_possible == 0:
            return 0.0
        return min(100.0, (self.observed_count / self.total_possible) * 100)

    def observed_values_str(self) -> list[str]:
        return sorted(v.value if isinstance(v, Enum) else str(v) for v in self.observed_values)


@dataclass
class DimensionCoverage:
    """Coverage report for all dimension axes.

    Produced by ``DimensionCoverage.from_hypergraph``.

    Attributes:
        axes: Per-dimension coverage.
        total_states: Number of states in the hypergraph.
        unexplored_combos: Estimated number of unexplored dimension combinations.
    """

    axes: dict[str, DimensionAxisCoverage] = field(default_factory=dict)
    total_states: int = 0
    unexplored_combos: int = 0

    @classmethod
    def from_hypergraph(
        cls,
        hg: Hypergraph,
        known_dimensions: dict[str, type[Enum]] | None = None,
    ) -> DimensionCoverage:
        """Build a coverage report from a Hypergraph.

        Args:
            hg: The populated Hypergraph.
            known_dimensions: Optional mapping of dimension name → Enum class,
                used to determine total_possible values for each axis.
                Defaults to the built-in dimensions if not provided.
        """
        from venomqa.v1.core.dimensions import BUILTIN_DIMENSIONS
        dim_enum_map = known_dimensions if known_dimensions is not None else BUILTIN_DIMENSIONS

        axes: dict[str, DimensionAxisCoverage] = {}
        for dim in hg.all_dimensions():
            enum_cls = dim_enum_map.get(dim)
            total = len(list(enum_cls)) if enum_cls else 0
            axes[dim] = DimensionAxisCoverage(
                dimension=dim,
                observed_values=hg.all_values(dim),
                total_possible=total,
            )

        # Estimate unexplored combos for the 2 most-populated dimensions
        unexplored = 0
        dims_by_count = sorted(
            hg.all_dimensions(), key=lambda d: len(hg.all_values(d)), reverse=True
        )
        if len(dims_by_count) >= 2:
            combos = hg.unexplored_combos(*dims_by_count[:2])
            unexplored = len(combos)

        return cls(
            axes=axes,
            total_states=hg.node_count,
            unexplored_combos=unexplored,
        )

    def summary(self) -> dict[str, Any]:
        """Return a plain dict summary suitable for JSON serialisation."""
        return {
            "total_states": self.total_states,
            "unexplored_combos": self.unexplored_combos,
            "dimensions": {
                dim: {
                    "observed": cov.observed_count,
                    "total_possible": cov.total_possible,
                    "coverage_percent": round(cov.coverage_percent, 1),
                    "values": cov.observed_values_str(),
                }
                for dim, cov in self.axes.items()
            },
        }
