"""Connection pooling for HTTP and database connections."""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class PoolStats:
    """Statistics for a connection pool."""

    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    wait_count: int = 0
    wait_time_ms: float = 0.0
    checkout_count: int = 0
    checkin_count: int = 0
    creation_count: int = 0
    validation_errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total_connections,
            "active": self.active_connections,
            "idle": self.idle_connections,
            "wait_count": self.wait_count,
            "avg_wait_ms": round(self.wait_time_ms / max(1, self.wait_count), 2),
            "checkouts": self.checkout_count,
            "checkins": self.checkin_count,
            "creations": self.creation_count,
            "validation_errors": self.validation_errors,
        }


@dataclass
class PooledConnection(Generic[T]):
    """Wrapper for a pooled connection."""

    connection: T
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    checkout_count: int = 0
    is_valid: bool = True


class ConnectionPool(Generic[T]):
    """Thread-safe generic connection pool."""

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
        """Create minimum number of connections."""
        for _ in range(self.min_size):
            try:
                conn = self._create_connection()
                self._pool.put(conn)
            except Exception as e:
                logger.warning(f"Failed to create initial connection: {e}")

    def _create_connection(self) -> PooledConnection[T]:
        """Create a new connection."""
        conn = self.factory()
        pooled = PooledConnection(connection=conn)
        with self._lock:
            self._all_connections.add(pooled)
            self._stats.total_connections += 1
            self._stats.creation_count += 1
        logger.debug("Created new connection")
        return pooled

    @contextmanager
    def acquire(self, timeout: float | None = None) -> Any:
        """Acquire a connection from the pool."""
        if self._closed:
            raise RuntimeError("Pool is closed")

        start_time = time.time()
        pooled_conn = self._get_connection(timeout)
        wait_time_ms = (time.time() - start_time) * 1000

        with self._lock:
            self._stats.wait_count += 1
            self._stats.wait_time_ms += wait_time_ms
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
        """Get a connection from the pool or create new one."""
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
                pooled_conn = self._pool.get(block=True, timeout=timeout or 30.0)
                if self._is_connection_valid(pooled_conn):
                    return pooled_conn
                else:
                    self._destroy_connection(pooled_conn)
            except queue.Empty:
                raise TimeoutError("Timeout waiting for connection from pool") from None

    def _release_connection(self, pooled_conn: PooledConnection[T]) -> None:
        """Return a connection to the pool."""
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
        """Check if a connection is still valid."""
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
        """Destroy a connection."""
        with self._lock:
            self._all_connections.discard(pooled_conn)
            self._stats.total_connections -= 1

        if self.on_close:
            try:
                self.on_close(pooled_conn.connection)
            except Exception as e:
                logger.warning(f"Close callback failed: {e}")

        pooled_conn.is_valid = False
        logger.debug("Destroyed connection")

    def cleanup_idle(self) -> int:
        """Remove idle connections beyond minimum. Returns count removed."""
        removed = 0
        temp_list = []

        while True:
            try:
                temp_list.append(self._pool.get(block=False))
            except queue.Empty:
                break

        for pooled_conn in temp_list:
            if (
                len(self._all_connections) > self.min_size
                and time.time() - pooled_conn.last_used > self.max_idle_time
            ):
                self._destroy_connection(pooled_conn)
                removed += 1
            else:
                self._pool.put(pooled_conn)

        return removed

    def get_stats(self) -> PoolStats:
        """Get pool statistics."""
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
            )

    def close(self) -> None:
        """Close all connections in the pool."""
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


class HTTPConnectionPool:
    """HTTP connection pool using httpx."""

    def __init__(
        self,
        base_url: str,
        max_connections: int = 10,
        max_keepalive: int = 5,
        keepalive_expiry: float = 30.0,
        timeout: float = 30.0,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_connections = max_connections
        self.max_keepalive = max_keepalive
        self.keepalive_expiry = keepalive_expiry
        self.timeout = timeout
        self.default_headers = default_headers or {}

        self._pool: ConnectionPool[Any] | None = None
        self._stats = PoolStats()

    def initialize(self) -> None:
        """Initialize the HTTP connection pool."""
        import httpx

        limits = httpx.Limits(
            max_connections=self.max_connections,
            max_keepalive_connections=self.max_keepalive,
            keepalive_expiry=self.keepalive_expiry,
        )

        def _client_factory():
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
        """Acquire an HTTP client from the pool."""
        if not self._pool:
            self.initialize()
        return self._pool.acquire(timeout)

    def get_stats(self) -> PoolStats:
        """Get pool statistics."""
        if self._pool:
            return self._pool.get_stats()
        return self._stats

    def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            self._pool.close()
            self._pool = None


class DBConnectionPool:
    """Database connection pool."""

    def __init__(
        self,
        connection_url: str,
        max_connections: int = 10,
        min_connections: int = 2,
        max_idle_time: float = 300.0,
        validation_query: str = "SELECT 1",
    ) -> None:
        self.connection_url = connection_url
        self.max_connections = max_connections
        self.min_connections = min_connections
        self.max_idle_time = max_idle_time
        self.validation_query = validation_query

        self._pool: ConnectionPool[Any] | None = None
        self._stats = PoolStats()
        self._pool_type: str | None = None

    def initialize_postgresql(self) -> None:
        """Initialize PostgreSQL connection pool."""
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
        """Initialize SQLite connection pool."""
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
        """Acquire a database connection from the pool."""
        if not self._pool:
            raise RuntimeError("Pool not initialized. Call initialize_* first.")
        return self._pool.acquire(timeout)

    def get_stats(self) -> PoolStats:
        """Get pool statistics."""
        if self._pool:
            return self._pool.get_stats()
        return self._stats

    def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            self._pool.close()
            self._pool = None
