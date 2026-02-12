"""Redis Queue adapter for job queue testing.

RQ (Redis Queue) is a simple Python library for queueing jobs and
processing them in the background with workers.

Installation:
    pip install redis rq

Example:
    >>> from venomqa.adapters import RedisQueueAdapter
    >>> adapter = RedisQueueAdapter(host="localhost", port=6379)
    >>> job_id = adapter.enqueue(my_function, "arg1", "arg2")
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from redis import Redis

from venomqa.ports.queue import JobInfo, JobResult, JobStatus, QueuePort

try:
    from rq import Queue
    from rq.job import Job

    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False
    Queue = None
    Job = None


@dataclass
class RedisQueueConfig:
    """Configuration for Redis Queue adapter."""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    default_queue: str = "default"
    timeout: float = 30.0


class RedisQueueAdapter(QueuePort):
    """Adapter for Redis Queue (RQ) job queue.

    This adapter provides integration with RQ for job queue
    management in test environments.

    Attributes:
        config: Configuration for the Redis connection.

    Example:
        >>> adapter = RedisQueueAdapter()
        >>> job_id = adapter.enqueue(process_data, data={})
        >>> result = adapter.get_job_result(job_id, timeout=60)
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        default_queue: str = "default",
    ) -> None:
        """Initialize the Redis Queue adapter.

        Args:
            host: Redis server hostname.
            port: Redis server port.
            db: Redis database number.
            password: Redis password if required.
            default_queue: Default queue name.

        Raises:
            ImportError: If rq is not installed.
        """
        if not RQ_AVAILABLE:
            raise ImportError("rq is required. Install with: pip install rq")

        self.config = RedisQueueConfig(
            host=host,
            port=port,
            db=db,
            password=password,
            default_queue=default_queue,
        )
        self._redis = Redis(
            host=host,
            port=port,
            db=db,
            password=password,
        )
        self._queues: dict[str, Queue] = {}

    def _get_queue(self, name: str) -> Queue:
        """Get or create a queue by name."""
        if name not in self._queues:
            self._queues[name] = Queue(name, connection=self._redis)
        return self._queues[name]

    def _map_status(self, status: str) -> JobStatus:
        """Map RQ job status to JobStatus enum."""
        status_map = {
            "queued": JobStatus.PENDING,
            "started": JobStatus.RUNNING,
            "finished": JobStatus.COMPLETED,
            "failed": JobStatus.FAILED,
            "deferred": JobStatus.PENDING,
            "scheduled": JobStatus.PENDING,
            "stopped": JobStatus.CANCELLED,
        }
        return status_map.get(status, JobStatus.PENDING)

    def _job_to_info(self, job: Job) -> JobInfo:
        """Convert an RQ Job to JobInfo."""
        return JobInfo(
            id=job.id,
            name=job.func_name,
            queue=job.origin or self.config.default_queue,
            status=self._map_status(job.get_status()),
            args=job.args,
            kwargs=job.kwargs,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.ended_at,
            error=str(job.exc_info) if job.exc_info else None,
            retries=0,
            max_retries=3,
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
            func: Function to execute or task name.
            *args: Positional arguments for the function.
            queue: Queue name to submit to.
            **kwargs: Keyword arguments for the function.

        Returns:
            Job ID.
        """
        q = self._get_queue(queue)
        if isinstance(func, str):
            job = q.enqueue(func, *args, **kwargs)
        else:
            job = q.enqueue(func, *args, **kwargs)
        return job.id

    def get_job(self, job_id: str) -> JobInfo | None:
        """Get information about a job.

        Args:
            job_id: ID of the job.

        Returns:
            Job information or None if not found.
        """
        try:
            job = Job.fetch(job_id, connection=self._redis)
            return self._job_to_info(job)
        except Exception:
            return None

    def get_job_result(self, job_id: str, timeout: float = 30.0) -> JobResult | None:
        """Wait for and get the result of a job.

        Args:
            job_id: ID of the job.
            timeout: Maximum time to wait in seconds.

        Returns:
            Job result or None if timeout.
        """
        try:
            job = Job.fetch(job_id, connection=self._redis)
        except Exception:
            return None

        start = time.time()
        while time.time() - start < timeout:
            status = job.get_status()
            if status == "finished":
                duration = 0.0
                if job.started_at and job.ended_at:
                    duration = (job.ended_at - job.started_at).total_seconds()
                return JobResult(
                    job_id=job_id,
                    success=True,
                    result=job.result,
                    duration=duration,
                )
            elif status == "failed":
                return JobResult(
                    job_id=job_id,
                    success=False,
                    error=str(job.exc_info) if job.exc_info else "Unknown error",
                    traceback=str(job.exc_info) if job.exc_info else None,
                )
            time.sleep(0.5)

        return None

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or running job.

        Args:
            job_id: ID of the job to cancel.

        Returns:
            True if cancelled, False if not possible.
        """
        try:
            job = Job.fetch(job_id, connection=self._redis)
            job.cancel()
            return True
        except Exception:
            return False

    def get_queue_length(self, queue: str = "default") -> int:
        """Get the number of jobs in a queue.

        Args:
            queue: Queue name.

        Returns:
            Number of pending jobs.
        """
        q = self._get_queue(queue)
        return len(q)

    def get_active_jobs(self, queue: str | None = None) -> list[JobInfo]:
        """Get all currently active (running) jobs.

        Args:
            queue: Optional queue filter.

        Returns:
            List of active jobs.
        """
        jobs = []
        queue_names = [queue] if queue else list(self._queues.keys()) or [self.config.default_queue]

        for qname in queue_names:
            q = self._get_queue(qname)
            for job_id in q.started_job_registry.get_job_ids():
                try:
                    job = Job.fetch(job_id, connection=self._redis)
                    jobs.append(self._job_to_info(job))
                except Exception:
                    pass

        return jobs

    def get_failed_jobs(self, queue: str | None = None) -> list[JobInfo]:
        """Get all failed jobs.

        Args:
            queue: Optional queue filter.

        Returns:
            List of failed jobs.
        """
        jobs = []
        queue_names = [queue] if queue else list(self._queues.keys()) or [self.config.default_queue]

        for qname in queue_names:
            q = self._get_queue(qname)
            for job_id in q.failed_job_registry.get_job_ids():
                try:
                    job = Job.fetch(job_id, connection=self._redis)
                    jobs.append(self._job_to_info(job))
                except Exception:
                    pass

        return jobs

    def clear_queue(self, queue: str = "default") -> int:
        """Clear all jobs from a queue.

        Args:
            queue: Queue name to clear.

        Returns:
            Number of jobs removed.
        """
        q = self._get_queue(queue)
        count = len(q)
        q.empty()
        return count

    def retry_job(self, job_id: str) -> bool:
        """Retry a failed job.

        Args:
            job_id: ID of the job to retry.

        Returns:
            True if retry was scheduled.
        """
        try:
            job = Job.fetch(job_id, connection=self._redis)
            job.requeue()
            return True
        except Exception:
            return False

    def health_check(self) -> bool:
        """Check if the queue service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            return self._redis.ping()
        except Exception:
            return False

    def get_workers(self) -> list[dict[str, Any]]:
        """Get information about active workers.

        Returns:
            List of worker information dictionaries.
        """
        from rq import Worker

        workers = []
        for worker in Worker.all(connection=self._redis):
            workers.append(
                {
                    "name": worker.name,
                    "queues": [q.name for q in worker.queues],
                    "state": worker.get_state(),
                    "current_job": worker.get_current_job_id(),
                }
            )
        return workers

    def get_job_ids(self, queue: str = "default") -> list[str]:
        """Get all job IDs in a queue.

        Args:
            queue: Queue name.

        Returns:
            List of job IDs.
        """
        q = self._get_queue(queue)
        return q.job_ids
