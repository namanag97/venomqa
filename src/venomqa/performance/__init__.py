"""Performance optimization module for VenomQA.

This module provides performance-enhancing utilities including:

- **Connection Pooling**: Thread-safe pools for HTTP and database connections
- **Response Caching**: LRU cache with TTL for HTTP response reuse
- **Batch Execution**: Parallel journey execution with concurrency control
- **Load Testing**: Comprehensive load testing with configurable patterns
- **Benchmarking**: Detailed performance measurement with statistics

Quick Start:
    >>> from venomqa.performance import (
    ...     BatchExecutor,
    ...     ResponseCache,
    ...     ConnectionPool,
    ...     LoadTester,
    ...     LoadTestConfig,
    ...     Benchmarker,
    ...     BenchmarkConfig,
    ... )
    >>>
    >>> # Caching responses
    >>> cache = ResponseCache(max_size=1000, default_ttl=300.0)
    >>> key = cache.compute_key("GET", "https://api.example.com/users")
    >>> cache.set(key, {"users": []})
    >>>
    >>> # Batch execution
    >>> executor = BatchExecutor(max_concurrent=8, fail_fast=True)
    >>> result = executor.execute(journeys, runner_factory)
    >>>
    >>> # Load testing
    >>> config = LoadTestConfig(duration_seconds=60, concurrent_users=10)
    >>> tester = LoadTester(config)
    >>> load_result = tester.run(journey, runner_factory)
    >>>
    >>> # Benchmarking
    >>> bench_config = BenchmarkConfig(iterations=100, warmup_iterations=10)
    >>> benchmarker = Benchmarker(bench_config)
    >>> bench_result = benchmarker.run(journey, runner_factory)
    >>> print(bench_result.get_summary())

For more details, see the individual module documentation.
"""

from venomqa.performance.batch import (
    BatchExecutor,
    BatchProgress,
    BatchResult,
    ProgressCallback,
    RunnerFactory,
    aggregate_results,
    default_progress_callback,
)
from venomqa.performance.benchmark import (
    BenchmarkConfig,
    Benchmarker,
    BenchmarkMetric,
    BenchmarkResult,
    BenchmarkSuite,
    IterationResult,
    compare_benchmarks,
    run_benchmark,
)
from venomqa.performance.cache import (
    CachedResponse,
    CacheEntry,
    CacheStats,
    ResponseCache,
)
from venomqa.performance.load_tester import (
    LoadPattern,
    LoadTestAssertions,
    LoadTestConfig,
    LoadTester,
    LoadTestMetrics,
    LoadTestResult,
    RequestSample,
    TimeSeries,
    benchmark_journey,
    run_quick_load_test,
)
from venomqa.performance.optimizations import (
    CachedFixture,
    CompactStepResult,
    ConnectionReuseStrategy,
    FixtureCache,
    LazyInitializer,
    OptimizedSerializer,
    ParallelExecutionResult,
    ParallelJourneyExecutor,
    StreamingResultCollector,
)
from venomqa.performance.pool import (
    ConnectionPool,
    DBConnectionPool,
    HTTPConnectionPool,
    PooledConnection,
    PoolStats,
)

__all__ = [
    # Cache
    "ResponseCache",
    "CacheEntry",
    "CacheStats",
    "CachedResponse",
    # Connection Pool
    "ConnectionPool",
    "HTTPConnectionPool",
    "DBConnectionPool",
    "PoolStats",
    "PooledConnection",
    # Batch Execution
    "BatchExecutor",
    "BatchProgress",
    "BatchResult",
    "ProgressCallback",
    "RunnerFactory",
    "aggregate_results",
    "default_progress_callback",
    # Load Testing
    "LoadTester",
    "LoadTestConfig",
    "LoadTestResult",
    "LoadTestMetrics",
    "LoadTestAssertions",
    "LoadPattern",
    "RequestSample",
    "TimeSeries",
    "run_quick_load_test",
    "benchmark_journey",
    # Benchmarking
    "Benchmarker",
    "BenchmarkConfig",
    "BenchmarkResult",
    "BenchmarkMetric",
    "BenchmarkSuite",
    "IterationResult",
    "run_benchmark",
    "compare_benchmarks",
    # Optimizations
    "FixtureCache",
    "CachedFixture",
    "ParallelJourneyExecutor",
    "ParallelExecutionResult",
    "OptimizedSerializer",
    "CompactStepResult",
    "StreamingResultCollector",
    "ConnectionReuseStrategy",
    "LazyInitializer",
]
