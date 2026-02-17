"""Tests for VenomQA benchmark and optimization modules."""

from __future__ import annotations

import json
import tempfile
import threading
import time
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from venomqa.core.models import Journey, Step
from venomqa.performance.benchmark import (
    BenchmarkConfig,
    Benchmarker,
    BenchmarkResult,
    BenchmarkSuite,
    IterationResult,
    compare_benchmarks,
    run_benchmark,
)
from venomqa.performance.optimizations import (
    CachedFixture,
    CompactStepResult,
    FixtureCache,
    LazyInitializer,
    OptimizedSerializer,
    ParallelExecutionResult,
    ParallelJourneyExecutor,
)


class TestBenchmarkConfig:
    """Tests for BenchmarkConfig."""

    def test_default_config(self) -> None:
        config = BenchmarkConfig()
        assert config.iterations == 100
        assert config.warmup_iterations == 10
        assert config.parallel_workers == 1

    def test_custom_config(self) -> None:
        config = BenchmarkConfig(
            iterations=50,
            warmup_iterations=5,
            track_memory=True,
        )
        assert config.iterations == 50
        assert config.warmup_iterations == 5
        assert config.track_memory is True

    def test_invalid_iterations(self) -> None:
        with pytest.raises(ValueError):
            BenchmarkConfig(iterations=0)

    def test_invalid_warmup(self) -> None:
        with pytest.raises(ValueError):
            BenchmarkConfig(warmup_iterations=-1)

    def test_invalid_workers(self) -> None:
        with pytest.raises(ValueError):
            BenchmarkConfig(parallel_workers=0)


class TestIterationResult:
    """Tests for IterationResult."""

    def test_create_result(self) -> None:
        result = IterationResult(
            iteration=0,
            duration_ms=45.5,
            success=True,
            steps_executed=5,
        )
        assert result.iteration == 0
        assert result.duration_ms == 45.5
        assert result.success is True
        assert result.steps_executed == 5

    def test_failed_result(self) -> None:
        result = IterationResult(
            iteration=1,
            duration_ms=10.0,
            success=False,
            error="Connection refused",
        )
        assert result.success is False
        assert result.error == "Connection refused"


