"""Connection pooling for HTTP and database connections.

This module provides thread-safe, generic connection pooling with support for:
- Configurable min/max pool sizes
- Connection validation and health checks
- Idle connection cleanup
- Comprehensive metrics collection
- Callback hooks for connection lifecycle events

Example:
    >>> def create_connection():
    ...     return SomeDBConnection("localhost", 5432)
    >>> pool = ConnectionPool(
    ...     factory=create_connection,
    ...     max_size=10,
    ...     min_size=2,
    ...     validation_query=lambda conn: conn.is_alive(),
    ... )
    >>> with pool.acquire() as conn:
    ...     conn.execute("SELECT 1")
    >>> pool.close()
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class PoolStats:
    """Statistics for a connection pool.

    Tracks connection lifecycle events and performance metrics including
    creation, checkout/checkin operations, and validation errors.

    Attributes:
        total_connections: Current total number of connections in the pool.
        active_connections: Number of connections currently in use.
        idle_connections: Number of connections available for use.
        wait_count: Total number of times clients waited for a connection.
        wait_time_ms: Cumulative wait time in milliseconds.
        checkout_count: Total number of connection checkouts.
        checkin_count: Total number of connection checkins.
        creation_count: Total number of connections created.
        validation_errors: Total number of validation failures.
        peak_connections: Maximum number of concurrent connections reached.
        last_checkout_time_ms: Duration of the most recent checkout in ms.
    """

    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    wait_count: int = 0
    wait_time_ms: float = 0.0
    checkout_count: int = 0
    checkin_count: int = 0
    creation_count: int = 0
    validation_errors: int = 0
    peak_connections: int = 0
    last_checkout_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert stats to a dictionary for serialization.

        Returns:
            Dictionary containing all pool statistics with calculated averages.
        """
        return {
            "total": self.total_connections,
            "active": self.active_connections,
            "idle": self.idle_connections,
            "peak": self.peak_connections,
            "wait_count": self.wait_count,
            "avg_wait_ms": round(self.wait_time_ms / max(1, self.wait_count), 2),
            "last_checkout_ms": round(self.last_checkout_time_ms, 2),
            "checkouts": self.checkout_count,
            "checkins": self.checkin_count,
            "creations": self.creation_count,
            "validation_errors": self.validation_errors,
            "utilization_pct": round(
                (self.active_connections / max(1, self.total_connections)) * 100, 1
            ),
        }


@dataclass(eq=False)
class PooledConnection(Generic[T]):
    """Wrapper for a pooled connection with lifecycle tracking.

    Generic wrapper that tracks connection metadata including creation time,
    last usage, and checkout count for pool management decisions.

    Type Parameters:
        T: The type of the underlying connection.

    Attributes:
        connection: The actual connection object.
        created_at: Unix timestamp when the connection was created.
        last_used: Unix timestamp of the most recent use.
        checkout_count: Number of times this connection has been checked out.
        is_valid: Whether this connection is still usable.
    """

    connection: T
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    checkout_count: int = 0
    is_valid: bool = True

    def __hash__(self) -> int:
        return id(self)

    @property
    def age_seconds(self) -> float:
        """Get the age of this connection in seconds.

        Returns:
            Number of seconds since the connection was created.
        """
        return time.time() - self.created_at

    @property
    def idle_seconds(self) -> float:
        """Get how long this connection has been idle in seconds.

        Returns:
            Number of seconds since the connection was last used.
        """
        return time.time() - self.last_used


