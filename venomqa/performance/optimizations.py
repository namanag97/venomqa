"""Performance optimizations for VenomQA test execution.

This module provides various performance optimizations including:
- Fixture result caching (avoid recreating fixtures)
- Parallel journey execution with thread isolation
- Optimized JSON serialization
- Connection reuse strategies
- Memory-efficient data structures

Example:
    >>> from venomqa.performance.optimizations import (
    ...     FixtureCache,
    ...     ParallelJourneyExecutor,
    ...     OptimizedSerializer,
    ... )
    >>>
    >>> # Cache fixture results
    >>> cache = FixtureCache()
    >>> result = cache.get_or_create("user_fixture", create_user)
    >>>
    >>> # Run journeys in parallel
    >>> executor = ParallelJourneyExecutor(max_workers=4)
    >>> results = executor.run(journeys, runner_factory)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# Fixture Caching
# =============================================================================


@dataclass
class CachedFixture(Generic[T]):
    """A cached fixture result with metadata.

    Attributes:
        name: Fixture name/key.
        value: The cached fixture value.
        created_at: When the fixture was created.
        ttl_seconds: Time-to-live in seconds (None = infinite).
        hits: Number of times this fixture was accessed.
        dependencies: List of fixture names this depends on.
    """

    name: str
    value: T
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float | None = None
    hits: int = 0
    dependencies: list[str] = field(default_factory=list)

    def is_expired(self) -> bool:
        """Check if fixture has expired."""
        if self.ttl_seconds is None:
            return False
        return time.time() > self.created_at + self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        """Get fixture age in seconds."""
        return time.time() - self.created_at


class FixtureCache:
    """Thread-safe cache for fixture results.

    Caches fixture creation results to avoid redundant setup operations.
    Supports TTL-based expiration, dependency tracking, and LRU eviction.

    Attributes:
        max_size: Maximum number of fixtures to cache.
        default_ttl: Default TTL for fixtures (None = infinite).

    Example:
        >>> cache = FixtureCache(max_size=100, default_ttl=300.0)
        >>>
        >>> def create_user():
        ...     return db.insert("users", {"name": "test"})
        >>>
        >>> # First call creates, subsequent calls return cached
        >>> user1 = cache.get_or_create("test_user", create_user)
        >>> user2 = cache.get_or_create("test_user", create_user)
        >>> assert user1 is user2  # Same object
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: float | None = None,
    ) -> None:
        """Initialize the fixture cache.

        Args:
            max_size: Maximum cached fixtures.
            default_ttl: Default TTL in seconds (None = no expiration).
        """
        if max_size <= 0:
            raise ValueError(f"max_size must be positive, got {max_size}")

        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CachedFixture[Any]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._creation_locks: dict[str, threading.Lock] = {}

    def get(self, name: str) -> Any | None:
        """Get a cached fixture by name.

        Args:
            name: Fixture name.

        Returns:
            Cached fixture value, or None if not found or expired.
        """
        with self._lock:
            if name not in self._cache:
                self._misses += 1
                return None

            fixture = self._cache[name]

            if fixture.is_expired():
                self._remove(name)
                self._misses += 1
                return None

            # Move to end for LRU
            self._cache.move_to_end(name)
            fixture.hits += 1
            self._hits += 1
            return fixture.value

    def get_or_create(
        self,
        name: str,
        factory: Callable[[], T],
        ttl: float | None = None,
        dependencies: list[str] | None = None,
    ) -> T:
        """Get a cached fixture or create it if missing.

        Thread-safe creation that prevents thundering herd.

        Args:
            name: Fixture name.
            factory: Callable to create the fixture if not cached.
            ttl: TTL for this fixture (overrides default).
            dependencies: Names of fixtures this depends on.

        Returns:
            The cached or newly created fixture value.
        """
        # First, quick check with shared lock
        with self._lock:
            if name in self._cache:
                fixture = self._cache[name]
                if not fixture.is_expired():
                    self._cache.move_to_end(name)
                    fixture.hits += 1
                    self._hits += 1
                    return fixture.value

            # Need to create - get or create a creation lock
            if name not in self._creation_locks:
                self._creation_locks[name] = threading.Lock()
            creation_lock = self._creation_locks[name]

        # Create with per-fixture lock to avoid thundering herd
        with creation_lock:
            # Double-check after acquiring lock
            with self._lock:
                if name in self._cache:
                    fixture = self._cache[name]
                    if not fixture.is_expired():
                        self._cache.move_to_end(name)
                        fixture.hits += 1
                        self._hits += 1
                        return fixture.value

            # Actually create
            value = factory()

            # Store
            self.set(name, value, ttl, dependencies)

            return value

    def set(
        self,
        name: str,
        value: T,
        ttl: float | None = None,
        dependencies: list[str] | None = None,
    ) -> None:
        """Store a fixture in the cache.

        Args:
            name: Fixture name.
            value: Fixture value.
            ttl: TTL for this fixture.
            dependencies: Names of fixtures this depends on.
        """
        effective_ttl = ttl if ttl is not None else self.default_ttl

        with self._lock:
            # Remove if exists
            if name in self._cache:
                self._remove(name)

            # Create entry
            fixture = CachedFixture(
                name=name,
                value=value,
                ttl_seconds=effective_ttl,
                dependencies=dependencies or [],
            )

            self._cache[name] = fixture
            self._evict_if_needed()

    def invalidate(self, name: str) -> bool:
        """Invalidate a specific fixture.

        Also invalidates any fixtures that depend on it.

        Args:
            name: Fixture name to invalidate.

        Returns:
            True if the fixture existed.
        """
        with self._lock:
            if name not in self._cache:
                return False

            # Find dependents and invalidate them first
            dependents = [
                n for n, f in self._cache.items()
                if name in f.dependencies
            ]
            for dep in dependents:
                self._remove(dep)

            self._remove(name)
            return True

    def invalidate_all(self) -> int:
        """Invalidate all cached fixtures.

        Returns:
            Number of fixtures invalidated.
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def cleanup_expired(self) -> int:
        """Remove all expired fixtures.

        Returns:
            Number of fixtures removed.
        """
        with self._lock:
            expired = [
                name for name, fixture in self._cache.items()
                if fixture.is_expired()
            ]
            for name in expired:
                self._remove(name)
            return len(expired)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with hit/miss counts and rates.
        """
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / total if total > 0 else 0.0,
            }

    def _remove(self, name: str) -> None:
        """Remove a fixture from cache (internal, must hold lock)."""
        self._cache.pop(name, None)

    def _evict_if_needed(self) -> None:
        """Evict oldest entries if over capacity (internal, must hold lock)."""
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)


