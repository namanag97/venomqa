"""Journey Runner - executes journeys with branching and rollback."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import TYPE_CHECKING, Any

from venomqa.core.context import ExecutionContext
from venomqa.core.models import (
    Branch,
    BranchResult,
    Checkpoint,
    Issue,
    Journey,
    JourneyResult,
    Path,
    PathResult,
    Severity,
    Step,
    StepResult,
)

if TYPE_CHECKING:
    from venomqa.client import Client
    from venomqa.state import StateManager

logger = logging.getLogger(__name__)


class JourneyRunner:
    """Executes journeys with state branching and rollback support."""

    def __init__(
        self,
        client: Client,
        state_manager: StateManager | None = None,
        parallel_paths: int = 1,
        fail_fast: bool = False,
        capture_logs: bool = True,
        log_lines: int = 50,
    ) -> None:
        self.client = client
        self.state_manager = state_manager
        self.parallel_paths = parallel_paths
        self.fail_fast = fail_fast
        self.capture_logs = capture_logs
        self.log_lines = log_lines
        self._issues: list[Issue] = []

    def run(self, journey: Journey) -> JourneyResult:
        """Execute a complete journey with all branches."""
        logger.info(f"Starting journey: {journey.name}")

        started_at = datetime.now()
        self._issues = []

        if self.state_manager:
            self.state_manager.connect()

        self.client.clear_history()
        context = ExecutionContext()

        step_results: list[StepResult] = []
        branch_results: list[BranchResult] = []

        try:
            for step in journey.steps:
                if isinstance(step, Checkpoint):
                    self._handle_checkpoint(step)

                elif isinstance(step, Branch):
                    branch_result = self._handle_branch(step, journey.name, context)
                    branch_results.append(branch_result)

                elif isinstance(step, Step):
                    result = self._run_step(step, journey.name, "main", context)
                    step_results.append(result)

                    if not result.success and self.fail_fast:
                        logger.error(f"Fail fast triggered on step: {step.name}")
                        break

        except Exception as e:
            logger.exception(f"Journey {journey.name} failed with exception")
            self._add_issue(
                journey=journey.name,
                path="main",
                step="journey",
                error=str(e),
                severity=Severity.CRITICAL,
            )

        finally:
            if self.state_manager:
                self.state_manager.disconnect()

        finished_at = datetime.now()
        duration_ms = (finished_at - started_at).total_seconds() * 1000

        all_passed = all(r.success for r in step_results) and all(
            br.all_passed for br in branch_results
        )

        return JourneyResult(
            journey_name=journey.name,
            success=all_passed,
            started_at=started_at,
            finished_at=finished_at,
            step_results=step_results,
            branch_results=branch_results,
            issues=self._issues.copy(),
            duration_ms=duration_ms,
        )

    def _handle_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Create a database checkpoint."""
        if self.state_manager:
            self.state_manager.checkpoint(checkpoint.name)
            logger.debug(f"Created checkpoint: {checkpoint.name}")

    def _handle_branch(
        self,
        branch: Branch,
        journey_name: str,
        context: ExecutionContext,
    ) -> BranchResult:
        """Execute all paths in a branch, rolling back after each."""
        logger.info(f"Exploring branch with {len(branch.paths)} paths")

        path_results: list[PathResult] = []
        context_snapshot = context.snapshot()

        if self.parallel_paths > 1 and len(branch.paths) > 1:
            path_results = self._run_paths_parallel(branch, journey_name, context_snapshot)
        else:
            path_results = self._run_paths_sequential(branch, journey_name, context_snapshot)

        all_passed = all(r.success for r in path_results)

        return BranchResult(
            checkpoint_name=branch.checkpoint_name,
            path_results=path_results,
            all_passed=all_passed,
        )

    def _run_paths_sequential(
        self,
        branch: Branch,
        journey_name: str,
        context_snapshot: dict[str, Any],
    ) -> list[PathResult]:
        """Run paths sequentially with rollback between each."""
        results: list[PathResult] = []

        for path in branch.paths:
            context = ExecutionContext()
            context.restore(context_snapshot)

            path_result = self._run_path(path, journey_name, context)
            results.append(path_result)

            if self.state_manager:
                self.state_manager.rollback(branch.checkpoint_name)
                logger.debug(f"Rolled back to checkpoint: {branch.checkpoint_name}")

        return results

    def _run_paths_parallel(
        self,
        branch: Branch,
        journey_name: str,
        context_snapshot: dict[str, Any],
    ) -> list[PathResult]:
        """Run paths in parallel using thread pool."""
        results: list[PathResult] = []

        with ThreadPoolExecutor(max_workers=self.parallel_paths) as executor:
            futures = {}

            for path in branch.paths:
                context = ExecutionContext()
                context.restore(context_snapshot)

                future = executor.submit(self._run_path, path, journey_name, context)
                futures[future] = path.name

            for future in as_completed(futures):
                path_name = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.exception(f"Path {path_name} raised exception")
                    results.append(
                        PathResult(
                            path_name=path_name,
                            success=False,
                            error=str(e),
                        )
                    )

        return results

    def _run_path(
        self,
        path: Path,
        journey_name: str,
        context: ExecutionContext,
    ) -> PathResult:
        """Execute all steps in a path."""
        logger.info(f"Running path: {path.name}")

        step_results: list[StepResult] = []

        for step in path.steps:
            if isinstance(step, Checkpoint):
                self._handle_checkpoint(step)
                continue

            if isinstance(step, Branch):
                logger.warning(
                    f"Nested branches not yet supported, skipping: {step.checkpoint_name}"
                )
                continue

            result = self._run_step(step, journey_name, path.name, context)
            step_results.append(result)

            if not result.success and self.fail_fast:
                break

        all_passed = all(r.success for r in step_results)

        return PathResult(
            path_name=path.name,
            success=all_passed,
            step_results=step_results,
        )

    def _run_step(
        self,
        step: Step,
        journey_name: str,
        path_name: str,
        context: ExecutionContext,
    ) -> StepResult:
        """Execute a single step and capture results."""
        logger.debug(f"Running step: {step.name}")

        started_at = datetime.now()
        error: str | None = None
        response: dict[str, Any] | None = None
        request: dict[str, Any] | None = None
        success = False

        try:
            result = step.action(self.client, context)

            if hasattr(result, "status_code"):
                response = {
                    "status_code": result.status_code,
                    "body": self._safe_json(result),
                    "headers": dict(result.headers),
                }

                if self.client.history:
                    last = self.client.last_request()
                    if last:
                        request = {
                            "method": last.method,
                            "url": last.url,
                            "body": last.request_body,
                        }

            context.store_step_result(step.name, result)

            expected_failure = step.expect_failure
            is_http_error = hasattr(result, "is_error") and result.is_error

            if expected_failure:
                success = is_http_error
                if not success:
                    error = "Expected failure but step succeeded"
            else:
                success = not is_http_error
                if not success and hasattr(result, "status_code"):
                    error = f"HTTP {result.status_code}"

        except Exception as e:
            error = str(e)
            success = step.expect_failure

            if self.client.history:
                last = self.client.last_request()
                if last:
                    request = {
                        "method": last.method,
                        "url": last.url,
                        "body": last.request_body,
                    }
                    if last.error:
                        error = last.error

        finished_at = datetime.now()
        duration_ms = (finished_at - started_at).total_seconds() * 1000

        if not success:
            logs = self._capture_logs() if self.capture_logs else []
            self._add_issue(
                journey=journey_name,
                path=path_name,
                step=step.name,
                error=error or "Unknown error",
                request=request,
                response=response,
                logs=logs,
            )

        return StepResult(
            step_name=step.name,
            success=success,
            started_at=started_at,
            finished_at=finished_at,
            response=response,
            error=error,
            request=request,
            duration_ms=duration_ms,
        )

    def _add_issue(
        self,
        journey: str,
        path: str,
        step: str,
        error: str,
        severity: Severity = Severity.HIGH,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        logs: list[str] | None = None,
    ) -> None:
        """Add an issue to the issues list."""
        issue = Issue(
            journey=journey,
            path=path,
            step=step,
            error=error,
            severity=severity,
            request=request,
            response=response,
            logs=logs or [],
        )
        self._issues.append(issue)
        logger.warning(f"Issue captured: {journey}/{path}/{step} - {error}")

    def _capture_logs(self) -> list[str]:
        """Capture recent logs from infrastructure."""
        return []

    def _safe_json(self, response: Any) -> Any:
        """Safely extract JSON from response."""
        try:
            if hasattr(response, "json"):
                return response.json()
        except Exception:
            pass
        if hasattr(response, "text"):
            return response.text
        return str(response)

    def get_issues(self) -> list[Issue]:
        """Get all captured issues."""
        return self._issues.copy()
