"""Wait and polling actions for QA testing.

This module provides reusable wait/polling action functions for:
- Waiting for HTTP responses
- Waiting for specific conditions
- Polling with custom predicates

Example:
    >>> from venomqa.tools import wait_for_response, wait_for_condition, wait_for_status
    >>>
    >>> # Wait for endpoint to return 200
    >>> response = wait_for_status(client, context, "/health", 200, timeout=30)
    >>>
    >>> # Wait for custom condition
    >>> response = wait_for_condition(
    ...     client, context,
    ...     condition_fn=lambda r: r.json().get("status") == "ready",
    ...     path="/api/job/123"
    ... )
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import httpx

from venomqa.errors import VenomQAError
from venomqa.tools.http import get

if TYPE_CHECKING:
    from venomqa.client import Client
    from venomqa.state.context import Context


class WaitTimeoutError(VenomQAError):
    """Raised when a wait operation times out."""

    pass


class WaitError(VenomQAError):
    """Raised when a wait operation fails."""

    pass


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

    while time.time() - start_time < timeout:
        try:
            response = get(client, context, path, **kwargs)
            min_status, max_status = expected_status_range
            if min_status <= response.status_code <= max_status:
                return response
        except Exception as e:
            last_error = e

        time.sleep(interval)

    elapsed = time.time() - start_time
    msg = f"Timeout after {elapsed:.1f}s waiting for response from {path}"
    if last_error:
        msg += f" (last error: {last_error})"
    raise WaitTimeoutError(msg)


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

    while time.time() - start_time < timeout:
        try:
            response = get(client, context, path, **kwargs)
            last_status = response.status_code
            if response.status_code in expected_statuses:
                return response
        except Exception:
            pass

        time.sleep(interval)

    elapsed = time.time() - start_time
    status_str = ", ".join(map(str, expected_statuses))
    msg = f"Timeout after {elapsed:.1f}s waiting for status {status_str} from {path}"
    if last_status is not None:
        msg += f" (last status: {last_status})"
    raise WaitTimeoutError(msg)


def wait_for_condition(
    client: Client,
    context: Context,
    condition_fn: Callable[[httpx.Response], bool],
    path: str = "",
    timeout: float = 30.0,
    interval: float = 1.0,
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
        ...     path="/api/jobs/123"
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

    while time.time() - start_time < timeout:
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
    msg = f"Timeout after {elapsed:.1f}s waiting for condition"
    if path:
        msg += f" on {path}"
    if last_result is not None:
        msg += f" (last result: {last_result})"
    if last_error:
        msg += f" (last error: {last_error})"
    raise WaitTimeoutError(msg)


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
