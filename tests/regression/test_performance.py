"""Performance regression tests.

These tests track timing and memory characteristics.
Performance degradation is detected even if functional tests pass.

Key metrics:
- Execution time (with statistical analysis)
- Memory usage (peak and steady-state)
- Throughput (operations per second)
"""

from __future__ import annotations

import gc
import statistics
import time
import tracemalloc
from dataclasses import dataclass
from typing import Callable

import pytest

from venomqa.core.graph import StateGraph


@dataclass
class PerfResult:
    """Performance measurement result."""
    name: str
    timing_ms: list[float]
    memory_peak_kb: float
    memory_current_kb: float

    @property
    def timing_mean_ms(self) -> float:
        return statistics.mean(self.timing_ms)

    @property
    def timing_std_ms(self) -> float:
        return statistics.stdev(self.timing_ms) if len(self.timing_ms) > 1 else 0.0

    @property
    def timing_p95_ms(self) -> float:
        sorted_times = sorted(self.timing_ms)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]


def measure_performance(
    func: Callable[[], None],
    name: str,
    iterations: int = 5,
    warmup: int = 1,
) -> PerfResult:
    """Measure performance of a function."""
    # Warmup
    for _ in range(warmup):
        func()

    # Measure timing
    timings = []
    for _ in range(iterations):
        gc.collect()
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        timings.append((end - start) * 1000)

    # Measure memory
    gc.collect()
    tracemalloc.start()
    func()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return PerfResult(
        name=name,
        timing_ms=timings,
        memory_peak_kb=peak / 1024,
        memory_current_kb=current / 1024,
    )


# =============================================================================
# PERFORMANCE BASELINES
# =============================================================================
# These are "acceptable" performance bounds.
# If exceeded, something has regressed.

PERFORMANCE_BASELINES = {
    # Timing baselines (mean ms) - generous bounds
    "linear_10_nodes_timing_ms": 50.0,
    "tree_3x4_timing_ms": 200.0,
    "wide_10_branches_timing_ms": 100.0,

    # Memory baselines (peak KB)
    "linear_10_nodes_memory_kb": 500.0,
    "tree_3x4_memory_kb": 2000.0,
    "wide_10_branches_memory_kb": 1000.0,

    # Throughput baselines (paths per second)
    "exploration_throughput_paths_per_sec": 100.0,
}


def check_performance(result: PerfResult, metric: str, baseline_key: str) -> None:
    """Check performance against baseline."""
    baseline = PERFORMANCE_BASELINES.get(baseline_key)

    if baseline is None:
        pytest.skip(f"No baseline for {baseline_key}")

    if metric == "timing":
        actual = result.timing_mean_ms
        assert actual < baseline, (
            f"Timing regression for {result.name}!\n"
            f"Mean: {actual:.2f}ms (baseline: {baseline:.2f}ms)\n"
            f"P95: {result.timing_p95_ms:.2f}ms\n"
            f"Std: {result.timing_std_ms:.2f}ms"
        )
    elif metric == "memory":
        actual = result.memory_peak_kb
        assert actual < baseline, (
            f"Memory regression for {result.name}!\n"
            f"Peak: {actual:.2f}KB (baseline: {baseline:.2f}KB)"
        )


# =============================================================================
# TIMING TESTS
# =============================================================================


class TestTimingRegression:
    """Tests for timing regression."""

    def test_linear_graph_timing(self):
        """Timing for linear graph exploration."""
        graph = StateGraph(name="linear")
        for i in range(11):
            graph.add_node(f"N{i}", initial=(i == 0))
        for i in range(10):
            graph.add_edge(
                f"N{i}", f"N{i+1}",
                action=lambda c, ctx: "ok",
                name=f"e{i}"
            )

        def run():
            list(graph.explore_iter(client=None, max_depth=20))

        result = measure_performance(run, "linear_10_nodes", iterations=5)
        check_performance(result, "timing", "linear_10_nodes_timing_ms")

    def test_tree_graph_timing(self):
        """Timing for tree graph exploration."""
        graph = StateGraph(name="tree")
        graph.add_node("root", initial=True)

        # 3-wide, 4-deep tree
        nodes_at_level = {0: ["root"]}
        for level in range(1, 4):
            nodes_at_level[level] = []
            for parent in nodes_at_level[level - 1]:
                for c in range(3):
                    child = f"L{level}_N{len(nodes_at_level[level])}"
                    graph.add_node(child)
                    nodes_at_level[level].append(child)
                    graph.add_edge(
                        parent, child,
                        action=lambda c, ctx: "ok",
                        name=f"{parent}_to_{child}"
                    )

        def run():
            list(graph.explore_iter(client=None, max_depth=10))

        result = measure_performance(run, "tree_3x4", iterations=3)
        check_performance(result, "timing", "tree_3x4_timing_ms")

    def test_wide_graph_timing(self):
        """Timing for wide (high branching factor) graph."""
        graph = StateGraph(name="wide")
        graph.add_node("root", initial=True)

        for i in range(10):
            child = f"child_{i}"
            graph.add_node(child)
            graph.add_edge(
                "root", child,
                action=lambda c, ctx: "ok",
                name=f"to_{child}"
            )

        def run():
            list(graph.explore_iter(client=None, max_depth=10))

        result = measure_performance(run, "wide_10_branches", iterations=5)
        check_performance(result, "timing", "wide_10_branches_timing_ms")


