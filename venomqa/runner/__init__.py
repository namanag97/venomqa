"""Journey Runner - executes journeys with branching and rollback."""

from __future__ import annotations

import concurrent.futures
import logging
import time
import traceback
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
from venomqa.errors import (
    BranchError,
    ErrorContext,
    JourneyAbortedError,
    JourneyError,
    JourneyTimeoutError,
    VenomQAError,
    create_debug_context,
    format_error,
)
from venomqa.errors.debug import DebugLogger, StepThroughController
from venomqa.errors import (
    PathError as PathError,
)
from venomqa.errors.retry import (
    JourneyTimeoutError as EnhancedJourneyTimeoutError,
    StepTimeoutError,
)

if TYPE_CHECKING:
    from venomqa.client import Client
    from venomqa.performance import ResponseCache
    from venomqa.performance.pool import ConnectionPool
    from venomqa.state import StateManager
    from venomqa.storage import ResultsRepository

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
    ) -> None:
        self.client = client
        self.state_manager = state_manager
        self.parallel_paths = parallel_paths
        self.fail_fast = fail_fast
        self.capture_logs = capture_logs
        self.log_lines = log_lines
        self._issues: list[Issue] = []

        self.cache = cache
        self.db_pool = db_pool
        self.use_caching = use_caching and cache is not None
        self.cache_ttl = cache_ttl
        self.cacheable_methods = cacheable_methods or {"GET", "HEAD", "OPTIONS"}

        self._cache_hits = 0
        self._cache_misses = 0
        self.ports = ports or {}
        self.output = output
        self._step_counter = 0

        # Results persistence
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

        started_at = datetime.now()
        self._issues = []

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
        except VenomQAError as e:
            _journey_err = e
            del _journey_err
            logger.exception(f"Journey {journey.name} failed with VenomQA error")
            self._add_issue(
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

        result = JourneyResult(
            journey_name=journey.name,
            success=all_passed,
            started_at=started_at,
            finished_at=finished_at,
            step_results=step_results,
            branch_results=branch_results,
            issues=self._issues.copy(),
            duration_ms=duration_ms,
        )

        # Persist results if configured
        self._persist_result(result, journey)

        return result

    def _handle_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Create a database checkpoint."""
        if self.state_manager:
            self.state_manager.checkpoint(checkpoint.name)
            logger.debug(f"Created checkpoint: {checkpoint.name}")
        else:
            logger.warning(
                f"Checkpoint '{checkpoint.name}' created but no StateManager configured. "
                "Checkpoint/rollback will not work. Configure a StateManager or remove checkpoints."
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
            logger.warning(
                f"Branch at checkpoint '{branch.checkpoint_name}' is being executed but no StateManager "
                "configured. Rollback between paths will not work - each path will see state changes "
                "from previous paths. Configure a StateManager for proper branch isolation."
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
            action = (
                step.get_action_callable() if hasattr(step, "get_action_callable") else step.action
            )
            if callable(action):
                step_ports = {
                    k: v for k, v in self.ports.items() if k in (step.requires_ports or [])
                }
                step_args = getattr(step, "args", {})
                merged_args = {**step_ports, **step_args}

                # Log request details for debug mode
                if self.debug_logger and self.client.history:
                    # Log will be captured after request via history
                    pass

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
            self._add_issue(
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
            error_output = self._format_step_failure(
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

    def _format_step_failure(
        self,
        step_name: str,
        error: str,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
    ) -> str:
        """Format step failure with full request/response details.

        Always shows request and response information when a step fails,
        regardless of debug mode setting (TD-004).

        Args:
            step_name: Name of the failed step.
            error: Error message.
            request: Request data (method, URL, headers, body).
            response: Response data (status_code, headers, body).

        Returns:
            Formatted error string with request/response details.
        """
        import json

        lines: list[str] = []
        lines.append("")
        lines.append(f"Step '{step_name}' failed: {error}")
        lines.append("")

        # Format request details
        if request:
            lines.append("Request:")
            method = request.get("method", "?")
            url = request.get("url", "?")
            lines.append(f"  {method} {url}")

            # Show relevant headers (Content-Type is most important)
            headers = request.get("headers", {})
            if headers:
                content_type = headers.get("Content-Type") or headers.get("content-type")
                if content_type:
                    lines.append(f"  Content-Type: {content_type}")

            # Show request body
            body = request.get("body")
            if body:
                body_str = self._format_body_for_display(body)
                lines.append(f"  {body_str}")
            lines.append("")

        # Format response details
        if response:
            status_code = response.get("status_code", "?")
            lines.append(f"Response ({status_code}):")

            # Show response body
            body = response.get("body")
            if body:
                body_str = self._format_body_for_display(body)
                lines.append(f"  {body_str}")
            lines.append("")

        # Add suggestion based on error type
        suggestion = self._get_error_suggestion(error, response)
        if suggestion:
            lines.append(f"Suggestion: {suggestion}")
            lines.append("")

        return "\n".join(lines)

    def _format_body_for_display(self, body: Any) -> str:
        """Format request/response body for display.

        Args:
            body: Body data (string, dict, or other).

        Returns:
            Formatted body string.
        """
        import json

        if body is None:
            return "(empty)"

        if isinstance(body, str):
            # Try to parse as JSON for pretty formatting
            try:
                parsed = json.loads(body)
                return json.dumps(parsed, indent=2)
            except (json.JSONDecodeError, TypeError):
                # Truncate long strings
                if len(body) > 500:
                    return body[:500] + "... [truncated]"
                return body

        if isinstance(body, (dict, list)):
            try:
                formatted = json.dumps(body, indent=2, default=str)
                if len(formatted) > 500:
                    return formatted[:500] + "... [truncated]"
                return formatted
            except (TypeError, ValueError):
                return str(body)

        return str(body)

    def _get_error_suggestion(
        self,
        error: str,
        response: dict[str, Any] | None = None,
    ) -> str:
        """Get a helpful suggestion based on the error.

        Args:
            error: Error message.
            response: Response data if available.

        Returns:
            Suggestion string or empty string.
        """
        error_lower = error.lower()
        status_code = response.get("status_code") if response else None

        # Status code based suggestions
        if status_code:
            status_suggestions = {
                400: "Check request body format and required fields",
                401: "Check authentication token or credentials",
                403: "Check user permissions for this action",
                404: "Check endpoint path and resource ID",
                405: "Check HTTP method (GET/POST/PUT/DELETE)",
                409: "Check for duplicate entries or state conflicts",
                422: "Check request body validation rules",
                429: "Rate limit exceeded - add delays between requests",
                500: "Check backend logs for exception details",
                502: "Check if upstream services are running",
                503: "Service unavailable - check if service is healthy",
                504: "Gateway timeout - check service performance",
            }
            if status_code in status_suggestions:
                return status_suggestions[status_code]

        # Error pattern based suggestions
        if "connection refused" in error_lower:
            return "Is the service running? Check with `docker ps` or service status"
        if "timeout" in error_lower:
            return "Service may be slow - try increasing timeout"
        if "validation" in error_lower:
            return "Check input data matches expected format"
        if "not found" in error_lower:
            return "Resource may not exist - check if it was created first"

        return ""

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

    def get_cache_stats(self) -> dict[str, Any]:
        """Get caching statistics."""
        if not self.cache:
            return {"enabled": False}
        stats = self.cache.get_stats()
        return {
            "enabled": True,
            "runner_hits": self._cache_hits,
            "runner_misses": self._cache_misses,
            **stats.to_dict(),
        }

    def _try_get_cached_response(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        body: Any,
    ) -> Any | None:
        """Try to get a cached response for the request."""
        if not self.use_caching or not self.cache:
            return None

        if method.upper() not in self.cacheable_methods:
            return None

        key = self.cache.compute_key(method, url, headers, body)
        cached = self.cache.get(key)

        if cached is not None:
            self._cache_hits += 1
            logger.debug(f"Cache hit for {method} {url}")
            from venomqa.performance.cache import CachedResponse

            if isinstance(cached, dict):
                return CachedResponse(
                    status_code=cached.get("status_code", 200),
                    headers=cached.get("headers", {}),
                    body=cached.get("body"),
                    from_cache=True,
                )
            return cached

        self._cache_misses += 1
        return None

    def _cache_response(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        body: Any,
        response: Any,
    ) -> None:
        """Cache a response if caching is enabled and method is cacheable."""
        if not self.use_caching or not self.cache:
            return

        if method.upper() not in self.cacheable_methods:
            return

        if hasattr(response, "status_code") and response.status_code >= 400:
            return

        key = self.cache.compute_key(method, url, headers, body)

        cached_data = {
            "status_code": getattr(response, "status_code", 200),
            "headers": dict(getattr(response, "headers", {})),
            "body": self._safe_json(response),
        }

        self.cache.set(key, cached_data, ttl=self.cache_ttl)
        logger.debug(f"Cached response for {method} {url}")

    def _get_pooled_db_connection(self, timeout: float | None = None):
        """Get a database connection from the pool if available."""
        if self.db_pool:
            return self.db_pool.acquire(timeout)
        return None

    def _persist_result(self, result: JourneyResult, journey: Journey) -> str | None:
        """Persist journey result to storage if configured.

        Args:
            result: The JourneyResult to persist.
            journey: The Journey that was executed.

        Returns:
            The run ID if persisted, None otherwise.
        """
        if not self.persist_results:
            return None

        try:
            # Lazy import to avoid circular imports
            if self.results_repository is None:
                from venomqa.storage import ResultsRepository
                self.results_repository = ResultsRepository()
                self.results_repository.initialize()

            # Merge journey tags with configured tags
            tags = list(set(self.results_tags + getattr(journey, "tags", [])))

            # Add journey metadata
            metadata = {
                **self.results_metadata,
                "journey_description": getattr(journey, "description", ""),
                "parallel_paths": self.parallel_paths,
                "fail_fast": self.fail_fast,
            }

            run_id = self.results_repository.save_journey_result(
                result,
                tags=tags,
                metadata=metadata,
            )

            logger.info(f"Persisted journey result: {result.journey_name} (run_id: {run_id})")
            return run_id

        except Exception as e:
            logger.warning(f"Failed to persist journey result: {e}")
            return None

    def close(self) -> None:
        """Clean up resources."""
        if self.db_pool:
            self.db_pool.close()
        if self.cache:
            self.cache.clear()
        if self.results_repository:
            self.results_repository.close()
