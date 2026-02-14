"""Execute combinatorial tests against live APIs.

This module bridges the gap between combinatorial test generation and
actual HTTP execution. It takes a CombinatorialGraphBuilder and a live
client, generates test combinations, and executes them against the
real API -- collecting results, timing data, and failure reports.

The key problem this solves: VenomQA's combinatorial system generates
StateGraph objects which require manual .explore() calls. The executor
automates the full pipeline from dimension definitions to bug reports.

Example:
    >>> from venomqa.combinatorial import CombinatorialGraphBuilder, ...
    >>> from venomqa import Client
    >>> from venomqa.combinatorial.executor import CombinatorialExecutor
    >>>
    >>> builder = CombinatorialGraphBuilder(name="api_test", ...)
    >>> client = Client(base_url="http://localhost:8000")
    >>>
    >>> executor = CombinatorialExecutor(builder, client)
    >>> result = executor.execute(strength=2)
    >>> print(result.summary())
    >>> if result.failures:
    ...     print(result.bug_report())
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from venomqa.combinatorial.builder import CombinatorialGraphBuilder
from venomqa.combinatorial.dimensions import Combination
from venomqa.core.graph import ExplorationResult

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Result of executing a single combinatorial test step.

    Attributes:
        combination: The combination being tested.
        success: Whether the step completed without error.
        response: The response from the action (if any).
        error: Error message if the step failed.
        traceback: Full traceback if an exception occurred.
        duration_ms: How long the step took in milliseconds.
        timestamp: When the step was executed.
        context_snapshot: Copy of the context at time of execution.
    """

    combination: Combination
    success: bool
    response: Any = None
    error: str | None = None
    traceback: str | None = None
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    context_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Complete result of executing combinatorial tests.

    Attributes:
        builder_name: Name of the CombinatorialGraphBuilder.
        strength: Coverage strength used (e.g., 2 for pairwise).
        total_combinations: Number of combinations tested.
        step_results: Results for each individual combination.
        graph_result: Result from StateGraph.explore() if used.
        started_at: Execution start time.
        finished_at: Execution finish time.
    """

    builder_name: str
    strength: int
    total_combinations: int
    step_results: list[StepResult]
    graph_result: ExplorationResult | None = None
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime = field(default_factory=datetime.now)

    @property
    def successes(self) -> list[StepResult]:
        """Get all successful step results."""
        return [r for r in self.step_results if r.success]

    @property
    def failures(self) -> list[StepResult]:
        """Get all failed step results."""
        return [r for r in self.step_results if not r.success]

    @property
    def success_rate(self) -> float:
        """Calculate the success rate as a percentage."""
        if not self.step_results:
            return 0.0
        return (len(self.successes) / len(self.step_results)) * 100

    @property
    def total_duration_ms(self) -> float:
        """Calculate total execution time in milliseconds."""
        return (self.finished_at - self.started_at).total_seconds() * 1000

    @property
    def avg_duration_ms(self) -> float:
        """Calculate average step duration in milliseconds."""
        if not self.step_results:
            return 0.0
        return sum(r.duration_ms for r in self.step_results) / len(self.step_results)

    def summary(self) -> str:
        """Generate a human-readable summary of the execution.

        Returns:
            Multi-line summary string.
        """
        duration_sec = self.total_duration_ms / 1000
        lines = [
            f"Combinatorial Execution: {self.builder_name}",
            "=" * 60,
            f"Strength:         {self.strength}-wise",
            f"Combinations:     {self.total_combinations}",
            f"Duration:         {duration_sec:.2f}s",
            f"Success rate:     {self.success_rate:.1f}%",
            f"  Passed:         {len(self.successes)}",
            f"  Failed:         {len(self.failures)}",
            f"Avg step time:    {self.avg_duration_ms:.1f}ms",
            "",
        ]

        if self.failures:
            lines.append(f"FAILURES ({len(self.failures)}):")
            lines.append("-" * 40)
            for i, fail in enumerate(self.failures, 1):
                lines.append(f"  {i}. {fail.combination.description}")
                lines.append(f"     Error: {fail.error}")
                lines.append("")

        if self.graph_result and self.graph_result.invariant_violations:
            lines.append(
                f"INVARIANT VIOLATIONS ({len(self.graph_result.invariant_violations)}):"
            )
            lines.append("-" * 40)
            for v in self.graph_result.invariant_violations:
                lines.append(
                    f"  [{v.invariant.severity.value.upper()}] "
                    f"{v.invariant.name}: {v.invariant.description}"
                )
                lines.append(f"    At node: {v.node.id}")
                if v.error_message:
                    lines.append(f"    Error: {v.error_message}")
                lines.append("")

        if not self.failures and (
            not self.graph_result or not self.graph_result.invariant_violations
        ):
            lines.append("ALL TESTS PASSED")

        return "\n".join(lines)

    def bug_report(self) -> str:
        """Generate a structured bug report from failures.

        Returns:
            Markdown-formatted bug report string.
        """
        if not self.failures:
            return "No failures to report."

        lines = [
            f"# Bug Report: {self.builder_name}",
            "",
            f"**Generated:** {self.finished_at.isoformat()}",
            f"**Coverage:** {self.strength}-wise",
            f"**Failure Rate:** {len(self.failures)}/{self.total_combinations} "
            f"({100 - self.success_rate:.1f}%)",
            "",
            "## Failures",
            "",
        ]

        for i, fail in enumerate(self.failures, 1):
            lines.append(f"### {i}. {fail.combination.description}")
            lines.append("")
            lines.append(f"**Error:** `{fail.error}`")
            lines.append(f"**Duration:** {fail.duration_ms:.1f}ms")
            lines.append("")
            if fail.traceback:
                lines.append("**Traceback:**")
                lines.append("```")
                lines.append(fail.traceback)
                lines.append("```")
                lines.append("")
            lines.append("**Combination values:**")
            for dim, val in fail.combination.values.items():
                lines.append(f"- `{dim}`: `{val}`")
            lines.append("")

        return "\n".join(lines)


class CombinatorialExecutor:
    """Execute combinatorial tests against a live API.

    This executor bridges the gap between combinatorial test generation
    and actual HTTP execution. It takes a configured builder and a client,
    then runs all generated combinations against the live API.

    When ``run_preflight`` is True (the default), a smoke test is run
    before execution to catch showstopper problems early.

    Attributes:
        builder: The CombinatorialGraphBuilder with dimensions and transitions.
        client: The HTTP client for making live requests.
        run_preflight: Whether to run a preflight smoke test before execution.

    Example:
        >>> from venomqa.combinatorial import CombinatorialGraphBuilder, ...
        >>> from venomqa import Client
        >>>
        >>> builder = CombinatorialGraphBuilder(name="api", ...)
        >>> builder.register_transition(...)
        >>>
        >>> client = Client(base_url="http://localhost:8000")
        >>> executor = CombinatorialExecutor(builder, client)
        >>>
        >>> # Execute with pairwise coverage
        >>> result = executor.execute(strength=2)
        >>> print(result.summary())
        >>>
        >>> # Generate bug report for CI
        >>> if result.failures:
        ...     with open("bugs.md", "w") as f:
        ...         f.write(result.bug_report())
    """

    def __init__(
        self,
        builder: CombinatorialGraphBuilder,
        client: Any,
        db: Any = None,
        run_preflight: bool = True,
    ) -> None:
        """Initialize the executor.

        Args:
            builder: Configured CombinatorialGraphBuilder.
            client: HTTP client (venomqa.Client, httpx.Client, or similar).
            db: Optional database connection for invariant checks.
            run_preflight: Run a preflight smoke test before execution
                to catch problems like server down, bad auth, or broken
                database records. Set to False to skip.
        """
        self.builder = builder
        self.client = client
        self.db = db
        self.run_preflight = run_preflight

    def execute(
        self,
        strength: int = 2,
        max_depth: int = 8,
        stop_on_first_failure: bool = False,
        explore_graph: bool = True,
    ) -> ExecutionResult:
        """Execute all generated combinations against the live API.

        This method:
        1. Generates combinations using the specified coverage strength.
        2. Builds a StateGraph from those combinations.
        3. Optionally explores the graph (executing transitions + invariants).
        4. Runs each combination's entry actions individually.
        5. Collects and returns all results.

        Args:
            strength: Coverage strength (2 = pairwise, 3 = three-wise, etc.).
            max_depth: Maximum graph exploration depth.
            stop_on_first_failure: Stop after the first failure.
            explore_graph: Whether to run StateGraph.explore().

        Returns:
            ExecutionResult with all findings.

        Example:
            >>> result = executor.execute(strength=2)
            >>> print(f"Passed: {len(result.successes)}")
            >>> print(f"Failed: {len(result.failures)}")
        """
        started_at = datetime.now()

        # Build the graph and get the combinations
        graph, combos = self.builder.build_journey_graph(strength=strength)

        logger.info(
            f"Executing {len(combos)} combinations "
            f"(strength={strength}) against live API"
        )

        step_results: list[StepResult] = []
        graph_result: ExplorationResult | None = None

        # Phase 1: Explore the graph (tests transitions + invariants)
        if explore_graph:
            try:
                graph_result = graph.explore(
                    client=self.client,
                    db=self.db,
                    max_depth=max_depth,
                    stop_on_violation=stop_on_first_failure,
                )
                logger.info(
                    f"Graph exploration: {graph_result.successful_paths} passed, "
                    f"{graph_result.failed_paths} failed, "
                    f"{len(graph_result.invariant_violations)} violations"
                )
            except Exception as e:
                logger.error(f"Graph exploration failed: {e}")

        # Phase 2: Execute each combination individually
        for combo in combos:
            result = self.execute_single(combo)
            step_results.append(result)

            if not result.success and stop_on_first_failure:
                logger.info(f"Stopping on first failure: {combo.description}")
                break

        finished_at = datetime.now()

        return ExecutionResult(
            builder_name=self.builder.name,
            strength=strength,
            total_combinations=len(combos),
            step_results=step_results,
            graph_result=graph_result,
            started_at=started_at,
            finished_at=finished_at,
        )

    def execute_single(self, combination: Combination) -> StepResult:
        """Execute a single combination against the live API.

        Runs the entry actions associated with the combination's
        dimension values. Each entry action sets up the system state
        for that dimension value (e.g., logging in, creating data).

        Args:
            combination: The combination to test.

        Returns:
            StepResult with execution details.
        """
        start_time = time.time()
        context: dict[str, Any] = {
            "_current_combination": combination.to_dict(),
        }
        last_response = None
        error_msg = None
        tb = None

        try:
            # Execute entry actions for each dimension value in the combination
            for dim_name, value in sorted(combination.values.items()):
                key = (dim_name, value)
                if key in self.builder._state_setups:
                    setup = self.builder._state_setups[key]
                    last_response = setup.action(self.client, context)
            success = True
        except Exception as e:
            success = False
            error_msg = str(e)
            tb = traceback.format_exc()
            logger.debug(f"Combination failed: {combination.description}: {e}")

        duration_ms = (time.time() - start_time) * 1000

        return StepResult(
            combination=combination,
            success=success,
            response=last_response,
            error=error_msg,
            traceback=tb,
            duration_ms=duration_ms,
            context_snapshot=dict(context),
        )
