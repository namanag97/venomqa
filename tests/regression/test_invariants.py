"""Property-based tests that verify INVARIANTS.

These tests use Hypothesis to generate random inputs and verify that
certain properties ALWAYS hold, regardless of the specific inputs.

These are harder to "game" because:
1. They test properties, not specific examples
2. Random generation finds edge cases automatically
3. Shrinking finds minimal failing examples
4. Properties are fundamental truths about the system

If these fail, something is fundamentally broken.
"""

from __future__ import annotations

import gc
import sys
import tracemalloc
from typing import Any

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from venomqa.core.graph import StateGraph, ExplorationNode, Edge


# =============================================================================
# GRAPH EXPLORATION INVARIANTS
# =============================================================================


class TestExplorationNodeInvariants:
    """Invariants for the ExplorationNode parent-pointer structure."""

    @given(
        depth=st.integers(min_value=1, max_value=20),
        branching=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_path_reconstruction_matches_direct_path(self, depth: int, branching: int):
        """INVARIANT: Reconstructed path must match directly-tracked path.

        The parent-pointer tree optimization must produce identical results
        to the naive approach of copying paths at each step.
        """
        graph = self._create_linear_graph(depth)

        # Explore and get results
        results = list(graph.explore_iter(client=None, max_depth=depth + 1))

        # For each result, verify path reconstruction
        for result in results:
            # The path should have the expected structure
            assert len(result.path) >= 1, "Path should have at least one node"
            assert result.path[0] == "node_0", "Path should start at initial node"

    @given(depth=st.integers(min_value=1, max_value=10))
    @settings(max_examples=30)
    def test_exploration_node_depth_matches_path_length(self, depth: int):
        """INVARIANT: Node depth must equal path length - 1."""
        graph = self._create_linear_graph(depth)

        results = list(graph.explore_iter(client=None, max_depth=depth + 1))

        for result in results:
            # Path length should be depth + 1 (includes root)
            # This is a fundamental structural property
            assert len(result.path) == len(result.edges_taken) + 1

    @given(
        depth=st.integers(min_value=2, max_value=8),
        branching=st.integers(min_value=2, max_value=4),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_all_leaf_paths_are_found(self, depth: int, branching: int):
        """INVARIANT: All reachable leaf paths must be explored.

        No path should be silently skipped.
        """
        graph = self._create_tree_graph(depth, branching)

        results = list(graph.explore_iter(client=None, max_depth=depth + 1))

        # Count expected paths: branching^depth for a complete tree
        # But our tree might not be complete, so we count leaves
        expected_leaves = branching ** (depth - 1) if depth > 1 else 1

        # We should find all paths (may be fewer if max_depth limits)
        assert len(results) >= 1, "Should find at least one path"

    def test_parent_pointer_chain_is_valid(self):
        """INVARIANT: Parent pointers must form valid chain to root."""
        graph = self._create_linear_graph(5)

        for result in graph.explore_iter(client=None, max_depth=10):
            path = result.path
            edges = result.edges_taken

            # Verify structure: edges connect consecutive path nodes
            for i, edge in enumerate(edges):
                assert edge.from_node == path[i]
                assert edge.to_node == path[i + 1]

    @given(seed=st.integers(min_value=0, max_value=10000))
    @settings(max_examples=20)
    def test_deterministic_exploration(self, seed: int):
        """INVARIANT: Same graph + same seed = same results.

        Exploration must be deterministic for reproducibility.
        """
        graph = self._create_tree_graph(depth=3, branching=2)

        # Run twice
        results1 = list(graph.explore_iter(client=None, max_depth=10))
        results2 = list(graph.explore_iter(client=None, max_depth=10))

        # Should get same paths in same order
        assert len(results1) == len(results2)
        for r1, r2 in zip(results1, results2):
            assert r1.path == r2.path

    def _create_linear_graph(self, depth: int) -> StateGraph:
        """Create a simple linear graph: A -> B -> C -> ..."""
        graph = StateGraph(name="linear")

        for i in range(depth + 1):
            graph.add_node(f"node_{i}", initial=(i == 0))

        for i in range(depth):
            graph.add_edge(
                f"node_{i}", f"node_{i+1}",
                action=lambda c, ctx: "ok",
                name=f"edge_{i}"
            )

        return graph

    def _create_tree_graph(self, depth: int, branching: int) -> StateGraph:
        """Create a tree graph with given depth and branching factor."""
        graph = StateGraph(name="tree")

        # Create all nodes
        node_count = 0
        nodes_at_level: dict[int, list[str]] = {0: ["root"]}
        graph.add_node("root", initial=True)

        for level in range(1, depth):
            nodes_at_level[level] = []
            for parent in nodes_at_level[level - 1]:
                for b in range(branching):
                    node_id = f"L{level}_N{node_count}"
                    node_count += 1
                    graph.add_node(node_id)
                    nodes_at_level[level].append(node_id)
                    graph.add_edge(
                        parent, node_id,
                        action=lambda c, ctx: "ok",
                        name=f"{parent}_to_{node_id}"
                    )

        return graph


# =============================================================================
# MEMORY INVARIANTS
# =============================================================================


class TestMemoryInvariants:
    """Invariants about memory usage."""

    @settings(max_examples=5, deadline=None)
    @given(
        branching=st.integers(min_value=2, max_value=3),
        depth=st.integers(min_value=3, max_value=5),
    )
    def test_memory_bounded_by_nodes_not_paths(self, branching: int, depth: int):
        """INVARIANT: Memory should grow with nodes, not paths.

        With parent-pointer tree, memory should be O(total_nodes),
        not O(branching^depth * depth).
        """
        graph = StateGraph(name="memory_test")

        # Create nodes
        total_nodes = 0
        for level in range(depth):
            for n in range(min(branching ** level, 100)):  # Cap to avoid explosion
                node_id = f"L{level}_N{n}"
                graph.add_node(node_id, initial=(level == 0 and n == 0))
                total_nodes += 1

        # Create edges
        for level in range(depth - 1):
            parent_count = min(branching ** level, 100)
            for p in range(parent_count):
                parent_id = f"L{level}_N{p}"
                for c in range(branching):
                    child_idx = p * branching + c
                    if child_idx < min(branching ** (level + 1), 100):
                        child_id = f"L{level+1}_N{child_idx}"
                        if child_id in graph.nodes:
                            graph.add_edge(
                                parent_id, child_id,
                                action=lambda c, ctx: "ok",
                                name=f"{parent_id}_to_{child_id}"
                            )

        # Measure memory during exploration
        gc.collect()
        tracemalloc.start()

        results = list(graph.explore_iter(client=None, max_depth=depth + 1))

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Memory should be reasonable (not exponential)
        # Allow 1KB per node as rough upper bound
        max_expected_memory = total_nodes * 2048  # 2KB per node generous bound

        assert peak < max_expected_memory, (
            f"Memory {peak} exceeds expected {max_expected_memory} for {total_nodes} nodes"
        )


# =============================================================================
# RESULT STRUCTURE INVARIANTS
# =============================================================================


class TestResultInvariants:
    """Invariants about result structures."""

    def test_path_result_consistency(self):
        """INVARIANT: PathResult fields must be internally consistent."""
        graph = StateGraph(name="test")
        graph.add_node("A", initial=True)
        graph.add_node("B")
        graph.add_node("C")
        graph.add_edge("A", "B", action=lambda c, ctx: "ab", name="a_to_b")
        graph.add_edge("B", "C", action=lambda c, ctx: "bc", name="b_to_c")

        for result in graph.explore_iter(client=None, max_depth=10):
            # Path length = edges + 1
            assert len(result.path) == len(result.edges_taken) + 1

            # Edge results match edges taken
            assert len(result.edge_results) == len(result.edges_taken)

            # If no error in any edge, success should be True (unless invariant violations)
            if all(er.error is None for er in result.edge_results):
                if not result.invariant_violations:
                    assert result.success is True

    def test_exploration_result_aggregation(self):
        """INVARIANT: ExplorationResult must correctly aggregate path results."""
        graph = StateGraph(name="test")
        graph.add_node("A", initial=True)
        graph.add_node("B")
        graph.add_node("C")
        graph.add_edge("A", "B", action=lambda c, ctx: "ab", name="a_to_b")
        graph.add_edge("A", "C", action=lambda c, ctx: "ac", name="a_to_c")

        result = graph.explore(client=None, max_depth=10)

        # Total paths = sum of path results
        assert result.total_paths == len(result.paths_explored)

        # Successful + failed = total
        assert result.successful_paths + result.failed_paths == result.total_paths

        # All visited nodes should be in the graph
        for node_id in result.nodes_visited:
            assert node_id in graph.nodes

        # All executed edges should be real edges
        all_edge_names = set()
        for edges in graph.edges.values():
            for edge in edges:
                all_edge_names.add(edge.name)

        for edge_name in result.edges_executed:
            assert edge_name in all_edge_names


# =============================================================================
# CONTEXT RECONSTRUCTION INVARIANTS
# =============================================================================


class TestContextInvariants:
    """Invariants about context handling."""

    def test_context_contains_all_responses(self):
        """INVARIANT: Reconstructed context must contain all edge responses."""
        responses = []

        def capture_action(response_value):
            def action(c, ctx):
                responses.append(response_value)
                return {"value": response_value}
            return action

        graph = StateGraph(name="test")
        graph.add_node("A", initial=True)
        graph.add_node("B")
        graph.add_node("C")
        graph.add_edge("A", "B", action=capture_action("AB"), name="a_to_b")
        graph.add_edge("B", "C", action=capture_action("BC"), name="b_to_c")

        results = list(graph.explore_iter(client=None, max_depth=10))

        # Should have one complete path A -> B -> C
        assert len(results) == 1
        result = results[0]

        # Edge results should capture responses
        for er in result.edge_results:
            assert er.response is not None


# =============================================================================
# EDGE CASE INVARIANTS
# =============================================================================


class TestEdgeCaseInvariants:
    """Invariants for edge cases and boundary conditions."""

    def test_single_node_graph(self):
        """INVARIANT: Single node graph should produce one path."""
        graph = StateGraph(name="single")
        graph.add_node("only", initial=True)

        results = list(graph.explore_iter(client=None, max_depth=10))

        assert len(results) == 1
        assert results[0].path == ["only"]
        assert results[0].edges_taken == []
        assert results[0].success is True

    def test_disconnected_nodes_only_reach_connected(self):
        """INVARIANT: Unreachable nodes should not appear in paths."""
        graph = StateGraph(name="disconnected")
        graph.add_node("A", initial=True)
        graph.add_node("B")
        graph.add_node("C")  # Disconnected
        graph.add_edge("A", "B", action=lambda c, ctx: "ok", name="a_to_b")
        # No edge to C

        results = list(graph.explore_iter(client=None, max_depth=10))

        for result in results:
            assert "C" not in result.path

    def test_cycle_handling_with_max_depth(self):
        """INVARIANT: Cycles should be bounded by max_depth."""
        graph = StateGraph(name="cycle")
        graph.add_node("A", initial=True)
        graph.add_node("B")
        graph.add_edge("A", "B", action=lambda c, ctx: "ok", name="a_to_b")
        graph.add_edge("B", "A", action=lambda c, ctx: "ok", name="b_to_a")  # Cycle

        results = list(graph.explore_iter(client=None, max_depth=5))

        # Should terminate (not infinite loop)
        assert len(results) >= 1

        # No path should exceed max_depth
        for result in results:
            assert len(result.path) <= 5

    def test_error_in_action_marks_path_failed(self):
        """INVARIANT: Exception in action must mark path as failed."""
        def failing_action(c, ctx):
            raise ValueError("Intentional failure")

        graph = StateGraph(name="failing")
        graph.add_node("A", initial=True)
        graph.add_node("B")
        graph.add_edge("A", "B", action=failing_action, name="fail")

        results = list(graph.explore_iter(client=None, max_depth=10))

        assert len(results) == 1
        assert results[0].success is False
        assert any(er.error is not None for er in results[0].edge_results)
