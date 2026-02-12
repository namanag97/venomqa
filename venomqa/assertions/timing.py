"""Performance and timing assertions for VenomQA.

Provides assertion functions for validating execution time, eventual
consistency, and performance thresholds.

Example:
    >>> from venomqa.assertions import assert_completes_within, assert_eventual_success
    >>> assert_completes_within(lambda: api.call(), max_seconds=5.0)
    >>> assert_eventual_success(lambda: check_ready(), timeout=30, interval=2)
"""

from __future__ import annotations

import functools
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

from venomqa.assertions.expect import AssertionFailed

T = TypeVar("T")


class TimingAssertionError(AssertionFailed):
    """Raised when a timing assertion fails."""

    pass


class TimeoutError(TimingAssertionError):
    """Raised when an operation times out."""

    pass


def assert_completes_within(
    func: Callable[[], T],
    max_seconds: float,
    message: str | None = None,
) -> T:
    """Assert function completes within time limit.

    Args:
        func: Function to execute.
        max_seconds: Maximum allowed execution time in seconds.
        message: Custom error message on timeout.

    Returns:
        The return value of func.

    Raises:
        TimingAssertionError: If execution exceeds time limit.

    Example:
        >>> result = assert_completes_within(lambda: slow_api(), 5.0)
    """
    start = time.perf_counter()
    try:
        result = func()
    finally:
        elapsed = time.perf_counter() - start

    if elapsed > max_seconds:
        msg = message or f"Function took {elapsed:.3f}s, exceeded limit of {max_seconds}s"
        raise TimingAssertionError(
            msg,
            actual=f"{elapsed:.3f}s",
            expected=f"<= {max_seconds}s",
        )

    return result


def assert_response_time_under(
    func: Callable[[], Any],
    max_ms: float,
) -> Any:
    """Assert function response time is under threshold.

    Args:
        func: Function to execute.
        max_ms: Maximum allowed response time in milliseconds.

    Returns:
        The return value of func.

    Raises:
        TimingAssertionError: If response time exceeds threshold.

    Example:
        >>> response = assert_response_time_under(lambda: client.get("/api"), 500)
    """
    start = time.perf_counter()
    result = func()
    elapsed = time.perf_counter() - start
    elapsed_ms = elapsed * 1000

    if elapsed_ms > max_ms:
        raise TimingAssertionError(
            f"Response time {elapsed_ms:.2f}ms exceeded limit of {max_ms}ms",
            actual=f"{elapsed_ms:.2f}ms",
            expected=f"<= {max_ms}ms",
        )

    return result


def assert_eventual_success(
    func: Callable[[], T],
    timeout: float,
    interval: float = 0.5,
    success_check: Callable[[T], bool] | None = None,
    message: str | None = None,
) -> T:
    """Assert function eventually succeeds within timeout.

    Repeatedly calls func until it returns a truthy value (or passes
    success_check) within the timeout period.

    Args:
        func: Function to poll.
        timeout: Maximum time to wait in seconds.
        interval: Time between retries in seconds.
        success_check: Optional function to validate result.
        message: Custom error message on timeout.

    Returns:
        The successful return value of func.

    Raises:
        TimeoutError: If function doesn't succeed within timeout.

    Example:
        >>> result = assert_eventual_success(
        ...     lambda: client.get("/status").json().get("ready"),
        ...     timeout=30,
        ...     interval=2
        ... )
    """
    start = time.perf_counter()
    last_result = None
    last_error = None

    while True:
        try:
            result = func()
            if success_check is not None:
                if success_check(result):
                    return result
            elif result:
                return result
            last_result = result
        except Exception as e:
            last_error = e

        elapsed = time.perf_counter() - start
        if elapsed >= timeout:
            break

        time.sleep(min(interval, timeout - elapsed))

    msg = message or f"Function did not succeed within {timeout}s"
    if last_error:
        msg += f" (last error: {last_error})"
    elif last_result is not None:
        msg += f" (last result: {last_result})"
    raise TimeoutError(
        msg,
        actual="timeout",
        expected=f"success within {timeout}s",
    )


