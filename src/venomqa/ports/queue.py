"""Queue Port interface for VenomQA."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    """Status of a queue job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    CANCELLED = "cancelled"


@dataclass
class JobInfo:
    """Information about a queued job."""

    id: str
    name: str
    queue: str
    status: JobStatus
    args: tuple[Any, ...] = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress: float = 0.0
    error: str | None = None
    retries: int = 0
    max_retries: int = 3


@dataclass
class JobResult:
    """Result of a completed job."""

    job_id: str
    success: bool
    result: Any = None
    error: str | None = None
    duration: float = 0.0
    traceback: str | None = None


class QueuePort(ABC):
    """Abstract port for queue operations in QA testing.

    This port defines the interface for job queue systems like
    Redis Queue, Celery, etc. Implementations should support
    job submission, monitoring, and result retrieval.
    """

    @abstractmethod
    def enqueue(
        self,
        func: Callable[..., Any] | str,
        *args: Any,
        queue: str = "default",
        **kwargs: Any,
    ) -> str:
        """Enqueue a job for execution.

        Args:
            func: Function to execute or task name.
            *args: Positional arguments for the function.
            queue: Queue name to submit to.
            **kwargs: Keyword arguments for the function.

        Returns:
            Job ID.
        """
        ...

    @abstractmethod
    def get_job(self, job_id: str) -> JobInfo | None:
        """Get information about a job.

        Args:
            job_id: ID of the job.

        Returns:
            Job information or None if not found.
        """
        ...

    @abstractmethod
    def get_job_result(self, job_id: str, timeout: float = 30.0) -> JobResult | None:
        """Wait for and get the result of a job.

        Args:
            job_id: ID of the job.
            timeout: Maximum time to wait in seconds.

        Returns:
            Job result or None if timeout.
        """
        ...

    @abstractmethod
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or running job.

        Args:
            job_id: ID of the job to cancel.

        Returns:
            True if cancelled, False if not possible.
        """
        ...

    @abstractmethod
    def get_queue_length(self, queue: str = "default") -> int:
        """Get the number of jobs in a queue.

        Args:
            queue: Queue name.

        Returns:
            Number of pending jobs.
        """
        ...

    @abstractmethod
    def get_active_jobs(self, queue: str | None = None) -> list[JobInfo]:
        """Get all currently active (running) jobs.

        Args:
            queue: Optional queue filter.

        Returns:
            List of active jobs.
        """
        ...

    @abstractmethod
    def get_failed_jobs(self, queue: str | None = None) -> list[JobInfo]:
        """Get all failed jobs.

        Args:
            queue: Optional queue filter.

        Returns:
            List of failed jobs.
        """
        ...

    @abstractmethod
    def clear_queue(self, queue: str = "default") -> int:
        """Clear all jobs from a queue.

        Args:
            queue: Queue name to clear.

        Returns:
            Number of jobs removed.
        """
        ...

    @abstractmethod
    def retry_job(self, job_id: str) -> bool:
        """Retry a failed job.

        Args:
            job_id: ID of the job to retry.

        Returns:
            True if retry was scheduled.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the queue service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        ...
