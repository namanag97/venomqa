"""Tests for caching and connection pooling performance in VenomQA."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import MockClient, MockHTTPResponse, MockStateManager
from venomqa.core.context import ExecutionContext
from venomqa.core.models import Journey, Step
from venomqa.http import Client
from venomqa.runner import JourneyRunner


class TestConnectionPooling:
    """Tests for HTTP connection pooling behavior."""

    def test_client_reuses_connection(self) -> None:
        with patch("venomqa.http.rest.httpx.Client") as mock_httpx_client:
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
        with patch("venomqa.http.rest.httpx.Client") as mock_httpx_client:
            mock_instance = MagicMock()
            mock_httpx_client.return_value = mock_instance

            client = Client(base_url="http://localhost:8000")
            client.connect()
            client.disconnect()

            mock_instance.close.assert_called_once()

    def test_lazy_connection_on_first_request(self) -> None:
        with patch("venomqa.http.rest.httpx.Client") as mock_httpx_client:
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
        from venomqa.http import Client

        with patch("venomqa.http.rest.httpx.Client") as mock_httpx_client:
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
        from venomqa.http import Client

        with patch("venomqa.http.rest.httpx.Client") as mock_httpx_client:
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
        from venomqa.http import Client

        with patch("venomqa.http.rest.httpx.Client") as mock_httpx_client:
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
        for _i in range(10000):
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
            Step(name=f"step_{i}", action=lambda c, ctx: c.get("/endpoint")) for i in range(100)
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


class TestConnectionPool:
    """Tests for the generic ConnectionPool."""

    def test_pool_creates_min_connections(self) -> None:
        from venomqa.performance.pool import ConnectionPool

        created_count = 0

        def factory():
            nonlocal created_count
            created_count += 1
            return object()

        pool = ConnectionPool(factory=factory, max_size=5, min_size=2)
        assert created_count == 2
        pool.close()

    def test_pool_acquires_and_releases(self) -> None:
        from venomqa.performance.pool import ConnectionPool

        pool = ConnectionPool(factory=lambda: object(), max_size=2, min_size=1)

        with pool.acquire() as conn:
            assert conn is not None
            stats = pool.get_stats()
            assert stats.active_connections == 1

        stats = pool.get_stats()
        assert stats.active_connections == 0
        pool.close()

    def test_pool_max_size_limit(self) -> None:
        from venomqa.performance.pool import ConnectionPool

        pool = ConnectionPool(factory=lambda: object(), max_size=2, min_size=1)

        with pool.acquire(timeout=1.0):
            with pool.acquire(timeout=1.0):
                stats = pool.get_stats()
                assert stats.total_connections == 2

        pool.close()

    def test_pool_stats_tracking(self) -> None:
        from venomqa.performance.pool import ConnectionPool

        pool = ConnectionPool(factory=lambda: {"id": id(object())}, max_size=5, min_size=1)

        with pool.acquire():
            pass

        with pool.acquire():
            pass

        stats = pool.get_stats()
        assert stats.checkout_count == 2
        assert stats.checkin_count == 2
        pool.close()

    def test_pool_validation_query(self) -> None:
        from venomqa.performance.pool import ConnectionPool

        class MockConnection:
            is_alive = True

        def validate(conn):
            return conn.is_alive

        pool = ConnectionPool(
            factory=lambda: MockConnection(),
            max_size=2,
            validation_query=validate,
        )

        with pool.acquire() as conn:
            assert conn.is_alive

        pool.close()

    def test_pool_context_manager(self) -> None:
        from venomqa.performance.pool import ConnectionPool

        with ConnectionPool(factory=lambda: object(), max_size=2) as pool:
            with pool.acquire() as conn:
                assert conn is not None

        stats = pool.get_stats()
        assert stats.total_connections == 0

    def test_pool_health_check(self) -> None:
        from venomqa.performance.pool import ConnectionPool

        pool = ConnectionPool(factory=lambda: object(), max_size=5, min_size=2)
        health = pool.health_check()
        assert health["healthy"] is True
        assert health["closed"] is False
        pool.close()


class TestResponseCache:
    """Tests for the ResponseCache."""

    def test_cache_set_and_get(self) -> None:
        from venomqa.performance.cache import ResponseCache

        cache = ResponseCache(max_size=100, default_ttl=60.0)
        cache.set("key1", {"data": "value1"})

        result = cache.get("key1")
        assert result == {"data": "value1"}

    def test_cache_miss_returns_none(self) -> None:
        from venomqa.performance.cache import ResponseCache

        cache = ResponseCache()
        result = cache.get("nonexistent")
        assert result is None

    def test_cache_lru_eviction(self) -> None:
        from venomqa.performance.cache import ResponseCache

        cache = ResponseCache(max_size=3, default_ttl=300.0)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")

        assert cache.get("key1") is None
        assert cache.get("key2") is not None
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None

    def test_cache_compute_key(self) -> None:
        from venomqa.performance.cache import ResponseCache

        cache = ResponseCache()

        key1 = cache.compute_key("GET", "https://api.example.com/users")
        key2 = cache.compute_key("GET", "https://api.example.com/users")
        key3 = cache.compute_key("POST", "https://api.example.com/users")

        assert key1 == key2
        assert key1 != key3
        assert len(key1) == 64

    def test_cache_headers_normalized(self) -> None:
        from venomqa.performance.cache import ResponseCache

        cache = ResponseCache()

        key1 = cache.compute_key(
            "GET", "/api", headers={"Authorization": "Bearer token", "Accept": "application/json"}
        )
        key2 = cache.compute_key(
            "GET",
            "/api",
            headers={"Authorization": "Different token", "Accept": "application/json"},
        )
        key3 = cache.compute_key("GET", "/api", headers={"accept": "application/json"})

        assert key1 == key2
        assert key1 == key3

    def test_cache_stats(self) -> None:
        from venomqa.performance.cache import ResponseCache

        cache = ResponseCache()

        cache.set("key1", "value1")
        cache.get("key1")
        cache.get("key1")
        cache.get("nonexistent")

        stats = cache.get_stats()
        assert stats.hits == 2
        assert stats.misses == 1
        assert stats.sets == 1
        assert stats.hit_rate == 2 / 3

    def test_cache_get_or_set(self) -> None:
        from venomqa.performance.cache import ResponseCache

        cache = ResponseCache()
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return {"data": "computed"}

        result1 = cache.get_or_set("key1", factory)
        result2 = cache.get_or_set("key1", factory)

        assert result1 == result2
        assert call_count == 1

    def test_cache_cleanup_expired(self) -> None:
        from venomqa.performance.cache import ResponseCache

        cache = ResponseCache(default_ttl=0.01)

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        time.sleep(0.05)

        removed = cache.cleanup_expired()
        assert removed == 2


class TestBatchExecutor:
    """Tests for the BatchExecutor."""

    def test_batch_executor_basic(self, mock_client: MockClient) -> None:
        from venomqa.performance.batch import BatchExecutor
        from venomqa.runner import JourneyRunner

        steps = [Step(name=f"step_{i}", action=lambda c, ctx: c.get(f"/api/{i}")) for i in range(3)]
        journey = Journey(name="test_batch", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 3)

        executor = BatchExecutor(max_concurrent=2)
        result = executor.execute([journey], lambda: JourneyRunner(client=mock_client))

        assert result.total == 1
        assert result.passed == 1

    def test_batch_executor_progress_callback(self, mock_client: MockClient) -> None:
        from venomqa.performance.batch import BatchExecutor, BatchProgress
        from venomqa.runner import JourneyRunner

        progress_updates: list[BatchProgress] = []

        def on_progress(p: BatchProgress) -> None:
            progress_updates.append(p)

        steps = [Step(name="step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="progress_test", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})])

        executor = BatchExecutor(max_concurrent=1, progress_callback=on_progress)
        executor.execute([journey], lambda: JourneyRunner(client=mock_client))

        assert len(progress_updates) >= 1

    def test_batch_aggregate_results(self, mock_client: MockClient) -> None:
        from venomqa.performance.batch import aggregate_results
        from venomqa.runner import JourneyRunner

        steps = [Step(name="step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="test", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 3)

        runner = JourneyRunner(client=mock_client)
        results = [runner.run(journey) for _ in range(3)]

        summary = aggregate_results(results)
        assert summary["total_journeys"] == 3
        assert summary["passed"] == 3

    def test_batch_result_properties(self) -> None:
        from datetime import datetime

        from venomqa.core.models import JourneyResult, StepResult
        from venomqa.performance.batch import BatchResult

        now = datetime.now()
        results = [
            JourneyResult(
                journey_name="j1",
                success=True,
                started_at=now,
                finished_at=now,
                step_results=[
                    StepResult(
                        step_name="s1",
                        success=True,
                        started_at=now,
                        finished_at=now,
                        duration_ms=20.0,
                    ),
                    StepResult(
                        step_name="s2",
                        success=True,
                        started_at=now,
                        finished_at=now,
                        duration_ms=30.0,
                    ),
                ],
                issues=[],
                duration_ms=100.0,
            ),
            JourneyResult(
                journey_name="j2",
                success=True,
                started_at=now,
                finished_at=now,
                step_results=[
                    StepResult(
                        step_name="s1",
                        success=True,
                        started_at=now,
                        finished_at=now,
                        duration_ms=50.0,
                    ),
                ],
                issues=[],
                duration_ms=200.0,
            ),
        ]

        batch_result = BatchResult(
            total=2,
            passed=2,
            failed=0,
            duration_ms=300.0,
            journey_results=results,
            started_at=datetime.now(),
            finished_at=datetime.now(),
        )

        assert batch_result.avg_journey_duration_ms == 150.0
        assert batch_result.min_journey_duration_ms == 100.0
        assert batch_result.max_journey_duration_ms == 200.0
        assert batch_result.success_rate == 100.0


class TestLoadTester:
    """Tests for the LoadTester."""

    def test_load_test_config_validation(self) -> None:
        from venomqa.performance.load_tester import LoadTestConfig

        with pytest.raises(ValueError):
            LoadTestConfig(duration_seconds=0)

        with pytest.raises(ValueError):
            LoadTestConfig(concurrent_users=0)

        config = LoadTestConfig(duration_seconds=10, concurrent_users=5)
        assert config.duration_seconds == 10
        assert config.concurrent_users == 5

    def test_load_test_quick_execution(self, mock_client: MockClient) -> None:
        from venomqa.performance.load_tester import LoadTestConfig, LoadTester
        from venomqa.runner import JourneyRunner

        steps = [Step(name="step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="load_test", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 50)

        config = LoadTestConfig(
            duration_seconds=1.0,
            concurrent_users=2,
            ramp_up_seconds=0.0,
        )
        tester = LoadTester(config)
        result = tester.run(journey, lambda: JourneyRunner(client=mock_client))

        assert result.duration_seconds >= 1.0
        assert result.metrics["total_requests"] > 0
        assert "p50" in result.percentiles
        assert "p99" in result.percentiles

    def test_load_test_result_summary(self, mock_client: MockClient) -> None:
        from venomqa.performance.load_tester import LoadTestConfig, LoadTester
        from venomqa.runner import JourneyRunner

        steps = [Step(name="step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="summary_test", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 20)

        config = LoadTestConfig(duration_seconds=0.5, concurrent_users=2)
        tester = LoadTester(config)
        result = tester.run(journey, lambda: JourneyRunner(client=mock_client))

        summary = result.get_summary()
        # Summary format may have variations, check for key content
        assert "SUMMARY" in summary.upper() or "Summary" in summary
        assert "Duration" in summary or "duration" in summary.lower()

    def test_benchmark_journey(self, mock_client: MockClient) -> None:
        from venomqa.performance.load_tester import benchmark_journey
        from venomqa.runner import JourneyRunner

        steps = [Step(name="step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="benchmark", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 50)

        result = benchmark_journey(
            journey,
            lambda: JourneyRunner(client=mock_client),
            iterations=10,
            warmup_iterations=2,
        )

        assert result["iterations"] == 10
        assert "avg_time_ms" in result
        assert "p50_ms" in result
        assert "p99_ms" in result

    def test_run_quick_load_test(self, mock_client: MockClient) -> None:
        from venomqa.performance.load_tester import run_quick_load_test
        from venomqa.runner import JourneyRunner

        steps = [Step(name="step", action=lambda c, ctx: c.get("/api"))]
        journey = Journey(name="quick_test", steps=steps)

        mock_client.set_responses([MockHTTPResponse(status_code=200, json_data={})] * 30)

        result = run_quick_load_test(
            journey,
            lambda: JourneyRunner(client=mock_client),
            duration_seconds=0.5,
            concurrent_users=2,
        )

        assert result.duration_seconds >= 0.5


class TestCachedResponse:
    """Tests for CachedResponse."""

    def test_cached_response_json(self) -> None:
        from venomqa.performance.cache import CachedResponse

        response = CachedResponse(
            status_code=200,
            headers={"Content-Type": "application/json"},
            body={"id": 1, "name": "test"},
        )

        data = response.json()
        assert data["id"] == 1

    def test_cached_response_text(self) -> None:
        from venomqa.performance.cache import CachedResponse

        response = CachedResponse(
            status_code=200,
            headers={},
            body="plain text",
        )

        assert response.text == "plain text"

    def test_cached_response_age(self) -> None:
        from venomqa.performance.cache import CachedResponse

        response = CachedResponse(
            status_code=200,
            headers={},
            body={},
        )

        time.sleep(0.1)
        assert response.age_seconds >= 0.1