# =============================================================================
# Parallel Journey Execution with Thread Isolation
# =============================================================================


@dataclass
class ParallelExecutionResult:
    """Result of parallel journey execution.

    Attributes:
        total_journeys: Total number of journeys executed.
        passed: Number of passed journeys.
        failed: Number of failed journeys.
        duration_ms: Total execution duration.
        journey_results: Individual journey results.
        errors: List of error messages.
    """

    total_journeys: int
    passed: int
    failed: int
    duration_ms: float
    journey_results: list[Any]
    errors: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_journeys == 0:
            return 0.0
        return (self.passed / self.total_journeys) * 100


class ParallelJourneyExecutor:
    """Execute multiple journeys in parallel with thread isolation.

    Each journey gets its own client and state manager to ensure
    isolation. Supports configurable concurrency and fail-fast.

    Attributes:
        max_workers: Maximum concurrent journeys.
        fail_fast: Stop on first failure if True.
        timeout_per_journey: Timeout for each journey in seconds.

    Example:
        >>> executor = ParallelJourneyExecutor(max_workers=4)
        >>>
        >>> def runner_factory():
        ...     return JourneyRunner(Client("http://localhost:8000"))
        >>>
        >>> results = executor.run(journeys, runner_factory)
        >>> print(f"Passed: {results.passed}/{results.total_journeys}")
    """

    def __init__(
        self,
        max_workers: int = 4,
        fail_fast: bool = False,
        timeout_per_journey: float | None = None,
    ) -> None:
        """Initialize the executor.

        Args:
            max_workers: Maximum concurrent journeys.
            fail_fast: Stop on first failure.
            timeout_per_journey: Per-journey timeout in seconds.
        """
        if max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {max_workers}")

        self.max_workers = max_workers
        self.fail_fast = fail_fast
        self.timeout_per_journey = timeout_per_journey
        self._stop_event = threading.Event()

    def run(
        self,
        journeys: list[Any],
        runner_factory: Callable[[], Any],
    ) -> ParallelExecutionResult:
        """Execute journeys in parallel.

        Each journey runs in its own thread with an isolated runner.

        Args:
            journeys: List of Journey objects to execute.
            runner_factory: Factory that creates a new JourneyRunner per thread.

        Returns:
            ParallelExecutionResult with all results.
        """
        self._stop_event.clear()
        started_at = datetime.now()

        results: list[Any] = []
        errors: list[str] = []
        lock = threading.Lock()

        def execute_journey(journey: Any) -> Any:
            """Execute a single journey with isolated resources."""
            if self._stop_event.is_set():
                return None

            try:
                # Create isolated runner for this thread
                runner = runner_factory()
                result = runner.run(journey)

                with lock:
                    results.append(result)
                    if not result.success and self.fail_fast:
                        self._stop_event.set()

                return result

            except Exception as e:
                error_msg = f"Journey {getattr(journey, 'name', 'unknown')}: {e}"
                logger.exception(error_msg)
                with lock:
                    errors.append(error_msg)
                return None

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures: dict[Future, Any] = {}

            for journey in journeys:
                if self._stop_event.is_set():
                    break
                future = executor.submit(execute_journey, journey)
                futures[future] = journey

            for future in as_completed(futures):
                if self._stop_event.is_set():
                    break

                try:
                    if self.timeout_per_journey:
                        future.result(timeout=self.timeout_per_journey)
                    else:
                        future.result()
                except TimeoutError:
                    journey = futures[future]
                    error_msg = (
                        f"Journey {getattr(journey, 'name', 'unknown')} "
                        f"timed out after {self.timeout_per_journey}s"
                    )
                    with lock:
                        errors.append(error_msg)
                except Exception as e:
                    journey = futures[future]
                    error_msg = f"Journey {getattr(journey, 'name', 'unknown')}: {e}"
                    with lock:
                        errors.append(error_msg)

        finished_at = datetime.now()
        duration_ms = (finished_at - started_at).total_seconds() * 1000

        passed = sum(1 for r in results if r and getattr(r, "success", False))
        failed = len(results) - passed

        return ParallelExecutionResult(
            total_journeys=len(journeys),
            passed=passed,
            failed=failed,
            duration_ms=duration_ms,
            journey_results=results,
            errors=errors,
        )

    def stop(self) -> None:
        """Stop execution early."""
        self._stop_event.set()


