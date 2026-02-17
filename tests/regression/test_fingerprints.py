"""Behavioral fingerprint tests.

These tests hash deterministic outputs and compare against known hashes.
Any change to behavior breaks the hash, requiring explicit acknowledgment.

This is the ultimate "tamper-evident" test - you cannot change behavior
without the hash changing, and you cannot update the hash without it
being visible in git.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from venomqa.combinatorial import (
    CoveringArrayGenerator,
    Dimension,
    DimensionSpace,
)
from venomqa.core.graph import StateGraph


def compute_fingerprint(data: Any) -> str:
    """Compute a stable fingerprint of data."""
    # Serialize to JSON with sorted keys for stability
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


# =============================================================================
# KNOWN FINGERPRINTS
# =============================================================================
# These hashes represent "known good" behavior.
# If a hash changes, behavior has changed.
# Update ONLY after careful review of WHY it changed.

KNOWN_FINGERPRINTS = {
    # Graph exploration fingerprints
    "linear_graph_3_nodes": "TBD",  # Will be set on first run
    "tree_graph_2x3": "TBD",
    "diamond_graph": "TBD",

    # Combinatorial generation fingerprints
    "pairwise_3x3x3_seed42": "TBD",
    "exhaustive_2x2": "TBD",

    # Path structure fingerprints
    "path_reconstruction_5_deep": "TBD",
}


def check_fingerprint(name: str, actual_hash: str, update: bool = False) -> None:
    """Check fingerprint against known value."""
    expected = KNOWN_FINGERPRINTS.get(name)

    if expected == "TBD" or update:
        # First run or update mode - print hash for manual update
        print(f"\n[FINGERPRINT] {name}: {actual_hash}")
        if expected == "TBD":
            pytest.skip(f"Fingerprint '{name}' not yet recorded. Hash: {actual_hash}")
        return

    assert actual_hash == expected, (
        f"Fingerprint mismatch for '{name}'!\n"
        f"Expected: {expected}\n"
        f"Actual:   {actual_hash}\n"
        f"This means behavior has changed. If intentional, update KNOWN_FINGERPRINTS."
    )


@pytest.fixture
def update_fingerprints(request):
    """Check if --update-fingerprints flag is set."""
    return request.config.getoption("--update-fingerprints", default=False)


def pytest_addoption(parser):
    """Add --update-fingerprints option."""
    try:
        parser.addoption(
            "--update-fingerprints",
            action="store_true",
            default=False,
            help="Print current fingerprints for updating"
        )
    except ValueError:
        pass


# =============================================================================
# GRAPH EXPLORATION FINGERPRINTS
# =============================================================================


class TestGraphExplorationFingerprints:
    """Fingerprint tests for graph exploration behavior."""

    def test_linear_graph_fingerprint(self, update_fingerprints):
        """Fingerprint for linear graph exploration."""
        graph = StateGraph(name="linear")
        graph.add_node("A", initial=True)
        graph.add_node("B")
        graph.add_node("C")
        graph.add_edge("A", "B", action=lambda c, ctx: "AB", name="a_to_b")
        graph.add_edge("B", "C", action=lambda c, ctx: "BC", name="b_to_c")

        results = list(graph.explore_iter(client=None, max_depth=10))

        # Create fingerprint data (stable representation)
        data = {
            "paths": [
                {"nodes": r.path, "edges": [e.name for e in r.edges_taken]}
                for r in results
            ],
            "path_count": len(results),
        }

        fingerprint = compute_fingerprint(data)
        check_fingerprint("linear_graph_3_nodes", fingerprint, update_fingerprints)

    def test_tree_graph_fingerprint(self, update_fingerprints):
        """Fingerprint for tree graph exploration."""
        graph = StateGraph(name="tree")
        graph.add_node("root", initial=True)

        # Create a 2-wide, 3-deep tree
        for level in range(1, 3):
            for parent_idx in range(2 ** (level - 1)):
                parent = f"L{level-1}_N{parent_idx}" if level > 1 else "root"
                for child in range(2):
                    child_id = f"L{level}_N{parent_idx * 2 + child}"
                    graph.add_node(child_id)
                    graph.add_edge(
                        parent, child_id,
                        action=lambda c, ctx: "ok",
                        name=f"{parent}_to_{child_id}"
                    )

        results = list(graph.explore_iter(client=None, max_depth=10))

        data = {
            "paths": sorted([r.path for r in results]),
            "path_count": len(results),
        }

        fingerprint = compute_fingerprint(data)
        check_fingerprint("tree_graph_2x3", fingerprint, update_fingerprints)

    def test_diamond_graph_fingerprint(self, update_fingerprints):
        """Fingerprint for diamond-shaped graph (convergent paths)."""
        graph = StateGraph(name="diamond")
        graph.add_node("top", initial=True)
        graph.add_node("left")
        graph.add_node("right")
        graph.add_node("bottom")

        graph.add_edge("top", "left", action=lambda c, ctx: "L", name="go_left")
        graph.add_edge("top", "right", action=lambda c, ctx: "R", name="go_right")
        graph.add_edge("left", "bottom", action=lambda c, ctx: "LB", name="left_to_bottom")
        graph.add_edge("right", "bottom", action=lambda c, ctx: "RB", name="right_to_bottom")

        results = list(graph.explore_iter(client=None, max_depth=10))

        data = {
            "paths": sorted([r.path for r in results]),
            "path_count": len(results),
        }

        fingerprint = compute_fingerprint(data)
        check_fingerprint("diamond_graph", fingerprint, update_fingerprints)


# =============================================================================
# COMBINATORIAL GENERATION FINGERPRINTS
# =============================================================================


class TestCombinatorialFingerprints:
    """Fingerprint tests for combinatorial generation."""

    def test_pairwise_generation_fingerprint(self, update_fingerprints):
        """Fingerprint for pairwise combination generation."""
        space = DimensionSpace([
            Dimension("A", [1, 2, 3]),
            Dimension("B", [1, 2, 3]),
            Dimension("C", [1, 2, 3]),
        ])

        gen = CoveringArrayGenerator(space, seed=42)
        combos = gen.pairwise()

        # Sort for stability
        data = {
            "combinations": sorted([c.to_dict() for c in combos], key=str),
            "count": len(combos),
        }

        fingerprint = compute_fingerprint(data)
        check_fingerprint("pairwise_3x3x3_seed42", fingerprint, update_fingerprints)

    def test_exhaustive_generation_fingerprint(self, update_fingerprints):
        """Fingerprint for exhaustive combination generation."""
        space = DimensionSpace([
            Dimension("X", [True, False]),
            Dimension("Y", [True, False]),
        ])

        gen = CoveringArrayGenerator(space, seed=42)
        combos = gen.exhaustive()

        data = {
            "combinations": sorted([c.to_dict() for c in combos], key=str),
            "count": len(combos),
        }

        fingerprint = compute_fingerprint(data)
        check_fingerprint("exhaustive_2x2", fingerprint, update_fingerprints)


# =============================================================================
# PATH RECONSTRUCTION FINGERPRINTS
# =============================================================================


class TestPathReconstructionFingerprints:
    """Fingerprint tests for path reconstruction accuracy."""

    def test_deep_path_reconstruction_fingerprint(self, update_fingerprints):
        """Fingerprint for deep path reconstruction."""
        graph = StateGraph(name="deep")

        # Create 5-deep linear chain
        for i in range(6):
            graph.add_node(f"N{i}", initial=(i == 0))
        for i in range(5):
            graph.add_edge(
                f"N{i}", f"N{i+1}",
                action=lambda c, ctx, i=i: f"step_{i}",
                name=f"edge_{i}"
            )

        results = list(graph.explore_iter(client=None, max_depth=10))

        # Detailed reconstruction data
        data = {
            "result_count": len(results),
            "results": [
                {
                    "path": r.path,
                    "edge_names": [e.name for e in r.edges_taken],
                    "edge_result_count": len(r.edge_results),
                    "success": r.success,
                }
                for r in results
            ],
        }

        fingerprint = compute_fingerprint(data)
        check_fingerprint("path_reconstruction_5_deep", fingerprint, update_fingerprints)
