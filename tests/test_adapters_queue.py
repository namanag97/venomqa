"""Tests for queue adapters in VenomQA."""

from __future__ import annotations

from datetime import datetime

import pytest

from venomqa.ports.queue import JobInfo, JobResult, JobStatus
from venomqa.adapters.queue import MockQueueAdapter


def sample_task(x: int, y: int) -> int:
    return x + y


def failing_task() -> None:
    raise ValueError("Task failed")


class TestMockQueueAdapter:
    """Tests for MockQueueAdapter."""

    @pytest.fixture
    def adapter(self) -> MockQueueAdapter:
        return MockQueueAdapter()

    def test_adapter_initialization(self, adapter: MockQueueAdapter) -> None:
        assert adapter.health_check() is True
        assert adapter.get_queue_length() == 0

    def test_enqueue_returns_job_id(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(sample_task, 1, 2)
        assert job_id is not None
        assert job_id.startswith("job-")

    def test_enqueue_creates_pending_job(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(sample_task, 1, 2)
        job = adapter.get_job(job_id)

        assert job is not None
        assert job.status == JobStatus.PENDING
        assert job.args == (1, 2)

    def test_enqueue_with_named_queue(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(sample_task, 1, 2, queue="priority")
        job = adapter.get_job(job_id)

        assert job is not None
        assert job.queue == "priority"

    def test_enqueue_with_kwargs(self, adapter: MockQueueAdapter) -> None:
        def task_with_kwargs(a: int, b: int = 0) -> int:
            return a + b

        job_id = adapter.enqueue(task_with_kwargs, 5, b=10)
        job = adapter.get_job(job_id)

        assert job is not None
        assert job.kwargs == {"b": 10}

    def test_get_job_returns_none_for_nonexistent(self, adapter: MockQueueAdapter) -> None:
        result = adapter.get_job("nonexistent-job-id")
        assert result is None

    def test_get_queue_length_counts_pending_jobs(self, adapter: MockQueueAdapter) -> None:
        adapter.enqueue(sample_task, 1, 2)
        adapter.enqueue(sample_task, 3, 4)
        adapter.enqueue(sample_task, 5, 6, queue="other")

        assert adapter.get_queue_length() == 2
        assert adapter.get_queue_length("other") == 1

    def test_get_queue_length_excludes_completed_jobs(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(sample_task, 1, 2)
        adapter.complete_job(job_id, success=True)

        assert adapter.get_queue_length() == 0

    def test_cancel_pending_job(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(sample_task, 1, 2)
        result = adapter.cancel_job(job_id)

        assert result is True
        job = adapter.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.CANCELLED

    def test_cancel_running_job(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(sample_task, 1, 2)
        adapter.start_job(job_id)
        result = adapter.cancel_job(job_id)

        assert result is True

    def test_cancel_nonexistent_job(self, adapter: MockQueueAdapter) -> None:
        result = adapter.cancel_job("nonexistent")
        assert result is False

    def test_complete_job_success(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(sample_task, 1, 2)
        adapter.complete_job(job_id, result=42, success=True)

        job = adapter.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED
        assert job.completed_at is not None

        result = adapter.get_job_result(job_id)
        assert result is not None
        assert result.success is True
        assert result.result == 42

    def test_complete_job_failure(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(failing_task)
        adapter.complete_job(job_id, success=False)

        job = adapter.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.FAILED

    def test_start_job(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(sample_task, 1, 2)
        adapter.start_job(job_id)

        job = adapter.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.RUNNING
        assert job.started_at is not None

    def test_get_active_jobs(self, adapter: MockQueueAdapter) -> None:
        job_id1 = adapter.enqueue(sample_task, 1, 2)
        job_id2 = adapter.enqueue(sample_task, 3, 4)
        adapter.enqueue(sample_task, 5, 6)

        adapter.start_job(job_id1)
        adapter.start_job(job_id2)

        active = adapter.get_active_jobs()
        assert len(active) == 2

    def test_get_active_jobs_filter_by_queue(self, adapter: MockQueueAdapter) -> None:
        job_id1 = adapter.enqueue(sample_task, 1, 2, queue="default")
        job_id2 = adapter.enqueue(sample_task, 3, 4, queue="priority")

        adapter.start_job(job_id1)
        adapter.start_job(job_id2)

        active_default = adapter.get_active_jobs(queue="default")
        assert len(active_default) == 1

    def test_get_failed_jobs(self, adapter: MockQueueAdapter) -> None:
        job_id1 = adapter.enqueue(sample_task, 1, 2)
        job_id2 = adapter.enqueue(sample_task, 3, 4)

        adapter.complete_job(job_id1, success=True)
        adapter.complete_job(job_id2, success=False)

        failed = adapter.get_failed_jobs()
        assert len(failed) == 1
        assert failed[0].id == job_id2

    def test_clear_queue(self, adapter: MockQueueAdapter) -> None:
        adapter.enqueue(sample_task, 1, 2)
        adapter.enqueue(sample_task, 3, 4)
        adapter.enqueue(sample_task, 5, 6, queue="other")

        count = adapter.clear_queue()
        assert count == 2
        assert adapter.get_queue_length() == 0
        assert adapter.get_queue_length("other") == 1

    def test_retry_failed_job(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(sample_task, 1, 2)
        adapter.complete_job(job_id, success=False)

        result = adapter.retry_job(job_id)
        assert result is True

        job = adapter.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.PENDING
        assert job.retries == 1

    def test_retry_non_failed_job(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(sample_task, 1, 2)
        result = adapter.retry_job(job_id)
        assert result is False

    def test_get_job_result_for_nonexistent(self, adapter: MockQueueAdapter) -> None:
        result = adapter.get_job_result("nonexistent")
        assert result is None

    def test_health_check_returns_true_by_default(self, adapter: MockQueueAdapter) -> None:
        assert adapter.health_check() is True

    def test_set_healthy_changes_status(self, adapter: MockQueueAdapter) -> None:
        adapter.set_healthy(False)
        assert adapter.health_check() is False

    def test_job_info_has_created_at(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(sample_task, 1, 2)
        job = adapter.get_job(job_id)

        assert job is not None
        assert job.created_at is not None
        assert isinstance(job.created_at, datetime)

    def test_enqueue_with_string_task_name(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue("process_order", order_id=123)
        job = adapter.get_job(job_id)

        assert job is not None
        assert job.name == "process_order"

    def test_multiple_queues_isolated(self, adapter: MockQueueAdapter) -> None:
        adapter.enqueue(sample_task, 1, 2, queue="queue1")
        adapter.enqueue(sample_task, 3, 4, queue="queue2")

        assert adapter.get_queue_length("queue1") == 1
        assert adapter.get_queue_length("queue2") == 1

        adapter.clear_queue("queue1")
        assert adapter.get_queue_length("queue1") == 0
        assert adapter.get_queue_length("queue2") == 1

    def test_job_result_duration(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(sample_task, 1, 2)
        adapter.start_job(job_id)
        adapter.complete_job(job_id, result=3, success=True)

        result = adapter.get_job_result(job_id)
        assert result is not None
        assert result.duration >= 0

    def test_enqueue_same_queue_multiple_times(self, adapter: MockQueueAdapter) -> None:
        for i in range(10):
            adapter.enqueue(sample_task, i, i + 1)

        assert adapter.get_queue_length() == 10

    def test_job_max_retries_default(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(sample_task, 1, 2)
        job = adapter.get_job(job_id)

        assert job is not None
        assert job.max_retries == 3

    def test_complete_job_with_error_message(self, adapter: MockQueueAdapter) -> None:
        job_id = adapter.enqueue(failing_task)
        adapter.complete_job(job_id, success=False)

        result = adapter.get_job_result(job_id)
        assert result is not None
        assert result.success is False
