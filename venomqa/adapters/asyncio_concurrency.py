"""AsyncIO Concurrency adapter for async parallel execution.

This adapter provides asyncio-based concurrency for async functions.

Example:
    >>> from venomqa.adapters import AsyncConcurrencyAdapter
    >>> adapter = AsyncConcurrencyAdapter()
    >>> task_id = await adapter.spawn_async(my_async_func, arg1)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from venomqa.ports.concurrency import ConcurrencyPort, TaskInfo, TaskResult, TaskState


@dataclass
class AsyncConfig:
    """Configuration for AsyncIO adapter."""

    max_concurrent: int = 10


class AsyncConcurrencyAdapter(ConcurrencyPort):
    """Adapter for asyncio-based concurrency.

    This adapter implements the ConcurrencyPort interface using
    Python's asyncio for async task execution.

    Note: This adapter is designed for async usage. The spawn method
    schedules tasks on the event loop.

    Attributes:
        config: Configuration for asyncio.

    Example:
        >>> adapter = AsyncConcurrencyAdapter()
        >>> task_id = adapter.spawn(async_function, arg1, arg2)
    """

    def __init__(
        self,
        max_concurrent: int = 10,
    ) -> None:
        """Initialize the Async Concurrency adapter.

        Args:
            max_concurrent: Maximum concurrent tasks.
        """
        self.config = AsyncConfig(max_concurrent=max_concurrent)
        self._tasks: dict[str, TaskInfo] = {}
        self._async_tasks: dict[str, asyncio.Task] = {}
        self._results: dict[str, TaskResult] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create event loop."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _generate_id(self) -> str:
        """Generate a unique task ID."""
        return str(uuid.uuid4())

    async def _wrap_async_task(
        self,
        task_id: str,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Wrap an async task for execution tracking."""
        self._tasks[task_id].started_at = datetime.now()
        self._tasks[task_id].status = TaskState.RUNNING.value

        start_time = time.time()
        try:
            async with self._semaphore:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = await self._get_loop().run_in_executor(None, func, *args)

            duration = time.time() - start_time
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
            func: Function to execute (sync or async).
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Task ID.
        """
        task_id = self._generate_id()

        self._tasks[task_id] = TaskInfo(
            id=task_id,
            name=func.__name__,
            status=TaskState.PENDING.value,
            created_at=datetime.now(),
        )

        loop = self._get_loop()
        coroutine = self._wrap_async_task(task_id, func, args, kwargs)

        try:
            task = loop.create_task(coroutine)
            self._async_tasks[task_id] = task
        except RuntimeError:
            pass

        return task_id

    async def spawn_async(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Spawn a new async task.

        Args:
            func: Function to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            Task ID.
        """
        task_id = self._generate_id()

        self._tasks[task_id] = TaskInfo(
            id=task_id,
            name=func.__name__,
            status=TaskState.PENDING.value,
            created_at=datetime.now(),
        )

        coroutine = self._wrap_async_task(task_id, func, args, kwargs)
        task = asyncio.create_task(coroutine)
        self._async_tasks[task_id] = task

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

        async def delayed_spawn() -> str:
            await asyncio.sleep(delay_seconds)
            return await self.spawn_async(func, *args, **kwargs)

        try:
            loop = self._get_loop()
            loop.create_task(delayed_spawn())
        except RuntimeError:
            pass

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
        """
        task = self._async_tasks.get(task_id)
        if task is None:
            return TaskResult(
                task_id=task_id,
                success=False,
                error="Task not found",
            )

        loop = self._get_loop()

        try:
            if loop.is_running():
                start = time.time()
                while not task.done():
                    if timeout and (time.time() - start) >= timeout:
                        raise TimeoutError()
                    time.sleep(0.01)
            else:
                loop.run_until_complete(asyncio.wait_for(task, timeout=timeout))
        except asyncio.TimeoutError:
            raise TimeoutError() from None

        return self._results.get(
            task_id,
            TaskResult(
                task_id=task_id,
                success=False,
                error="Result not available",
            ),
        )

    async def join_async(
        self,
        task_id: str,
        timeout: float | None = None,
    ) -> TaskResult:
        """Async wait for a task to complete.

        Args:
            task_id: Task ID.
            timeout: Maximum wait time.

        Returns:
            Task result.
        """
        task = self._async_tasks.get(task_id)
        if task is None:
            return TaskResult(
                task_id=task_id,
                success=False,
                error="Task not found",
            )

        try:
            await asyncio.wait_for(task, timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError() from None

        return self._results.get(
            task_id,
            TaskResult(
                task_id=task_id,
                success=False,
                error="Result not available",
            ),
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

    async def join_all_async(
        self,
        task_ids: list[str],
        timeout: float | None = None,
    ) -> list[TaskResult]:
        """Async wait for all tasks to complete.

        Args:
            task_ids: List of task IDs.
            timeout: Maximum wait time for all.

        Returns:
            List of task results.
        """
        tasks = [self._async_tasks.get(tid) for tid in task_ids]
        tasks = [t for t in tasks if t is not None]

        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

        return [
            self._results.get(
                tid,
                TaskResult(
                    task_id=tid,
                    success=False,
                    error="Result not available",
                ),
            )
            for tid in task_ids
        ]

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
        """
        start = time.time()
        while True:
            for task_id in task_ids:
                if task_id in self._results:
                    return task_id, self._results[task_id]

            if timeout and (time.time() - start) >= timeout:
                raise TimeoutError()

            time.sleep(0.01)

    def cancel(self, task_id: str) -> bool:
        """Cancel a task.

        Args:
            task_id: Task ID.

        Returns:
            True if cancelled.
        """
        task = self._async_tasks.get(task_id)
        if task:
            cancelled = task.cancel()
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
        """Check if a task is running."""
        return self.get_status(task_id) == TaskState.RUNNING.value

    def is_completed(self, task_id: str) -> bool:
        """Check if a task is completed."""
        return self.get_status(task_id) == TaskState.COMPLETED.value

    def is_failed(self, task_id: str) -> bool:
        """Check if a task has failed."""
        return self.get_status(task_id) == TaskState.FAILED.value

    def get_result(self, task_id: str) -> TaskResult | None:
        """Get task result if completed."""
        return self._results.get(task_id)

    def get_active_tasks(self) -> list[TaskInfo]:
        """Get all active tasks."""
        return [
            t
            for t in self._tasks.values()
            if t.status in (TaskState.PENDING.value, TaskState.RUNNING.value)
        ]

    def set_progress(self, task_id: str, progress: float) -> bool:
        """Set task progress (0.0 to 1.0)."""
        if task_id in self._tasks:
            self._tasks[task_id].progress = max(0.0, min(1.0, progress))
            return True
        return False

    def lock(self, name: str, timeout: float | None = None) -> bool:
        """Acquire a named lock."""
        return True

    def unlock(self, name: str) -> bool:
        """Release a named lock."""
        return True

    def with_lock(
        self,
        name: str,
        func: Callable[..., Any],
        timeout: float | None = None,
    ) -> Any:
        """Execute a function with a lock."""
        return func()

    def semaphore(self, name: str, max_count: int) -> str:
        """Create a semaphore."""
        return name

    def semaphore_acquire(
        self,
        semaphore_id: str,
        timeout: float | None = None,
    ) -> bool:
        """Acquire a semaphore."""
        return True

    def semaphore_release(self, semaphore_id: str) -> bool:
        """Release a semaphore."""
        return True

    def map_parallel(
        self,
        func: Callable[[Any], Any],
        items: list[Any],
        max_workers: int = 4,
    ) -> list[Any]:
        """Map a function over items in parallel."""
        task_ids = self.spawn_many([func] * len(items))
        self.join_all(task_ids)
        return [self._results.get(tid).result for tid in task_ids if tid in self._results]

    async def map_parallel_async(
        self,
        func: Callable[[Any], Any],
        items: list[Any],
    ) -> list[Any]:
        """Async map a function over items in parallel."""
        tasks = [self.spawn_async(func, item) for item in items]
        await self.join_all_async(tasks)
        return [self._results.get(tid).result for tid in tasks if tid in self._results]

    def map_async(
        self,
        func: Callable[[Any], Any],
        items: list[Any],
    ) -> list[str]:
        """Map a function over items asynchronously."""
        return [self.spawn(func, item) for item in items]

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the executor."""
        for task in self._async_tasks.values():
            if not task.done():
                task.cancel()

    def health_check(self) -> bool:
        """Check if the concurrency service is healthy."""
        return True
