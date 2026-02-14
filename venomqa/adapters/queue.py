"""Mock Queue adapter for testing.

This adapter provides an in-memory job queue mock for testing purposes.
It implements the QueuePort interface with full job lifecycle management,
retries, and manual job control for testing.

Example:
    >>> from venomqa.adapters.queue import MockQueueAdapter
    >>> queue = MockQueueAdapter(max_retries=3)
    >>> job_id = queue.enqueue(process_data, "arg1", "arg2")
    >>> queue.process_job(job_id)  # Manually process for testing
    >>> result = queue.get_job_result(job_id)
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from venomqa.ports.queue import JobInfo, JobResult, JobStatus, QueuePort


class JobNotFoundError(Exception):
    """Raised when a job cannot be found."""

    pass


class JobStateError(Exception):
    """Raised when a job is in an invalid state for the operation."""

    pass


@dataclass
class MockQueueConfig:
    """Configuration for Mock Queue adapter.

    Attributes:
        max_retries: Maximum number of retry attempts for failed jobs.
        default_queue: Name of the default queue.
        job_timeout: Default timeout for job execution in seconds.
    """

    max_retries: int = 3
    default_queue: str = "default"
    job_timeout: float = 30.0


@dataclass
class MockJob:
    """Internal job representation.

    Attributes:
        id: Unique job identifier.
        name: Job/task name.
        queue: Queue name this job belongs to.
        func: Callable to execute (may be None for named tasks).
        args: Positional arguments for the function.
        kwargs: Keyword arguments for the function.
        status: Current job status.
        created_at: When the job was created.
        started_at: When the job started running.
        completed_at: When the job completed (success or failure).
        progress: Job progress (0.0 to 1.0).
        error: Error message if the job failed.
        retries: Number of retry attempts made.
        max_retries: Maximum retry attempts allowed.
        result: Job result if completed successfully.
    """

    id: str
    name: str
    queue: str
    func: Callable[..., Any] | None = None
    args: tuple[Any, ...] = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress: float = 0.0
    error: str | None = None
    retries: int = 0
    max_retries: int = 3
    result: Any = None


class MockQueueAdapter(QueuePort):
    """In-memory mock queue adapter for testing.

    This adapter provides a fully functional in-memory job queue for testing.
    It supports manual job processing, automatic retries, and full job
    lifecycle management.

    Attributes:
        config: Configuration for the mock queue.

    Example:
        >>> queue = MockQueueAdapter(max_retries=3)
        >>> job_id = queue.enqueue(lambda x: x * 2, 21)
        >>> queue.process_job(job_id)
        >>> result = queue.get_job_result(job_id)
        >>> print(result.result)  # 42
    """

    def __init__(
        self,
        max_retries: int = 3,
        default_queue: str = "default",
        job_timeout: float = 30.0,
    ) -> None:
        """Initialize the Mock Queue adapter.

        Args:
            max_retries: Maximum number of retry attempts for failed jobs.
                Defaults to 3.
            default_queue: Name of the default queue. Defaults to "default".
            job_timeout: Default timeout for job execution in seconds.
                Defaults to 30.0.

        Raises:
            ValueError: If max_retries is negative.
        """
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")

        self.config = MockQueueConfig(
            max_retries=max_retries,
            default_queue=default_queue,
            job_timeout=job_timeout,
        )
        self._jobs: dict[str, MockJob] = {}
        self._queues: dict[str, list[str]] = {default_queue: []}
        self._healthy: bool = True

    def _generate_id(self) -> str:
        """Generate a unique job ID.

        Returns:
            A unique job identifier string.
        """
        return f"job-{uuid.uuid4().hex[:8]}"

    def _job_to_info(self, job: MockJob) -> JobInfo:
        """Convert a MockJob to JobInfo.

        Args:
            job: The MockJob to convert.

        Returns:
            A JobInfo dataclass instance.
        """
        return JobInfo(
            id=job.id,
            name=job.name,
            queue=job.queue,
            status=job.status,
            args=job.args,
            kwargs=job.kwargs,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            progress=job.progress,
            error=job.error,
            retries=job.retries,
            max_retries=job.max_retries,
        )

    def enqueue(
        self,
        func: Callable[..., Any] | str,
        *args: Any,
        queue: str = "default",
        **kwargs: Any,
    ) -> str:
        """Enqueue a job for execution.

        Args:
            func: Function to execute or task name string.
            *args: Positional arguments for the function.
            queue: Queue name to submit to. Defaults to "default".
            **kwargs: Keyword arguments for the function.

        Returns:
            The job ID.

        Raises:
            ValueError: If queue name is empty.
        """
        if not queue:
            raise ValueError("Queue name cannot be empty")

        if queue not in self._queues:
            self._queues[queue] = []

        job_id = self._generate_id()
        name = func if isinstance(func, str) else func.__name__
        callable_func = func if callable(func) else None

        job = MockJob(
            id=job_id,
            name=name,
            queue=queue,
            func=callable_func,
            args=args,
            kwargs=kwargs,
            max_retries=self.config.max_retries,
        )

        self._jobs[job_id] = job
        self._queues[queue].append(job_id)
        return job_id

    def get_job(self, job_id: str) -> JobInfo | None:
        """Get information about a job.

        Args:
            job_id: ID of the job to retrieve.

        Returns:
            Job information or None if the job doesn't exist.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return self._job_to_info(job)

    def get_job_result(self, job_id: str, timeout: float = 30.0) -> JobResult | None:
        """Wait for and get the result of a job.

        This method polls until the job completes or times out.

        Args:
            job_id: ID of the job.
            timeout: Maximum time to wait in seconds.

        Returns:
            JobResult if the job completed, None if timeout or not found.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return None

        start = time.time()
        while time.time() - start < timeout:
            if job.status == JobStatus.COMPLETED:
                duration = 0.0
                if job.started_at and job.completed_at:
                    duration = (job.completed_at - job.started_at).total_seconds()
                return JobResult(
                    job_id=job.id,
                    success=True,
                    result=job.result,
                    duration=duration,
                )
            if job.status == JobStatus.FAILED:
                duration = 0.0
                if job.started_at and job.completed_at:
                    duration = (job.completed_at - job.started_at).total_seconds()
                return JobResult(
                    job_id=job.id,
                    success=False,
                    error=job.error,
                    duration=duration,
                )
            time.sleep(0.01)

        return None

    def process_job(self, job_id: str) -> bool:
        """Process a job manually.

        This method executes the job's function synchronously. Use this
        in tests to control when jobs are processed.

        Args:
            job_id: ID of the job to process.

        Returns:
            True if the job completed successfully, False otherwise.

        Raises:
            JobNotFoundError: If the job doesn't exist.
            JobStateError: If the job is not in a processable state.
        """
        job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id} not found")

        if job.status not in (JobStatus.PENDING, JobStatus.RETRY):
            raise JobStateError(
                f"Job {job_id} is in {job.status.value} state and cannot be processed"
            )

        if job.func is None:
            job.status = JobStatus.FAILED
            job.error = "No callable function associated with job"
            job.completed_at = datetime.now()
            return False

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now()

        try:
            result = job.func(*job.args, **job.kwargs)
            job.result = result
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now()
            return True
        except Exception as e:
            job.error = str(e)
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now()
            return False

    def start_job(self, job_id: str) -> bool:
        """Mark a job as started without executing it.

        Use this to simulate job execution in tests.

        Args:
            job_id: ID of the job to start.

        Returns:
            True if the job was started, False if not found.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now()
        return True

    def complete_job(
        self,
        job_id: str,
        result: Any = None,
        success: bool = True,
        error: str | None = None,
    ) -> bool:
        """Mark a job as completed with a result.

        Use this to simulate job completion in tests.

        Args:
            job_id: ID of the job to complete.
            result: The result value (if success is True).
            success: Whether the job succeeded.
            error: Error message (if success is False).

        Returns:
            True if the job was completed, False if not found.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if success:
            job.status = JobStatus.COMPLETED
            job.result = result
        else:
            job.status = JobStatus.FAILED
            job.error = error
        job.completed_at = datetime.now()
        return True

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or running job.

        Args:
            job_id: ID of the job to cancel.

        Returns:
            True if the job was cancelled, False if not found or not cancellable.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.status in (JobStatus.PENDING, JobStatus.RETRY, JobStatus.RUNNING):
            job.status = JobStatus.CANCELLED
            return True
        return False

    def get_queue_length(self, queue: str = "default") -> int:
        """Get the number of pending jobs in a queue.

        Args:
            queue: Queue name to check.

        Returns:
            Number of pending jobs in the queue.
        """
        if queue not in self._queues:
            return 0
        return len(
            [
                jid
                for jid in self._queues[queue]
                if self._jobs.get(jid, MockJob(id="", name="", queue="")).status
                == JobStatus.PENDING
            ]
        )

    def get_active_jobs(self, queue: str | None = None) -> list[JobInfo]:
        """Get all currently running jobs.

        Args:
            queue: Optional queue name to filter by.

        Returns:
            List of running job information.
        """
        jobs = []
        for job in self._jobs.values():
            if job.status == JobStatus.RUNNING:
                if queue is None or job.queue == queue:
                    jobs.append(self._job_to_info(job))
        return jobs

    def get_failed_jobs(self, queue: str | None = None) -> list[JobInfo]:
        """Get all failed jobs.

        Args:
            queue: Optional queue name to filter by.

        Returns:
            List of failed job information.
        """
        jobs = []
        for job in self._jobs.values():
            if job.status == JobStatus.FAILED:
                if queue is None or job.queue == queue:
                    jobs.append(self._job_to_info(job))
        return jobs

    def get_completed_jobs(self, queue: str | None = None) -> list[JobInfo]:
        """Get all completed jobs.

        Args:
            queue: Optional queue name to filter by.

        Returns:
            List of completed job information.
        """
        jobs = []
        for job in self._jobs.values():
            if job.status == JobStatus.COMPLETED:
                if queue is None or job.queue == queue:
                    jobs.append(self._job_to_info(job))
        return jobs

    def get_pending_jobs(self, queue: str | None = None) -> list[JobInfo]:
        """Get all pending jobs.

        Args:
            queue: Optional queue name to filter by.

        Returns:
            List of pending job information.
        """
        jobs = []
        for job in self._jobs.values():
            if job.status == JobStatus.PENDING:
                if queue is None or job.queue == queue:
                    jobs.append(self._job_to_info(job))
        return jobs

    def clear_queue(self, queue: str = "default") -> int:
        """Clear all jobs from a queue.

        Args:
            queue: Queue name to clear.

        Returns:
            Number of jobs removed.
        """
        if queue not in self._queues:
            return 0
        count = len(self._queues[queue])
        for job_id in self._queues[queue]:
            if job_id in self._jobs:
                del self._jobs[job_id]
        self._queues[queue] = []
        return count

    def retry_job(self, job_id: str) -> bool:
        """Retry a failed job.

        Args:
            job_id: ID of the job to retry.

        Returns:
            True if the job was queued for retry, False if not possible.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.status == JobStatus.FAILED and job.retries < job.max_retries:
            job.status = JobStatus.PENDING
            job.retries += 1
            job.error = None
            job.started_at = None
            job.completed_at = None
            return True
        return False

    def set_job_progress(self, job_id: str, progress: float) -> bool:
        """Set the progress of a running job.

        Args:
            job_id: ID of the job.
            progress: Progress value between 0.0 and 1.0.

        Returns:
            True if progress was set, False if job not found.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.progress = max(0.0, min(1.0, progress))
        return True

    def health_check(self) -> bool:
        """Check if the queue service is healthy.

        Returns:
            True if healthy, False if set_healthy(False) was called.
        """
        return self._healthy

    def set_healthy(self, healthy: bool) -> None:
        """Set the health status of the queue.

        Use this to simulate unhealthy queue states in tests.

        Args:
            healthy: True for healthy, False for unhealthy.
        """
        self._healthy = healthy

    def get_all_jobs(self) -> list[JobInfo]:
        """Get all jobs regardless of status.

        Returns:
            List of all job information.
        """
        return [self._job_to_info(job) for job in self._jobs.values()]

    def get_job_count(self, queue: str | None = None) -> int:
        """Get the total number of jobs.

        Args:
            queue: Optional queue name to filter by.

        Returns:
            Total number of jobs.
        """
        if queue is None:
            return len(self._jobs)
        return sum(1 for job in self._jobs.values() if job.queue == queue)

    def get_queues(self) -> list[str]:
        """Get all queue names.

        Returns:
            List of queue names.
        """
        return list(self._queues.keys())

    def clear_all(self) -> int:
        """Clear all jobs from all queues.

        Returns:
            Total number of jobs removed.
        """
        count = len(self._jobs)
        self._jobs.clear()
        for queue in self._queues:
            self._queues[queue] = []
        return count
