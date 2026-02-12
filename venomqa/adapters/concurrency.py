"""Concurrency adapter using threading.

This adapter provides thread-based concurrency for testing purposes.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from venomqa.ports.concurrency import ConcurrencyPort, TaskInfo, TaskResult, TaskState


@dataclass
class ThreadConcurrencyConfig:
    """Configuration for Thread Concurrency adapter."""

    max_workers: int = 10


class ThreadConcurrencyAdapter(ConcurrencyPort):
    """Thread-based concurrency adapter.

    Attributes:
        config: Configuration for threading.
    """

    def __init__(self, max_workers: int = 10) -> None:
        self.config = ThreadConcurrencyConfig(max_workers=max_workers)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, TaskInfo] = {}
        self._futures: dict[str, Future] = {}
        self._results: dict[str, TaskResult] = {}

    def _generate_id(self) -> str:
        return str(uuid.uuid4())

    def spawn(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        task_id = self._generate_id()
        self._tasks[task_id] = TaskInfo(
            id=task_id,
            name=func.__name__,
            status=TaskState.PENDING.value,
            created_at=datetime.now(),
        )

        def wrapper() -> Any:
            self._tasks[task_id].status = TaskState.RUNNING.value
            self._tasks[task_id].started_at = datetime.now()
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                self._tasks[task_id].status = TaskState.COMPLETED.value
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
                self._tasks[task_id].status = TaskState.FAILED.value
                self._tasks[task_id].completed_at = datetime.now()
                self._results[task_id] = TaskResult(
                    task_id=task_id,
                    success=False,
                    error=str(e),
                    duration_ms=duration * 1000,
                )
                raise

        future = self._executor.submit(wrapper)
        self._futures[task_id] = future
        return task_id

    async def spawn_async(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        import asyncio

        task_id = self._generate_id()
        self._tasks[task_id] = TaskInfo(
            id=task_id,
            name=func.__name__,
            status=TaskState.PENDING.value,
            created_at=datetime.now(),
        )

        async def async_wrapper() -> Any:
            self._tasks[task_id].status = TaskState.RUNNING.value
            self._tasks[task_id].started_at = datetime.now()
            start_time = time.time()
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = await asyncio.get_event_loop().run_in_executor(None, func, *args)
                duration = time.time() - start_time
                self._tasks[task_id].status = TaskState.COMPLETED.value
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
                self._tasks[task_id].status = TaskState.FAILED.value
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
        def delayed() -> str:
            time.sleep(delay_seconds)
            return self.spawn(func, *args, **kwargs)

        self._executor.submit(delayed)
        return ""

    def spawn_many(self, funcs: list[Callable[..., Any]], *args: Any, **kwargs: Any) -> list[str]:
        return [self.spawn(f, *args, **kwargs) for f in funcs]

    def join(self, task_id: str, timeout: float | None = None) -> TaskResult:
        future = self._futures.get(task_id)
        if future is None:
            return TaskResult(task_id=task_id, success=False, error="Task not found")
        try:
            future.result(timeout=timeout)
        except TimeoutError:
            return TaskResult(task_id=task_id, success=False, error="Timeout")
        except Exception:
            pass
        return self._results.get(
            task_id, TaskResult(task_id=task_id, success=False, error="No result")
        )

    async def join_async(self, task_id: str, timeout: float | None = None) -> TaskResult:
        return self.join(task_id, timeout)

    def join_all(self, task_ids: list[str], timeout: float | None = None) -> list[TaskResult]:
        return [self.join(tid, timeout) for tid in task_ids]

    async def join_all_async(
        self, task_ids: list[str], timeout: float | None = None
    ) -> list[TaskResult]:
        return self.join_all(task_ids, timeout)

    def join_any(self, task_ids: list[str], timeout: float | None = None) -> tuple[str, TaskResult]:
        start = time.time()
        while True:
            for task_id in task_ids:
                if task_id in self._results:
                    return task_id, self._results[task_id]
            if timeout and (time.time() - start) >= timeout:
                raise TimeoutError()
            time.sleep(0.01)

    def cancel(self, task_id: str) -> bool:
        future = self._futures.get(task_id)
        if future:
            cancelled = future.cancel()
            if cancelled and task_id in self._tasks:
                self._tasks[task_id].status = TaskState.CANCELLED.value
            return cancelled
        return False

    def cancel_all(self, task_ids: list[str]) -> int:
        return sum(1 for tid in task_ids if self.cancel(tid))

    def get_task(self, task_id: str) -> TaskInfo | None:
        return self._tasks.get(task_id)

    def get_status(self, task_id: str) -> str | None:
        task = self.get_task(task_id)
        return task.status if task else None

    def is_running(self, task_id: str) -> bool:
        return self.get_status(task_id) == TaskState.RUNNING.value

    def is_completed(self, task_id: str) -> bool:
        return self.get_status(task_id) == TaskState.COMPLETED.value

    def is_failed(self, task_id: str) -> bool:
        return self.get_status(task_id) == TaskState.FAILED.value

    def get_result(self, task_id: str) -> TaskResult | None:
        return self._results.get(task_id)

    def get_active_tasks(self) -> list[TaskInfo]:
        return [
            t
            for t in self._tasks.values()
            if t.status in (TaskState.PENDING.value, TaskState.RUNNING.value)
        ]

    def set_progress(self, task_id: str, progress: float) -> bool:
        if task_id in self._tasks:
            self._tasks[task_id].progress = max(0.0, min(1.0, progress))
            return True
        return False

    def lock(self, name: str, timeout: float | None = None) -> bool:
        return True

    def unlock(self, name: str) -> bool:
        return True

    def with_lock(self, name: str, func: Callable[..., Any], timeout: float | None = None) -> Any:
        return func()

    def semaphore(self, name: str, max_count: int) -> str:
        return name

    def semaphore_acquire(self, semaphore_id: str, timeout: float | None = None) -> bool:
        return True

    def semaphore_release(self, semaphore_id: str) -> bool:
        return True

    def map_parallel(
        self, func: Callable[[Any], Any], items: list[Any], max_workers: int = 4
    ) -> list[Any]:
        task_ids = self.spawn_many([func] * len(items))
        self.join_all(task_ids)
        return [
            self._results.get(tid).result
            for tid in task_ids
            if tid in self._results and self._results[tid].result is not None
        ]

    async def map_parallel_async(self, func: Callable[[Any], Any], items: list[Any]) -> list[Any]:
        tasks = [self.spawn_async(func, item) for item in items]
        await self.join_all_async(tasks)
        return [
            self._results.get(tid).result
            for tid in tasks
            if tid in self._results and self._results[tid].result is not None
        ]

    def map_async(self, func: Callable[[Any], Any], items: list[Any]) -> list[str]:
        return [self.spawn(func, item) for item in items]

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)

    def health_check(self) -> bool:
        return True
