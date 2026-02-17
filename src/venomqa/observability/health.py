"""Health check endpoints for VenomQA.

This module provides comprehensive health check capabilities including:
- Liveness probes (is the service running?)
- Readiness probes (is the service ready to accept traffic?)
- Custom health checks with timeout and caching
- Standard health check factory functions (database, HTTP, memory, disk)
- Kubernetes-compatible health endpoints

Example:
    Basic usage::

        from venomqa.observability.health import HealthCheck, HealthStatus

        health = HealthCheck(service_name="my-service", version="1.0.0")

        # Add a custom health check
        def check_database():
            # Perform check
            return HealthCheckResult(
                name="database",
                status=HealthStatus.HEALTHY,
                message="Connected"
            )

        health.register("database", check_database)

        # Get readiness status
        readiness = health.readiness()

    Kubernetes endpoints::

        # Liveness: GET /health/live
        return health.liveness()

        # Readiness: GET /health/ready
        return health.readiness()

        # Full health: GET /health
        return health.full_health()
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class HealthStatus(Enum):
    """Health check status levels.

    Attributes:
        HEALTHY: Component is functioning normally.
        DEGRADED: Component is functioning but with issues.
        UNHEALTHY: Component is not functioning properly.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """Result of a single health check.

    Contains the status, timing, and any additional details from
    executing a health check.

    Attributes:
        name: Name of the health check.
        status: Current health status.
        message: Human-readable status message.
        duration_ms: Time taken to execute the check in milliseconds.
        details: Additional key-value details about the check.
        timestamp: ISO timestamp when the check was performed.

    Example:
        >>> result = HealthCheckResult(
        ...     name="database",
        ...     status=HealthStatus.HEALTHY,
        ...     message="Connected to primary",
        ...     details={"latency_ms": 5.2}
        ... )
    """

    name: str
    status: HealthStatus
    message: str = ""
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the health check result.
        """
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "durationMs": round(self.duration_ms, 2),
            "details": dict(self.details),
            "timestamp": self.timestamp,
        }

    def is_healthy(self) -> bool:
        """Check if status is healthy."""
        return self.status == HealthStatus.HEALTHY

    def is_degraded(self) -> bool:
        """Check if status is degraded."""
        return self.status == HealthStatus.DEGRADED

    def is_unhealthy(self) -> bool:
        """Check if status is unhealthy."""
        return self.status == HealthStatus.UNHEALTHY


HealthCheckFunc = Callable[[], HealthCheckResult]
AsyncHealthCheckFunc = Callable[[], "asyncio.Future[HealthCheckResult]"]


@dataclass
class ComponentHealth:
    """Configuration and state for a health check component.

    Attributes:
        name: Unique name for this health check.
        check: Function that performs the health check.
        critical: If True, unhealthy status makes overall status unhealthy.
        timeout_seconds: Maximum time for the check to complete.
        cache_seconds: How long to cache results (0 = no caching).
    """

    name: str
    check: HealthCheckFunc
    critical: bool = True
    timeout_seconds: float = 5.0
    cache_seconds: float = 0.0
    _last_result: HealthCheckResult | None = field(default=None, repr=False)
    _last_check_time: float = field(default=0.0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class HealthCheck:
    """Centralized health check management.

    Manages registration, execution, and aggregation of health checks.
    Provides Kubernetes-compatible liveness and readiness endpoints.

    Attributes:
        service_name: Name of the service.
        version: Service version string.

    Example:
        >>> health = HealthCheck("api-server", "1.0.0")
        >>> health.register("redis", check_redis_connection, critical=False)
        >>> health.register("database", check_database, timeout_seconds=3.0)
        >>> print(health.to_json())
    """

    def __init__(
        self,
        service_name: str = "venomqa",
        version: str = "0.1.0",
        default_timeout: float = 5.0,
    ) -> None:
        """Initialize the health check manager.

        Args:
            service_name: Name of the service for responses.
            version: Version string for responses.
            default_timeout: Default timeout for health checks in seconds.
        """
        self.service_name = service_name
        self.version = version
        self.default_timeout = default_timeout
        self._components: dict[str, ComponentHealth] = {}
        self._lock = threading.Lock()
        self._startup_time = time.time()
        self._executor = ThreadPoolExecutor(max_workers=4)

        self._register_default_checks()

    def _register_default_checks(self) -> None:
        """Register built-in health checks."""
        self.register("liveness", self._check_liveness, critical=True)
        self.register("readiness", self._check_readiness, critical=True)

    def register(
        self,
        name: str,
        check: HealthCheckFunc,
        critical: bool = True,
        timeout_seconds: float | None = None,
        cache_seconds: float = 0.0,
    ) -> None:
        """Register a health check component.

        Args:
            name: Unique name for this health check.
            check: Function that returns a HealthCheckResult.
            critical: If True, unhealthy status affects overall health.
            timeout_seconds: Maximum time for check execution.
            cache_seconds: Duration to cache results (0 = no caching).

        Example:
            >>> def check_db():
            ...     try:
            ...         db.ping()
            ...         return HealthCheckResult("db", HealthStatus.HEALTHY)
            ...     except Exception as e:
            ...         return HealthCheckResult("db", HealthStatus.UNHEALTHY, str(e))
            >>> health.register("database", check_db, timeout_seconds=2.0)
        """
        with self._lock:
            self._components[name] = ComponentHealth(
                name=name,
                check=check,
                critical=critical,
                timeout_seconds=timeout_seconds or self.default_timeout,
                cache_seconds=cache_seconds,
            )

    def unregister(self, name: str) -> None:
        """Unregister a health check.

        Args:
            name: Name of the health check to remove.
        """
        with self._lock:
            self._components.pop(name, None)

    def run_check(self, name: str) -> HealthCheckResult | None:
        """Run a specific health check.

        Args:
            name: Name of the health check to run.

        Returns:
            HealthCheckResult or None if check doesn't exist.
        """
        with self._lock:
            component = self._components.get(name)
            if not component:
                return None

        if component.cache_seconds > 0:
            with component._lock:
                elapsed = time.time() - component._last_check_time
                if elapsed < component.cache_seconds and component._last_result:
                    return component._last_result

        start_time = time.time()
        try:
            result = self._run_check_with_timeout(component)
            result.duration_ms = (time.time() - start_time) * 1000

            if component.cache_seconds > 0:
                with component._lock:
                    component._last_result = result
                    component._last_check_time = time.time()

            return result

        except FuturesTimeoutError:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check timed out after {component.timeout_seconds}s",
                duration_ms=(time.time() - start_time) * 1000,
                details={"timeout_seconds": component.timeout_seconds},
            )
        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                duration_ms=(time.time() - start_time) * 1000,
                details={"exception": str(e), "exception_type": type(e).__name__},
            )

    def _run_check_with_timeout(self, component: ComponentHealth) -> HealthCheckResult:
        """Run a health check with timeout enforcement."""
        future = self._executor.submit(component.check)
        return future.result(timeout=component.timeout_seconds)

    def run_all_checks(self) -> dict[str, HealthCheckResult]:
        """Run all registered health checks.

        Returns:
            Dictionary mapping check names to their results.
        """
        results: dict[str, HealthCheckResult] = {}
        with self._lock:
            names = list(self._components.keys())

        for name in names:
            result = self.run_check(name)
            if result:
                results[name] = result

        return results

    def run_all_checks_parallel(self) -> dict[str, HealthCheckResult]:
        """Run all health checks in parallel using thread pool.

        Returns:
            Dictionary mapping check names to their results.
        """
        results: dict[str, HealthCheckResult] = {}
        with self._lock:
            names = list(self._components.keys())

        futures = {}
        for name in names:
            future = self._executor.submit(self.run_check, name)
            futures[future] = name

        for future in futures:
            name = futures[future]
            try:
                result = future.result(timeout=self.default_timeout * 2)
                if result:
                    results[name] = result
            except Exception as e:
                results[name] = HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Health check failed: {e}",
                    details={"exception": str(e)},
                )

        return results

    def get_overall_status(
        self,
        results: dict[str, HealthCheckResult] | None = None,
    ) -> HealthStatus:
        """Calculate overall health status from individual check results.

        The overall status is determined by:
        - UNHEALTHY if any critical check is unhealthy
        - DEGRADED if any check (critical or not) is degraded
        - HEALTHY if all checks pass

        Args:
            results: Check results (runs all checks if None).

        Returns:
            Aggregated health status.
        """
        if results is None:
            results = self.run_all_checks()

        if not results:
            return HealthStatus.HEALTHY

        has_unhealthy_critical = False
        has_degraded = False

        for name, result in results.items():
            with self._lock:
                component = self._components.get(name)
                is_critical = component.critical if component else True

            if result.status == HealthStatus.UNHEALTHY:
                if is_critical:
                    has_unhealthy_critical = True
            elif result.status == HealthStatus.DEGRADED:
                has_degraded = True

        if has_unhealthy_critical:
            return HealthStatus.UNHEALTHY
        if has_degraded:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    def liveness(self) -> dict[str, Any]:
        """Get liveness probe response.

        Liveness indicates whether the service is running. If this
        endpoint returns successfully, the service should be considered
        alive even if it's not ready to serve traffic.

        Returns:
            Dictionary with liveness status.

        Note:
            Kubernetes uses this endpoint at /health/live to determine
            if the container should be restarted.
        """
        return {
            "status": "alive",
            "service": self.service_name,
            "version": self.version,
            "uptime_seconds": round(time.time() - self._startup_time, 2),
        }

    def readiness(self) -> dict[str, Any]:
        """Get readiness probe response.

        Readiness indicates whether the service is ready to accept
        traffic. This checks all registered health checks.

        Returns:
            Dictionary with readiness status and check details.

        Note:
            Kubernetes uses this endpoint at /health/ready to determine
            if the service should receive traffic.
        """
        results = self.run_all_checks()
        overall = self.get_overall_status(results)

        return {
            "status": overall.value,
            "service": self.service_name,
            "version": self.version,
            "checks": {name: result.to_dict() for name, result in results.items()},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def full_health(self) -> dict[str, Any]:
        """Get full health report with all details.

        This is a comprehensive health report including all checks,
        uptime, and detailed status information.

        Returns:
            Dictionary with complete health information.
        """
        results = self.run_all_checks()
        overall = self.get_overall_status(results)

        healthy_count = sum(1 for r in results.values() if r.status == HealthStatus.HEALTHY)
        degraded_count = sum(1 for r in results.values() if r.status == HealthStatus.DEGRADED)
        unhealthy_count = sum(1 for r in results.values() if r.status == HealthStatus.UNHEALTHY)

        return {
            "status": overall.value,
            "service": self.service_name,
            "version": self.version,
            "uptime_seconds": round(time.time() - self._startup_time, 2),
            "summary": {
                "total_checks": len(results),
                "healthy": healthy_count,
                "degraded": degraded_count,
                "unhealthy": unhealthy_count,
            },
            "checks": {name: result.to_dict() for name, result in results.items()},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def to_json(self, include_all: bool = True) -> str:
        """Export health status as JSON.

        Args:
            include_all: If True, returns full health. If False, returns readiness.

        Returns:
            JSON string of health status.
        """
        if include_all:
            return json.dumps(self.full_health(), indent=2)
        return json.dumps(self.readiness(), indent=2)

    def _check_liveness(self) -> HealthCheckResult:
        """Built-in liveness check.

        This always returns healthy as long as the process is running.
        """
        return HealthCheckResult(
            name="liveness",
            status=HealthStatus.HEALTHY,
            message="Service is alive",
            details={"uptime_seconds": round(time.time() - self._startup_time, 2)},
        )

    def _check_readiness(self) -> HealthCheckResult:
        """Built-in readiness check.

        This returns healthy as a baseline. Override or add additional
        checks for actual readiness verification.
        """
        return HealthCheckResult(
            name="readiness",
            status=HealthStatus.HEALTHY,
            message="Service is ready",
        )

    def shutdown(self) -> None:
        """Shutdown the health check executor.

        Call this during graceful shutdown to clean up resources.
        """
        self._executor.shutdown(wait=False)


def create_database_health_check(
    name: str,
    connection_func: Callable[[], Any],
    query: str = "SELECT 1",
) -> HealthCheckFunc:
    """Create a database health check function.

    Args:
        name: Name for the health check.
        connection_func: Function that returns a database connection.
        query: SQL query to execute (default: "SELECT 1").

    Returns:
        A health check function.

    Example:
        >>> def get_db_connection():
        ...     return psycopg.connect(DATABASE_URL)
        >>> health.register("postgres", create_database_health_check(
        ...     "postgres", get_db_connection
        ... ))
    """

    def check() -> HealthCheckResult:
        start_time = time.time()
        try:
            conn = connection_func()
            if hasattr(conn, "execute"):
                conn.execute(query)
            elif hasattr(conn, "cursor"):
                cursor = conn.cursor()
                cursor.execute(query)
                cursor.close()
            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message="Database connection successful",
                duration_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Database check failed: {e}",
                duration_ms=(time.time() - start_time) * 1000,
                details={"exception": str(e), "exception_type": type(e).__name__},
            )

    return check


def create_http_health_check(
    name: str,
    url: str,
    expected_status: int = 200,
    timeout_seconds: float = 5.0,
    expected_body: str | None = None,
) -> HealthCheckFunc:
    """Create an HTTP endpoint health check function.

    Args:
        name: Name for the health check.
        url: URL to check.
        expected_status: Expected HTTP status code (default: 200).
        timeout_seconds: Request timeout in seconds.
        expected_body: Optional string that must be in response body.

    Returns:
        A health check function.

    Example:
        >>> health.register("api", create_http_health_check(
        ...     "api", "https://api.example.com/health", timeout_seconds=3.0
        ... ))
    """

    def check() -> HealthCheckResult:
        import httpx

        start_time = time.time()
        try:
            response = httpx.get(url, timeout=timeout_seconds)
            duration_ms = (time.time() - start_time) * 1000

            details: dict[str, Any] = {
                "status_code": response.status_code,
                "url": url,
                "response_time_ms": round(duration_ms, 2),
            }

            if response.status_code == expected_status:
                if expected_body and expected_body not in response.text:
                    return HealthCheckResult(
                        name=name,
                        status=HealthStatus.DEGRADED,
                        message="Response body missing expected content",
                        duration_ms=duration_ms,
                        details=details,
                    )
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    message=f"HTTP {response.status_code}",
                    duration_ms=duration_ms,
                    details=details,
                )
            else:
                details["expected_status"] = expected_status
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.DEGRADED
                    if response.status_code < 500
                    else HealthStatus.UNHEALTHY,
                    message=f"Unexpected status: {response.status_code}",
                    duration_ms=duration_ms,
                    details=details,
                )
        except httpx.TimeoutException:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"HTTP request timed out after {timeout_seconds}s",
                duration_ms=(time.time() - start_time) * 1000,
                details={"url": url, "timeout_seconds": timeout_seconds},
            )
        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"HTTP check failed: {e}",
                duration_ms=(time.time() - start_time) * 1000,
                details={"exception": str(e), "url": url},
            )

    return check


def create_tcp_health_check(
    name: str,
    host: str,
    port: int,
    timeout_seconds: float = 5.0,
) -> HealthCheckFunc:
    """Create a TCP port health check function.

    Args:
        name: Name for the health check.
        host: Hostname or IP address.
        port: TCP port number.
        timeout_seconds: Connection timeout in seconds.

    Returns:
        A health check function.

    Example:
        >>> health.register("redis", create_tcp_health_check(
        ...     "redis", "localhost", 6379
        ... ))
    """

    def check() -> HealthCheckResult:
        import socket

        start_time = time.time()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout_seconds)
            result = sock.connect_ex((host, port))
            sock.close()

            duration_ms = (time.time() - start_time) * 1000

            if result == 0:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    message=f"TCP port {port} is open",
                    duration_ms=duration_ms,
                    details={"host": host, "port": port},
                )
            else:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"TCP port {port} is closed or filtered",
                    duration_ms=duration_ms,
                    details={"host": host, "port": port, "error_code": result},
                )
        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"TCP check failed: {e}",
                duration_ms=(time.time() - start_time) * 1000,
                details={"exception": str(e), "host": host, "port": port},
            )

    return check


def create_memory_health_check(
    name: str = "memory",
    threshold_percent: float = 90.0,
    degraded_threshold_percent: float | None = None,
) -> HealthCheckFunc:
    """Create a memory usage health check function.

    Args:
        name: Name for the health check.
        threshold_percent: Memory usage % considered unhealthy.
        degraded_threshold_percent: Memory usage % considered degraded.

    Returns:
        A health check function.

    Note:
        Requires the 'psutil' package. Returns HEALTHY if not available.
    """
    if degraded_threshold_percent is None:
        degraded_threshold_percent = threshold_percent * 0.8

    def check() -> HealthCheckResult:
        try:
            import psutil

            memory = psutil.virtual_memory()
            percent_used = memory.percent

            details = {
                "percent_used": round(percent_used, 2),
                "total_mb": round(memory.total / (1024 * 1024), 2),
                "available_mb": round(memory.available / (1024 * 1024), 2),
                "used_mb": round(memory.used / (1024 * 1024), 2),
            }

            if percent_used >= threshold_percent:
                status = HealthStatus.UNHEALTHY
                message = f"Memory usage critical: {percent_used:.1f}%"
            elif percent_used >= degraded_threshold_percent:
                status = HealthStatus.DEGRADED
                message = f"Memory usage high: {percent_used:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory usage normal: {percent_used:.1f}%"

            return HealthCheckResult(
                name=name,
                status=status,
                message=message,
                details=details,
            )
        except ImportError:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message="Memory check skipped (psutil not available)",
            )

    return check


def create_disk_health_check(
    name: str = "disk",
    path: str = "/",
    threshold_percent: float = 90.0,
    degraded_threshold_percent: float | None = None,
) -> HealthCheckFunc:
    """Create a disk usage health check function.

    Args:
        name: Name for the health check.
        path: Filesystem path to check.
        threshold_percent: Disk usage % considered unhealthy.
        degraded_threshold_percent: Disk usage % considered degraded.

    Returns:
        A health check function.

    Note:
        Requires the 'psutil' package. Returns HEALTHY if not available.
    """
    if degraded_threshold_percent is None:
        degraded_threshold_percent = threshold_percent * 0.8

    def check() -> HealthCheckResult:
        try:
            import psutil

            disk = psutil.disk_usage(path)
            percent_used = (disk.used / disk.total) * 100

            details = {
                "path": path,
                "percent_used": round(percent_used, 2),
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
            }

            if percent_used >= threshold_percent:
                status = HealthStatus.UNHEALTHY
                message = f"Disk usage critical: {percent_used:.1f}%"
            elif percent_used >= degraded_threshold_percent:
                status = HealthStatus.DEGRADED
                message = f"Disk usage high: {percent_used:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Disk usage normal: {percent_used:.1f}%"

            return HealthCheckResult(
                name=name,
                status=status,
                message=message,
                details=details,
            )
        except ImportError:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message="Disk check skipped (psutil not available)",
            )

    return check


def create_redis_health_check(
    name: str = "redis",
    host: str = "localhost",
    port: int = 6379,
    password: str | None = None,
    db: int = 0,
) -> HealthCheckFunc:
    """Create a Redis health check function.

    Args:
        name: Name for the health check.
        host: Redis host.
        port: Redis port.
        password: Redis password.
        db: Redis database number.

    Returns:
        A health check function.

    Note:
        Requires the 'redis' package. Returns HEALTHY if not available.
    """

    def check() -> HealthCheckResult:
        try:
            import redis

            start_time = time.time()
            client = redis.Redis(host=host, port=port, password=password, db=db)
            result = client.ping()
            duration_ms = (time.time() - start_time) * 1000

            if result:
                info = client.info("server")
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    message="Redis connection successful",
                    duration_ms=duration_ms,
                    details={
                        "redis_version": info.get("redis_version"),
                        "connected_clients": info.get("connected_clients"),
                    },
                )
            else:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message="Redis ping failed",
                    duration_ms=duration_ms,
                )
        except ImportError:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message="Redis check skipped (redis package not available)",
            )
        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Redis check failed: {e}",
                details={"exception": str(e), "host": host, "port": port},
            )

    return check
