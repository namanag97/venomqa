"""Exploration scheduler for CI and background running."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

from venomqa.v1.core.result import ExplorationResult

if TYPE_CHECKING:
    from venomqa.v1.agent import Agent


@dataclass
class ScheduledRun:
    """A scheduled exploration run."""

    id: str
    name: str
    agent_factory: Callable[[], "Agent"]
    schedule: str  # cron-like or "once"
    enabled: bool = True
    last_run: datetime | None = None
    last_result: ExplorationResult | None = None


@dataclass
class RunResult:
    """Result of a scheduled run."""

    run_id: str
    name: str
    success: bool
    violations_count: int
    states_visited: int
    duration_ms: float
    started_at: datetime
    finished_at: datetime
    error: str | None = None


class Scheduler:
    """Scheduler for running explorations in CI or background.

    The scheduler manages multiple exploration runs and can:
    - Run explorations on-demand
    - Run multiple explorations in parallel
    - Export results in various formats for CI integration
    """

    def __init__(
        self,
        max_workers: int = 4,
        results_dir: str | Path | None = None,
    ) -> None:
        """Initialize the scheduler.

        Args:
            max_workers: Maximum parallel explorations
            results_dir: Directory to store results (optional)
        """
        self.max_workers = max_workers
        self.results_dir = Path(results_dir) if results_dir else None
        self._runs: dict[str, ScheduledRun] = {}
        self._results: list[RunResult] = []
        self._executor: ThreadPoolExecutor | None = None

    def register(
        self,
        run_id: str,
        name: str,
        agent_factory: Callable[[], Agent],
        schedule: str = "once",
    ) -> None:
        """Register an exploration run.

        Args:
            run_id: Unique identifier for this run
            name: Human-readable name
            agent_factory: Function that creates a fresh Agent
            schedule: When to run ("once" or cron expression)
        """
        self._runs[run_id] = ScheduledRun(
            id=run_id,
            name=name,
            agent_factory=agent_factory,
            schedule=schedule,
        )

    def run(self, run_id: str) -> RunResult:
        """Run a single exploration synchronously.

        Args:
            run_id: The run to execute

        Returns:
            The run result
        """
        if run_id not in self._runs:
            raise ValueError(f"Unknown run: {run_id}")

        scheduled_run = self._runs[run_id]
        return self._execute_run(scheduled_run)

    def run_all(self, parallel: bool = True) -> list[RunResult]:
        """Run all registered explorations.

        Args:
            parallel: Whether to run in parallel

        Returns:
            List of all run results
        """
        if parallel:
            return self._run_parallel()
        return self._run_sequential()

    def _run_sequential(self) -> list[RunResult]:
        """Run all explorations sequentially."""
        results = []
        for run in self._runs.values():
            if run.enabled:
                result = self._execute_run(run)
                results.append(result)
        return results

    def _run_parallel(self) -> list[RunResult]:
        """Run all explorations in parallel."""
        results: list[RunResult] = []
        futures: dict[Future[RunResult], str] = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for run in self._runs.values():
                if run.enabled:
                    future = executor.submit(self._execute_run, run)
                    futures[future] = run.id

            for future in futures:
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    # Handle failed runs
                    run_id = futures[future]
                    run = self._runs[run_id]
                    results.append(RunResult(
                        run_id=run_id,
                        name=run.name,
                        success=False,
                        violations_count=0,
                        states_visited=0,
                        duration_ms=0,
                        started_at=datetime.now(),
                        finished_at=datetime.now(),
                        error=str(e),
                    ))

        return results

    def _execute_run(self, run: ScheduledRun) -> RunResult:
        """Execute a single run."""
        started_at = datetime.now()
        error: str | None = None

        try:
            # Create fresh agent
            agent = run.agent_factory()

            # Run exploration
            result = agent.explore()

            # Update run state
            run.last_run = datetime.now()
            run.last_result = result

            run_result = RunResult(
                run_id=run.id,
                name=run.name,
                success=result.success,
                violations_count=len(result.violations),
                states_visited=result.states_visited,
                duration_ms=result.duration_ms,
                started_at=started_at,
                finished_at=datetime.now(),
            )

        except Exception as e:
            run_result = RunResult(
                run_id=run.id,
                name=run.name,
                success=False,
                violations_count=0,
                states_visited=0,
                duration_ms=(datetime.now() - started_at).total_seconds() * 1000,
                started_at=started_at,
                finished_at=datetime.now(),
                error=str(e),
            )

        self._results.append(run_result)
        self._save_result(run_result)

        return run_result

    def _save_result(self, result: RunResult) -> None:
        """Save result to disk if results_dir is configured."""
        if self.results_dir is None:
            return

        self.results_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{result.run_id}_{result.started_at.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.results_dir / filename

        data = {
            "run_id": result.run_id,
            "name": result.name,
            "success": result.success,
            "violations_count": result.violations_count,
            "states_visited": result.states_visited,
            "duration_ms": result.duration_ms,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
            "error": result.error,
        }

        filepath.write_text(json.dumps(data, indent=2))

    def export_junit(self, results: list[RunResult]) -> str:
        """Export results as JUnit XML for CI integration."""
        from xml.etree import ElementTree as ET

        testsuite = ET.Element("testsuite")
        testsuite.set("name", "venomqa")
        testsuite.set("tests", str(len(results)))
        testsuite.set("failures", str(sum(1 for r in results if not r.success)))

        for result in results:
            testcase = ET.SubElement(testsuite, "testcase")
            testcase.set("name", result.name)
            testcase.set("classname", f"venomqa.{result.run_id}")
            testcase.set("time", str(result.duration_ms / 1000))

            if not result.success:
                failure = ET.SubElement(testcase, "failure")
                if result.error:
                    failure.set("message", result.error)
                else:
                    failure.set("message", f"{result.violations_count} violations found")

        tree = ET.ElementTree(testsuite)
        import io
        output = io.StringIO()
        output.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(output, encoding="unicode")
        return output.getvalue()

    def get_results(self) -> list[RunResult]:
        """Get all recorded results."""
        return list(self._results)

    def clear_results(self) -> None:
        """Clear recorded results."""
        self._results.clear()