class TestBenchmarkResult:
    """Tests for BenchmarkResult."""

    def test_empty_result(self) -> None:
        config = BenchmarkConfig(iterations=10)
        result = BenchmarkResult(
            config=config,
            journey_name="test",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            total_duration_ms=1000.0,
        )
        assert result.avg_duration_ms == 0.0
        assert result.min_duration_ms == 0.0
        assert result.max_duration_ms == 0.0
        assert result.success_rate == 0.0

    def test_result_statistics(self) -> None:
        config = BenchmarkConfig(iterations=5)
        iterations = [
            IterationResult(i, duration_ms=float(10 + i * 5), success=True, steps_executed=3)
            for i in range(5)
        ]
        # durations: 10, 15, 20, 25, 30

        result = BenchmarkResult(
            config=config,
            journey_name="test_stats",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            total_duration_ms=5000.0,
            iterations=iterations,
        )

        assert result.avg_duration_ms == 20.0
        assert result.min_duration_ms == 10.0
        assert result.max_duration_ms == 30.0
        assert result.success_rate == 100.0
        assert len(result.successful_iterations) == 5
        assert len(result.failed_iterations) == 0

    def test_result_with_failures(self) -> None:
        config = BenchmarkConfig(iterations=4)
        iterations = [
            IterationResult(0, duration_ms=10.0, success=True, steps_executed=3),
            IterationResult(1, duration_ms=15.0, success=False, error="Error"),
            IterationResult(2, duration_ms=20.0, success=True, steps_executed=3),
            IterationResult(3, duration_ms=25.0, success=False, error="Error"),
        ]

        result = BenchmarkResult(
            config=config,
            journey_name="test_failures",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            total_duration_ms=2000.0,
            iterations=iterations,
        )

        assert result.success_rate == 50.0
        assert len(result.successful_iterations) == 2
        assert len(result.failed_iterations) == 2
        # Only successful iterations count for duration stats
        assert result.avg_duration_ms == 15.0

    def test_percentiles(self) -> None:
        config = BenchmarkConfig(iterations=100)
        iterations = [
            IterationResult(i, duration_ms=float(i + 1), success=True)
            for i in range(100)
        ]

        result = BenchmarkResult(
            config=config,
            journey_name="test_percentiles",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            total_duration_ms=10000.0,
            iterations=iterations,
        )

        # Percentile calculation uses floor-based index, so p50 of [1..100] is 51
        assert 50.0 <= result.p50_ms <= 51.0
        assert 90.0 <= result.p90_ms <= 91.0
        assert 95.0 <= result.p95_ms <= 96.0
        assert 99.0 <= result.p99_ms <= 100.0

    def test_throughput_metrics(self) -> None:
        config = BenchmarkConfig(iterations=10)
        iterations = [
            IterationResult(i, duration_ms=100.0, success=True, steps_executed=5)
            for i in range(10)
        ]

        result = BenchmarkResult(
            config=config,
            journey_name="test_throughput",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            total_duration_ms=1000.0,
            iterations=iterations,
        )

        # 5 steps per iteration, 100ms per iteration = 50 steps/sec
        assert result.steps_per_second == 50.0
        # 100ms per journey = 600 journeys/minute
        assert result.journeys_per_minute == 600.0
        # 10 requests per second
        assert result.throughput_rps == 10.0

    def test_to_dict(self) -> None:
        config = BenchmarkConfig(iterations=5)
        iterations = [
            IterationResult(i, duration_ms=10.0, success=True)
            for i in range(5)
        ]

        result = BenchmarkResult(
            config=config,
            journey_name="test_dict",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            total_duration_ms=500.0,
            iterations=iterations,
        )

        d = result.to_dict()
        assert d["journey_name"] == "test_dict"
        assert "metrics" in d
        assert d["metrics"]["iterations_total"] == 5
        assert d["metrics"]["success_rate_pct"] == 100.0

    def test_get_summary(self) -> None:
        config = BenchmarkConfig(iterations=5)
        iterations = [
            IterationResult(i, duration_ms=10.0, success=True, steps_executed=3)
            for i in range(5)
        ]

        result = BenchmarkResult(
            config=config,
            journey_name="test_summary",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            total_duration_ms=500.0,
            iterations=iterations,
        )

        summary = result.get_summary()
        assert "test_summary" in summary
        assert "Latency" in summary
        assert "Throughput" in summary

    def test_csv_export(self) -> None:
        config = BenchmarkConfig(iterations=5)
        iterations = [
            IterationResult(i, duration_ms=10.0, success=True)
            for i in range(5)
        ]

        result = BenchmarkResult(
            config=config,
            journey_name="test_csv",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            total_duration_ms=500.0,
            iterations=iterations,
        )

        header = BenchmarkResult.csv_header()
        row = result.to_csv_row()

        assert "journey_name" in header
        assert "test_csv" in row


class TestBenchmarker:
    """Tests for Benchmarker."""

    def test_basic_benchmark(self) -> None:
        config = BenchmarkConfig(iterations=5, warmup_iterations=1)
        benchmarker = Benchmarker(config)

        # Create a simple journey
        steps = [
            Step(name="step1", action=lambda c, ctx: MagicMock(is_error=False))
        ]
        journey = Journey(name="benchmark_test", steps=steps)

        # Mock runner factory
        def runner_factory():
            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.total_steps = 1
            mock_runner.run.return_value = mock_result
            return mock_runner

        result = benchmarker.run(journey, runner_factory)

        assert result.journey_name == "benchmark_test"
        assert len(result.iterations) == 5
        assert result.warmup_iterations == 1

    def test_benchmark_with_failures(self) -> None:
        config = BenchmarkConfig(iterations=3, warmup_iterations=0)
        benchmarker = Benchmarker(config)

        steps = [Step(name="step1", action=lambda c, ctx: None)]
        journey = Journey(name="failure_test", steps=steps)

        call_count = 0

        def runner_factory():
            nonlocal call_count
            call_count += 1
            mock_runner = MagicMock()
            mock_result = MagicMock()
            # Alternate success/failure
            mock_result.success = call_count % 2 == 1
            mock_result.total_steps = 1
            mock_runner.run.return_value = mock_result
            return mock_runner

        result = benchmarker.run(journey, runner_factory)

        assert len(result.successful_iterations) > 0
        assert len(result.failed_iterations) > 0

    def test_benchmark_stop(self) -> None:
        config = BenchmarkConfig(iterations=100, warmup_iterations=0)
        benchmarker = Benchmarker(config)

        steps = [Step(name="step1", action=lambda c, ctx: None)]
        journey = Journey(name="stop_test", steps=steps)

        iteration_count = 0

        def runner_factory():
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 5:
                benchmarker.stop()
            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.total_steps = 1
            mock_runner.run.return_value = mock_result
            return mock_runner

        result = benchmarker.run(journey, runner_factory)

        # Should have stopped early
        assert len(result.iterations) < 100


