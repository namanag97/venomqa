from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskState(Enum):
    """Task state enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    id: str
    name: str
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    task_id: str
    success: bool
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0


class ConcurrencyPort(ABC):
    @abstractmethod
    def spawn(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        """Spawn a new task."""
        ...

    @abstractmethod
    def spawn_after(
        self, delay_seconds: float, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> str:
        """Spawn a task after a delay."""
        ...

    @abstractmethod
    def spawn_many(self, funcs: list[Callable[..., Any]], *args: Any, **kwargs: Any) -> list[str]:
        """Spawn multiple tasks."""
        ...

    @abstractmethod
    def join(self, task_id: str, timeout: float | None = None) -> TaskResult:
        """Wait for a task to complete."""
        ...

    @abstractmethod
    def join_all(self, task_ids: list[str], timeout: float | None = None) -> list[TaskResult]:
        """Wait for all tasks to complete."""
        ...

    @abstractmethod
    def join_any(self, task_ids: list[str], timeout: float | None = None) -> tuple[str, TaskResult]:
        """Wait for any task to complete."""
        ...

    @abstractmethod
    def cancel(self, task_id: str) -> bool:
        """Cancel a task."""
        ...

    @abstractmethod
    def cancel_all(self, task_ids: list[str]) -> int:
        """Cancel multiple tasks."""
        ...

    @abstractmethod
    def get_task(self, task_id: str) -> TaskInfo | None:
        """Get task info."""
        ...

    @abstractmethod
    def get_status(self, task_id: str) -> str | None:
        """Get task status."""
        ...

    @abstractmethod
    def is_running(self, task_id: str) -> bool:
        """Check if a task is running."""
        ...

    @abstractmethod
    def is_completed(self, task_id: str) -> bool:
        """Check if a task is completed."""
        ...

    @abstractmethod
    def is_failed(self, task_id: str) -> bool:
        """Check if a task has failed."""
        ...

    @abstractmethod
    def get_result(self, task_id: str) -> TaskResult | None:
        """Get task result if completed."""
        ...

    @abstractmethod
    def get_active_tasks(self) -> list[TaskInfo]:
        """Get all active tasks."""
        ...

    @abstractmethod
    def set_progress(self, task_id: str, progress: float) -> bool:
        """Set task progress (0.0 to 1.0)."""
        ...

    @abstractmethod
    def lock(self, name: str, timeout: float | None = None) -> bool:
        """Acquire a named lock."""
        ...

    @abstractmethod
    def unlock(self, name: str) -> bool:
        """Release a named lock."""
        ...

    @abstractmethod
    def with_lock(self, name: str, func: Callable[..., Any], timeout: float | None = None) -> Any:
        """Execute a function with a lock."""
        ...

    @abstractmethod
    def semaphore(self, name: str, max_count: int) -> str:
        """Create a semaphore."""
        ...

    @abstractmethod
    def semaphore_acquire(self, semaphore_id: str, timeout: float | None = None) -> bool:
        """Acquire a semaphore."""
        ...

    @abstractmethod
    def semaphore_release(self, semaphore_id: str) -> bool:
        """Release a semaphore."""
        ...

    @abstractmethod
    def map_parallel(
        self, func: Callable[[Any], Any], items: list[Any], max_workers: int = 4
    ) -> list[Any]:
        """Map a function over items in parallel."""
        ...

    @abstractmethod
    def map_async(self, func: Callable[[Any], Any], items: list[Any]) -> list[str]:
        """Map a function over items asynchronously."""
        ...