def assert_eventually_equals(
    func: Callable[[], T],
    expected: T,
    timeout: float,
    interval: float = 0.5,
) -> T:
    """Assert function eventually returns expected value.

    Args:
        func: Function to poll.
        expected: Expected return value.
        timeout: Maximum time to wait in seconds.
        interval: Time between retries in seconds.

    Returns:
        The expected value once matched.

    Raises:
        TimeoutError: If value doesn't match within timeout.

    Example:
        >>> status = assert_eventually_equals(
        ...     lambda: client.get("/status").json()["status"],
        ...     "completed",
        ...     timeout=60
        ... )
    """
    start = time.perf_counter()
    last_result = None

    while True:
        result = func()
        if result == expected:
            return result
        last_result = result

        elapsed = time.perf_counter() - start
        if elapsed >= timeout:
            break

        time.sleep(min(interval, timeout - elapsed))

    raise TimeoutError(
        f"Function did not return {expected!r} within {timeout}s (last: {last_result!r})",
        actual=last_result,
        expected=expected,
    )


def assert_stable_for(
    func: Callable[[], T],
    duration: float,
    interval: float = 0.5,
    message: str | None = None,
) -> T:
    """Assert function return value remains stable for duration.

    Args:
        func: Function to poll.
        duration: Time to verify stability in seconds.
        interval: Time between checks in seconds.
        message: Custom error message on instability.

    Returns:
        The stable value.

    Raises:
        TimingAssertionError: If value changes during period.

    Example:
        >>> value = assert_stable_for(lambda: get_counter(), duration=5.0)
    """
    initial = func()
    start = time.perf_counter()

    while time.perf_counter() - start < duration:
        time.sleep(interval)
        current = func()
        if current != initial:
            msg = message or f"Value changed from {initial!r} to {current!r}"
            raise TimingAssertionError(
                msg,
                actual=current,
                expected=initial,
            )

    return initial


def assert_performance_regression(
    func: Callable[[], Any],
    baseline_seconds: float,
    tolerance: float = 0.1,
    runs: int = 3,
) -> float:
    """Assert function doesn't regress from baseline performance.

    Runs the function multiple times and checks average against baseline.

    Args:
        func: Function to benchmark.
        baseline_seconds: Expected baseline time.
        tolerance: Allowed regression as fraction (0.1 = 10% slower OK).
        runs: Number of runs to average.

    Returns:
        Average execution time.

    Raises:
        TimingAssertionError: If performance regressed beyond tolerance.

    Example:
        >>> avg_time = assert_performance_regression(
        ...     lambda: expensive_operation(),
        ...     baseline_seconds=1.0,
        ...     tolerance=0.2
        ... )
    """
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        func()
        times.append(time.perf_counter() - start)

    avg_time = sum(times) / len(times)
    max_allowed = baseline_seconds * (1 + tolerance)

    if avg_time > max_allowed:
        raise TimingAssertionError(
            f"Performance regression: average {avg_time:.3f}s exceeds "
            f"baseline {baseline_seconds:.3f}s + {tolerance:.0%} tolerance",
            actual=f"{avg_time:.3f}s",
            expected=f"<= {max_allowed:.3f}s",
        )

    return avg_time


