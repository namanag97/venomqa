"""Celery Queue adapter for job queue testing.

Celery is a distributed task queue that supports real-time processing
and scheduling. This adapter provides inspection and control capabilities.

Installation:
    pip install celery redis

Example:
    >>> from venomqa.adapters import CeleryQueueAdapter
    >>> adapter = CeleryQueueAdapter(broker_url="redis://localhost:6379/0")
    >>> job_id = adapter.enqueue("myapp.tasks.process", arg1, arg2)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from venomqa.ports.queue import JobInfo, JobResult, JobStatus, QueuePort

try:
    from celery import Celery
    from celery.app.control import Inspect
    from celery.result import AsyncResult

    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    Celery = None
    AsyncResult = None


@dataclass
class CeleryQueueConfig:
    """Configuration for Celery Queue adapter."""

    broker_url: str = "redis://localhost:6379/0"
    result_backend: str = "redis://localhost:6379/1"
    default_queue: str = "celery"
    timeout: float = 30.0


class CeleryQueueAdapter(QueuePort):
    """Adapter for Celery task queue.

    This adapter provides integration with Celery for task queue
    management and inspection in test environments.

    Attributes:
        config: Configuration for the Celery connection.

    Example:
        >>> adapter = CeleryQueueAdapter(broker_url="redis://localhost:6379/0")
        >>> job_id = adapter.enqueue("myapp.tasks.send_email", to="user@test.com")
        >>> result = adapter.get_job_result(job_id)
    """

    def __init__(
        self,
        broker_url: str = "redis://localhost:6379/0",
        result_backend: str = "redis://localhost:6379/1",
        default_queue: str = "celery",
    ) -> None:
        """Initialize the Celery Queue adapter.

        Args:
            broker_url: Celery broker URL.
            result_backend: Celery result backend URL.
            default_queue: Default queue name.

        Raises:
            ImportError: If celery is not installed.
        """
        if not CELERY_AVAILABLE:
            raise ImportError("celery is required. Install with: pip install celery")

        self.config = CeleryQueueConfig(
            broker_url=broker_url,
            result_backend=result_backend,
            default_queue=default_queue,
        )
        self._app = Celery(
            "venomqa_celery_adapter",
            broker=broker_url,
            backend=result_backend,
        )
        self._app.conf.update(
            task_track_started=True,
            task_send_sent_event=True,
        )

    def _map_status(self, state: str) -> JobStatus:
        """Map Celery task state to JobStatus enum."""
        status_map = {
            "PENDING": JobStatus.PENDING,
            "STARTED": JobStatus.RUNNING,
            "SUCCESS": JobStatus.COMPLETED,
            "FAILURE": JobStatus.FAILED,
            "RETRY": JobStatus.RETRY,
            "REVOKED": JobStatus.CANCELLED,
            "RECEIVED": JobStatus.PENDING,
        }
        return status_map.get(state, JobStatus.PENDING)

    def _result_to_info(self, result: AsyncResult) -> JobInfo:
        """Convert an AsyncResult to JobInfo."""
        state = result.state
        info = result.info if result.info else {}

        if isinstance(info, dict):
            args = info.get("args", ())
            kwargs = info.get("kwargs", {})
        else:
            args = ()
            kwargs = {}

        return JobInfo(
            id=result.id,
            name=result.name or "",
            queue=self.config.default_queue,
            status=self._map_status(state),
            args=tuple(args) if isinstance(args, (list, tuple)) else (),
            kwargs=kwargs if isinstance(kwargs, dict) else {},
            error=str(info) if state == "FAILURE" and info else None,
        )

    def enqueue(
        self,
        func: Callable[..., Any] | str,
        *args: Any,
        queue: str = "celery",
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
        if isinstance(func, str):
            result = self._app.send_task(
                func,
                args=args,
                kwargs=kwargs,
                queue=queue,
            )
        else:
            result = self._app.send_task(
                func.__name__,
                args=args,
                kwargs=kwargs,
                queue=queue,
            )
        return result.id

    def get_job(self, job_id: str) -> JobInfo | None:
        """Get information about a job.

        Args:
            job_id: ID of the job.

        Returns:
            Job information or None if not found.
        """
        try:
            result = AsyncResult(job_id, app=self._app)
            if result.state == "PENDING" and result.result is None:
                return None
            return self._result_to_info(result)
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
            result = AsyncResult(job_id, app=self._app)
            value = result.get(timeout=timeout)
            return JobResult(
                job_id=job_id,
                success=True,
                result=value,
            )
        except Exception as e:
            if "timeout" in str(e).lower():
                return None
            return JobResult(
                job_id=job_id,
                success=False,
                error=str(e),
            )

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or running job.

        Args:
            job_id: ID of the job to cancel.

        Returns:
            True if cancelled, False if not possible.
        """
        try:
            self._app.control.revoke(job_id, terminate=True)
            return True
        except Exception:
            return False

    def get_queue_length(self, queue: str = "celery") -> int:
        """Get the number of jobs in a queue.

        Args:
            queue: Queue name.

        Returns:
            Number of pending jobs.
        """
        try:
            inspect = Inspect(app=self._app)
            stats = inspect.stats()
            if stats:
                for worker_stat in stats.values():
                    queues = worker_stat.get("queues", {})
                    if queue in queues:
                        return queues[queue].get("length", 0)
            return 0
        except Exception:
            return 0

    def get_active_jobs(self, queue: str | None = None) -> list[JobInfo]:
        """Get all currently active (running) jobs.

        Args:
            queue: Optional queue filter.

        Returns:
            List of active jobs.
        """
        jobs = []
        try:
            inspect = Inspect(app=self._app)
            active = inspect.active()
            if active:
                for worker_tasks in active.values():
                    for task in worker_tasks:
                        if queue and task.get("delivery_info", {}).get("routing_key") != queue:
                            continue
                        jobs.append(
                            JobInfo(
                                id=task["id"],
                                name=task["name"],
                                queue=task.get("delivery_info", {}).get("routing_key", ""),
                                status=JobStatus.RUNNING,
                                args=tuple(task.get("args", [])),
                                kwargs=task.get("kwargs", {}),
                            )
                        )
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
        try:
            inspect = Inspect(app=self._app)
            reserved = inspect.reserved()
            if reserved:
                for worker_tasks in reserved.values():
                    for task in worker_tasks:
                        result = AsyncResult(task["id"], app=self._app)
                        if result.state == "FAILURE":
                            jobs.append(self._result_to_info(result))
        except Exception:
            pass
        return jobs

    def clear_queue(self, queue: str = "celery") -> int:
        """Clear all jobs from a queue.

        Note: This purges all messages from the queue.

        Args:
            queue: Queue name to clear.

        Returns:
            Number of jobs removed (estimate).
        """
        try:
            return self._app.control.purge()
        except Exception:
            return 0

    def retry_job(self, job_id: str) -> bool:
        """Retry a failed job.

        Args:
            job_id: ID of the job to retry.

        Returns:
            True if retry was scheduled.
        """
        try:
            result = AsyncResult(job_id, app=self._app)
            if result.state == "FAILURE":
                result.backend.retry(job_id)
                return True
            return False
        except Exception:
            return False

    def health_check(self) -> bool:
        """Check if the queue service is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            inspect = Inspect(app=self._app)
            stats = inspect.stats()
            return stats is not None
        except Exception:
            return False

    def get_workers(self) -> list[dict[str, Any]]:
        """Get information about active workers.

        Returns:
            List of worker information dictionaries.
        """
        workers = []
        try:
            inspect = Inspect(app=self._app)
            stats = inspect.stats()
            if stats:
                for worker_name, worker_stat in stats.items():
                    workers.append(
                        {
                            "name": worker_name,
                            "pool": worker_stat.get("pool", {}),
                            "queues": list(worker_stat.get("queues", {}).keys()),
                        }
                    )
        except Exception:
            pass
        return workers

    def apply_async(
        self,
        task_name: str,
        args: tuple = (),
        kwargs: dict | None = None,
        queue: str | None = None,
        countdown: float | None = None,
        eta: datetime | None = None,
        expires: float | datetime | None = None,
    ) -> str:
        """Apply a task asynchronously with advanced options.

        Args:
            task_name: Name of the task.
            args: Positional arguments.
            kwargs: Keyword arguments.
            queue: Queue to send to.
            countdown: Seconds to wait before executing.
            eta: Scheduled execution time.
            expires: Expiration time or seconds.

        Returns:
            Task ID.
        """
        result = self._app.send_task(
            task_name,
            args=args,
            kwargs=kwargs or {},
            queue=queue,
            countdown=countdown,
            eta=eta,
            expires=expires,
        )
        return result.id

    def get_registered_tasks(self) -> list[str]:
        """Get list of registered task names.

        Returns:
            List of task names.
        """
        try:
            inspect = Inspect(app=self._app)
            registered = inspect.registered()
            tasks = set()
            if registered:
                for worker_tasks in registered.values():
                    tasks.update(worker_tasks)
            return sorted(tasks)
        except Exception:
            return []
