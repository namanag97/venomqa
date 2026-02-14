"""Stress tests for concurrent execution in VenomQA."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from unittest.mock import MagicMock

import pytest

from venomqa.core.context import ExecutionContext
from venomqa.core.models import (
    Branch,
    Checkpoint,
    Journey,
    JourneyResult,
    Path,
    Step,
)
from venomqa.runner import JourneyRunner
from tests.conftest import MockClient, MockHTTPResponse, MockStateManager


class TestConcurrentJourneyExecution:
    """Tests for concurrent journey execution."""

    def test_concurrent_journey_runs(self) -> None:
        results: list[JourneyResult] = []
        errors: list[Exception] = []
        lock = Lock()

        def run_journey(journey_id: int) -> None:
            try:
                mock_client = MockClient()
                mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 5)

                journey = Journey(
                    name=f"concurrent_journey_{journey_id}",
                    steps=[
                        Step(name=f"step_{i}", action=lambda c, ctx: c.get(f"/endpoint/{i}"))
                        for i in range(5)
                    ],
                )

                runner = JourneyRunner(client=mock_client)
                result = runner.run(journey)

                with lock:
                    results.append(result)
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(run_journey, i) for i in range(10)]
            for future in as_completed(futures):
                future.result()

        assert len(errors) == 0
        assert len(results) == 10
        for result in results:
            assert result.success is True

    def test_concurrent_step_execution_with_shared_client(self) -> None:
        mock_client = MockClient()
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 50)

        errors: list[Exception] = []
        execution_count = 0
        lock = Lock()

        def execute_step(step_id: int) -> None:
            nonlocal execution_count
            try:
                mock_client.get(f"/step/{step_id}")
                with lock:
                    execution_count += 1
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(execute_step, i) for i in range(50)]
            for future in as_completed(futures):
                future.result()

        assert len(errors) == 0
        assert execution_count == 50
        assert len(mock_client.history) == 50


class TestConcurrentContextAccess:
    """Tests for concurrent context access."""

    def test_concurrent_context_read_write(self) -> None:
        ctx = ExecutionContext()
        errors: list[Exception] = []
        lock = Lock()

        def writer(writer_id: int) -> None:
            try:
                for i in range(100):
                    ctx.set(f"writer_{writer_id}_key_{i}", f"value_{i}")
            except Exception as e:
                with lock:
                    errors.append(e)

        def reader(reader_id: int) -> None:
            try:
                for i in range(100):
                    ctx.get(f"writer_{reader_id % 5}_key_{i}")
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            writer_futures = [executor.submit(writer, i) for i in range(5)]
            reader_futures = [executor.submit(reader, i) for i in range(5)]

            for future in as_completed(writer_futures + reader_futures):
                future.result()

        assert len(errors) == 0

    def test_concurrent_context_snapshot_restore(self) -> None:
        ctx = ExecutionContext()
        errors: list[Exception] = []
        lock = Lock()

        for i in range(100):
            ctx.set(f"initial_key_{i}", f"initial_value_{i}")

        initial_snapshot = ctx.snapshot()

        def modifier(modifier_id: int) -> None:
            try:
                ctx.set(f"modifier_{modifier_id}", f"modified_{modifier_id}")
                snapshot = ctx.snapshot()
                ctx.restore(initial_snapshot)
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(modifier, i) for i in range(20)]
            for future in as_completed(futures):
                future.result()

        assert len(errors) == 0


class TestConcurrentBranchExecution:
    """Tests for concurrent branch path execution."""

    def test_parallel_branch_paths(self) -> None:
        mock_client = MockClient()
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 20)

        checkpoint = Checkpoint(name="initial")
        branch = Branch(
            checkpoint_name="initial",
            paths=[
                Path(
                    name=f"path_{i}",
                    steps=[
                        Step(name=f"step_{j}", action=lambda c, ctx: c.get(f"/path/{i}/step/{j}"))
                        for j in range(5)
                    ],
                )
                for i in range(4)
            ],
        )

        journey = Journey(name="parallel_branches", steps=[checkpoint, branch])

        runner = JourneyRunner(client=mock_client, parallel_paths=4)
        result = runner.run(journey)

        assert result.success is True
        assert result.total_paths == 4
        assert result.passed_paths == 4

    def test_high_concurrency_branches(self) -> None:
        mock_client = MockClient()
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 100)

        checkpoint = Checkpoint(name="start")
        branch = Branch(
            checkpoint_name="start",
            paths=[
                Path(
                    name=f"path_{i}",
                    steps=[Step(name="single", action=lambda c, ctx: c.get("/"))],
                )
                for i in range(50)
            ],
        )

        journey = Journey(name="high_concurrency", steps=[checkpoint, branch])

        runner = JourneyRunner(client=mock_client, parallel_paths=10)
        result = runner.run(journey)

        assert result.success is True
        assert result.total_paths == 50


class TestConcurrentStateManager:
    """Tests for concurrent state manager operations."""

    def test_concurrent_checkpoints(self) -> None:
        state_manager = MockStateManager()
        state_manager.connect()

        errors: list[Exception] = []
        lock = Lock()

        def create_checkpoint(cp_id: int) -> None:
            try:
                state_manager.checkpoint(f"checkpoint_{cp_id}")
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_checkpoint, i) for i in range(100)]
            for future in as_completed(futures):
                future.result()

        assert len(errors) == 0
        assert len(state_manager._checkpoints) == 100

    def test_concurrent_rollback_release(self) -> None:
        state_manager = MockStateManager()
        state_manager.connect()

        for i in range(50):
            state_manager.checkpoint(f"cp_{i}")

        errors: list[Exception] = []
        lock = Lock()

        def rollback_release(cp_id: int) -> None:
            try:
                state_manager.rollback(f"cp_{cp_id}")
                state_manager.release(f"cp_{cp_id}")
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(rollback_release, i) for i in range(50)]
            for future in as_completed(futures):
                future.result()

        assert len(errors) == 0


class TestLoadTesting:
    """Load testing scenarios."""

    def test_high_volume_requests(self) -> None:
        mock_client = MockClient()
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 1000)

        start_time = time.perf_counter()

        for i in range(1000):
            mock_client.get(f"/endpoint/{i}")

        elapsed = time.perf_counter() - start_time

        assert len(mock_client.history) == 1000
        assert elapsed < 5.0

    def test_high_volume_steps_in_journey(self) -> None:
        mock_client = MockClient()
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 200)

        steps = [
            Step(name=f"step_{i}", action=lambda c, ctx: c.get(f"/api/{i}")) for i in range(200)
        ]

        journey = Journey(name="high_volume", steps=steps)

        runner = JourneyRunner(client=mock_client)

        start_time = time.perf_counter()
        result = runner.run(journey)
        elapsed = time.perf_counter() - start_time

        assert result.success is True
        assert result.total_steps == 200
        assert elapsed < 10.0

    def test_many_journeys_sequentially(self) -> None:
        results = []

        for i in range(50):
            mock_client = MockClient()
            mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 10)

            journey = Journey(
                name=f"journey_{i}",
                steps=[Step(name=f"step_{j}", action=lambda c, ctx: c.get("/")) for j in range(10)],
            )

            runner = JourneyRunner(client=mock_client)
            result = runner.run(journey)
            results.append(result)

        assert len(results) == 50
        assert all(r.success for r in results)


class TestRaceConditions:
    """Tests for race condition detection."""

    def test_history_modification_race(self) -> None:
        mock_client = MockClient()
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 100)

        errors: list[Exception] = []
        lock = Lock()

        def modify_history() -> None:
            try:
                for i in range(50):
                    mock_client.get(f"/test/{i}")
            except Exception as e:
                with lock:
                    errors.append(e)

        def clear_history() -> None:
            try:
                time.sleep(0.01)
                mock_client.clear_history()
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(modify_history) for _ in range(5)]
            futures.extend([executor.submit(clear_history) for _ in range(2)])

            for future in as_completed(futures):
                future.result()

        assert len(errors) == 0

    def test_context_clear_race(self) -> None:
        ctx = ExecutionContext()
        errors: list[Exception] = []
        lock = Lock()

        for i in range(100):
            ctx.set(f"key_{i}", f"value_{i}")

        def read_context() -> None:
            try:
                for i in range(50):
                    ctx.get(f"key_{i}")
            except Exception as e:
                with lock:
                    errors.append(e)

        def clear_context() -> None:
            try:
                time.sleep(0.01)
                ctx.clear()
            except Exception as e:
                with lock:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_context) for _ in range(5)]
            futures.extend([executor.submit(clear_context) for _ in range(2)])

            for future in as_completed(futures):
                future.result()

        assert len(errors) == 0


class TestResourceCleanup:
    """Tests for resource cleanup under load."""

    def test_client_disconnect_under_load(self) -> None:
        from venomqa.client import Client
        from unittest.mock import patch

        with patch("venomqa.http.rest.httpx.Client") as mock_httpx:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.is_server_error = False
            mock_response.headers = {}
            mock_response.json.return_value = {}
            mock_instance.request.return_value = mock_response
            mock_httpx.return_value = mock_instance

            clients = []
            for _ in range(100):
                client = Client(base_url="http://localhost:8000")
                client.connect()
                client.get("/test")
                clients.append(client)

            for client in clients:
                client.disconnect()

            assert mock_instance.close.call_count == 100

    def test_state_manager_reset_under_load(self) -> None:
        state_managers = []

        for _ in range(50):
            sm = MockStateManager()
            sm.connect()
            for i in range(10):
                sm.checkpoint(f"cp_{i}")
            state_managers.append(sm)

        for sm in state_managers:
            sm.reset()

        for sm in state_managers:
            assert len(sm._checkpoints) == 0
