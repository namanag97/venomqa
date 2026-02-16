"""Golden file / snapshot tests.

These tests compare actual outputs against known-good "golden" files.
Any change to behavior shows up clearly in git diff.

Key principle: The expected output is stored in a SEPARATE FILE that
the AI cannot silently modify along with the code. Any change requires
explicit human approval via --update-golden flag.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from venomqa.core.graph import StateGraph


# Path to golden files
GOLDEN_DIR = Path(__file__).parent / "golden"


def load_golden(name: str) -> dict[str, Any]:
    """Load a golden file."""
    path = GOLDEN_DIR / f"{name}.json"
    if not path.exists():
        pytest.skip(f"Golden file {path} does not exist. Run with --update-golden to create.")
    return json.loads(path.read_text())


def save_golden(name: str, data: dict[str, Any]) -> None:
    """Save a golden file."""
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = GOLDEN_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str))


def compare_golden(name: str, actual: dict[str, Any], update: bool = False) -> None:
    """Compare actual output against golden file."""
    if update:
        save_golden(name, actual)
        return

    expected = load_golden(name)

    # Deep comparison
    assert actual == expected, (
        f"Output differs from golden file '{name}.json'.\n"
        f"Run with --update-golden to update if this is intentional.\n"
        f"Actual: {json.dumps(actual, indent=2, default=str)[:500]}...\n"
        f"Expected: {json.dumps(expected, indent=2, default=str)[:500]}..."
    )


@pytest.fixture
def update_golden(request):
    """Fixture to check if --update-golden flag is set."""
    return request.config.getoption("--update-golden", default=False)


def pytest_addoption(parser):
    """Add --update-golden option to pytest."""
    try:
        parser.addoption(
            "--update-golden",
            action="store_true",
            default=False,
            help="Update golden files with current output"
        )
    except ValueError:
        # Option already added
        pass


# =============================================================================
# GOLDEN FILE TESTS
# =============================================================================


class TestGraphExplorationGolden:
    """Golden tests for graph exploration output format."""

    def test_simple_graph_exploration_output(self, update_golden):
        """Verify exploration result format is stable."""
        graph = StateGraph(name="golden_test")
        graph.add_node("start", initial=True)
        graph.add_node("middle")
        graph.add_node("end")
        graph.add_edge("start", "middle", action=lambda c, ctx: {"step": 1}, name="step1")
        graph.add_edge("middle", "end", action=lambda c, ctx: {"step": 2}, name="step2")

        result = graph.explore(client=None, max_depth=10)

        # Extract stable output (excluding timestamps)
        actual = {
            "graph_name": result.graph_name,
            "total_paths": result.total_paths,
            "successful_paths": result.successful_paths,
            "failed_paths": result.failed_paths,
            "nodes_visited": sorted(result.nodes_visited),
            "edges_executed": sorted(result.edges_executed),
            "paths": [
                {
                    "path": p.path,
                    "edges_taken": [e.name for e in p.edges_taken],
                    "success": p.success,
                }
                for p in result.paths_explored
            ],
        }

        compare_golden("simple_graph_exploration", actual, update_golden)

    def test_branching_graph_exploration_output(self, update_golden):
        """Verify branching exploration output is stable."""
        graph = StateGraph(name="branching_golden")
        graph.add_node("root", initial=True)
        graph.add_node("left")
        graph.add_node("right")
        graph.add_node("left_end")
        graph.add_node("right_end")

        graph.add_edge("root", "left", action=lambda c, ctx: "L", name="go_left")
        graph.add_edge("root", "right", action=lambda c, ctx: "R", name="go_right")
        graph.add_edge("left", "left_end", action=lambda c, ctx: "LE", name="left_finish")
        graph.add_edge("right", "right_end", action=lambda c, ctx: "RE", name="right_finish")

        result = graph.explore(client=None, max_depth=10)

        actual = {
            "graph_name": result.graph_name,
            "total_paths": result.total_paths,
            "nodes_visited": sorted(result.nodes_visited),
            "edges_executed": sorted(result.edges_executed),
            "paths": sorted([
                {
                    "path": p.path,
                    "success": p.success,
                }
                for p in result.paths_explored
            ], key=lambda x: str(x["path"])),
        }

        compare_golden("branching_graph_exploration", actual, update_golden)


class TestExplorationNodeGolden:
    """Golden tests for ExplorationNode structure."""

    def test_path_reconstruction_format(self, update_golden):
        """Verify path reconstruction output format is stable."""
        graph = StateGraph(name="reconstruction_test")
        graph.add_node("A", initial=True)
        graph.add_node("B")
        graph.add_node("C")
        graph.add_node("D")
        graph.add_edge("A", "B", action=lambda c, ctx: "ab", name="a_to_b")
        graph.add_edge("B", "C", action=lambda c, ctx: "bc", name="b_to_c")
        graph.add_edge("C", "D", action=lambda c, ctx: "cd", name="c_to_d")

        results = list(graph.explore_iter(client=None, max_depth=10))

        actual = {
            "result_count": len(results),
            "results": [
                {
                    "path": r.path,
                    "edges": [e.name for e in r.edges_taken],
                    "success": r.success,
                    "edge_count": len(r.edge_results),
                }
                for r in results
            ],
        }

        compare_golden("path_reconstruction", actual, update_golden)


class TestSummaryFormatGolden:
    """Golden tests for summary output format."""

    def test_exploration_summary_format(self, update_golden):
        """Verify summary() output format is stable."""
        graph = StateGraph(name="summary_test")
        graph.add_node("start", initial=True)
        graph.add_node("end")
        graph.add_edge("start", "end", action=lambda c, ctx: "ok", name="go")

        result = graph.explore(client=None, max_depth=10)
        summary = result.summary()

        # Hash the summary to detect format changes
        summary_hash = hashlib.sha256(summary.encode()).hexdigest()[:16]

        # Check key content is present (not exact match due to timestamps)
        actual = {
            "contains_graph_name": "summary_test" in summary,
            "contains_nodes_visited": "Nodes visited:" in summary,
            "contains_edges_executed": "Edges executed:" in summary,
            "contains_paths_explored": "Paths explored:" in summary,
            "line_count": len(summary.strip().split("\n")),
        }

        compare_golden("summary_format", actual, update_golden)