class ConnectionPool(Generic[T]):
    """Thread-safe generic connection pool with lifecycle management.

    A production-ready connection pool that manages connection creation, reuse,
    validation, and cleanup. Supports configurable pool sizes, idle timeouts,
    and validation queries.

    The pool maintains minimum connections eagerly and creates additional
    connections on demand up to the maximum size. Idle connections beyond
    the minimum are cleaned up automatically.

    Type Parameters:
        T: The type of connections managed by this pool.

    Attributes:
        factory: Callable that creates new connections.
        max_size: Maximum number of connections allowed.
        min_size: Minimum number of connections to maintain.
        max_idle_time: Seconds before idle connections are closed.
        validation_query: Optional callable to validate connections.
        on_checkout: Optional callback invoked when connection is acquired.
        on_checkin: Optional callback invoked when connection is returned.
        on_close: Optional callback invoked when connection is destroyed.

    Example:
        >>> pool = ConnectionPool(
        ...     factory=lambda: sqlite3.connect(":memory:"),
        ...     max_size=5,
        ...     min_size=1,
        ...     validation_query=lambda c: c.execute("SELECT 1") is not None,
        ... )
        >>> with pool.acquire(timeout=5.0) as conn:
        ...     conn.execute("CREATE TABLE test (id INT)")
        >>> stats = pool.get_stats()
        >>> pool.close()
    """

    def __init__(
        self,
        factory: Callable[[], T],
        max_size: int = 10,
        min_size: int = 1,
        max_idle_time: float = 300.0,
        validation_query: Callable[[T], bool] | None = None,
        on_checkout: Callable[[T], None] | None = None,
        on_checkin: Callable[[T], None] | None = None,
        on_close: Callable[[T], None] | None = None,
    ) -> None:
        """Initialize the connection pool.

        Args:
            factory: Callable that creates a new connection.
            max_size: Maximum number of connections. Must be >= min_size.
            min_size: Minimum connections to maintain. Defaults to 1.
            max_idle_time: Seconds before closing idle connections. Defaults to 300.
            validation_query: Optional callable to check connection health.
            on_checkout: Optional callback on connection acquisition.
            on_checkin: Optional callback on connection return.
            on_close: Optional callback on connection destruction.

        Raises:
            ValueError: If max_size < min_size or min_size < 0.
        """
        if max_size < min_size:
            raise ValueError(f"max_size ({max_size}) must be >= min_size ({min_size})")
        if min_size < 0:
            raise ValueError(f"min_size ({min_size}) must be >= 0")

        self.factory = factory
        self.max_size = max_size
        self.min_size = min_size
        self.max_idle_time = max_idle_time
        self.validation_query = validation_query
        self.on_checkout = on_checkout
        self.on_checkin = on_checkin
        self.on_close = on_close

        self._pool: queue.Queue[PooledConnection[T]] = queue.Queue()
        self._all_connections: set[PooledConnection[T]] = set()
        self._lock = threading.RLock()
        self._stats = PoolStats()
        self._closed = False

        self._initialize_min_connections()

    def _initialize_min_connections(self) -> None:
        """Create minimum number of connections at startup.

        Creates min_size connections to have them ready for use.
        Failures are logged but don't raise exceptions to allow
        pool initialization to complete.
        """
        for _ in range(self.min_size):
            try:
                conn = self._create_connection()
                self._pool.put(conn)
            except Exception as e:
                logger.warning(f"Failed to create initial connection: {e}")

    def _create_connection(self) -> PooledConnection[T]:
        """Create a new pooled connection using the factory.

        Returns:
            A new PooledConnection wrapping the created connection.

        Raises:
            Exception: If the factory fails to create a connection.
        """
        conn = self.factory()
        pooled = PooledConnection(connection=conn)
        with self._lock:
            self._all_connections.add(pooled)
            self._stats.total_connections += 1
            self._stats.creation_count += 1
            if self._stats.total_connections > self._stats.peak_connections:
                self._stats.peak_connections = self._stats.total_connections
        logger.debug("Created new connection (total: %d)", self._stats.total_connections)
        return pooled

    @contextmanager
    def acquire(self, timeout: float | None = None) -> Generator[T, None, None]:
        """Acquire a connection from the pool as a context manager.

        Gets an available connection or creates a new one if below max_size.
        The connection is automatically returned to the pool when the
        context exits, even if an exception occurs.

        Args:
            timeout: Maximum seconds to wait for a connection. None means
                use default timeout (30 seconds).

        Yields:
            The underlying connection object.

        Raises:
            RuntimeError: If the pool has been closed.
            TimeoutError: If no connection becomes available within timeout.

        Example:
            >>> with pool.acquire(timeout=5.0) as conn:
            ...     result = conn.execute("SELECT * FROM users")
        """
        if self._closed:
            raise RuntimeError("Pool is closed")

        start_time = time.perf_counter()
        pooled_conn = self._get_connection(timeout)
        wait_time_ms = (time.perf_counter() - start_time) * 1000

        with self._lock:
            self._stats.wait_count += 1
            self._stats.wait_time_ms += wait_time_ms
            self._stats.last_checkout_time_ms = wait_time_ms
            self._stats.active_connections += 1
            self._stats.idle_connections -= 1
            self._stats.checkout_count += 1

        pooled_conn.last_used = time.time()
        pooled_conn.checkout_count += 1

        if self.on_checkout:
            try:
                self.on_checkout(pooled_conn.connection)
            except Exception as e:
                logger.warning(f"Checkout callback failed: {e}")

        try:
            yield pooled_conn.connection
        finally:
            self._release_connection(pooled_conn)

    def _get_connection(self, timeout: float | None = None) -> PooledConnection[T]:
        """Get a connection from the pool or create a new one.

        Attempts to get an existing valid connection from the pool first.
        If none available and below max_size, creates a new connection.
        Otherwise waits for a connection to become available.

        Args:
            timeout: Maximum seconds to wait. Defaults to 30.

        Returns:
            A valid pooled connection ready for use.

        Raises:
            TimeoutError: If no connection available within timeout.
        """
        actual_timeout = timeout or 30.0

        while True:
            try:
                pooled_conn = self._pool.get(block=False)
                if self._is_connection_valid(pooled_conn):
                    return pooled_conn
                else:
                    self._destroy_connection(pooled_conn)
            except queue.Empty:
                pass

            with self._lock:
                if len(self._all_connections) < self.max_size:
                    return self._create_connection()

            try:
                pooled_conn = self._pool.get(block=True, timeout=actual_timeout)
                if self._is_connection_valid(pooled_conn):
                    return pooled_conn
                else:
                    self._destroy_connection(pooled_conn)
            except queue.Empty:
                raise TimeoutError("Timeout waiting for connection from pool") from None

    def _release_connection(self, pooled_conn: PooledConnection[T]) -> None:
        """Return a connection to the pool after use.

        If the pool is closed or connection is invalid, destroys it instead.
        Updates statistics and invokes callbacks as appropriate.

        Args:
            pooled_conn: The connection to return to the pool.
        """
        if self._closed:
            self._destroy_connection(pooled_conn)
            return

        if not pooled_conn.is_valid:
            self._destroy_connection(pooled_conn)
            return

        if self.on_checkin:
            try:
                self.on_checkin(pooled_conn.connection)
            except Exception as e:
                logger.warning(f"Checkin callback failed: {e}")

        with self._lock:
            self._stats.active_connections -= 1
            self._stats.idle_connections += 1
            self._stats.checkin_count += 1

        self._pool.put(pooled_conn)

    def _is_connection_valid(self, pooled_conn: PooledConnection[T]) -> bool:
        """Check if a connection is still valid for use.

        A connection is invalid if:
        - It has been explicitly marked invalid
        - It has been idle longer than max_idle_time
        - The validation query fails (if configured)

        Args:
            pooled_conn: The connection to validate.

        Returns:
            True if the connection is valid, False otherwise.
        """
        if time.time() - pooled_conn.last_used > self.max_idle_time:
            return False

        if self.validation_query:
            try:
                return self.validation_query(pooled_conn.connection)
            except Exception:
                with self._lock:
                    self._stats.validation_errors += 1
                return False

        return pooled_conn.is_valid

    def _destroy_connection(self, pooled_conn: PooledConnection[T]) -> None:
        """Destroy a connection and remove it from the pool.

        Removes the connection from tracking, invokes the close callback,
        and marks it as invalid.

        Args:
            pooled_conn: The connection to destroy.
        """
        with self._lock:
            self._all_connections.discard(pooled_conn)
            self._stats.total_connections -= 1

        if self.on_close:
            try:
                self.on_close(pooled_conn.connection)
            except Exception as e:
                logger.warning(f"Close callback failed: {e}")

        pooled_conn.is_valid = False
        logger.debug("Destroyed connection (remaining: %d)", self._stats.total_connections)

    def cleanup_idle(self) -> int:
        """Remove idle connections beyond the minimum pool size.

        Drains the pool, destroys connections that have been idle too long
        (while maintaining min_size), and returns valid ones to the pool.

        Returns:
            Number of connections removed.
        """
        removed = 0
        temp_list: list[PooledConnection[T]] = []

        while True:
            try:
                temp_list.append(self._pool.get(block=False))
            except queue.Empty:
                break

        for pooled_conn in temp_list:
            should_destroy = (
                len(self._all_connections) > self.min_size
                and time.time() - pooled_conn.last_used > self.max_idle_time
            )
            if should_destroy:
                self._destroy_connection(pooled_conn)
                removed += 1
            else:
                self._pool.put(pooled_conn)

        if removed > 0:
            logger.info("Cleaned up %d idle connections", removed)
        return removed

    def get_stats(self) -> PoolStats:
        """Get current pool statistics.

        Returns a snapshot of current pool metrics including connection
        counts, wait times, and operation counters.

        Returns:
            PoolStats with current statistics.
        """
        with self._lock:
            self._stats.idle_connections = self._pool.qsize()
            return PoolStats(
                total_connections=self._stats.total_connections,
                active_connections=self._stats.active_connections,
                idle_connections=self._stats.idle_connections,
                wait_count=self._stats.wait_count,
                wait_time_ms=self._stats.wait_time_ms,
                checkout_count=self._stats.checkout_count,
                checkin_count=self._stats.checkin_count,
                creation_count=self._stats.creation_count,
                validation_errors=self._stats.validation_errors,
                peak_connections=self._stats.peak_connections,
                last_checkout_time_ms=self._stats.last_checkout_time_ms,
            )

    def health_check(self) -> dict[str, Any]:
        """Perform a health check on the pool.

        Returns:
            Dictionary with health status and metrics.
        """
        stats = self.get_stats()
        is_healthy = (
            not self._closed
            and stats.total_connections >= 0
            and (stats.checkout_count == 0 or stats.validation_errors < stats.checkout_count * 0.1)
        )

        return {
            "healthy": is_healthy,
            "closed": self._closed,
            "utilization_pct": round(
                (stats.active_connections / max(1, stats.total_connections)) * 100, 1
            ),
            "stats": stats.to_dict(),
        }

    def close(self) -> None:
        """Close all connections and shut down the pool.

        After calling close(), acquire() will raise RuntimeError.
        Any connections currently in use will be destroyed when returned.
        """
        self._closed = True

        while True:
            try:
                pooled_conn = self._pool.get(block=False)
                self._destroy_connection(pooled_conn)
            except queue.Empty:
                break

        with self._lock:
            remaining = list(self._all_connections)
            for conn in remaining:
                self._destroy_connection(conn)

        logger.info("Connection pool closed")

    def __enter__(self) -> ConnectionPool[T]:
        """Enter context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context manager and close pool."""
        self.close()


