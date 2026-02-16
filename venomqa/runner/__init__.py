"""Journey Runner - executes journeys with branching and rollback."""

from __future__ import annotations

import concurrent.futures
import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

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
from venomqa.errors import (
    BranchError,
    ErrorContext,
    JourneyAbortedError,
    JourneyError,
    JourneyTimeoutError,
    VenomQAError,
)
from venomqa.errors.debug import DebugLogger, StepThroughController
from venomqa.errors import (
    PathError as PathError,
)
from venomqa.errors.retry import (
    JourneyTimeoutError as EnhancedJourneyTimeoutError,
    StepTimeoutError,
)
from venomqa.runner.cache import CacheManager
from venomqa.runner.formatter import IssueFormatter
from venomqa.runner.persistence import ResultsPersister
from venomqa.runner.resolver import ActionResolver, RegistryActionResolver

if TYPE_CHECKING:
    from venomqa.http import Client
    from venomqa.performance import ResponseCache
    from venomqa.performance.pool import ConnectionPool
    from venomqa.ports.client import ClientPort
    from venomqa.state import StateManager
    from venomqa.storage import ResultsRepository

logger = logging.getLogger(__name__)


class MissingStateManagerError(VenomQAError):
    """Raised when checkpoint/rollback is attempted without a StateManager."""

    pass


@runtime_checkable
class ClientProtocol(Protocol):
    """Protocol defining the minimal client interface needed by JourneyRunner."""

    def clear_history(self) -> None: ...
    def last_request(self) -> Any: ...

    @property
    def history(self) -> Any: ...


