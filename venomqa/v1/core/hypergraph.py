"""Hypergraph: dimension-indexed state store."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from venomqa.v1.core.hyperedge import Hyperedge


@dataclass
class HypergraphNode:
    """A state registered in the Hypergraph, with its hyperedge label."""

    state_id: str
    hyperedge: Hyperedge


class Hypergraph:
    """Multi-dimensional index over states.

    Stores states keyed by their Hyperedge labels, enabling queries such as:

    - "all states where auth=AUTH and role=ADMIN"
    - "which (auth, role) combinations haven't been explored yet"
    - "states closest (in Hamming distance) to a target hyperedge"

    The Hypergraph is *additive* — you only add nodes, never remove them.
    It operates alongside the regular Graph; use it for targeting novelty.
    """

    def __init__(self) -> None:
        # Primary store: hyperedge → list[state_id]
        self._by_edge: dict[Hyperedge, list[str]] = defaultdict(list)
        # Inverted index: dimension_name → dimension_value → set[state_id]
        self._by_dim: dict[str, dict[Any, set[str]]] = defaultdict(lambda: defaultdict(set))
        # All nodes
        self._nodes: dict[str, HypergraphNode] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, state_id: str, hyperedge: Hyperedge) -> None:
        """Register a state with its hyperedge label."""
        if state_id in self._nodes:
            return  # Idempotent
        node = HypergraphNode(state_id=state_id, hyperedge=hyperedge)
        self._nodes[state_id] = node
        self._by_edge[hyperedge].append(state_id)
        for dim, val in hyperedge.dimensions.items():
            self._by_dim[dim][val].add(state_id)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query_by_dimension(self, **kwargs: Any) -> list[str]:
        """Return state IDs matching all the given dimension=value pairs.

        Example::

            hg.query_by_dimension(auth=AuthStatus.AUTH, role=UserRole.ADMIN)
        """
        if not kwargs:
            return list(self._nodes.keys())

        result: set[str] | None = None
        for dim, val in kwargs.items():
            matches = self._by_dim.get(dim, {}).get(val, set())
            result = matches if result is None else result & matches

        return list(result or set())

    def get_hyperedge(self, state_id: str) -> Hyperedge | None:
        """Get the hyperedge label for a state."""
        node = self._nodes.get(state_id)
        return node.hyperedge if node else None

    def all_values(self, dimension: str) -> set[Any]:
        """All distinct values seen for a dimension."""
        return set(self._by_dim.get(dimension, {}).keys())

    def all_dimensions(self) -> set[str]:
        """All dimension names registered so far."""
        return set(self._by_dim.keys())

    # ------------------------------------------------------------------
    # Coverage / novelty
    # ------------------------------------------------------------------

    def observed_combinations(self, *dimensions: str) -> set[tuple[Any, ...]]:
        """Return all (value, ...) tuples observed for the given dimensions."""
        combos: set[tuple[Any, ...]] = set()
        for node in self._nodes.values():
            combo = tuple(node.hyperedge.dimensions.get(d) for d in dimensions)
            if any(v is not None for v in combo):
                combos.add(combo)
        return combos

    def unexplored_combos(self, *dimensions: str) -> set[tuple[Any, ...]]:
        """Cartesian-product combos not yet seen for the given dimensions.

        Returns the set of all *possible* value tuples (built from values seen
        so far in those dimensions) that have NOT yet been observed together.
        """
        from itertools import product

        axes: list[list[Any]] = []
        for d in dimensions:
            vals = list(self.all_values(d))
            if not vals:
                return set()
            axes.append(vals)

        all_possible = set(product(*axes))
        observed = self.observed_combinations(*dimensions)
        return all_possible - observed

    def nearest_novel_state(
        self, target: Hyperedge, exclude: set[str] | None = None
    ) -> str | None:
        """Find the registered state closest in Hamming distance to ``target``.

        Returns None if no states are registered or all are excluded.
        """
        candidates = [
            (state_id, node.hyperedge.hamming_distance(target))
            for state_id, node in self._nodes.items()
            if (exclude is None or state_id not in exclude)
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda x: x[1])[0]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    def coverage_per_dimension(self) -> dict[str, int]:
        """How many distinct values have been seen per dimension."""
        return {dim: len(vals) for dim, vals in self._by_dim.items()}