class HTTPConnectionPool:
    """HTTP connection pool using httpx with connection reuse.

    Manages a pool of httpx.Client instances for efficient HTTP request
    handling with keep-alive connections and connection limits.

    Attributes:
        base_url: Base URL for all requests.
        max_connections: Maximum total connections.
        max_keepalive: Maximum keep-alive connections.
        keepalive_expiry: Seconds before keep-alive connections expire.
        timeout: Request timeout in seconds.
        default_headers: Headers to include in all requests.

    Example:
        >>> pool = HTTPConnectionPool("https://api.example.com")
        >>> pool.initialize()
        >>> with pool.acquire() as client:
        ...     response = client.get("/users")
        >>> pool.close()
    """

    def __init__(
        self,
        base_url: str,
        max_connections: int = 10,
        max_keepalive: int = 5,
        keepalive_expiry: float = 30.0,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize HTTP connection pool configuration.

        Args:
            base_url: Base URL for all HTTP requests.
            max_connections: Maximum total connections. Defaults to 10.
            max_keepalive: Maximum keep-alive connections. Defaults to 5.
            keepalive_expiry: Keep-alive expiry in seconds. Defaults to 30.
            timeout: Request timeout in seconds. Defaults to 30.
            default_headers: Optional headers for all requests.
        """
        self.base_url = base_url.rstrip("/")
        self.max_connections = max_connections
        self.max_keepalive = max_keepalive
        self.keepalive_expiry = keepalive_expiry
        self.timeout = timeout
        self.default_headers = default_headers or {}

        self._pool: ConnectionPool[Any] | None = None
        self._stats = PoolStats()

    def initialize(self) -> None:
        """Initialize the HTTP connection pool.

        Creates the underlying connection pool with httpx clients.
        Must be called before acquire() if not using lazy initialization.
        """
        import httpx

        limits = httpx.Limits(
            max_connections=self.max_connections,
            max_keepalive_connections=self.max_keepalive,
            keepalive_expiry=self.keepalive_expiry,
        )

        def _client_factory() -> httpx.Client:
            return httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                limits=limits,
                headers=self.default_headers,
            )

        self._pool = ConnectionPool(
            factory=_client_factory,
            max_size=self.max_connections,
            min_size=1,
            max_idle_time=self.keepalive_expiry,
            on_close=lambda c: c.close(),
        )
        logger.info(f"HTTP connection pool initialized for {self.base_url}")

    def acquire(self, timeout: float | None = None):
        """Acquire an HTTP client from the pool.

        Lazily initializes the pool if not already done.

        Args:
            timeout: Maximum seconds to wait for a client.

        Returns:
            Context manager yielding an httpx.Client.
        """
        if not self._pool:
            self.initialize()
        return self._pool.acquire(timeout)

    def get_stats(self) -> PoolStats:
        """Get pool statistics.

        Returns:
            Current pool statistics.
        """
        if self._pool:
            return self._pool.get_stats()
        return self._stats

    def close(self) -> None:
        """Close the connection pool and release resources."""
        if self._pool:
            self._pool.close()
            self._pool = None


class DBConnectionPool:
    """Database connection pool with support for PostgreSQL and SQLite.

    Provides connection pooling for database operations with configurable
    pool sizes, validation queries, and automatic cleanup.

    Attributes:
        connection_url: Database connection URL.
        max_connections: Maximum connections in pool.
        min_connections: Minimum connections to maintain.
        max_idle_time: Seconds before idle connections close.
        validation_query: SQL query to validate connections.

    Example:
        >>> pool = DBConnectionPool("postgresql://localhost/mydb")
        >>> pool.initialize_postgresql()
        >>> with pool.acquire() as conn:
        ...     result = conn.execute("SELECT * FROM users")
        >>> pool.close()
    """

    def __init__(
        self,
        connection_url: str,
        max_connections: int = 10,
        min_connections: int = 2,
        max_idle_time: float = 300.0,
        validation_query: str = "SELECT 1",
    ) -> None:
        """Initialize database connection pool configuration.

        Args:
            connection_url: Database connection URL.
            max_connections: Maximum pool size. Defaults to 10.
            min_connections: Minimum pool size. Defaults to 2.
            max_idle_time: Idle timeout in seconds. Defaults to 300.
            validation_query: SQL to validate connections. Defaults to "SELECT 1".
        """
        self.connection_url = connection_url
        self.max_connections = max_connections
        self.min_connections = min_connections
        self.max_idle_time = max_idle_time
        self.validation_query = validation_query

        self._pool: ConnectionPool[Any] | None = None
        self._stats = PoolStats()
        self._pool_type: str | None = None

    def initialize_postgresql(self) -> None:
        """Initialize PostgreSQL connection pool using psycopg.

        Creates a pool with dict row factory for convenient row access.
        The validation query tests connection health before reuse.

        Raises:
            ImportError: If psycopg is not installed.
        """
        import psycopg
        from psycopg.rows import dict_row

        self._pool_type = "postgresql"

        def factory():
            return psycopg.connect(self.connection_url, row_factory=dict_row)

        def validate(conn):
            try:
                with conn.cursor() as cur:
                    cur.execute(self.validation_query)
                return True
            except Exception:
                return False

        def on_close(conn):
            try:
                conn.close()
            except Exception:
                pass

        self._pool = ConnectionPool(
            factory=factory,
            max_size=self.max_connections,
            min_size=self.min_connections,
            max_idle_time=self.max_idle_time,
            validation_query=validate,
            on_close=on_close,
        )
        logger.info("PostgreSQL connection pool initialized")

    def initialize_sqlite(self, check_same_thread: bool = False) -> None:
        """Initialize SQLite connection pool.

        SQLite has threading limitations, so by default uses a single
        connection with check_same_thread=False for thread safety.

        Args:
            check_same_thread: If True, allows multi-connection pool.
                If False, uses single connection for thread safety.

        Note:
            SQLite URL format: sqlite:///path/to/database.db
        """
        import sqlite3

        self._pool_type = "sqlite"

        db_path = self.connection_url.replace("sqlite:///", "")

        def factory():
            conn = sqlite3.connect(db_path, check_same_thread=check_same_thread)
            conn.row_factory = sqlite3.Row
            return conn

        def validate(conn):
            try:
                conn.execute(self.validation_query)
                return True
            except Exception:
                return False

        def on_close(conn):
            try:
                conn.close()
            except Exception:
                pass

        self._pool = ConnectionPool(
            factory=factory,
            max_size=1 if not check_same_thread else self.max_connections,
            min_size=1,
            max_idle_time=self.max_idle_time,
            validation_query=validate,
            on_close=on_close,
        )
        logger.info("SQLite connection pool initialized")

    def acquire(self, timeout: float | None = None):
        """Acquire a database connection from the pool.

        Args:
            timeout: Maximum seconds to wait for a connection.

        Returns:
            Context manager yielding a database connection.

        Raises:
            RuntimeError: If pool not initialized.
        """
        if not self._pool:
            raise RuntimeError("Pool not initialized. Call initialize_* first.")
        return self._pool.acquire(timeout)

    def get_stats(self) -> PoolStats:
        """Get pool statistics.

        Returns:
            Current pool statistics.
        """
        if self._pool:
            return self._pool.get_stats()
        return self._stats

    def close(self) -> None:
        """Close the connection pool and release all connections."""
        if self._pool:
            self._pool.close()
            self._pool = None
