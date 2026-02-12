"""Tests for caching and connection pooling performance in VenomQA."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

import pytest

from venomqa.client import Client, AsyncClient, RequestRecord
from venomqa.core.context import ExecutionContext
from venomqa.core.models import Journey, Step
from venomqa.errors import RetryExhaustedError
from venomqa.runner import JourneyRunner
from tests.conftest import MockClient, MockHTTPResponse, MockStateManager


class TestConnectionPooling:
    """Tests for HTTP connection pooling behavior."""

    def test_client_reuses_connection(self) -> None:
        with patch("venomqa.client.httpx.Client") as mock_httpx_client:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.is_server_error = False
            mock_response.headers = {}
            mock_response.json.return_value = {}
            mock_instance.request.return_value = mock_response
            mock_httpx_client.return_value = mock_instance

            client = Client(base_url="http://localhost:8000")
            client.connect()

            client.get("/users/1")
            client.get("/users/2")
            client.get("/users/3")

            mock_httpx_client.assert_called_once()

    def test_client_disconnect_closes_connection(self) -> None:
        with patch("venomqa.client.httpx.Client") as mock_httpx_client:
            mock_instance = MagicMock()
            mock_httpx_client.return_value = mock_instance

            client = Client(base_url="http://localhost:8000")
            client.connect()
            client.disconnect()

            mock_instance.close.assert_called_once()

    def test_lazy_connection_on_first_request(self) -> None:
        with patch("venomqa.client.httpx.Client") as mock_httpx_client:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.is_server_error = False
            mock_response.headers = {}
            mock_response.json.return_value = {}
            mock_instance.request.return_value = mock_response
            mock_httpx_client.return_value = mock_instance

            client = Client(base_url="http://localhost:8000")

            assert client._client is None

            client.get("/users")

            mock_httpx_client.assert_called_once()


class TestRetryMechanism:
    """Tests for retry mechanism performance."""

    def test_retry_on_server_error(self, mock_client: MockClient) -> None:
        from venomqa.client import Client

        with patch("venomqa.client.httpx.Client") as mock_httpx_client:
            mock_instance = MagicMock()
            mock_response_fail = MagicMock()
            mock_response_fail.status_code = 500
            mock_response_fail.is_server_error = True
            mock_response_fail.headers = {}

            mock_response_success = MagicMock()
            mock_response_success.status_code = 200
            mock_response_success.is_server_error = False
            mock_response_success.headers = {}
            mock_response_success.json.return_value = {}

            mock_instance.request.side_effect = [
                mock_response_fail,
                mock_response_fail,
                mock_response_success,
            ]
            mock_httpx_client.return_value = mock_instance

            client = Client(base_url="http://localhost:8000", retry_count=3, retry_delay=0.01)
            client.connect()

            response = client.get("/flaky")

            assert response.status_code == 200
            assert mock_instance.request.call_count == 3

    def test_retry_exhausted_returns_error_response(self) -> None:
        from venomqa.client import Client

        with patch("venomqa.client.httpx.Client") as mock_httpx_client:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.is_server_error = True
            mock_response.headers = {}
            mock_instance.request.return_value = mock_response
            mock_httpx_client.return_value = mock_instance

            client = Client(base_url="http://localhost:8000", retry_count=3, retry_delay=0.01)
            client.connect()

            response = client.get("/always-fails")

            assert response.status_code == 500
            assert mock_instance.request.call_count == 3

    def test_no_retry_on_client_error(self) -> None:
        from venomqa.client import Client

        with patch("venomqa.client.httpx.Client") as mock_httpx_client:
            mock_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.is_server_error = False
            mock_response.headers = {}
            mock_response.json.return_value = {"error": "Not found"}
            mock_instance.request.return_value = mock_response
            mock_httpx_client.return_value = mock_instance

            client = Client(base_url="http://localhost:8000", retry_count=3)
            client.connect()

            response = client.get("/not-found")

            assert response.status_code == 404
            assert mock_instance.request.call_count == 1


class TestHistoryPerformance:
    """Tests for request history performance."""

    def test_large_history_does_not_slow_down(self, mock_client: MockClient) -> None:
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 1000)

        start_time = time.perf_counter()
        for i in range(1000):
            mock_client.get(f"/users/{i}")
        elapsed = time.perf_counter() - start_time

        assert len(mock_client.history) == 1000
        assert elapsed < 1.0

    def test_clear_history_is_fast(self, mock_client: MockClient) -> None:
        for i in range(10000):
            mock_client.history.append(MagicMock())

        start_time = time.perf_counter()
        mock_client.clear_history()
        elapsed = time.perf_counter() - start_time

        assert len(mock_client.history) == 0
        assert elapsed < 0.1

    def test_get_history_returns_copy(self, mock_client: MockClient) -> None:
        mock_client.get("/users")

        history1 = mock_client.get_history()
        history2 = mock_client.get_history()

        assert history1 is not history2
        assert len(history1) == len(history2)


class TestContextPerformance:
    """Tests for execution context performance."""

    def test_context_snapshot_performance(self) -> None:
        ctx = ExecutionContext()
        for i in range(1000):
            ctx.set(f"key_{i}", f"value_{i}")

        start_time = time.perf_counter()
        for _ in range(100):
            ctx.snapshot()
        elapsed = time.perf_counter() - start_time

        assert elapsed < 0.5

    def test_context_restore_performance(self) -> None:
        ctx = ExecutionContext()
        for i in range(1000):
            ctx.set(f"key_{i}", f"value_{i}")

        snapshot = ctx.snapshot()

        start_time = time.perf_counter()
        for _ in range(100):
            ctx.restore(snapshot)
        elapsed = time.perf_counter() - start_time

        assert elapsed < 0.5

    def test_context_large_data_storage(self) -> None:
        ctx = ExecutionContext()
        large_data = {"data": list(range(10000))}

        start_time = time.perf_counter()
        ctx.set("large_key", large_data)
        retrieved = ctx.get("large_key")
        elapsed = time.perf_counter() - start_time

        assert retrieved == large_data
        assert elapsed < 0.1


class TestStepExecutionPerformance:
    """Tests for step execution performance."""

    def test_rapid_step_execution(self, mock_client: MockClient) -> None:
        steps = [
            Step(name=f"step_{i}", action=lambda c, ctx: c.get(f"/endpoint")) for i in range(100)
        ]

        journey = Journey(name="perf_test", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 100)

        runner = JourneyRunner(client=mock_client)

        start_time = time.perf_counter()
        result = runner.run(journey)
        elapsed = time.perf_counter() - start_time

        assert result.success is True
        assert result.total_steps == 100
        assert elapsed < 5.0

    def test_step_result_overhead(self, mock_client: MockClient) -> None:
        from datetime import datetime
        from venomqa.core.models import StepResult

        start_time = time.perf_counter()
        results = []
        for i in range(1000):
            results.append(
                StepResult(
                    step_name=f"step_{i}",
                    success=True,
                    started_at=datetime.now(),
                    finished_at=datetime.now(),
                    duration_ms=1.0,
                )
            )
        elapsed = time.perf_counter() - start_time

        assert len(results) == 1000
        assert elapsed < 1.0


class TestStateManagerPerformance:
    """Tests for state manager performance."""

    def test_checkpoint_creation_performance(self) -> None:
        state_manager = MockStateManager()
        state_manager.connect()

        start_time = time.perf_counter()
        for i in range(1000):
            state_manager.checkpoint(f"checkpoint_{i}")
        elapsed = time.perf_counter() - start_time

        assert len(state_manager._checkpoints) == 1000
        assert elapsed < 0.5

    def test_rollback_performance(self) -> None:
        state_manager = MockStateManager()
        state_manager.connect()

        for i in range(100):
            state_manager.checkpoint(f"cp_{i}")

        start_time = time.perf_counter()
        for i in range(100):
            state_manager.rollback(f"cp_{i}")
        elapsed = time.perf_counter() - start_time

        assert elapsed < 0.5

    def test_reset_clears_all_checkpoints(self) -> None:
        state_manager = MockStateManager()
        state_manager.connect()

        for i in range(1000):
            state_manager.checkpoint(f"cp_{i}")

        start_time = time.perf_counter()
        state_manager.reset()
        elapsed = time.perf_counter() - start_time

        assert len(state_manager._checkpoints) == 0
        assert elapsed < 0.1


class TestMemoryEfficiency:
    """Tests for memory efficiency."""

    def test_history_memory_cleanup(self, mock_client: MockClient) -> None:
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 1000)

        for i in range(1000):
            mock_client.get(f"/users/{i}")

        assert len(mock_client.history) == 1000

        mock_client.clear_history()

        assert len(mock_client.history) == 0

    def test_context_clear_frees_memory(self) -> None:
        ctx = ExecutionContext()

        for i in range(10000):
            ctx.set(f"key_{i}", f"value_{i}")

        assert len(ctx._data) == 10000

        ctx.clear()

        assert len(ctx._data) == 0
        assert len(ctx._step_results) == 0


class TestConcurrencyPerformance:
    """Tests for concurrency-related performance."""

    def test_concurrent_context_access(self) -> None:
        ctx = ExecutionContext()
        errors = []

        def worker(worker_id: int) -> None:
            try:
                for i in range(100):
                    ctx.set(f"worker_{worker_id}_key_{i}", i)
                    ctx.get(f"worker_{worker_id}_key_{i}")
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]
            for future in as_completed(futures):
                future.result()

        assert len(errors) == 0

    def test_concurrent_client_history(self, mock_client: MockClient) -> None:
        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 100)

        errors = []

        def worker() -> None:
            try:
                for i in range(10):
                    mock_client.get(f"/users/{i}")
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker) for _ in range(10)]
            for future in as_completed(futures):
                future.result()

        assert len(errors) == 0
        assert len(mock_client.history) == 100


class TestReportGenerationPerformance:
    """Tests for report generation performance."""

    def test_large_markdown_report_generation(self, mock_client: MockClient) -> None:
        from venomqa.reporters.markdown import MarkdownReporter

        steps = [Step(name=f"step_{i}", action=lambda c, ctx: c.get("/")) for i in range(50)]
        journey = Journey(name="large_journey", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 50)

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        reporter = MarkdownReporter()

        start_time = time.perf_counter()
        report = reporter.generate([result])
        elapsed = time.perf_counter() - start_time

        assert len(report) > 0
        assert elapsed < 1.0

    def test_large_json_report_generation(self, mock_client: MockClient) -> None:
        from venomqa.reporters.json_report import JSONReporter

        steps = [Step(name=f"step_{i}", action=lambda c, ctx: c.get("/")) for i in range(50)]
        journey = Journey(name="large_journey", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 50)

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        reporter = JSONReporter()

        start_time = time.perf_counter()
        report = reporter.generate([result])
        elapsed = time.perf_counter() - start_time

        assert len(report) > 0
        assert elapsed < 1.0

    def test_large_junit_report_generation(self, mock_client: MockClient) -> None:
        from venomqa.reporters.junit import JUnitReporter

        steps = [Step(name=f"step_{i}", action=lambda c, ctx: c.get("/")) for i in range(50)]
        journey = Journey(name="large_journey", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 50)

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        reporter = JUnitReporter()

        start_time = time.perf_counter()
        report = reporter.generate([result])
        elapsed = time.perf_counter() - start_time

        assert len(report) > 0
        assert elapsed < 1.0


class TestCachingBehavior:
    """Tests for caching behavior in the framework."""

    def test_step_result_caching_in_context(self, mock_client: MockClient) -> None:
        ctx = ExecutionContext()

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={"id": 1})])

        mock_client.get("/users/1")
        ctx.store_step_result("get_user", {"id": 1})

        result = ctx.get_step_result("get_user")
        assert result == {"id": 1}

        cached_result = ctx.get_step_result("get_user")
        assert cached_result is result

    def test_context_snapshot_caches_state(self) -> None:
        ctx = ExecutionContext()
        ctx.set("key1", "value1")

        snapshot1 = ctx.snapshot()
        ctx.set("key2", "value2")
        snapshot2 = ctx.snapshot()

        assert snapshot1 is not snapshot2
        assert "key2" not in snapshot1["data"]
        assert "key2" in snapshot2["data"]
