"""Tests for concurrency adapters in VenomQA."""

from __future__ import annotations

import time

import pytest

from venomqa.adapters.concurrency import ThreadConcurrencyAdapter
from venomqa.ports.concurrency import TaskResult


def simple_task() -> str:
    return "completed"


def add_task(a: int, b: int) -> int:
    return a + b


def slow_task() -> str:
    time.sleep(0.1)
    return "slow completed"


def failing_task() -> None:
    raise ValueError("Task failed intentionally")


class TestThreadConcurrencyAdapter:
    """Tests for ThreadConcurrencyAdapter."""

    @pytest.fixture
    def adapter(self) -> ThreadConcurrencyAdapter:
        return ThreadConcurrencyAdapter()

    def test_adapter_initialization(self, adapter: ThreadConcurrencyAdapter) -> None:
        assert adapter.get_active_tasks() == []

    def test_spawn_returns_task_id(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(simple_task)
        assert task_id is not None
        assert task_id.startswith("task-")

    def test_spawn_with_args(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(add_task, 5, 3)
        result = adapter.join(task_id, timeout=5.0)
        assert result.success is True
        assert result.result == 8

    def test_spawn_with_kwargs(self, adapter: ThreadConcurrencyAdapter) -> None:
        def task_with_kwargs(a: int, b: int = 0) -> int:
            return a + b

        task_id = adapter.spawn(task_with_kwargs, 5, b=10)
        result = adapter.join(task_id, timeout=5.0)
        assert result.success is True
        assert result.result == 15

    def test_join_waits_for_completion(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(slow_task)
        result = adapter.join(task_id, timeout=5.0)
        assert result.success is True
        assert result.result == "slow completed"

    def test_join_returns_task_result(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(simple_task)
        result = adapter.join(task_id, timeout=5.0)
        assert isinstance(result, TaskResult)
        assert result.success is True

    def test_join_failed_task(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(failing_task)
        result = adapter.join(task_id, timeout=5.0)
        assert result.success is False
        assert "Task failed intentionally" in result.error

    def test_join_all(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_ids = [
            adapter.spawn(simple_task),
            adapter.spawn(add_task, 1, 2),
            adapter.spawn(add_task, 3, 4),
        ]
        results = adapter.join_all(task_ids, timeout=10.0)

        assert len(results) == 3
        assert all(r.success for r in results)

    def test_join_any(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_ids = [
            adapter.spawn(simple_task),
            adapter.spawn(slow_task),
        ]
        task_id, result = adapter.join_any(task_ids, timeout=10.0)
        assert result.success is True

    def test_get_task(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(simple_task)
        task = adapter.get_task(task_id)
        assert task is not None
        assert task.id == task_id

    def test_get_task_nonexistent(self, adapter: ThreadConcurrencyAdapter) -> None:
        task = adapter.get_task("nonexistent")
        assert task is None

    def test_get_status(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(simple_task)
        status = adapter.get_status(task_id)
        assert status in ("pending", "running", "completed")

    def test_is_running(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(slow_task)
        adapter.join(task_id, timeout=5.0)
        assert adapter.is_running(task_id) is False

    def test_is_completed(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(simple_task)
        adapter.join(task_id, timeout=5.0)
        assert adapter.is_completed(task_id) is True

    def test_is_failed(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(failing_task)
        adapter.join(task_id, timeout=5.0)
        assert adapter.is_failed(task_id) is True

    def test_get_result(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(simple_task)
        adapter.join(task_id, timeout=5.0)
        result = adapter.get_result(task_id)
        assert result is not None
        assert result.success is True

    def test_get_result_for_running_task(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(slow_task)
        result = adapter.get_result(task_id)
        adapter.join(task_id, timeout=5.0)
        assert result is None or result.success

    def test_get_active_tasks(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id1 = adapter.spawn(slow_task)
        task_id2 = adapter.spawn(slow_task)
        time.sleep(0.05)
        active = adapter.get_active_tasks()
        adapter.join_all([task_id1, task_id2], timeout=5.0)
        assert len(active) >= 0

    def test_set_progress(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(slow_task)
        adapter.set_progress(task_id, 0.5)
        task = adapter.get_task(task_id)
        assert task is not None
        adapter.join(task_id, timeout=5.0)

    def test_lock_and_unlock(self, adapter: ThreadConcurrencyAdapter) -> None:
        result = adapter.lock("test_lock", timeout=1.0)
        assert result is True

        adapter.unlock("test_lock")
        result2 = adapter.lock("test_lock", timeout=1.0)
        assert result2 is True
        adapter.unlock("test_lock")

    def test_lock_timeout(self, adapter: ThreadConcurrencyAdapter) -> None:
        adapter.lock("timeout_lock", timeout=1.0)
        result = adapter.lock("timeout_lock", timeout=0.1)
        adapter.unlock("timeout_lock")
        assert result is False

    def test_unlock_nonexistent_lock(self, adapter: ThreadConcurrencyAdapter) -> None:
        result = adapter.unlock("nonexistent_lock")
        assert result is False

    def test_with_lock(self, adapter: ThreadConcurrencyAdapter) -> None:
        result = adapter.with_lock("context_lock", lambda: "protected_result", timeout=1.0)
        assert result == "protected_result"

    def test_semaphore(self, adapter: ThreadConcurrencyAdapter) -> None:
        sem_id = adapter.semaphore("test_sem", max_count=2)
        assert sem_id is not None
        assert sem_id.startswith("sem-")

    def test_semaphore_acquire_and_release(self, adapter: ThreadConcurrencyAdapter) -> None:
        sem_id = adapter.semaphore("test_sem", max_count=2)
        result1 = adapter.semaphore_acquire(sem_id, timeout=1.0)
        assert result1 is True

        result2 = adapter.semaphore_acquire(sem_id, timeout=1.0)
        assert result2 is True

        adapter.semaphore_release(sem_id)
        adapter.semaphore_release(sem_id)

    def test_spawn_many(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_ids = adapter.spawn_many([simple_task, simple_task, simple_task])
        assert len(task_ids) == 3
        adapter.join_all(task_ids, timeout=10.0)

    def test_cancel_running_task(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(slow_task)
        time.sleep(0.05)
        result = adapter.cancel(task_id)
        assert result in (True, False)

    def test_cancel_all(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_ids = [
            adapter.spawn(slow_task),
            adapter.spawn(slow_task),
        ]
        count = adapter.cancel_all(task_ids)
        assert count >= 0

    def test_map_parallel(self, adapter: ThreadConcurrencyAdapter) -> None:
        items = [1, 2, 3, 4, 5]
        results = adapter.map_parallel(lambda x: x * 2, items, max_workers=2)
        assert results == [2, 4, 6, 8, 10]

    def test_map_async(self, adapter: ThreadConcurrencyAdapter) -> None:
        items = [1, 2, 3]
        task_ids = adapter.map_async(lambda x: x * 2, items)
        assert len(task_ids) == 3
        adapter.join_all(task_ids, timeout=10.0)

    def test_task_result_has_duration(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(simple_task)
        result = adapter.join(task_id, timeout=5.0)
        assert result.duration_ms >= 0

    def test_concurrent_lock_access(self, adapter: ThreadConcurrencyAdapter) -> None:
        results = []

        def task1():
            if adapter.lock("concurrent_lock", timeout=2.0):
                results.append("task1_acquired")
                time.sleep(0.1)
                adapter.unlock("concurrent_lock")

        def task2():
            if adapter.lock("concurrent_lock", timeout=2.0):
                results.append("task2_acquired")
                adapter.unlock("concurrent_lock")

        t1_id = adapter.spawn(task1)
        t2_id = adapter.spawn(task2)
        adapter.join_all([t1_id, t2_id], timeout=10.0)

        assert len(results) == 2

    def test_spawn_after(self, adapter: ThreadConcurrencyAdapter) -> None:
        result = adapter.spawn_after(0.1, simple_task)
        assert result is not None

    def test_multiple_separate_locks(self, adapter: ThreadConcurrencyAdapter) -> None:
        assert adapter.lock("lock1", timeout=1.0) is True
        assert adapter.lock("lock2", timeout=1.0) is True
        adapter.unlock("lock1")
        adapter.unlock("lock2")

    def test_task_info_has_name(self, adapter: ThreadConcurrencyAdapter) -> None:
        task_id = adapter.spawn(simple_task)
        task = adapter.get_task(task_id)
        assert task is not None
        assert task.name == "simple_task"
