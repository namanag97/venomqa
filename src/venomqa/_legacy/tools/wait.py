"""Wait and polling actions for QA testing.

This module provides reusable wait/polling action functions for:
- Waiting for HTTP responses
- Waiting for specific conditions
- Polling with custom predicates
- Async-first with sync wrappers

Example:
    >>> from venomqa.tools.wait import wait_for, poll_until
    >>>
    >>> # Simple condition wait
    >>> await wait_for(
    ...     lambda: client.get("/orders/123").json()["status"] == "shipped",
    ...     timeout=60,
    ...     interval=5
    ... )
    >>>
    >>> # Standalone poll until condition
    >>> result = await poll_until(
    ...     lambda: client.get("/api/job/123").json(),
    ...     condition=lambda r: r.get("status") == "completed",
    ...     timeout=120,
    ...     interval=2
    ... )
    >>>
    >>> # Legacy API still supported
    >>> response = wait_for_status(client, context, "/health", 200, timeout=30)
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

import httpx

from venomqa.errors import VenomQAError
from venomqa.errors.retry import WaitTimeoutError
from venomqa.tools.http import get

if TYPE_CHECKING:
    from venomqa.http import Client
    from venomqa.state.context import Context

T = TypeVar("T")


class WaitError(VenomQAError):
    """Raised when a wait operation fails (not timeout)."""

    pass


# Re-export for backward compatibility
__all__ = [
    "WaitTimeoutError",
    "WaitError",
    "wait_for",
    "poll_until",
    "wait_for_response",
    "wait_for_status",
    "wait_for_condition",
    "wait_until",
    "wait_for_health_check",
    "wait_for_json_path",
    "wait_for_email_received",
    "poll",
    "retry_on_failure",
    "wait_for_value_change",
    "wait_for_stable_value",
    "wait_all",
    "wait_any",
    "wait_for_retry_success",
]


# =============================================================================
# NEW SIMPLIFIED API
# =============================================================================


async def wait_for(
    condition: Callable[[], bool] | Callable[[], Awaitable[bool]],
    timeout: float = 30.0,
    interval: float = 1.0,
    description: str | None = None,
    raise_on_timeout: bool = True,
) -> bool:
    """Wait for a condition to become true.

    This is the primary wait function with a simple, flexible API.
    Works with both sync and async condition functions.

    Args:
        condition: Function returning bool (sync or async).
        timeout: Maximum wait time in seconds.
        interval: Time between checks in seconds.
        description: Description for error messages.
        raise_on_timeout: If True, raise WaitTimeoutError on timeout.

    Returns:
        True if condition was met, False if timed out (when raise_on_timeout=False).

    Raises:
        WaitTimeoutError: If timeout reached and raise_on_timeout=True.

    Example:
        >>> # Wait for job to complete
        >>> await wait_for(
        ...     lambda: client.get("/jobs/123").json()["status"] == "done",
        ...     timeout=60,
        ...     interval=5,
        ...     description="job 123 to complete"
        ... )
    """
    start_time = time.time()
    attempts = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            if raise_on_timeout:
                raise WaitTimeoutError(
                    condition_description=description or "condition to be true",
                    timeout_seconds=timeout,
                    elapsed_seconds=elapsed,
                    poll_attempts=attempts,
                    poll_interval=interval,
                )
            return False

        attempts += 1
        try:
            result = condition()
            if asyncio.iscoroutine(result):
                result = await result

            if result:
                return True
        except Exception:
            pass
            # Continue polling on exception

        await asyncio.sleep(interval)

    # Unreachable but makes type checker happy
    return False


def wait_for_sync(
    condition: Callable[[], bool],
    timeout: float = 30.0,
    interval: float = 1.0,
    description: str | None = None,
    raise_on_timeout: bool = True,
) -> bool:
    """Synchronous version of wait_for.

    Args:
        condition: Sync function returning bool.
        timeout: Maximum wait time in seconds.
        interval: Time between checks in seconds.
        description: Description for error messages.
        raise_on_timeout: If True, raise WaitTimeoutError on timeout.

    Returns:
        True if condition was met, False if timed out.

    Example:
        >>> wait_for_sync(
        ...     lambda: client.get("/health").status_code == 200,
        ...     timeout=30
        ... )
    """
    start_time = time.time()
    attempts = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            if raise_on_timeout:
                raise WaitTimeoutError(
                    condition_description=description or "condition to be true",
                    timeout_seconds=timeout,
                    elapsed_seconds=elapsed,
                    poll_attempts=attempts,
                    poll_interval=interval,
                )
            return False

        attempts += 1
        try:
            if condition():
                return True
        except Exception:
            pass  # Continue polling on exception

        time.sleep(interval)


async def poll_until(
    fetcher: Callable[[], T] | Callable[[], Awaitable[T]],
    condition: Callable[[T], bool],
    timeout: float = 30.0,
    interval: float = 1.0,
    description: str | None = None,
) -> T:
    """Poll a resource until a condition is met.

    Repeatedly fetches a value and checks it against a condition.
    Returns the value when condition is satisfied.

    Args:
        fetcher: Function to fetch the current value (sync or async).
        condition: Predicate function to check the fetched value.
        timeout: Maximum wait time in seconds.
        interval: Time between polls in seconds.
        description: Description for error messages.

    Returns:
        The fetched value that satisfied the condition.

    Raises:
        WaitTimeoutError: If timeout reached before condition is met.

    Example:
        >>> # Wait for order status
        >>> order = await poll_until(
        ...     fetcher=lambda: client.get("/orders/123").json(),
        ...     condition=lambda o: o["status"] in ("shipped", "delivered"),
        ...     timeout=120,
        ...     interval=5,
        ...     description="order 123 to be shipped"
        ... )
        >>> print(f"Order status: {order['status']}")
    """
    start_time = time.time()
    attempts = 0
    last_value: T | None = None

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            raise WaitTimeoutError(
                condition_description=description or "condition to be met",
                timeout_seconds=timeout,
                elapsed_seconds=elapsed,
                poll_attempts=attempts,
                poll_interval=interval,
                last_value=last_value,
            )

        attempts += 1
        try:
            value = fetcher()
            if asyncio.iscoroutine(value):
                value = await value

            last_value = value

            if condition(value):
                return value
        except Exception:
            pass
            # Continue polling on exception

        await asyncio.sleep(interval)


def poll_until_sync(
    fetcher: Callable[[], T],
    condition: Callable[[T], bool],
    timeout: float = 30.0,
    interval: float = 1.0,
    description: str | None = None,
) -> T:
    """Synchronous version of poll_until.

    Args:
        fetcher: Sync function to fetch the current value.
        condition: Predicate function to check the fetched value.
        timeout: Maximum wait time in seconds.
        interval: Time between polls in seconds.
        description: Description for error messages.

    Returns:
        The fetched value that satisfied the condition.

    Example:
        >>> order = poll_until_sync(
        ...     fetcher=lambda: client.get("/orders/123").json(),
        ...     condition=lambda o: o["status"] == "shipped",
        ...     timeout=60
        ... )
    """
    start_time = time.time()
    attempts = 0
    last_value: T | None = None

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            raise WaitTimeoutError(
                condition_description=description or "condition to be met",
                timeout_seconds=timeout,
                elapsed_seconds=elapsed,
                poll_attempts=attempts,
                poll_interval=interval,
                last_value=last_value,
            )

        attempts += 1
        try:
            value = fetcher()
            last_value = value

            if condition(value):
                return value
        except Exception:
            pass  # Continue polling on exception

        time.sleep(interval)


# =============================================================================
# LEGACY API (for backward compatibility)
# =============================================================================


def wait_for_response(
    client: Client,
    context: Context,
    path: str,
    timeout: float = 30.0,
    interval: float = 1.0,
    expected_status_range: tuple[int, int] = (200, 299),
    **kwargs: Any,
) -> httpx.Response:
    """Wait for an HTTP endpoint to return a successful response.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        timeout: Maximum time to wait in seconds.
        interval: Time between polling attempts in seconds.
        expected_status_range: Tuple of (min, max) acceptable status codes.
        **kwargs: Additional arguments passed to GET request.

    Returns:
        httpx.Response: The successful HTTP response.

    Raises:
        WaitTimeoutError: If timeout is reached without successful response.

    Example:
        >>> response = wait_for_response(
        ...     client, context,
        ...     "/api/health",
        ...     timeout=60,
        ...     interval=2
        ... )
        >>> print(response.json())
    """
    start_time = time.time()
    last_error: Exception | None = None
    last_status: int | None = None
    attempts = 0

    while time.time() - start_time < timeout:
        attempts += 1
        try:
            response = get(client, context, path, **kwargs)
            last_status = response.status_code
            min_status, max_status = expected_status_range
            if min_status <= response.status_code <= max_status:
                return response
        except Exception as e:
            last_error = e

        time.sleep(interval)

    elapsed = time.time() - start_time
    raise WaitTimeoutError(
        condition_description=f"response from {path} with status {expected_status_range[0]}-{expected_status_range[1]}",
        timeout_seconds=timeout,
        elapsed_seconds=elapsed,
        poll_attempts=attempts,
        poll_interval=interval,
        last_value=f"status={last_status}" if last_status else f"error={last_error}",
        expected_value=f"status in range {expected_status_range}",
    )


def wait_for_status(
    client: Client,
    context: Context,
    path: str,
    status: int | list[int],
    timeout: float = 30.0,
    interval: float = 1.0,
    **kwargs: Any,
) -> httpx.Response:
    """Wait for an HTTP endpoint to return a specific status code.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        status: Expected status code or list of acceptable codes.
        timeout: Maximum time to wait in seconds.
        interval: Time between polling attempts in seconds.
        **kwargs: Additional arguments passed to GET request.

    Returns:
        httpx.Response: The HTTP response with expected status.

    Raises:
        WaitTimeoutError: If timeout is reached without expected status.

    Example:
        >>> # Wait for specific status
        >>> response = wait_for_status(client, context, "/health", 200)
        >>>
        >>> # Wait for multiple acceptable statuses
        >>> response = wait_for_status(
        ...     client, context, "/api/resource/123",
        ...     status=[200, 201, 202],
        ...     timeout=60
        ... )
    """
    if isinstance(status, int):
        expected_statuses = {status}
    else:
        expected_statuses = set(status)

    start_time = time.time()
    last_status: int | None = None
    attempts = 0

    while time.time() - start_time < timeout:
        attempts += 1
        try:
            response = get(client, context, path, **kwargs)
            last_status = response.status_code
            if response.status_code in expected_statuses:
                return response
        except Exception:
            pass

        time.sleep(interval)

    elapsed = time.time() - start_time
    status_str = ", ".join(map(str, sorted(expected_statuses)))
    raise WaitTimeoutError(
        condition_description=f"status {status_str} from {path}",
        timeout_seconds=timeout,
        elapsed_seconds=elapsed,
        poll_attempts=attempts,
        poll_interval=interval,
        last_value=last_status,
        expected_value=status_str,
    )


def wait_for_condition(
    client: Client,
    context: Context,
    condition_fn: Callable[[httpx.Response], bool],
    path: str = "",
    timeout: float = 30.0,
    interval: float = 1.0,
    description: str | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """Wait for a custom condition to be met on an HTTP response.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        condition_fn: Function that takes response and returns True when condition is met.
        path: API endpoint path or full URL (optional if condition doesn't need HTTP).
        timeout: Maximum time to wait in seconds.
        interval: Time between polling attempts in seconds.
        description: Optional description for error messages.
        **kwargs: Additional arguments passed to GET request.

    Returns:
        httpx.Response: The HTTP response that met the condition.

    Raises:
        WaitTimeoutError: If timeout is reached without condition being met.

    Example:
        >>> # Wait for job to complete
        >>> response = wait_for_condition(
        ...     client, context,
        ...     condition_fn=lambda r: r.json().get("status") == "completed",
        ...     path="/api/jobs/123",
        ...     description="job 123 to complete"
        ... )
        >>>
        >>> # Wait for specific data
        >>> response = wait_for_condition(
        ...     client, context,
        ...     condition_fn=lambda r: len(r.json().get("items", [])) >= 5,
        ...     path="/api/items"
        ... )
    """
    start_time = time.time()
    last_result: bool | None = None
    last_error: Exception | None = None
    attempts = 0

    while time.time() - start_time < timeout:
        attempts += 1
        try:
            if path:
                response = get(client, context, path, **kwargs)
            else:
                mock_response = type("MockResponse", (), {"json": lambda: {}})()
                response = mock_response

            last_result = condition_fn(response)
            if last_result:
                return response
        except Exception as e:
            last_error = e

        time.sleep(interval)

    elapsed = time.time() - start_time
    desc = description or f"condition on {path}" if path else "custom condition"
    raise WaitTimeoutError(
        condition_description=desc,
        timeout_seconds=timeout,
        elapsed_seconds=elapsed,
        poll_attempts=attempts,
        poll_interval=interval,
        last_value=f"condition={last_result}" if last_error is None else f"error={last_error}",
        expected_value="condition to return True",
    )


def wait_until(
    client: Client,
    context: Context,
    condition_fn: Callable[[], bool],
    timeout: float = 30.0,
    interval: float = 0.5,
    error_message: str | None = None,
) -> None:
    """Wait until a condition function returns True.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        condition_fn: Function that returns True when condition is met.
        timeout: Maximum time to wait in seconds.
        interval: Time between polling attempts in seconds.
        error_message: Custom error message for timeout.

    Raises:
        WaitTimeoutError: If timeout is reached without condition being met.

    Example:
        >>> # Wait for database state
        >>> wait_until(
        ...     client, context,
        ...     condition_fn=lambda: db_query(client, context, "SELECT 1 FROM users WHERE id = 1"),
        ...     timeout=10
        ... )
        >>>
        >>> # Wait for context state
        >>> wait_until(
        ...     client, context,
        ...     condition_fn=lambda: getattr(context, "processing_complete", False),
        ...     error_message="Processing did not complete in time"
        ... )
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            if condition_fn():
                return
        except Exception:
            pass

        time.sleep(interval)

    elapsed = time.time() - start_time
    msg = error_message or f"Timeout after {elapsed:.1f}s waiting for condition"
    raise WaitTimeoutError(msg)


def wait_for_health_check(
    client: Client,
    context: Context,
    path: str = "/health",
    timeout: float = 60.0,
    interval: float = 2.0,
    healthy_status: int = 200,
) -> httpx.Response:
    """Wait for a health check endpoint to return healthy status.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: Health check endpoint path.
        timeout: Maximum time to wait in seconds.
        interval: Time between polling attempts in seconds.
        healthy_status: Expected healthy status code.

    Returns:
        httpx.Response: The healthy response.

    Raises:
        WaitTimeoutError: If timeout is reached without healthy response.

    Example:
        >>> response = wait_for_health_check(
        ...     client, context,
        ...     path="/api/health",
        ...     timeout=120
        ... )
        >>> print(f"Service is healthy: {response.json()}")
    """
    return wait_for_status(
        client=client,
        context=context,
        path=path,
        status=healthy_status,
        timeout=timeout,
        interval=interval,
    )


def wait_for_json_path(
    client: Client,
    context: Context,
    path: str,
    json_path: str,
    expected_value: Any = None,
    timeout: float = 30.0,
    interval: float = 1.0,
) -> httpx.Response:
    """Wait for a JSON response to contain a specific value at a path.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        json_path: Dot-separated path to check in JSON response (e.g., "data.status").
        expected_value: Expected value at the path. If None, just checks path exists.
        timeout: Maximum time to wait in seconds.
        interval: Time between polling attempts in seconds.

    Returns:
        httpx.Response: The HTTP response with expected value.

    Raises:
        WaitTimeoutError: If timeout is reached without expected value.

    Example:
        >>> # Wait for status field to be "completed"
        >>> response = wait_for_json_path(
        ...     client, context,
        ...     path="/api/jobs/123",
        ...     json_path="status",
        ...     expected_value="completed"
        ... )
        >>>
        >>> # Wait for nested value
        >>> response = wait_for_json_path(
        ...     client, context,
        ...     path="/api/orders/456",
        ...     json_path="payment.status",
        ...     expected_value="confirmed"
        ... )
    """

    def check_json_path(response: httpx.Response) -> bool:
        try:
            data = response.json()
            parts = json_path.split(".")
            current = data

            for part in parts:
                if isinstance(current, dict):
                    if part not in current:
                        return False
                    current = current[part]
                elif isinstance(current, list):
                    try:
                        idx = int(part)
                        current = current[idx]
                    except (ValueError, IndexError):
                        return False
                else:
                    return False

            if expected_value is None:
                return True
            return current == expected_value
        except Exception:
            return False

    return wait_for_condition(
        client=client,
        context=context,
        condition_fn=check_json_path,
        path=path,
        timeout=timeout,
        interval=interval,
    )


def wait_for_email_received(
    client: Client,
    context: Context,
    to_address: str,
    timeout: float = 60.0,
    interval: float = 2.0,
    subject_contains: str | None = None,
) -> dict[str, Any]:
    """Wait for an email to be received.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        to_address: Email address to wait for.
        timeout: Maximum time to wait in seconds.
        interval: Time between polling attempts in seconds.
        subject_contains: Optional string that subject must contain.

    Returns:
        dict: The received email data.

    Raises:
        WaitTimeoutError: If timeout is reached without email.

    Example:
        >>> from venomqa.tools import wait_for_email_received
        >>> email = wait_for_email_received(
        ...     client, context,
        ...     to_address="user@example.com",
        ...     subject_contains="Verify"
        ... )
        >>> print(email["subject"])
    """
    from venomqa.tools.email import get_latest_email

    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            email = get_latest_email(client, context, to_address, subject_contains=subject_contains)
            if email:
                return email
        except Exception:
            pass

        time.sleep(interval)

    elapsed = time.time() - start_time
    raise WaitTimeoutError(f"Timeout after {elapsed:.1f}s waiting for email to {to_address}")


def poll(
    client: Client,
    context: Context,
    path: str,
    times: int = 10,
    interval: float = 1.0,
    **kwargs: Any,
) -> list[httpx.Response]:
    """Poll an endpoint multiple times and collect responses.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        times: Number of times to poll.
        interval: Time between polls in seconds.
        **kwargs: Additional arguments passed to GET request.

    Returns:
        list: List of HTTP responses.

    Example:
        >>> responses = poll(
        ...     client, context,
        ...     path="/api/metrics",
        ...     times=5,
        ...     interval=2
        ... )
        >>> for r in responses:
        ...     print(r.json())
    """
    responses = []
    for _ in range(times):
        response = get(client, context, path, **kwargs)
        responses.append(response)
        if len(responses) < times:
            time.sleep(interval)
    return responses


def retry_on_failure(
    client: Client,
    context: Context,
    action_fn: Callable[[], Any],
    max_retries: int = 3,
    retry_delay: float = 1.0,
    retry_exceptions: tuple[type[Exception], ...] | None = None,
) -> Any:
    """Retry an action on failure.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        action_fn: Function to execute and retry on failure.
        max_retries: Maximum number of retry attempts.
        retry_delay: Delay between retries in seconds.
        retry_exceptions: Tuple of exception types to retry on. If None, retries on all.

    Returns:
        Any: Result of the action function.

    Raises:
        Exception: The last exception after all retries exhausted.

    Example:
        >>> result = retry_on_failure(
        ...     client, context,
        ...     action_fn=lambda: post(client, context, "/api/flaky-endpoint", json={}),
        ...     max_retries=5,
        ...     retry_delay=2.0
        ... )
    """
    last_exception: Exception | None = None
    retry_exceptions = retry_exceptions or (Exception,)

    for attempt in range(max_retries + 1):
        try:
            return action_fn()
        except retry_exceptions as e:
            last_exception = e
            if attempt < max_retries:
                time.sleep(retry_delay)

    raise last_exception or WaitError("Retry failed with unknown error")


def wait_for_value_change(
    client: Client,
    context: Context,
    path: str,
    initial_value: Any,
    get_value_fn: Callable[[httpx.Response], Any] | None = None,
    timeout: float = 30.0,
    interval: float = 1.0,
    **kwargs: Any,
) -> httpx.Response:
    """Wait for a value to change from its initial state.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        initial_value: The initial value to compare against.
        get_value_fn: Function to extract value from response. Default: response.json().
        timeout: Maximum time to wait in seconds.
        interval: Time between polling attempts in seconds.
        **kwargs: Additional arguments passed to GET request.

    Returns:
        httpx.Response: The HTTP response with changed value.

    Raises:
        WaitTimeoutError: If timeout is reached without value changing.

    Example:
        >>> response = wait_for_value_change(
        ...     client, context,
        ...     path="/api/job/123",
        ...     initial_value="pending",
        ...     get_value_fn=lambda r: r.json().get("status")
        ... )
    """
    if get_value_fn is None:

        def _default_get_value(r: httpx.Response) -> Any:
            return r.json()

        get_value_fn = _default_get_value

    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = get(client, context, path, **kwargs)
            current_value = get_value_fn(response)

            if current_value != initial_value:
                return response
        except Exception:
            pass

        time.sleep(interval)

    elapsed = time.time() - start_time
    raise WaitTimeoutError(
        f"Timeout after {elapsed:.1f}s waiting for value to change from {initial_value!r}"
    )


def wait_for_stable_value(
    client: Client,
    context: Context,
    path: str,
    stability_count: int = 3,
    get_value_fn: Callable[[httpx.Response], Any] | None = None,
    timeout: float = 30.0,
    interval: float = 1.0,
    **kwargs: Any,
) -> httpx.Response:
    """Wait for a value to stabilize (remain the same for N consecutive checks).

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        path: API endpoint path or full URL.
        stability_count: Number of consecutive checks with same value.
        get_value_fn: Function to extract value from response. Default: response.json().
        timeout: Maximum time to wait in seconds.
        interval: Time between polling attempts in seconds.
        **kwargs: Additional arguments passed to GET request.

    Returns:
        httpx.Response: The HTTP response with stable value.

    Raises:
        WaitTimeoutError: If timeout is reached without stabilization.

    Example:
        >>> response = wait_for_stable_value(
        ...     client, context,
        ...     path="/api/metrics",
        ...     stability_count=3,
        ...     get_value_fn=lambda r: r.json().get("active_connections")
        ... )
    """
    if get_value_fn is None:

        def _default_get_value_stable(r: httpx.Response) -> Any:
            return r.json()

        get_value_fn = _default_get_value_stable

    start_time = time.time()
    consecutive_matches = 0
    last_value: Any = object()

    while time.time() - start_time < timeout:
        try:
            response = get(client, context, path, **kwargs)
            current_value = get_value_fn(response)

            if current_value == last_value:
                consecutive_matches += 1
                if consecutive_matches >= stability_count:
                    return response
            else:
                consecutive_matches = 1
                last_value = current_value

        except Exception:
            consecutive_matches = 0
            last_value = object()

        time.sleep(interval)

    elapsed = time.time() - start_time
    raise WaitTimeoutError(
        f"Timeout after {elapsed:.1f}s waiting for value to stabilize "
        f"(needed {stability_count} consecutive matches, got {consecutive_matches})"
    )


def wait_all(
    client: Client,
    context: Context,
    conditions: list[Callable[[], bool]],
    timeout: float = 30.0,
    interval: float = 0.5,
) -> None:
    """Wait for all conditions to be true.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        conditions: List of condition functions that return True when met.
        timeout: Maximum time to wait in seconds.
        interval: Time between polling attempts in seconds.

    Raises:
        WaitTimeoutError: If timeout is reached without all conditions being met.

    Example:
        >>> wait_all(
        ...     client, context,
        ...     conditions=[
        ...         lambda: db_exists(client, context, "users", {"email": "test@example.com"}),
        ...         lambda: count_emails(client, context, "test@example.com") > 0,
        ...     ],
        ...     timeout=60
        ... )
    """
    start_time = time.time()
    failed_conditions: list[int] = []

    while time.time() - start_time < timeout:
        failed_conditions = []

        for i, condition in enumerate(conditions):
            try:
                if not condition():
                    failed_conditions.append(i)
            except Exception:
                failed_conditions.append(i)

        if not failed_conditions:
            return

        time.sleep(interval)

    elapsed = time.time() - start_time
    raise WaitTimeoutError(
        f"Timeout after {elapsed:.1f}s waiting for conditions. "
        f"Failed conditions: {failed_conditions}"
    )


def wait_any(
    client: Client,
    context: Context,
    conditions: list[Callable[[], bool]],
    timeout: float = 30.0,
    interval: float = 0.5,
) -> int:
    """Wait for any condition to be true.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        conditions: List of condition functions that return True when met.
        timeout: Maximum time to wait in seconds.
        interval: Time between polling attempts in seconds.

    Returns:
        int: Index of the first condition that succeeded.

    Raises:
        WaitTimeoutError: If timeout is reached without any condition being met.

    Example:
        >>> idx = wait_any(
        ...     client, context,
        ...     conditions=[
        ...         lambda: db_exists(client, context, "orders", {"status": "completed"}),
        ...         lambda: db_exists(client, context, "orders", {"status": "failed"}),
        ...     ],
        ...     timeout=60
        ... )
        >>> print(f"Order ended with condition {idx}")
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        for i, condition in enumerate(conditions):
            try:
                if condition():
                    return i
            except Exception:
                pass

        time.sleep(interval)

    elapsed = time.time() - start_time
    raise WaitTimeoutError(f"Timeout after {elapsed:.1f}s waiting for any condition to be met")


def wait_for_retry_success(
    client: Client,
    context: Context,
    action_fn: Callable[[], httpx.Response],
    success_status: int | list[int] = 200,
    max_attempts: int = 5,
    retry_delay: float = 2.0,
    backoff_multiplier: float = 2.0,
) -> httpx.Response:
    """Wait for an action to succeed with exponential backoff.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        action_fn: Function that returns an HTTP response.
        success_status: Expected status code(s).
        max_attempts: Maximum number of attempts.
        retry_delay: Initial delay between retries in seconds.
        backoff_multiplier: Multiplier for delay after each failure.

    Returns:
        httpx.Response: The successful response.

    Raises:
        WaitError: If all attempts fail.

    Example:
        >>> response = wait_for_retry_success(
        ...     client, context,
        ...     action_fn=lambda: post(client, context, "/api/process", json={"id": 123}),
        ...     success_status=[200, 201],
        ...     max_attempts=10,
        ...     retry_delay=1.0
        ... )
    """
    if isinstance(success_status, int):
        success_statuses = {success_status}
    else:
        success_statuses = set(success_status)

    current_delay = retry_delay
    last_response: httpx.Response | None = None
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            response = action_fn()

            if response.status_code in success_statuses:
                return response

            last_response = response
        except Exception as e:
            last_error = e

        if attempt < max_attempts - 1:
            time.sleep(current_delay)
            current_delay *= backoff_multiplier

    if last_response:
        raise WaitError(
            f"Action failed after {max_attempts} attempts. Last status: {last_response.status_code}"
        )

    raise WaitError(f"Action failed after {max_attempts} attempts. Last error: {last_error}")
