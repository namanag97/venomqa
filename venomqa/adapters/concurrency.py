"""Concurrency adapter using threading.

This adapter provides thread-based concurrency for testing purposes.
It implements the ConcurrencyPort interface with ThreadPoolExecutor.

Example:
    >>> from venomqa.adapters.concurrency import ThreadConcurrencyAdapter
    >>> adapter = ThreadConcurrencyAdapter(max_workers=4)
    >>> task_id = adapter.spawn(my_function, arg1, arg2)
    >>> result = adapter.join(task_id)
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


class TaskNotFoundError(Exception):
    """Raised when a task cannot be found."""

    pass


class TaskTimeoutError(Exception):
    """Raised when a task times out."""

    pass


@dataclass
class ThreadConcurrencyConfig:
    """Configuration for Thread Concurrency adapter.

    Attributes:
        max_workers: Maximum number of worker threads.
        thread_name_prefix: Prefix for thread names.
    """

    max_workers: int = 10
    thread_name_prefix: str = "venomqa-worker-"


class ThreadConcurrencyAdapter(ConcurrencyPort):
    """Thread-based concurrency adapter.

    This adapter implements the ConcurrencyPort interface using Python's
    ThreadPoolExecutor for parallel task execution. It supports locks,
    semaphores, and parallel mapping.

    Attributes:
        config: Configuration for threading.

    Example:
        >>> adapter = ThreadConcurrencyAdapter(max_workers=4)
        >>> task_id = adapter.spawn(lambda x: x * 2, 21)
        >>> result = adapter.join(task_id)
        >>> print(result.result)  # 42
    """

    def __init__(
        self,
        max_workers: int = 10,
        thread_name_prefix: str = "venomqa-worker-",
    ) -> None:
        """Initialize the Thread Concurrency adapter.

        Args:
            max_workers: Maximum number of worker threads.
                Defaults to 10.
            thread_name_prefix: Prefix for thread names.

        Raises:
            ValueError: If max_workers is not positive.
        """
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")

        self.config = ThreadConcurrencyConfig(
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
        self._locks: dict[str, threading.Lock] = {}
        self._semaphores: dict[str, threading.Semaphore] = {}
        self._lock = threading.Lock()

    def _generate_id(self) -> str:
        """Generate a unique task ID.

        Returns:
            A unique task identifier string.
        """
        return f"task-{uuid.uuid4()}"

    def _update_task_status(self, task_id: str, status: str) -> None:
        """Update task status thread-safely.

        Args:
            task_id: Task ID to update.
            status: New status value.
        """
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = status

    def _wrap_task(
        self,
        task_id: str,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Wrap a task for execution tracking.

        Args:
            task_id: Task ID.
            func: Function to execute.
            args: Positional arguments.
            kwargs: Keyword arguments.

        Returns:
            Function result.
        """
        self._update_task_status(task_id, TaskState.RUNNING.value)
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].started_at = datetime.now()

        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time

            self._update_task_status(task_id, TaskState.COMPLETED.value)
            with self._lock:
                if task_id in self._tasks:
                    self._tasks[task_id].completed_at = datetime.now()
                self._results[task_id] = TaskResult(
                    task_id=task_id,
                    success=True,
                    result=result,
                    duration_ms=duration * 1000,
                )
            return result
        except Exception as e:
            duration = time.time() - start_time
            self._update_task_status(task_id, TaskState.FAILED.value)
            with self._lock:
                if task_id in self._tasks:
                    self._tasks[task_id].completed_at = datetime.now()
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
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            Task ID.

        Raises:
            ValueError: If func is None.
        """
        if func is None:
            raise ValueError("Function cannot be None")

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

    async def spawn_async(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        """Spawn a new async task.

        For this threading adapter, async functions are run in the executor.

        Args:
            func: Function to execute (sync or async).
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Task ID.
        """
        import asyncio

        task_id = self._generate_id()

        with self._lock:
            self._tasks[task_id] = TaskInfo(
                id=task_id,
                name=func.__name__,
                status=TaskState.PENDING.value,
                created_at=datetime.now(),
            )

        async def async_wrapper() -> Any:
            self._update_task_status(task_id, TaskState.RUNNING.value)
            with self._lock:
                if task_id in self._tasks:
                    self._tasks[task_id].started_at = datetime.now()

            start_time = time.time()
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, func, *args)
                duration = time.time() - start_time

                self._update_task_status(task_id, TaskState.COMPLETED.value)
                with self._lock:
                    if task_id in self._tasks:
                        self._tasks[task_id].completed_at = datetime.now()
                    self._results[task_id] = TaskResult(
                        task_id=task_id,
                        success=True,
                        result=result,
                        duration_ms=duration * 1000,
                    )
                return result
            except Exception as e:
                duration = time.time() - start_time
                self._update_task_status(task_id, TaskState.FAILED.value)
                with self._lock:
                    if task_id in self._tasks:
                        self._tasks[task_id].completed_at = datetime.now()
                    self._results[task_id] = TaskResult(
                        task_id=task_id,
                        success=False,
                        error=str(e),
                        duration_ms=duration * 1000,
                    )
                raise

        asyncio.create_task(async_wrapper())
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
            delay_seconds: Delay before spawning in seconds.
            func: Function to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Empty string (actual task ID is created after delay).
        """

        def delayed() -> str:
            time.sleep(delay_seconds)
            return self.spawn(func, *args, **kwargs)

        self._executor.submit(delayed)
        return ""

    def spawn_many(self, funcs: list[Callable[..., Any]], *args: Any, **kwargs: Any) -> list[str]:
        """Spawn multiple tasks.

        Args:
            funcs: List of functions to execute.
            *args: Positional arguments for all functions.
            **kwargs: Keyword arguments for all functions.

        Returns:
            List of task IDs.
        """
        return [self.spawn(f, *args, **kwargs) for f in funcs]

    def join(self, task_id: str, timeout: float | None = None) -> TaskResult:
        """Wait for a task to complete.

        Args:
            task_id: Task ID.
            timeout: Maximum wait time in seconds.

        Returns:
            Task result.

        Raises:
            TaskNotFoundError: If the task doesn't exist.
            TimeoutError: If timeout exceeded.
        """
        with self._lock:
            future = self._futures.get(task_id)

        if future is None:
            return TaskResult(task_id=task_id, success=False, error="Task not found")

        try:
            future.result(timeout=timeout)
        except TimeoutError:
            return TaskResult(task_id=task_id, success=False, error="Timeout")
        except Exception:
            pass

        with self._lock:
            if task_id in self._results:
                return self._results[task_id]

        return TaskResult(task_id=task_id, success=False, error="No result")

    async def join_async(self, task_id: str, timeout: float | None = None) -> TaskResult:
        """Async wait for a task to complete.

        Args:
            task_id: Task ID.
            timeout: Maximum wait time.

        Returns:
            Task result.
        """
        return self.join(task_id, timeout)

    def join_all(self, task_ids: list[str], timeout: float | None = None) -> list[TaskResult]:
        """Wait for all tasks to complete.

        Args:
            task_ids: List of task IDs.
            timeout: Maximum wait time for each task.

        Returns:
            List of task results.
        """
        return [self.join(tid, timeout) for tid in task_ids]

    async def join_all_async(
        self, task_ids: list[str], timeout: float | None = None
    ) -> list[TaskResult]:
        """Async wait for all tasks to complete.

        Args:
            task_ids: List of task IDs.
            timeout: Maximum wait time.

        Returns:
            List of task results.
        """
        return self.join_all(task_ids, timeout)

    def join_any(self, task_ids: list[str], timeout: float | None = None) -> tuple[str, TaskResult]:
        """Wait for any task to complete.

        Args:
            task_ids: List of task IDs.
            timeout: Maximum wait time in seconds.

        Returns:
            Tuple of (completed_task_id, result).

        Raises:
            TimeoutError: If no task completes within timeout.
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
            True if cancelled, False otherwise.
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
            Task info or None if not found.
        """
        with self._lock:
            return self._tasks.get(task_id)

    def get_status(self, task_id: str) -> str | None:
        """Get task status.

        Args:
            task_id: Task ID.

        Returns:
            Status string or None if not found.
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
            timeout: Lock timeout in seconds.

        Returns:
            True if acquired.
        """
        with self._lock:
            if name not in self._locks:
                self._locks[name] = threading.Lock()
            lock = self._locks[name]
        if timeout is None:
            lock.acquire()
            return True
        return lock.acquire(timeout=timeout)

    def unlock(self, name: str) -> bool:
        """Release a named lock.

        Args:
            name: Lock name.

        Returns:
            True if released.
        """
        with self._lock:
            if name not in self._locks:
                return False
        try:
            self._locks[name].release()
            return True
        except RuntimeError:
            return False

    def with_lock(self, name: str, func: Callable[..., Any], timeout: float | None = None) -> Any:
        """Execute a function with a lock.

        Args:
            name: Lock name.
            func: Function to execute.
            timeout: Lock timeout.

        Returns:
            Function result.
        """
        if self.lock(name, timeout):
            try:
                return func()
            finally:
                self.unlock(name)
        raise TimeoutError(f"Could not acquire lock: {name}")

    def semaphore(self, name: str, max_count: int) -> str:
        """Create a semaphore.

        Args:
            name: Semaphore name.
            max_count: Maximum count.

        Returns:
            Semaphore ID.
        """
        sem_id = f"sem-{uuid.uuid4()}"
        with self._lock:
            self._semaphores[sem_id] = threading.Semaphore(max_count)
        return sem_id

    def semaphore_acquire(self, semaphore_id: str, timeout: float | None = None) -> bool:
        """Acquire a semaphore.

        Args:
            semaphore_id: Semaphore ID.
            timeout: Acquisition timeout.

        Returns:
            True if acquired.
        """
        with self._lock:
            sem = self._semaphores.get(semaphore_id)
        if sem is None:
            return False
        if timeout is None:
            sem.acquire()
            return True
        return sem.acquire(timeout=timeout)

    def semaphore_release(self, semaphore_id: str) -> bool:
        """Release a semaphore.

        Args:
            semaphore_id: Semaphore ID.

        Returns:
            True if released.
        """
        with self._lock:
            sem = self._semaphores.get(semaphore_id)
        if sem is None:
            return False
        try:
            sem.release()
            return True
        except ValueError:
            return False

    def map_parallel(
        self, func: Callable[[Any], Any], items: list[Any], max_workers: int = 4
    ) -> list[Any]:
        """Map a function over items in parallel.

        Args:
            func: Function to apply.
            items: Items to process.
            max_workers: Maximum workers (ignored, uses config).

        Returns:
            List of results.
        """
        task_ids = [self.spawn(func, item) for item in items]
        self.join_all(task_ids)
        return [
            self._results[tid].result
            for tid in task_ids
            if tid in self._results and self._results[tid].success
        ]

    async def map_parallel_async(self, func: Callable[[Any], Any], items: list[Any]) -> list[Any]:
        """Async map a function over items in parallel.

        Args:
            func: Function to apply.
            items: Items to process.

        Returns:
            List of results.
        """
        task_ids = [self.spawn(func, item) for item in items]
        self.join_all(task_ids)
        results = []
        for tid in task_ids:
            result = self._results.get(tid)
            if result is not None and result.result is not None:
                results.append(result.result)
        return results

    def map_async(self, func: Callable[[Any], Any], items: list[Any]) -> list[str]:
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
            True if the executor is not shut down.
        """
        return not self._executor._shutdown

    def get_task_count(self) -> int:
        """Get the total number of tracked tasks.

        Returns:
            Number of tasks.
        """
        with self._lock:
            return len(self._tasks)

    def clear_completed_tasks(self) -> int:
        """Clear completed and failed tasks from tracking.

        Returns:
            Number of tasks cleared.
        """
        count = 0
        with self._lock:
            to_remove = [
                tid
                for tid, task in self._tasks.items()
                if task.status
                in (TaskState.COMPLETED.value, TaskState.FAILED.value, TaskState.CANCELLED.value)
            ]
            for tid in to_remove:
                del self._tasks[tid]
                self._futures.pop(tid, None)
                count += 1
        return count
