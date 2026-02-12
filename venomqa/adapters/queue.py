"""Mock Queue adapter for testing.

This adapter provides an in-memory job queue mock for testing purposes.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from venomqa.ports.queue import JobInfo, JobResult, JobStatus, QueuePort


@dataclass
class MockJob:
    """Internal job representation."""

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
    """In-memory mock queue adapter for testing."""

    def __init__(self, max_retries: int = 3) -> None:
        self._jobs: dict[str, MockJob] = {}
        self._queues: dict[str, list[str]] = {"default": []}
        self._max_retries = max_retries

    def _generate_id(self) -> str:
        return f"job-{uuid.uuid4().hex[:8]}"

    def enqueue(
        self,
        func: Callable[..., Any] | str,
        *args: Any,
        queue: str = "default",
        **kwargs: Any,
    ) -> str:
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
            max_retries=self._max_retries,
        )

        self._jobs[job_id] = job
        self._queues[queue].append(job_id)
        return job_id

    def get_job(self, job_id: str) -> JobInfo | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
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

    def get_job_result(self, job_id: str, timeout: float = 30.0) -> JobResult | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None

        start = time.time()
        while time.time() - start < timeout:
            if job.status == JobStatus.COMPLETED:
                return JobResult(
                    job_id=job.id,
                    success=True,
                    result=job.result,
                )
            if job.status == JobStatus.FAILED:
                return JobResult(
                    job_id=job.id,
                    success=False,
                    error=job.error,
                )
            time.sleep(0.01)

        return None

    def process_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.func is None:
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

    def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.status in (JobStatus.PENDING, JobStatus.RETRY):
            job.status = JobStatus.CANCELLED
            return True
        return False

    def get_queue_length(self, queue: str = "default") -> int:
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
        jobs = []
        for job in self._jobs.values():
            if job.status == JobStatus.RUNNING:
                if queue is None or job.queue == queue:
                    jobs.append(
                        JobInfo(
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
                    )
        return jobs

    def get_failed_jobs(self, queue: str | None = None) -> list[JobInfo]:
        jobs = []
        for job in self._jobs.values():
            if job.status == JobStatus.FAILED:
                if queue is None or job.queue == queue:
                    jobs.append(
                        JobInfo(
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
                    )
        return jobs

    def clear_queue(self, queue: str = "default") -> int:
        if queue not in self._queues:
            return 0
        count = len(self._queues[queue])
        for job_id in self._queues[queue]:
            if job_id in self._jobs:
                del self._jobs[job_id]
        self._queues[queue] = []
        return count

    def retry_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.status == JobStatus.FAILED and job.retries < job.max_retries:
            job.status = JobStatus.RETRY
            job.retries += 1
            job.error = None
            return True
        return False

    def health_check(self) -> bool:
        return True