def assert_throughput_at_least(
    func: Callable[[], Any],
    min_ops_per_second: float,
    duration: float = 5.0,
) -> float:
    """Assert function achieves minimum throughput.

    Args:
        func: Function to benchmark.
        min_ops_per_second: Minimum required operations per second.
        duration: Test duration in seconds.

    Returns:
        Actual throughput (ops/second).

    Raises:
        TimingAssertionError: If throughput below minimum.

    Example:
        >>> throughput = assert_throughput_at_least(
        ...     lambda: api.ping(),
        ...     min_ops_per_second=100
        ... )
    """
    start = time.perf_counter()
    count = 0

    while time.perf_counter() - start < duration:
        func()
        count += 1

    elapsed = time.perf_counter() - start
    actual_throughput = count / elapsed

    if actual_throughput < min_ops_per_second:
        raise TimingAssertionError(
            f"Throughput {actual_throughput:.1f} ops/s below minimum {min_ops_per_second} ops/s",
            actual=f"{actual_throughput:.1f} ops/s",
            expected=f">= {min_ops_per_second} ops/s",
        )

    return actual_throughput


class PerformanceTimer:
    """Context manager for timing code blocks.

    Example:
        >>> with PerformanceTimer() as timer:
        ...     do_something()
        >>> print(f"Took {timer.elapsed_ms:.2f}ms")
        >>> timer.assert_under(100)  # Raises if > 100ms
    """

    def __init__(self, name: str = "operation"):
        self.name = name
        self.start_time: float | None = None
        self.end_time: float | None = None

    def __enter__(self) -> PerformanceTimer:
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self.end_time = time.perf_counter()

    @property
    def elapsed_seconds(self) -> float:
        """Elapsed time in seconds."""
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.perf_counter()
        return end - self.start_time

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time in milliseconds."""
        return self.elapsed_seconds * 1000

    def assert_under(self, max_ms: float, message: str | None = None) -> None:
        """Assert elapsed time is under threshold.

        Args:
            max_ms: Maximum allowed time in milliseconds.
            message: Custom error message.

        Raises:
            TimingAssertionError: If time exceeds threshold.
        """
        actual = self.elapsed_ms
        if actual > max_ms:
            msg = message or f"{self.name} took {actual:.2f}ms, exceeded {max_ms}ms limit"
            raise TimingAssertionError(
                msg,
                actual=f"{actual:.2f}ms",
                expected=f"<= {max_ms}ms",
            )


def timed(func: Callable[..., T]) -> Callable[..., tuple[T, float]]:
    """Decorator that returns (result, elapsed_seconds).

    Example:
        >>> @timed
        ... def slow_function():
        ...     time.sleep(0.1)
        ...     return "done"
        >>> result, elapsed = slow_function()
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> tuple[T, float]:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        return result, elapsed

    return wrapper


def assert_concurrent_completes(
    funcs: list[Callable[[], Any]],
    max_total_seconds: float,
) -> list[Any]:
    """Assert multiple functions complete within time limit when run concurrently.

    Args:
        funcs: List of functions to execute concurrently.
        max_total_seconds: Maximum total time for all to complete.

    Returns:
        List of results from each function.

    Raises:
        TimingAssertionError: If total time exceeds limit.

    Example:
        >>> results = assert_concurrent_completes(
        ...     [lambda: api.call(1), lambda: api.call(2)],
        ...     max_total_seconds=5.0
        ... )
    """
    results: list[Any] = [None] * len(funcs)
    errors: list[Exception | None] = [None] * len(funcs)

    def run_func(idx: int, func: Callable[[], Any]) -> None:
        try:
            results[idx] = func()
        except Exception as e:
            errors[idx] = e

    start = time.perf_counter()
    threads = [threading.Thread(target=run_func, args=(i, f)) for i, f in enumerate(funcs)]

    for t in threads:
        t.start()

    for t in threads:
        t.join(timeout=max_total_seconds)

    elapsed = time.perf_counter() - start

    if elapsed > max_total_seconds:
        raise TimingAssertionError(
            f"Concurrent execution took {elapsed:.3f}s, exceeded {max_total_seconds}s limit",
            actual=f"{elapsed:.3f}s",
            expected=f"<= {max_total_seconds}s",
        )

    for i, e in enumerate(errors):
        if e is not None:
            raise TimingAssertionError(
                f"Function {i} raised exception: {e}",
                actual=str(e),
                expected="no exceptions",
            )

    return results
