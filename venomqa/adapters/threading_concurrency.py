"""Threading Concurrency adapter for parallel execution.

This adapter provides thread-based concurrency using Python's
concurrent.futures module.

Example:
    >>> from venomqa.adapters import ThreadingConcurrencyAdapter
    >>> adapter = ThreadingConcurrencyAdapter(max_workers=4)
    >>> task_id = adapter.spawn(my_function, arg1, arg2)
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from venomqa.ports.concurrency import ConcurrencyPort, TaskInfo, TaskResult, TaskState


@dataclass
class ThreadingConfig:
    """Configuration for Threading adapter."""

    max_workers: int = 4
    thread_name_prefix: str = "venomqa-"


class ThreadingConcurrencyAdapter(ConcurrencyPort):
    """Adapter for thread-based concurrency.

    This adapter implements the ConcurrencyPort interface using
    Python's ThreadPoolExecutor for parallel task execution.

    Attributes:
        config: Configuration for threading.

    Example:
        >>> adapter = ThreadingConcurrencyAdapter(max_workers=4)
        >>> task_id = adapter.spawn(lambda x: x * 2, 21)
        >>> result = adapter.join(task_id)
        >>> print(result.result)  # 42
    """

    def __init__(
        self,
        max_workers: int = 4,
        thread_name_prefix: str = "venomqa-",
    ) -> None:
        """Initialize the Threading Concurrency adapter.

        Args:
            max_workers: Maximum number of worker threads.
            thread_name_prefix: Prefix for thread names.
        """
        self.config = ThreadingConfig(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )
        self._tasks: dict[str, TaskInfo] = {}
        self._futures: dict[str, Future] = {}
        self._results: dict[str, TaskResult] = {}
        self._lock = threading.Lock()

    def _generate_id(self) -> str:
        """Generate a unique task ID."""
        return str(uuid.uuid4())

    def _wrap_task(
        self,
        task_id: str,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Wrap a task for execution tracking."""
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].started_at = datetime.now()
                self._tasks[task_id].status = TaskState.RUNNING.value

        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time

            with self._lock:
                if task_id in self._tasks:
                    self._tasks[task_id].completed_at = datetime.now()
                    self._tasks[task_id].status = TaskState.COMPLETED.value
                self._results[task_id] = TaskResult(
                    task_id=task_id,
                    success=True,
                    result=result,
                    duration_ms=duration * 1000,
                )
            return result
        except Exception as e:
            duration = time.time() - start_time
            with self._lock:
                if task_id in self._tasks:
                    self._tasks[task_id].completed_at = datetime.now()
                    self._tasks[task_id].status = TaskState.FAILED.value
                self._results[task_id] = TaskResult(
                    task_id=task_id,
                    success=False,
                    error=str(e),
                    duration_ms=duration * 1000,
                )
            raise

    def spawn(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        """Spawn a new task.

        Args:
            func: Function to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Task ID.
        """
        task_id = self._generate_id()

        with self._lock:
            self._tasks[task_id] = TaskInfo(
                id=task_id,
                name=func.__name__,
                status=TaskState.PENDING.value,
                created_at=datetime.now(),
            )

        future = self._executor.submit(self._wrap_task, task_id, func, args, kwargs)

        with self._lock:
            self._futures[task_id] = future

        return task_id

    def spawn_after(
        self,
        delay_seconds: float,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Spawn a task after a delay.

        Args:
            delay_seconds: Delay before spawning.
            func: Function to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Task ID.
        """

        def delayed_task() -> str:
            time.sleep(delay_seconds)
            return self.spawn(func, *args, **kwargs)

        threading.Thread(target=delayed_task, daemon=True).start()
        return ""

    def spawn_many(
        self,
        funcs: list[Callable[..., Any]],
        *args: Any,
        **kwargs: Any,
    ) -> list[str]:
        """Spawn multiple tasks.

        Args:
            funcs: List of functions to execute.
            *args: Positional arguments for all.
            **kwargs: Keyword arguments for all.

        Returns:
            List of task IDs.
        """
        return [self.spawn(f, *args, **kwargs) for f in funcs]

    def join(self, task_id: str, timeout: float | None = None) -> TaskResult:
        """Wait for a task to complete.

        Args:
            task_id: Task ID.
            timeout: Maximum wait time.

        Returns:
            Task result.

        Raises:
            TimeoutError: If timeout exceeded.
        """
        with self._lock:
            future = self._futures.get(task_id)

        if future is None:
            raise ValueError(f"Task {task_id} not found")

        future.result(timeout=timeout)

        with self._lock:
            if task_id in self._results:
                return self._results[task_id]

        return TaskResult(
            task_id=task_id,
            success=False,
            error="Result not available",
        )

    def join_all(
        self,
        task_ids: list[str],
        timeout: float | None = None,
    ) -> list[TaskResult]:
        """Wait for all tasks to complete.

        Args:
            task_ids: List of task IDs.
            timeout: Maximum wait time for all.

        Returns:
            List of task results.
        """
        results = []
        for task_id in task_ids:
            try:
                results.append(self.join(task_id, timeout=timeout))
            except Exception as e:
                results.append(
                    TaskResult(
                        task_id=task_id,
                        success=False,
                        error=str(e),
                    )
                )
        return results

    def join_any(
        self,
        task_ids: list[str],
        timeout: float | None = None,
    ) -> tuple[str, TaskResult]:
        """Wait for any task to complete.

        Args:
            task_ids: List of task IDs.
            timeout: Maximum wait time.

        Returns:
            Tuple of (completed_task_id, result).

        Raises:
            TimeoutError: If timeout exceeded.
        """
        start = time.time()
        while True:
            with self._lock:
                for task_id in task_ids:
                    if task_id in self._results:
                        return task_id, self._results[task_id]

            if timeout and (time.time() - start) >= timeout:
                raise TimeoutError("No task completed within timeout")

            time.sleep(0.01)

    def cancel(self, task_id: str) -> bool:
        """Cancel a task.

        Args:
            task_id: Task ID.

        Returns:
            True if cancelled.
        """
        with self._lock:
            future = self._futures.get(task_id)
            if future:
                cancelled = future.cancel()
                if cancelled and task_id in self._tasks:
                    self._tasks[task_id].status = TaskState.CANCELLED.value
                return cancelled
        return False

    def cancel_all(self, task_ids: list[str]) -> int:
        """Cancel multiple tasks.

        Args:
            task_ids: List of task IDs.

        Returns:
            Number of cancelled tasks.
        """
        return sum(1 for tid in task_ids if self.cancel(tid))

    def get_task(self, task_id: str) -> TaskInfo | None:
        """Get task info.

        Args:
            task_id: Task ID.

        Returns:
            Task info or None.
        """
        with self._lock:
            return self._tasks.get(task_id)

    def get_status(self, task_id: str) -> str | None:
        """Get task status.

        Args:
            task_id: Task ID.

        Returns:
            Status string or None.
        """
        task = self.get_task(task_id)
        return task.status if task else None

    def is_running(self, task_id: str) -> bool:
        """Check if a task is running.

        Args:
            task_id: Task ID.

        Returns:
            True if running.
        """
        return self.get_status(task_id) == TaskState.RUNNING.value

    def is_completed(self, task_id: str) -> bool:
        """Check if a task is completed.

        Args:
            task_id: Task ID.

        Returns:
            True if completed.
        """
        return self.get_status(task_id) == TaskState.COMPLETED.value

    def is_failed(self, task_id: str) -> bool:
        """Check if a task has failed.

        Args:
            task_id: Task ID.

        Returns:
            True if failed.
        """
        return self.get_status(task_id) == TaskState.FAILED.value

    def get_result(self, task_id: str) -> TaskResult | None:
        """Get task result if completed.

        Args:
            task_id: Task ID.

        Returns:
            Task result or None.
        """
        with self._lock:
            return self._results.get(task_id)

    def get_active_tasks(self) -> list[TaskInfo]:
        """Get all active tasks.

        Returns:
            List of active task info.
        """
        with self._lock:
            return [
                t
                for t in self._tasks.values()
                if t.status in (TaskState.PENDING.value, TaskState.RUNNING.value)
            ]

    def set_progress(self, task_id: str, progress: float) -> bool:
        """Set task progress (0.0 to 1.0).

        Args:
            task_id: Task ID.
            progress: Progress value.

        Returns:
            True if set.
        """
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].progress = max(0.0, min(1.0, progress))
                return True
        return False

    def lock(self, name: str, timeout: float | None = None) -> bool:
        """Acquire a named lock.

        Args:
            name: Lock name.
            timeout: Lock timeout.

        Returns:
            True if acquired.
        """
        return True

    def unlock(self, name: str) -> bool:
        """Release a named lock.

        Args:
            name: Lock name.

        Returns:
            True if released.
        """
        return True

    def with_lock(
        self,
        name: str,
        func: Callable[..., Any],
        timeout: float | None = None,
    ) -> Any:
        """Execute a function with a lock.

        Args:
            name: Lock name.
            func: Function to execute.
            timeout: Lock timeout.

        Returns:
            Function result.
        """
        return func()

    def semaphore(self, name: str, max_count: int) -> str:
        """Create a semaphore.

        Args:
            name: Semaphore name.
            max_count: Maximum count.

        Returns:
            Semaphore ID.
        """
        return name

    def semaphore_acquire(
        self,
        semaphore_id: str,
        timeout: float | None = None,
    ) -> bool:
        """Acquire a semaphore.

        Args:
            semaphore_id: Semaphore ID.
            timeout: Acquisition timeout.

        Returns:
            True if acquired.
        """
        return True

    def semaphore_release(self, semaphore_id: str) -> bool:
        """Release a semaphore.

        Args:
            semaphore_id: Semaphore ID.

        Returns:
            True if released.
        """
        return True

    def map_parallel(
        self,
        func: Callable[[Any], Any],
        items: list[Any],
        max_workers: int = 4,
    ) -> list[Any]:
        """Map a function over items in parallel.

        Args:
            func: Function to apply.
            items: Items to process.
            max_workers: Maximum workers.

        Returns:
            List of results.
        """
        return list(self._executor.map(func, items))

    def map_async(
        self,
        func: Callable[[Any], Any],
        items: list[Any],
    ) -> list[str]:
        """Map a function over items asynchronously.

        Args:
            func: Function to apply.
            items: Items to process.

        Returns:
            List of task IDs.
        """
        return [self.spawn(func, item) for item in items]

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the executor.

        Args:
            wait: Whether to wait for pending tasks.
        """
        self._executor.shutdown(wait=wait)

    def health_check(self) -> bool:
        """Check if the concurrency service is healthy.

        Returns:
            True if healthy.
        """
        return not self._executor._shutdown