# =============================================================================
# Optimized JSON Serialization
# =============================================================================


class OptimizedSerializer:
    """Fast JSON serialization with caching and lazy encoding.

    Provides optimized JSON operations for common VenomQA data structures
    with caching of frequently serialized objects.

    Example:
        >>> serializer = OptimizedSerializer()
        >>> json_str = serializer.dumps({"key": "value"})
        >>> data = serializer.loads(json_str)
    """

    # Pre-computed separators for compact JSON
    COMPACT_SEPARATORS = (",", ":")
    PRETTY_SEPARATORS = (", ", ": ")

    def __init__(
        self,
        cache_size: int = 1000,
        enable_caching: bool = True,
    ) -> None:
        """Initialize the serializer.

        Args:
            cache_size: Maximum cached serializations.
            enable_caching: Whether to cache serializations.
        """
        self.enable_caching = enable_caching
        self._cache: OrderedDict[int, str] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()

    def dumps(
        self,
        obj: Any,
        pretty: bool = False,
        use_cache: bool = True,
    ) -> str:
        """Serialize object to JSON string.

        Args:
            obj: Object to serialize.
            pretty: Use pretty formatting.
            use_cache: Try to use cache.

        Returns:
            JSON string.
        """
        # Try cache for immutable objects
        if self.enable_caching and use_cache and self._is_cacheable(obj):
            cache_key = self._compute_cache_key(obj)

            with self._lock:
                if cache_key in self._cache:
                    self._cache.move_to_end(cache_key)
                    return self._cache[cache_key]

        # Serialize
        if pretty:
            result = json.dumps(
                obj,
                indent=2,
                separators=self.PRETTY_SEPARATORS,
                default=self._default_encoder,
                sort_keys=True,
            )
        else:
            result = json.dumps(
                obj,
                separators=self.COMPACT_SEPARATORS,
                default=self._default_encoder,
            )

        # Cache if appropriate
        if self.enable_caching and use_cache and self._is_cacheable(obj):
            with self._lock:
                self._cache[cache_key] = result
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)

        return result

    def loads(self, s: str) -> Any:
        """Parse JSON string to object.

        Args:
            s: JSON string.

        Returns:
            Parsed object.
        """
        return json.loads(s)

    def _default_encoder(self, obj: Any) -> Any:
        """Default encoder for non-JSON types."""
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        return str(obj)

    def _is_cacheable(self, obj: Any) -> bool:
        """Check if object is suitable for caching."""
        # Only cache small, immutable-like objects
        try:
            if isinstance(obj, (str, int, float, bool, type(None))):
                return True
            if isinstance(obj, (list, tuple)) and len(obj) < 100:
                return all(self._is_cacheable(item) for item in obj)
            if isinstance(obj, dict) and len(obj) < 50:
                return True
            return False
        except Exception:
            return False

    def _compute_cache_key(self, obj: Any) -> int:
        """Compute cache key for an object."""
        try:
            # Use repr for small objects
            if isinstance(obj, (str, int, float, bool, type(None))):
                return hash((type(obj).__name__, obj))
            return hash(repr(obj))
        except Exception:
            return id(obj)