class TestBenchmarkSuite:
    """Tests for BenchmarkSuite."""

    def test_suite_multiple_journeys(self) -> None:
        config = BenchmarkConfig(iterations=3, warmup_iterations=1)
        suite = BenchmarkSuite(config)

        journey1 = Journey(name="journey1", steps=[
            Step(name="s1", action=lambda c, ctx: None)
        ])
        journey2 = Journey(name="journey2", steps=[
            Step(name="s2", action=lambda c, ctx: None)
        ])

        def runner_factory():
            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.total_steps = 1
            mock_runner.run.return_value = mock_result
            return mock_runner

        suite.add(journey1, runner_factory)
        suite.add(journey2, runner_factory)

        results = suite.run_all()

        assert len(results) == 2
        assert results[0].journey_name == "journey1"
        assert results[1].journey_name == "journey2"

    def test_suite_comparison(self) -> None:
        config = BenchmarkConfig(iterations=3, warmup_iterations=0)
        suite = BenchmarkSuite(config)

        # Create journeys with different simulated durations
        journey1 = Journey(name="fast_journey", steps=[
            Step(name="s1", action=lambda c, ctx: None)
        ])
        journey2 = Journey(name="slow_journey", steps=[
            Step(name="s2", action=lambda c, ctx: None)
        ])

        fast_duration = 10.0
        slow_duration = 100.0

        def fast_factory():
            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.total_steps = 1
            time.sleep(fast_duration / 1000)  # Simulate fast execution
            mock_runner.run.return_value = mock_result
            return mock_runner

        def slow_factory():
            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.total_steps = 1
            time.sleep(slow_duration / 1000)  # Simulate slow execution
            mock_runner.run.return_value = mock_result
            return mock_runner

        suite.add(journey1, fast_factory)
        suite.add(journey2, slow_factory)

        suite.run_all()
        comparison = suite.get_comparison()

        assert comparison["count"] == 2
        assert comparison["fastest"] == "fast_journey"
        assert comparison["slowest"] == "slow_journey"

    def test_suite_export_json(self) -> None:
        config = BenchmarkConfig(iterations=2, warmup_iterations=0)
        suite = BenchmarkSuite(config)

        journey = Journey(name="export_test", steps=[
            Step(name="s1", action=lambda c, ctx: None)
        ])

        def runner_factory():
            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.total_steps = 1
            mock_runner.run.return_value = mock_result
            return mock_runner

        suite.add(journey, runner_factory)
        suite.run_all()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            suite.export_json(f.name)

            with open(f.name) as rf:
                data = json.load(rf)

            assert "results" in data
            assert len(data["results"]) == 1


class TestCompareBenchmarks:
    """Tests for compare_benchmarks function."""

    def test_compare_empty(self) -> None:
        comparison = compare_benchmarks([])
        assert "error" in comparison

    def test_compare_results(self) -> None:
        config = BenchmarkConfig(iterations=5)

        result1 = BenchmarkResult(
            config=config,
            journey_name="fast",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            total_duration_ms=100.0,
            iterations=[
                IterationResult(i, duration_ms=10.0, success=True)
                for i in range(5)
            ],
        )

        result2 = BenchmarkResult(
            config=config,
            journey_name="slow",
            started_at=datetime.now(),
            finished_at=datetime.now(),
            total_duration_ms=500.0,
            iterations=[
                IterationResult(i, duration_ms=50.0, success=True)
                for i in range(5)
            ],
        )

        comparison = compare_benchmarks([result1, result2])

        assert comparison["count"] == 2
        assert comparison["fastest"] == "fast"
        assert comparison["slowest"] == "slow"


class TestRunBenchmark:
    """Tests for run_benchmark convenience function."""

    def test_run_benchmark(self) -> None:
        journey = Journey(name="quick_bench", steps=[
            Step(name="s1", action=lambda c, ctx: None)
        ])

        def runner_factory():
            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.total_steps = 1
            mock_runner.run.return_value = mock_result
            return mock_runner

        result = run_benchmark(journey, runner_factory, iterations=5, warmup=1)

        assert result.journey_name == "quick_bench"
        assert len(result.iterations) == 5