class JourneyRunner:
    """Executes journeys with state branching and rollback support.

    This class orchestrates journey execution by coordinating:
    - Step execution with timeout and retry support
    - Branch exploration with checkpoint/rollback
    - Issue formatting and collection
    - Response caching
    - Results persistence

    Dependencies can be injected for testability.
    """

    def __init__(
        self,
        client: Client | ClientPort | ClientProtocol,
        state_manager: StateManager | None = None,
        parallel_paths: int = 1,
        fail_fast: bool = False,
        capture_logs: bool = True,
        log_lines: int = 50,
        cache: ResponseCache | None = None,
        db_pool: ConnectionPool[Any] | None = None,
        use_caching: bool = False,
        cache_ttl: float = 300.0,
        cacheable_methods: set[str] | None = None,
        ports: dict[str, Any] | None = None,
        output: Any | None = None,
        results_repository: ResultsRepository | None = None,
        persist_results: bool = False,
        results_tags: list[str] | None = None,
        results_metadata: dict[str, Any] | None = None,
        debug_logger: DebugLogger | None = None,
        step_controller: StepThroughController | None = None,
        # New injectable dependencies
        action_resolver: ActionResolver | None = None,
        issue_formatter: IssueFormatter | None = None,
        cache_manager: CacheManager | None = None,
        results_persister: ResultsPersister | None = None,
    ) -> None:
        self.client = client
        self.state_manager = state_manager
        self.parallel_paths = parallel_paths
        self.fail_fast = fail_fast
        self.capture_logs = capture_logs
        self.log_lines = log_lines

        # Use injected components or create defaults
        self._formatter = issue_formatter or IssueFormatter()
        self._cache_manager = cache_manager or CacheManager(
            cache=cache,
            enabled=use_caching,
            ttl=cache_ttl,
            cacheable_methods=cacheable_methods,
        )
        self._persister = results_persister or ResultsPersister(
            repository=results_repository,
            enabled=persist_results,
            tags=results_tags or [],
            metadata=results_metadata or {},
        )
        self._action_resolver = action_resolver or RegistryActionResolver()

        # Keep these for backward compatibility
        self.cache = cache
        self.db_pool = db_pool
        self.use_caching = use_caching and cache is not None
        self.cache_ttl = cache_ttl
        self.cacheable_methods = cacheable_methods or {"GET", "HEAD", "OPTIONS"}

        self.ports = ports or {}
        self.output = output
        self._step_counter = 0

        # Results persistence (for backward compat properties)
        self.results_repository = results_repository
        self.persist_results = persist_results or results_repository is not None
        self.results_tags = results_tags or []
        self.results_metadata = results_metadata or {}

        # Debug and step-through support
        self.debug_logger = debug_logger
        self.step_controller = step_controller
        self._current_journey_name = ""
        self._current_path_name = "main"

    def run(self, journey: Journey) -> JourneyResult:
        """Execute a complete journey with all branches."""
        logger.info(f"Starting journey: {journey.name}")

        # Validate journey structure before execution
        if hasattr(journey, 'validate'):
            issues = journey.validate()
            if issues:
                logger.warning(
                    f"Journey '{journey.name}' has validation issues: {issues}"
                )
                # Log each issue for visibility
                for issue in issues:
                    logger.warning(f"  - {issue}")

        started_at = datetime.now()
        self._formatter.clear()

        if self.state_manager:
            self.state_manager.connect()

        self.client.clear_history()
        context = ExecutionContext()
        context.state_manager = self.state_manager

        step_results: list[StepResult] = []
        branch_results: list[BranchResult] = []
        _journey_error: VenomQAError | None = None
        del _journey_error

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
                        _journey_err = JourneyAbortedError(
                            message=f"Journey aborted due to failure on step: {step.name}",
                            context=ErrorContext(
                                journey_name=journey.name,
                                step_name=step.name,
                                extra={"fail_fast": True},
                            ),
                        )
                        del _journey_err
                        break

        except JourneyAbortedError:
            raise
        except JourneyTimeoutError:
            raise
        except MissingStateManagerError:
            raise
        except VenomQAError as e:
            _journey_err = e
            del _journey_err
            logger.exception(f"Journey {journey.name} failed with VenomQA error")
            self._formatter.add_issue(
                journey=journey.name,
                path="main",
                step="journey",
                error=f"[{e.error_code.value}] {e.message}",
                severity=Severity.CRITICAL,
            )
        except Exception as e:
            _journey_error = JourneyError(
                message=f"Journey {journey.name} failed with exception: {e}",
                context=ErrorContext(
                    journey_name=journey.name,
                    extra={"traceback": traceback.format_exc()},
                ),
                cause=e,
            )
            del _journey_error
            logger.exception(f"Journey {journey.name} failed with exception")
            self._formatter.add_issue(
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

        result = JourneyResult(
            journey_name=journey.name,
            success=all_passed,
            started_at=started_at,
            finished_at=finished_at,
            step_results=step_results,
            branch_results=branch_results,
            issues=self._formatter.get_issues(),
            duration_ms=duration_ms,
        )

        # Persist results if configured
        self._persister.persist(
            result,
            journey,
            extra_metadata={
                "parallel_paths": self.parallel_paths,
                "fail_fast": self.fail_fast,
            },
        )

        return result

    def _handle_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Create a database checkpoint.

        Raises:
            MissingStateManagerError: If no StateManager is configured.
        """
        if self.state_manager:
            self.state_manager.checkpoint(checkpoint.name)
            logger.debug(f"Created checkpoint: {checkpoint.name}")
        else:
            raise MissingStateManagerError(
                message=f"Checkpoint '{checkpoint.name}' requires a StateManager but none is configured",
                context=ErrorContext(
                    extra={
                        "checkpoint_name": checkpoint.name,
                        "suggestion": "Pass a StateManager to JourneyRunner or remove checkpoints from the journey",
                    },
                ),
            )
        if self.output:
            self.output.checkpoint(checkpoint.name)

    def _handle_branch(
        self,
        branch: Branch,
        journey_name: str,
        context: ExecutionContext,
    ) -> BranchResult:
        """Execute all paths in a branch, rolling back after each."""
        logger.info(f"Exploring branch with {len(branch.paths)} paths")

        if not self.state_manager:
            raise MissingStateManagerError(
                message=f"Branch at checkpoint '{branch.checkpoint_name}' requires a StateManager but none is configured",
                context=ErrorContext(
                    journey_name=journey_name,
                    extra={
                        "checkpoint_name": branch.checkpoint_name,
                        "suggestion": "Pass a StateManager to JourneyRunner or remove branches from the journey",
                    },
                ),
            )

        if self.output:
            self.output.branch_start(branch.checkpoint_name, len(branch.paths))

        path_results: list[PathResult] = []
        context_snapshot = context.snapshot()

        try:
            if self.parallel_paths > 1 and len(branch.paths) > 1:
                path_results = self._run_paths_parallel(branch, journey_name, context_snapshot)
            else:
                path_results = self._run_paths_sequential(branch, journey_name, context_snapshot)
        except VenomQAError as e:
            logger.error(f"Branch failed at checkpoint {branch.checkpoint_name}: {e}")
            raise BranchError(
                message=f"Branch execution failed at checkpoint {branch.checkpoint_name}",
                context=ErrorContext(
                    journey_name=journey_name,
                    extra={"checkpoint_name": branch.checkpoint_name},
                ),
                cause=e,
            ) from e

        return BranchResult(
            checkpoint_name=branch.checkpoint_name,
            path_results=path_results,
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
            context.state_manager = self.state_manager

            path_result = self._run_path(path, journey_name, context)
            results.append(path_result)

            if self.state_manager:
                self.state_manager.rollback(branch.checkpoint_name)
                logger.debug(f"Rolled back to checkpoint: {branch.checkpoint_name}")
                if self.output:
                    self.output.rollback(branch.checkpoint_name)

        return results

    def _run_paths_parallel(
        self,
        branch: Branch,
        journey_name: str,
        context_snapshot: dict[str, Any],
    ) -> list[PathResult]:
        """Run paths in parallel using thread pool."""
        if self.state_manager:
            logger.warning(
                "Parallel path execution with state_manager may not properly isolate database state. "
                "Consider using parallel_paths=1 for reliable checkpoint/rollback behavior."
            )

        results: list[PathResult] = []

        with ThreadPoolExecutor(max_workers=self.parallel_paths) as executor:
            futures = {}

            for path in branch.paths:
                context = ExecutionContext()
                context.restore(context_snapshot)
                context.state_manager = self.state_manager

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

        if self.output:
            self.output.path_start(path.name)

        step_results: list[StepResult] = []
        path_error: str | None = None

        try:
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

        except VenomQAError as e:
            path_error = f"[{e.error_code.value}] {e.message}"
            logger.error(f"Path {path.name} failed: {path_error}")
        except Exception as e:
            path_error = str(e)
            logger.exception(f"Path {path.name} failed with exception")

        all_passed = all(r.success for r in step_results)

        if self.output:
            self.output.path_result(path.name, all_passed and path_error is None, len(step_results))

        return PathResult(
            path_name=path.name,
            success=all_passed and path_error is None,
            step_results=step_results,
            error=path_error,
        )

    def _run_step(
        self,
        step: Step,
        journey_name: str,
        path_name: str,
        context: ExecutionContext,
        journey_timeout: float | None = None,
    ) -> StepResult:
        """Execute a single step and capture results.

        Args:
            step: Step to execute.
            journey_name: Name of the journey.
            path_name: Name of the path.
            context: Execution context.
            journey_timeout: Optional journey-level timeout (for default step timeout).

        Returns:
            StepResult with execution outcome.
        """
        logger.debug(f"Running step: {step.name}")

        # Log step start for debug mode
        if self.debug_logger:
            self.debug_logger.log_step_start(step.name, journey_name, path_name)

        self._step_counter += 1
        if self.output:
            self.output.step_start(step.name, self._step_counter, step.description)

        started_at = datetime.now()
        start_time = time.time()
        error: str | None = None
        exception_raised: Exception | None = None
        response: dict[str, Any] | None = None
        request: dict[str, Any] | None = None
        success = False

        # Determine effective timeout: step timeout > journey timeout > default
        effective_timeout = step.timeout or journey_timeout

        try:
            # Use action resolver for string actions
            action = step.get_action_callable(self._action_resolver)

            if callable(action):
                step_ports = {
                    k: v for k, v in self.ports.items() if k in (step.requires_ports or [])
                }
                step_args = getattr(step, "args", {})
                merged_args = {**step_ports, **step_args}

                # Execute with timeout if configured
                if effective_timeout is not None:
                    result = self._execute_with_step_timeout(
                        action=action,
                        client=self.client,
                        context=context,
                        merged_args=merged_args,
                        timeout=effective_timeout,
                        step_name=step.name,
                        description=step.description,
                    )
                else:
                    result = action(self.client, context, **merged_args)

                # Log HTTP request/response if debug mode and we have history
                if self.debug_logger and self.client.history:
                    last = self.client.last_request()
                    if last:
                        req_id = self.debug_logger.log_request(
                            last.method,
                            last.url,
                            dict(last.headers) if hasattr(last, "headers") else None,
                            last.request_body,
                        )
                        self.debug_logger.log_response(
                            req_id,
                            last.response_status,
                            last.duration_ms,
                            None,
                            last.response_body,
                        )
            else:
                raise ValueError(f"Step action is not callable: {step.action}")

            if hasattr(result, "status_code"):
                headers = dict(getattr(result, "headers", {}))
                response = {
                    "status_code": result.status_code,
                    "body": self._safe_json(result),
                    "headers": headers,
                }

                if self.client.history:
                    last = self.client.last_request()
                    if last:
                        request = {
                            "method": last.method,
                            "url": last.url,
                            "body": last.request_body,
                            "headers": dict(last.headers) if hasattr(last, "headers") else {},
                        }

            context.store_step_result(step.name, result)

            expected_failure = step.expect_failure
            is_http_error = hasattr(result, "is_error") and result.is_error

            if expected_failure:
                # When expecting failure, success = actual failure occurred
                success = is_http_error
                if not success:
                    error = "Expected failure but step succeeded"
                    success = False  # Mark as failed when we expected failure but got success
            else:
                success = not is_http_error
                if not success and hasattr(result, "status_code"):
                    error = f"HTTP {result.status_code}"

        except VenomQAError as e:
            error = f"[{e.error_code.value}] {e.message}"
            exception_raised = e
            success = step.expect_failure

            if self.client.history:
                last = self.client.last_request()
                if last:
                    request = {
                        "method": last.method,
                        "url": last.url,
                        "body": last.request_body,
                        "headers": dict(last.headers) if hasattr(last, "headers") else {},
                    }
                    if last.error:
                        error = last.error

            logger.debug(f"Step {step.name} raised VenomQAError: {error}")

        except Exception as e:
            error = str(e)
            exception_raised = e
            success = step.expect_failure

            if self.client.history:
                last = self.client.last_request()
                if last:
                    request = {
                        "method": last.method,
                        "url": last.url,
                        "body": last.request_body,
                        "headers": dict(last.headers) if hasattr(last, "headers") else {},
                    }
                    if last.error:
                        error = last.error

        finished_at = datetime.now()
        duration_ms = (finished_at - started_at).total_seconds() * 1000

        # Log step end for debug mode
        if self.debug_logger:
            self.debug_logger.log_step_end(step.name, success, duration_ms, error)
            self.debug_logger.log_timing(f"step:{step.name}", duration_ms)

        if not success:
            logs = self._capture_logs() if self.capture_logs else []
            self._formatter.add_issue(
                journey=journey_name,
                path=path_name,
                step=step.name,
                error=error or "Unknown error",
                request=request,
                response=response,
                logs=logs,
            )
            if self.output:
                self.output.step_fail(step.name, error or "Unknown error", duration_ms)

            # Always print request/response details on failure (TD-004)
            error_output = self._formatter.format_step_failure(
                step_name=step.name,
                error=error or "Unknown error",
                request=request,
                response=response,
            )
            print(error_output)
        else:
            if self.output:
                self.output.step_pass(step.name, duration_ms)

        # Step-through mode: pause after step and allow inspection
        if self.step_controller and self.step_controller.enabled:
            # Build context data for display
            ctx_data = {}
            if hasattr(context, "_data"):
                ctx_data = dict(context._data)
            if hasattr(context, "_step_results"):
                ctx_data["_step_results"] = list(context._step_results.keys())

            # Get the result for inspection
            last_result = context.get_step_result(step.name)

            command = self.step_controller.pause(step.name, ctx_data, last_result)

            if command == "abort":
                raise JourneyAbortedError(
                    message="Journey aborted by user in step-through mode",
                    context=ErrorContext(
                        journey_name=journey_name,
                        path_name=path_name,
                        step_name=step.name,
                    ),
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

    def _execute_with_step_timeout(
        self,
        action: Any,
        client: Any,
        context: ExecutionContext,
        merged_args: dict[str, Any],
        timeout: float,
        step_name: str,
        description: str = "",
    ) -> Any:
        """Execute a step action with timeout.

        Args:
            action: Callable to execute.
            client: HTTP client.
            context: Execution context.
            merged_args: Arguments to pass to action.
            timeout: Timeout in seconds.
            step_name: Name of the step for error messages.
            description: Description for error messages.

        Returns:
            Result of the action.

        Raises:
            StepTimeoutError: If step times out.
        """
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(action, client, context, **merged_args)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                elapsed = time.time() - start_time
                raise StepTimeoutError(
                    step_name=step_name,
                    timeout_seconds=timeout,
                    elapsed_seconds=elapsed,
                    operation_description=description or f"executing step '{step_name}'",
                )

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
        return self._formatter.get_issues()

    def get_cache_stats(self) -> dict[str, Any]:
        """Get caching statistics."""
        return self._cache_manager.get_stats()

    def _get_pooled_db_connection(self, timeout: float | None = None):
        """Get a database connection from the pool if available."""
        if self.db_pool:
            return self.db_pool.acquire(timeout)
        return None

    def close(self) -> None:
        """Clean up resources."""
        if self.db_pool:
            self.db_pool.close()
        self._cache_manager.clear()
        self._persister.close()

    # Backward compatibility properties
    @property
    def _issues(self) -> list[Issue]:
        """Backward compatibility: access issues from formatter."""
        return self._formatter.get_issues()

    @property
    def _cache_hits(self) -> int:
        """Backward compatibility: access cache hits from cache manager."""
        return self._cache_manager._hits

    @property
    def _cache_misses(self) -> int:
        """Backward compatibility: access cache misses from cache manager."""
        return self._cache_manager._misses
