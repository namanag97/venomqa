"""Batch execution of independent journeys."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from venomqa.core.models import Journey, JourneyResult

logger = logging.getLogger(__name__)


@dataclass
class BatchProgress:
    """Progress information for batch execution."""

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
        return (datetime.now() - self.started_at).total_seconds()

    @property
    def progress_percent(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100

    @property
    def estimated_remaining_seconds(self) -> float | None:
        if self.completed == 0:
            return None
        avg_time = self.elapsed_seconds / self.completed
        return avg_time * self.pending

    def to_dict(self) -> dict[str, Any]:
        remaining = self.estimated_remaining_seconds
        return {
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "in_progress": self.in_progress,
            "pending": self.pending,
            "progress_percent": f"{self.progress_percent:.1f}%",
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "estimated_remaining_seconds": round(remaining, 2) if remaining else None,
            "current_journey": self.current_journey,
        }


@dataclass
class BatchResult:
    """Result of batch execution."""

    total: int
    passed: int
    failed: int
    duration_ms: float
    journey_results: list[JourneyResult]
    started_at: datetime
    finished_at: datetime

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.passed / self.total) * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "success_rate": f"{self.success_rate:.1f}%",
            "duration_ms": round(self.duration_ms, 2),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }


ProgressCallback = Callable[[BatchProgress], None]


class BatchExecutor:
    """Execute multiple journeys concurrently with resource limits."""

    def __init__(
        self,
        max_concurrent: int = 4,
        timeout_per_journey: float | None = None,
        fail_fast: bool = False,
        progress_callback: ProgressCallback | None = None,
        progress_interval: float = 1.0,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.timeout_per_journey = timeout_per_journey
        self.fail_fast = fail_fast
        self.progress_callback = progress_callback
        self.progress_interval = progress_interval

        self._progress = BatchProgress()
        self._lock = threading.RLock()
        self._stop_event = threading.Event()

    def execute(
        self,
        journeys: list[Journey],
        runner_factory: Callable[[], Any],
    ) -> BatchResult:
        """Execute journeys concurrently using provided runner factory."""
        self._stop_event.clear()
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
                        self._progress.results.append(result)

                    journey_results.append(result)

                    if not result.success and self.fail_fast:
                        logger.warning(f"Fail fast triggered by journey: {journey.name}")
                        self._stop_event.set()
                        break

                except TimeoutError:
                    logger.error(f"Journey {journey.name} timed out")
                    with self._lock:
                        self._progress.completed += 1
                        self._progress.pending -= 1
                        self._progress.failed += 1

                except Exception:
                    logger.exception(f"Journey {journey.name} raised exception")
                    with self._lock:
                        self._progress.completed += 1
                        self._progress.pending -= 1
                        self._progress.failed += 1

                self._update_progress()

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
        )

    def _run_journey(
        self,
        journey: Journey,
        runner_factory: Callable[[], Any],
    ) -> JourneyResult:
        """Run a single journey using a fresh runner."""
        with self._lock:
            self._progress.in_progress += 1
            self._progress.pending -= 1
            self._progress.current_journey = journey.name

        self._update_progress()

        try:
            runner = runner_factory()
            result = runner.run(journey)
            return result
        finally:
            with self._lock:
                self._progress.in_progress -= 1

    def _update_progress(self) -> None:
        """Invoke progress callback if set."""
        if self.progress_callback:
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
        """Signal batch execution to stop."""
        self._stop_event.set()

    def get_progress(self) -> BatchProgress:
        """Get current progress."""
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
    """Aggregate multiple journey results into a summary."""
    if not results:
        return {
            "total_journeys": 0,
            "passed": 0,
            "failed": 0,
            "total_steps": 0,
            "passed_steps": 0,
            "total_duration_ms": 0.0,
            "issues_count": 0,
        }

    total_steps = sum(r.total_steps for r in results)
    passed_steps = sum(r.passed_steps for r in results)
    total_duration = sum(r.duration_ms for r in results)
    total_issues = sum(len(r.issues) for r in results)
    passed = sum(1 for r in results if r.success)

    return {
        "total_journeys": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "success_rate": f"{(passed / len(results)) * 100:.1f}%",
        "total_steps": total_steps,
        "passed_steps": passed_steps,
        "failed_steps": total_steps - passed_steps,
        "step_success_rate": f"{(passed_steps / max(1, total_steps)) * 100:.1f}%",
        "total_duration_ms": round(total_duration, 2),
        "avg_duration_ms": round(total_duration / len(results), 2),
        "issues_count": total_issues,
        "journey_summaries": [
            {
                "name": r.journey_name,
                "success": r.success,
                "steps": r.total_steps,
                "duration_ms": round(r.duration_ms, 2),
                "issues": len(r.issues),
            }
            for r in results
        ],
    }


def default_progress_callback(progress: BatchProgress) -> None:
    """Default progress callback that logs progress."""
    logger.info(
        f"Batch progress: {progress.completed}/{progress.total} "
        f"({progress.progress_percent:.1f}%) - "
        f"Failed: {progress.failed} - "
        f"In progress: {progress.in_progress}"
    )
    if progress.estimated_remaining_seconds:
        logger.info(f"Estimated remaining: {progress.estimated_remaining_seconds:.1f}s")
