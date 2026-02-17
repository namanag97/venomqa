"""DimensionNoveltyStrategy: prioritise novel dimension combinations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.v1.core.action import Action
    from venomqa.v1.core.state import State
    from venomqa.v1.core.graph import Graph
    from venomqa.v1.core.hypergraph import Hypergraph
    from venomqa.v1.core.constraints import StateConstraint


class DimensionNoveltyStrategy:
    """Exploration strategy that prioritises novel dimension combinations.

    How it works:
    1. From all unexplored (state, action) pairs, score each state by
       computing the Hamming distance to the "least observed" target edge.
    2. The state with the *highest* Hamming distance (most novel) is picked.
    3. Ties are broken by BFS order (lowest step index first).

    This strategy is designed to be used with ``Agent(hypergraph=True)``.
    When hypergraph mode is disabled the strategy falls back to plain BFS
    behaviour.

    Args:
        hypergraph: The Hypergraph instance shared with the Agent.
        constraints: Optional list of constraints that filter invalid combos.
    """

    def __init__(
        self,
        hypergraph: "Hypergraph | None" = None,
        constraints: "list[StateConstraint] | None" = None,
    ) -> None:
        self._hypergraph = hypergraph
        self._constraints = constraints or []
        self._queue: list[tuple[str, str]] = []  # (state_id, action_name)

    # ------------------------------------------------------------------
    # Strategy protocol
    # ------------------------------------------------------------------

    def pick(self, graph: "Graph") -> "tuple[State, Action] | None":
        """Pick the next (state, action) pair to explore."""
        # Collect all unexplored pairs from the graph
        unexplored = list(graph.unexplored_pairs())
        if not unexplored:
            return None

        if self._hypergraph is None or self._hypergraph.node_count == 0:
            # Fallback: BFS order
            state_id, action_name = unexplored[0]
            state = graph.get_state(state_id)
            action = graph.get_action(action_name)
            if state and action:
                graph.mark_explored(state, action)
                return state, action
            return None

        # Score each candidate by novelty (Hamming distance to centroid)
        best: tuple[int, str, str] | None = None
        for state_id, action_name in unexplored:
            edge = self._hypergraph.get_hyperedge(state_id)
            if edge is None:
                score = 0  # Unknown → treat as low novelty
            else:
                score = self._novelty_score(edge)

            if best is None or score > best[0]:
                best = (score, state_id, action_name)

        if best is None:
            return None

        _, state_id, action_name = best
        state = graph.get_state(state_id)
        action = graph.get_action(action_name)
        if state and action:
            graph.mark_explored(state, action)
            return state, action
        return None

    def enqueue(self, state: "State", actions: list["Action"]) -> None:
        """Called by the Agent when a new state is discovered (BFS hook)."""
        pass  # Dimension strategy recalculates every pick()

    def push(self, state: "State", actions: list["Action"]) -> None:
        """Called by the Agent when a new state is discovered (DFS hook)."""
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _novelty_score(self, edge: "Hyperedge") -> int:  # type: ignore[name-defined]
        """Score an edge by how different it is from the most-common edge.

        Higher score = more novel = prefer picking this state.
        """
        from venomqa.v1.core.hyperedge import Hyperedge

        if self._hypergraph is None:
            return 0

        # Build the "centroid" — most commonly seen value per dimension
        centroid_dims: dict[str, Any] = {}
        for dim in self._hypergraph.all_dimensions():
            vals = self._hypergraph.all_values(dim)
            if vals:
                # Pick the most frequent value
                by_freq = {
                    v: len(self._hypergraph.query_by_dimension(**{dim: v}))
                    for v in vals
                }
                centroid_dims[dim] = max(by_freq, key=lambda v: by_freq[v])

        centroid = Hyperedge(dimensions=centroid_dims)
        return edge.hamming_distance(centroid)

    def _passes_constraints(self, edge: "Hyperedge") -> bool:
        return all(c.is_valid(edge) for c in self._constraints)