# =============================================================================
# MEMORY TESTS
# =============================================================================


class TestMemoryRegression:
    """Tests for memory regression."""

    def test_linear_graph_memory(self):
        """Memory for linear graph exploration."""
        graph = StateGraph(name="linear")
        for i in range(11):
            graph.add_node(f"N{i}", initial=(i == 0))
        for i in range(10):
            graph.add_edge(
                f"N{i}", f"N{i+1}",
                action=lambda c, ctx: "ok",
                name=f"e{i}"
            )

        def run():
            list(graph.explore_iter(client=None, max_depth=20))

        result = measure_performance(run, "linear_10_nodes", iterations=1)
        check_performance(result, "memory", "linear_10_nodes_memory_kb")

    def test_tree_graph_memory(self):
        """Memory for tree graph exploration."""
        graph = StateGraph(name="tree")
        graph.add_node("root", initial=True)

        nodes_at_level = {0: ["root"]}
        for level in range(1, 4):
            nodes_at_level[level] = []
            for parent in nodes_at_level[level - 1]:
                for c in range(3):
                    child = f"L{level}_N{len(nodes_at_level[level])}"
                    graph.add_node(child)
                    nodes_at_level[level].append(child)
                    graph.add_edge(
                        parent, child,
                        action=lambda c, ctx: "ok",
                        name=f"{parent}_to_{child}"
                    )

        def run():
            list(graph.explore_iter(client=None, max_depth=10))

        result = measure_performance(run, "tree_3x4", iterations=1)
        check_performance(result, "memory", "tree_3x4_memory_kb")


# =============================================================================
# THROUGHPUT TESTS
# =============================================================================


class TestThroughputRegression:
    """Tests for throughput regression."""

    def test_exploration_throughput(self):
        """Measure paths explored per second."""
        # Create a graph with many paths
        graph = StateGraph(name="throughput")
        graph.add_node("root", initial=True)

        for i in range(5):
            mid = f"mid_{i}"
            graph.add_node(mid)
            graph.add_edge("root", mid, action=lambda c, ctx: "ok", name=f"to_{mid}")

            for j in range(5):
                leaf = f"leaf_{i}_{j}"
                graph.add_node(leaf)
                graph.add_edge(mid, leaf, action=lambda c, ctx: "ok", name=f"to_{leaf}")

        # Measure
        gc.collect()
        start = time.perf_counter()
        results = list(graph.explore_iter(client=None, max_depth=10))
        end = time.perf_counter()

        duration_sec = end - start
        paths_per_sec = len(results) / duration_sec if duration_sec > 0 else float('inf')

        baseline = PERFORMANCE_BASELINES["exploration_throughput_paths_per_sec"]
        assert paths_per_sec >= baseline, (
            f"Throughput regression!\n"
            f"Actual: {paths_per_sec:.1f} paths/sec\n"
            f"Baseline: {baseline:.1f} paths/sec\n"
            f"Paths: {len(results)}, Duration: {duration_sec:.3f}s"
        )


# =============================================================================
# SCALING TESTS
# =============================================================================


class TestScalingRegression:
    """Tests for algorithmic complexity regression."""

    def test_linear_scaling_with_depth(self):
        """Memory should scale linearly with depth, not exponentially."""
        measurements = []

        for depth in [5, 10, 15]:
            graph = StateGraph(name=f"depth_{depth}")
            for i in range(depth + 1):
                graph.add_node(f"N{i}", initial=(i == 0))
            for i in range(depth):
                graph.add_edge(
                    f"N{i}", f"N{i+1}",
                    action=lambda c, ctx: "ok",
                    name=f"e{i}"
                )

            gc.collect()
            tracemalloc.start()
            list(graph.explore_iter(client=None, max_depth=depth + 5))
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            measurements.append((depth, peak / 1024))

        # Memory should grow roughly linearly with depth
        # Check that doubling depth doesn't more than triple memory
        depth_5_mem = measurements[0][1]
        depth_10_mem = measurements[1][1]
        depth_15_mem = measurements[2][1]

        # Allow some overhead, but shouldn't be exponential
        assert depth_10_mem < depth_5_mem * 4, (
            f"Memory scaling too steep! "
            f"Depth 5: {depth_5_mem:.1f}KB, Depth 10: {depth_10_mem:.1f}KB"
        )
        assert depth_15_mem < depth_10_mem * 4, (
            f"Memory scaling too steep! "
            f"Depth 10: {depth_10_mem:.1f}KB, Depth 15: {depth_15_mem:.1f}KB"
        )