# =============================================================================
# Optimization Tests
# =============================================================================


class TestFixtureCache:
    """Tests for FixtureCache."""

    def test_basic_caching(self) -> None:
        cache = FixtureCache(max_size=100)

        call_count = 0

        def create_user():
            nonlocal call_count
            call_count += 1
            return {"id": 1, "name": "test"}

        # First call should create
        user1 = cache.get_or_create("test_user", create_user)
        assert call_count == 1
        assert user1["id"] == 1

        # Second call should return cached
        user2 = cache.get_or_create("test_user", create_user)
        assert call_count == 1  # No additional call
        assert user2 is user1  # Same object

    def test_cache_invalidation(self) -> None:
        cache = FixtureCache()

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        cache.invalidate("key1")
        assert cache.get("key1") is None

    def test_cache_ttl_expiration(self) -> None:
        cache = FixtureCache(default_ttl=0.05)  # 50ms TTL

        cache.set("short_lived", "value")
        assert cache.get("short_lived") == "value"

        time.sleep(0.1)  # Wait for expiration

        assert cache.get("short_lived") is None

    def test_lru_eviction(self) -> None:
        cache = FixtureCache(max_size=3)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # Should evict key1

        assert cache.get("key1") is None
        assert cache.get("key2") is not None
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None

    def test_cache_stats(self) -> None:
        cache = FixtureCache()

        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 2 / 3

    def test_thread_safety(self) -> None:
        cache = FixtureCache()
        call_count = 0
        lock = threading.Lock()

        def expensive_create():
            nonlocal call_count
            with lock:
                call_count += 1
            time.sleep(0.01)  # Simulate work
            return {"created": True}

        def worker():
            for _ in range(10):
                cache.get_or_create("shared_key", expensive_create)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should only create once due to locking
        assert call_count == 1


class TestCachedFixture:
    """Tests for CachedFixture."""

    def test_fixture_expiration(self) -> None:
        fixture = CachedFixture(
            name="test",
            value="data",
            ttl_seconds=0.05,
        )

        assert not fixture.is_expired()
        time.sleep(0.1)
        assert fixture.is_expired()

    def test_fixture_age(self) -> None:
        fixture = CachedFixture(
            name="test",
            value="data",
        )

        time.sleep(0.05)
        assert fixture.age_seconds >= 0.05


class TestParallelJourneyExecutor:
    """Tests for ParallelJourneyExecutor."""

    def test_parallel_execution(self) -> None:
        executor = ParallelJourneyExecutor(max_workers=2)

        journeys = [
            Journey(name=f"journey_{i}", steps=[
                Step(name="s1", action=lambda c, ctx: None)
            ])
            for i in range(4)
        ]

        def runner_factory():
            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.journey_name = "test"
            mock_result.duration_ms = 10.0
            mock_result.step_results = []
            mock_result.issues = []
            mock_runner.run.return_value = mock_result
            return mock_runner

        result = executor.run(journeys, runner_factory)

        assert result.total_journeys == 4
        assert result.passed == 4
        assert result.failed == 0
        assert result.success_rate == 100.0

    def test_parallel_fail_fast(self) -> None:
        executor = ParallelJourneyExecutor(max_workers=2, fail_fast=True)

        journeys = [
            Journey(name=f"journey_{i}", steps=[
                Step(name="s1", action=lambda c, ctx: None)
            ])
            for i in range(10)
        ]

        call_count = 0

        def runner_factory():
            nonlocal call_count
            call_count += 1
            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.success = call_count > 2  # First 2 fail
            mock_result.journey_name = "test"
            mock_result.duration_ms = 10.0
            mock_result.step_results = []
            mock_result.issues = []
            mock_runner.run.return_value = mock_result
            return mock_runner

        result = executor.run(journeys, runner_factory)

        # Should stop early due to fail_fast
        assert result.failed > 0

    def test_parallel_stop(self) -> None:
        executor = ParallelJourneyExecutor(max_workers=2)

        journeys = [
            Journey(name=f"journey_{i}", steps=[
                Step(name="s1", action=lambda c, ctx: None)
            ])
            for i in range(100)
        ]

        count = 0

        def runner_factory():
            nonlocal count
            count += 1
            if count >= 5:
                executor.stop()
            mock_runner = MagicMock()
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.journey_name = "test"
            mock_result.step_results = []
            mock_result.issues = []
            mock_runner.run.return_value = mock_result
            return mock_runner

        result = executor.run(journeys, runner_factory)

        # Should have stopped before completing all 100
        assert result.total_journeys == 100
        assert len(result.journey_results) < 100


