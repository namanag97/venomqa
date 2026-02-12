"""Performance optimization module for VenomQA."""

from venomqa.performance.batch import (
    BatchExecutor,
    BatchProgress,
    BatchResult,
    ProgressCallback,
    aggregate_results,
    default_progress_callback,
)
from venomqa.performance.cache import (
    CachedResponse,
    CacheEntry,
    CacheStats,
    ResponseCache,
)
from venomqa.performance.pool import (
    ConnectionPool,
    DBConnectionPool,
    HTTPConnectionPool,
    PoolStats,
)

__all__ = [
    "ResponseCache",
    "CacheEntry",
    "CacheStats",
    "CachedResponse",
    "ConnectionPool",
    "HTTPConnectionPool",
    "DBConnectionPool",
    "PoolStats",
    "BatchExecutor",
    "BatchProgress",
    "BatchResult",
    "ProgressCallback",
    "aggregate_results",
    "default_progress_callback",
]
