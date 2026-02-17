"""Batch execution of independent journeys with concurrency control.

This module provides parallel execution of test journeys with configurable
concurrency limits, progress tracking, and result aggregation. Key features:

- Configurable maximum concurrent executions
- Per-journey timeouts
- Fail-fast mode to stop on first failure
- Real-time progress callbacks
- Comprehensive result aggregation and statistics

Example:
    >>> from venomqa.performance import BatchExecutor, BatchProgress
    >>>
    >>> def on_progress(progress: BatchProgress) -> None:
    ...     print(f"Progress: {progress.progress_percent:.1f}%")
    >>>
    >>> executor = BatchExecutor(
    ...     max_concurrent=4,
    ...     timeout_per_journey=30.0,
    ...     progress_callback=on_progress,
    ... )
    >>> result = executor.execute(journeys, runner_factory)
    >>> print(f"Success rate: {result.success_rate:.1f}%")
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from venomqa.core.models import Journey, JourneyResult

logger = logging.getLogger(__name__)


@dataclass
class BatchProgress:
    """Real-time progress information for batch execution.

    Tracks the state of a running batch including counts of completed,
    failed, in-progress, and pending journeys. Provides calculated
    properties for progress percentage and estimated remaining time.

    Attributes:
        total: Total number of journeys to execute.
        completed: Number of journeys that finished (success or failure).
        failed: Number of journeys that failed.
        in_progress: Number of journeys currently executing.
        pending: Number of journeys waiting to start.
        started_at: When batch execution began.
        current_journey: Name of the most recently started journey.
        results: List of completed journey results.
    """

    total: int = 0
    completed: int = 0
    failed: int = 0
    in_progress: int = 0
    pending: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    current_journey: str = ""
    results: list[JourneyResult] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time since batch execution started.

        Returns:
            Seconds elapsed since started_at.
        """
        return (datetime.now() - self.started_at).total_seconds()

    @property
    def progress_percent(self) -> float:
        """Get completion percentage.

        Returns:
            Percentage of total journeys completed (0.0 to 100.0).
        """
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100

    @property
    def success_rate(self) -> float:
        """Get success rate of completed journeys.

        Returns:
            Percentage of completed journeys that succeeded (0.0 to 100.0).
        """
        if self.completed == 0:
            return 0.0
        return ((self.completed - self.failed) / self.completed) * 100

    @property
    def estimated_remaining_seconds(self) -> float | None:
        """Estimate remaining time based on average completion rate.

        Returns:
            Estimated seconds remaining, or None if no journeys completed yet.
        """
        if self.completed == 0:
            return None
        avg_time = self.elapsed_seconds / self.completed
        return avg_time * self.pending

    @property
    def throughput(self) -> float:
        """Get current throughput in journeys per second.

        Returns:
            Journeys completed per second.
        """
        if self.elapsed_seconds == 0:
            return 0.0
        return self.completed / self.elapsed_seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert progress to a dictionary for serialization.

        Returns:
            Dictionary with all progress metrics.
        """
        remaining = self.estimated_remaining_seconds
        return {
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "in_progress": self.in_progress,
            "pending": self.pending,
            "progress_percent": f"{self.progress_percent:.1f}%",
            "success_rate": f"{self.success_rate:.1f}%",
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "estimated_remaining_seconds": round(remaining, 2) if remaining else None,
            "current_journey": self.current_journey,
            "throughput_per_sec": round(self.throughput, 2),
        }


@dataclass
class BatchResult:
    """Final result of a batch execution.

    Contains aggregate statistics and all individual journey results
    after batch execution completes.

    Attributes:
        total: Total number of journeys that were in the batch.
        passed: Number of journeys that succeeded.
        failed: Number of journeys that failed.
        duration_ms: Total batch execution time in milliseconds.
        journey_results: List of all individual journey results.
        started_at: When batch execution began.
        finished_at: When batch execution completed.
        timed_out: Number of journeys that timed out.
        errors: List of error messages from failed journeys.
    """

    total: int
    passed: int
    failed: int
    duration_ms: float
    journey_results: list[JourneyResult]
    started_at: datetime
    finished_at: datetime
    timed_out: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Get overall success rate.

        Returns:
            Percentage of journeys that passed (0.0 to 100.0).
        """
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100

    @property
    def avg_journey_duration_ms(self) -> float:
        """Get average journey duration.

        Returns:
            Average duration in milliseconds.
        """
        if not self.journey_results:
            return 0.0
        total = sum(r.duration_ms for r in self.journey_results)
        return total / len(self.journey_results)

    @property
    def min_journey_duration_ms(self) -> float:
        """Get minimum journey duration."""
        if not self.journey_results:
            return 0.0
        return min(r.duration_ms for r in self.journey_results)

    @property
    def max_journey_duration_ms(self) -> float:
        """Get maximum journey duration."""
        if not self.journey_results:
            return 0.0
        return max(r.duration_ms for r in self.journey_results)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to a dictionary for serialization.

        Returns:
            Dictionary with all result metrics.
        """
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "timed_out": self.timed_out,
            "success_rate": f"{self.success_rate:.1f}%",
            "duration_ms": round(self.duration_ms, 2),
            "avg_journey_ms": round(self.avg_journey_duration_ms, 2),
            "min_journey_ms": round(self.min_journey_duration_ms, 2),
            "max_journey_ms": round(self.max_journey_duration_ms, 2),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "error_count": len(self.errors),
        }

    def get_failed_journeys(self) -> list[JourneyResult]:
        """Get list of failed journey results.

        Returns:
            List of JourneyResult objects for failed journeys.
        """
        return [r for r in self.journey_results if not r.success]

    def get_passed_journeys(self) -> list[JourneyResult]:
        """Get list of passed journey results.

        Returns:
            List of JourneyResult objects for passed journeys.
        """
        return [r for r in self.journey_results if r.success]


ProgressCallback = Callable[[BatchProgress], None]
RunnerFactory = Callable[[], Any]


class BatchExecutor:
    """Execute multiple journeys concurrently with resource limits.

    Manages parallel execution of test journeys with configurable concurrency,
    timeouts, and progress tracking. Supports fail-fast mode to stop execution
    on first failure.

    Attributes:
        max_concurrent: Maximum number of journeys to run simultaneously.
        timeout_per_journey: Optional timeout in seconds for each journey.
        fail_fast: If True, stop execution on first failure.
        progress_callback: Optional callback for progress updates.
        progress_interval: Minimum seconds between progress callbacks.

    Example:
        >>> executor = BatchExecutor(
        ...     max_concurrent=8,
        ...     timeout_per_journey=60.0,
        ...     fail_fast=False,
        ...     progress_callback=lambda p: print(f"{p.progress_percent:.0f}%"),
        ... )
        >>> result = executor.execute(journeys, lambda: JourneyRunner(client))
        >>> print(f"Passed: {result.passed}/{result.total}")
    """

    def __init__(
        self,
        max_concurrent: int = 4,
        timeout_per_journey: float | None = None,
        fail_fast: bool = False,
        progress_callback: ProgressCallback | None = None,
        progress_interval: float = 1.0,
    ) -> None:
        """Initialize the batch executor.

        Args:
            max_concurrent: Maximum concurrent journeys. Defaults to 4.
            timeout_per_journey: Per-journey timeout in seconds. None for no timeout.
            fail_fast: Stop on first failure if True.
            progress_callback: Callback function for progress updates.
            progress_interval: Minimum interval between progress callbacks in seconds.

        Raises:
            ValueError: If max_concurrent < 1 or progress_interval < 0.
        """
        if max_concurrent < 1:
            raise ValueError(f"max_concurrent must be >= 1, got {max_concurrent}")
        if progress_interval < 0:
            raise ValueError(f"progress_interval must be >= 0, got {progress_interval}")

        self.max_concurrent = max_concurrent
        self.timeout_per_journey = timeout_per_journey
        self.fail_fast = fail_fast
        self.progress_callback = progress_callback
        self.progress_interval = progress_interval

        self._progress = BatchProgress()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._last_progress_update: float = 0.0
        self._timed_out_count: int = 0
        self._errors: list[str] = []

    def execute(
        self,
        journeys: list[Journey],
        runner_factory: RunnerFactory,
    ) -> BatchResult:
        """Execute journeys concurrently using provided runner factory.

        Submits all journeys to a thread pool and collects results as they
        complete. Progress callbacks are invoked periodically. Supports
        early termination via fail_fast or stop().

        Args:
            journeys: List of Journey objects to execute.
            runner_factory: Callable that returns a fresh JourneyRunner.
                Called once per journey to ensure isolation.

        Returns:
            BatchResult with aggregate statistics and individual results.

        Example:
            >>> def make_runner():
            ...     return JourneyRunner(Client(base_url="https://api.example.com"))
            >>> result = executor.execute(journeys, make_runner)
        """
        self._stop_event.clear()
        self._timed_out_count = 0
        self._errors = []
        started_at = datetime.now()

        with self._lock:
            self._progress = BatchProgress(
                total=len(journeys),
                pending=len(journeys),
                started_at=started_at,
            )

        journey_results: list[JourneyResult] = []
        futures: dict[Future[JourneyResult], Journey] = {}

        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            for journey in journeys:
                if self._stop_event.is_set():
                    break

                future = executor.submit(
                    self._run_journey,
                    journey,
                    runner_factory,
                )
                futures[future] = journey

            for future in as_completed(futures):
                if self._stop_event.is_set():
                    break

                journey = futures[future]

                with self._lock:
                    self._progress.current_journey = journey.name

                try:
                    result = (
                        future.result(timeout=self.timeout_per_journey)
                        if self.timeout_per_journey
                        else future.result()
                    )

                    with self._lock:
                        self._progress.completed += 1
                        self._progress.pending -= 1
                        if not result.success:
                            self._progress.failed += 1
                            for issue in result.issues:
                                self._errors.append(f"{journey.name}: {issue.message}")
                        self._progress.results.append(result)

                    journey_results.append(result)

                    if not result.success and self.fail_fast:
                        logger.warning(f"Fail fast triggered by journey: {journey.name}")
                        self._stop_event.set()
                        break

                except TimeoutError:
                    error_msg = (
                        f"Journey {journey.name} timed out after {self.timeout_per_journey}s"
                    )
                    logger.error(error_msg)
                    with self._lock:
                        self._progress.completed += 1
                        self._progress.pending -= 1
                        self._progress.failed += 1
                        self._timed_out_count += 1
                        self._errors.append(error_msg)

                except Exception as e:
                    error_msg = f"Journey {journey.name} raised exception: {e}"
                    logger.exception(error_msg)
                    with self._lock:
                        self._progress.completed += 1
                        self._progress.pending -= 1
                        self._progress.failed += 1
                        self._errors.append(error_msg)

                self._update_progress(force=False)

        finished_at = datetime.now()
        duration_ms = (finished_at - started_at).total_seconds() * 1000

        passed = sum(1 for r in journey_results if r.success)
        failed = len(journey_results) - passed

        return BatchResult(
            total=len(journeys),
            passed=passed,
            failed=failed,
            duration_ms=duration_ms,
            journey_results=journey_results,
            started_at=started_at,
            finished_at=finished_at,
            timed_out=self._timed_out_count,
            errors=self._errors,
        )

    def _run_journey(
        self,
        journey: Journey,
        runner_factory: RunnerFactory,
    ) -> JourneyResult:
        """Run a single journey using a fresh runner.

        Creates a new runner instance for isolation, executes the journey,
        and handles any exceptions.

        Args:
            journey: The journey to execute.
            runner_factory: Callable that creates a runner instance.

        Returns:
            JourneyResult from the execution.
        """
        with self._lock:
            self._progress.in_progress += 1
            self._progress.pending -= 1
            self._progress.current_journey = journey.name

        self._update_progress(force=True)

        try:
            runner = runner_factory()
            result = runner.run(journey)
            return result
        except Exception as e:
            logger.exception(f"Journey {journey.name} raised unhandled exception")
            from venomqa.core.models import JourneyResult

            return JourneyResult(
                journey_name=journey.name,
                success=False,
                steps=[],
                total_steps=0,
                passed_steps=0,
                duration_ms=0.0,
                issues=[],
                error=str(e),
            )
        finally:
            with self._lock:
                self._progress.in_progress -= 1

    def _update_progress(self, force: bool = False) -> None:
        """Invoke progress callback if conditions are met.

        Args:
            force: If True, invoke callback regardless of interval.
        """
        if not self.progress_callback:
            return

        current_time = time.time()
        if not force and (current_time - self._last_progress_update) < self.progress_interval:
            return

        self._last_progress_update = current_time

        try:
            with self._lock:
                progress = BatchProgress(
                    total=self._progress.total,
                    completed=self._progress.completed,
                    failed=self._progress.failed,
                    in_progress=self._progress.in_progress,
                    pending=self._progress.pending,
                    started_at=self._progress.started_at,
                    current_journey=self._progress.current_journey,
                    results=list(self._progress.results),
                )
            self.progress_callback(progress)
        except Exception as e:
            logger.warning(f"Progress callback failed: {e}")

    def stop(self) -> None:
        """Signal batch execution to stop.

        After calling stop(), no new journeys will be started and
        the execute() method will return soon with partial results.
        """
        self._stop_event.set()
        logger.info("Batch execution stop requested")

    def get_progress(self) -> BatchProgress:
        """Get current progress snapshot.

        Returns:
            Copy of current BatchProgress.
        """
        with self._lock:
            return BatchProgress(
                total=self._progress.total,
                completed=self._progress.completed,
                failed=self._progress.failed,
                in_progress=self._progress.in_progress,
                pending=self._progress.pending,
                started_at=self._progress.started_at,
                current_journey=self._progress.current_journey,
                results=list(self._progress.results),
            )


def aggregate_results(results: list[JourneyResult]) -> dict[str, Any]:
    """Aggregate multiple journey results into a comprehensive summary.

    Calculates aggregate statistics across all provided journey results,
    including success rates, timing, and step-level metrics.

    Args:
        results: List of JourneyResult objects to aggregate.

    Returns:
        Dictionary with aggregate statistics and per-journey summaries.

    Example:
        >>> summary = aggregate_results([result1, result2, result3])
        >>> print(f"Overall success rate: {summary['success_rate']}")
    """
    if not results:
        return {
            "total_journeys": 0,
            "passed": 0,
            "failed": 0,
            "total_steps": 0,
            "passed_steps": 0,
            "total_duration_ms": 0.0,
            "issues_count": 0,
            "success_rate": "N/A",
        }

    total_steps = sum(r.total_steps for r in results)
    passed_steps = sum(r.passed_steps for r in results)
    total_duration = sum(r.duration_ms for r in results)
    total_issues = sum(len(r.issues) for r in results)
    passed = sum(1 for r in results if r.success)
    failed = len(results) - passed

    durations = [r.duration_ms for r in results]

    return {
        "total_journeys": len(results),
        "passed": passed,
        "failed": failed,
        "success_rate": f"{(passed / len(results)) * 100:.1f}%",
        "total_steps": total_steps,
        "passed_steps": passed_steps,
        "failed_steps": total_steps - passed_steps,
        "step_success_rate": f"{(passed_steps / max(1, total_steps)) * 100:.1f}%",
        "total_duration_ms": round(total_duration, 2),
        "avg_duration_ms": round(total_duration / len(results), 2),
        "min_duration_ms": round(min(durations), 2),
        "max_duration_ms": round(max(durations), 2),
        "issues_count": total_issues,
        "journey_summaries": [
            {
                "name": r.journey_name,
                "success": r.success,
                "steps": r.total_steps,
                "passed_steps": r.passed_steps,
                "duration_ms": round(r.duration_ms, 2),
                "issues": len(r.issues),
            }
            for r in results
        ],
    }


def default_progress_callback(progress: BatchProgress) -> None:
    """Default progress callback that logs progress to INFO level.

    Args:
        progress: Current batch progress state.
    """
    logger.info(
        f"Batch progress: {progress.completed}/{progress.total} "
        f"({progress.progress_percent:.1f}%) - "
        f"Failed: {progress.failed} - "
        f"In progress: {progress.in_progress}"
    )
    if progress.estimated_remaining_seconds:
        logger.info(f"Estimated remaining: {progress.estimated_remaining_seconds:.1f}s")