# =============================================================================
# Memory-Efficient Response Collection
# =============================================================================


@dataclass
class CompactStepResult:
    """Memory-efficient step result storage.

    Stores only essential data to reduce memory footprint during
    large test runs.
    """

    step_name: str
    success: bool
    duration_ms: float
    status_code: int = 0
    error_hash: str | None = None

    @staticmethod
    def from_full_result(result: Any) -> CompactStepResult:
        """Create compact result from full StepResult."""
        error_hash = None
        if hasattr(result, "error") and result.error:
            error_hash = hashlib.md5(result.error.encode()).hexdigest()[:8]

        status_code = 0
        if hasattr(result, "response") and result.response:
            status_code = result.response.get("status_code", 0)

        return CompactStepResult(
            step_name=result.step_name,
            success=result.success,
            duration_ms=result.duration_ms,
            status_code=status_code,
            error_hash=error_hash,
        )


class StreamingResultCollector:
    """Memory-efficient result collection with streaming to disk.

    For very large test runs, streams results to disk to avoid
    memory exhaustion.

    Example:
        >>> collector = StreamingResultCollector("results.jsonl")
        >>> collector.add(step_result)
        >>> collector.add(step_result2)
        >>> collector.finalize()
    """

    def __init__(self, filepath: str, buffer_size: int = 100) -> None:
        """Initialize the collector.

        Args:
            filepath: Path to write results.
            buffer_size: Results to buffer before writing.
        """
        self.filepath = filepath
        self.buffer_size = buffer_size
        self._buffer: list[dict[str, Any]] = []
        self._count = 0
        self._file = None
        self._lock = threading.Lock()

    def __enter__(self) -> StreamingResultCollector:
        """Enter context manager."""
        self._file = open(self.filepath, "w")
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context manager."""
        self.finalize()
        if self._file:
            self._file.close()

    def add(self, result: Any) -> None:
        """Add a result to the collection.

        Args:
            result: Result object with to_dict() method.
        """
        with self._lock:
            if hasattr(result, "to_dict"):
                data = result.to_dict()
            else:
                data = {"value": str(result)}

            self._buffer.append(data)
            self._count += 1

            if len(self._buffer) >= self.buffer_size:
                self._flush()

    def _flush(self) -> None:
        """Write buffer to disk."""
        if not self._buffer or not self._file:
            return

        for item in self._buffer:
            self._file.write(json.dumps(item) + "\n")
        self._file.flush()
        self._buffer.clear()

    def finalize(self) -> None:
        """Flush remaining buffer and finalize."""
        with self._lock:
            self._flush()

    @property
    def count(self) -> int:
        """Get total results collected."""
        return self._count


# =============================================================================
# HTTP Connection Reuse Strategies
# =============================================================================


class ConnectionReuseStrategy:
    """Strategies for HTTP connection reuse.

    Provides different strategies for managing HTTP connections
    across test execution.
    """

    @staticmethod
    @contextmanager
    def per_journey(client_factory: Callable[[], Any]):
        """Create new client per journey (safest, slowest).

        Args:
            client_factory: Factory to create clients.

        Yields:
            Fresh client for each journey.
        """
        client = client_factory()
        try:
            if hasattr(client, "connect"):
                client.connect()
            yield client
        finally:
            if hasattr(client, "disconnect"):
                client.disconnect()

    @staticmethod
    @contextmanager
    def shared_pool(client_factory: Callable[[], Any], pool_size: int = 10):
        """Share a pool of clients across journeys.

        Args:
            client_factory: Factory to create clients.
            pool_size: Number of clients in pool.

        Yields:
            ConnectionPool for acquiring clients.
        """
        from venomqa.performance.pool import ConnectionPool

        pool = ConnectionPool(
            factory=client_factory,
            max_size=pool_size,
            min_size=2,
        )
        try:
            yield pool
        finally:
            pool.close()

    @staticmethod
    def reuse_if_possible(client: Any) -> bool:
        """Check if a client can be safely reused.

        Args:
            client: Client to check.

        Returns:
            True if client can be reused.
        """
        # Check common indicators of connection health
        if hasattr(client, "_client") and client._client is None:
            return False
        if hasattr(client, "is_connected") and callable(client.is_connected):
            return client.is_connected()
        return True


# =============================================================================
# Lazy Initialization Helpers
# =============================================================================


class LazyInitializer(Generic[T]):
    """Thread-safe lazy initialization wrapper.

    Delays object creation until first access.

    Example:
        >>> lazy_db = LazyInitializer(lambda: connect_to_database())
        >>> # Connection not made yet
        >>> db = lazy_db.get()  # Now connected
    """

    def __init__(self, factory: Callable[[], T]) -> None:
        """Initialize with factory function.

        Args:
            factory: Callable to create the object.
        """
        self._factory = factory
        self._value: T | None = None
        self._lock = threading.Lock()
        self._initialized = False

    def get(self) -> T:
        """Get the value, initializing if needed.

        Returns:
            The initialized value.
        """
        if self._initialized:
            return self._value  # type: ignore

        with self._lock:
            if not self._initialized:
                self._value = self._factory()
                self._initialized = True
            return self._value  # type: ignore

    def reset(self) -> None:
        """Reset to uninitialized state."""
        with self._lock:
            self._value = None
            self._initialized = False

    @property
    def is_initialized(self) -> bool:
        """Check if value has been initialized."""
        return self._initialized