class TestOptimizedSerializer:
    """Tests for OptimizedSerializer."""

    def test_basic_serialization(self) -> None:
        serializer = OptimizedSerializer()

        data = {"key": "value", "number": 42}
        json_str = serializer.dumps(data)
        parsed = serializer.loads(json_str)

        assert parsed == data

    def test_compact_output(self) -> None:
        # Disable caching to test actual serialization difference
        serializer = OptimizedSerializer(enable_caching=False)

        # Use larger data to see difference between compact and pretty
        data = {"key": "value", "items": [1, 2, 3], "nested": {"a": 1, "b": 2}}
        compact = serializer.dumps(data, pretty=False)
        pretty = serializer.dumps(data, pretty=True)

        # Pretty format has indentation and newlines, so should be longer
        assert len(compact) < len(pretty)
        assert "\n" in pretty  # Pretty should have newlines
        assert "\n" not in compact  # Compact should not

    def test_caching(self) -> None:
        serializer = OptimizedSerializer(enable_caching=True)

        data = "simple_string"

        # First call
        result1 = serializer.dumps(data)
        # Second call should use cache
        result2 = serializer.dumps(data)

        assert result1 == result2


class TestCompactStepResult:
    """Tests for CompactStepResult."""

    def test_from_full_result(self) -> None:
        full_result = MagicMock()
        full_result.step_name = "test_step"
        full_result.success = True
        full_result.duration_ms = 45.5
        full_result.error = None
        full_result.response = {"status_code": 200}

        compact = CompactStepResult.from_full_result(full_result)

        assert compact.step_name == "test_step"
        assert compact.success is True
        assert compact.duration_ms == 45.5
        assert compact.status_code == 200
        assert compact.error_hash is None

    def test_with_error(self) -> None:
        full_result = MagicMock()
        full_result.step_name = "failed_step"
        full_result.success = False
        full_result.duration_ms = 10.0
        full_result.error = "Connection timeout"
        full_result.response = None

        compact = CompactStepResult.from_full_result(full_result)

        assert compact.success is False
        assert compact.error_hash is not None
        assert len(compact.error_hash) == 8


class TestLazyInitializer:
    """Tests for LazyInitializer."""

    def test_lazy_initialization(self) -> None:
        call_count = 0

        def create_resource():
            nonlocal call_count
            call_count += 1
            return {"id": 1}

        lazy = LazyInitializer(create_resource)

        assert not lazy.is_initialized
        assert call_count == 0

        value = lazy.get()

        assert lazy.is_initialized
        assert call_count == 1
        assert value["id"] == 1

        # Second get should not call factory
        value2 = lazy.get()
        assert call_count == 1
        assert value2 is value

    def test_reset(self) -> None:
        call_count = 0

        def create_resource():
            nonlocal call_count
            call_count += 1
            return {"count": call_count}

        lazy = LazyInitializer(create_resource)

        value1 = lazy.get()
        assert value1["count"] == 1

        lazy.reset()
        assert not lazy.is_initialized

        value2 = lazy.get()
        assert value2["count"] == 2

    def test_thread_safety(self) -> None:
        call_count = 0
        lock = threading.Lock()

        def expensive_create():
            nonlocal call_count
            with lock:
                call_count += 1
            time.sleep(0.01)
            return {"created": True}

        lazy = LazyInitializer(expensive_create)

        def worker():
            for _ in range(10):
                lazy.get()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should only create once
        assert call_count == 1


class TestParallelExecutionResult:
    """Tests for ParallelExecutionResult."""

    def test_success_rate(self) -> None:
        result = ParallelExecutionResult(
            total_journeys=10,
            passed=8,
            failed=2,
            duration_ms=1000.0,
            journey_results=[],
        )

        assert result.success_rate == 80.0

    def test_empty_result(self) -> None:
        result = ParallelExecutionResult(
            total_journeys=0,
            passed=0,
            failed=0,
            duration_ms=0.0,
            journey_results=[],
        )

        assert result.success_rate == 0.0
