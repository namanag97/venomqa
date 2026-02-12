"""Health check endpoints for VenomQA."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class HealthStatus(Enum):
    """Health check status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheckResult:
    """Result of a single health check."""

    name: str
    status: HealthStatus
    message: str = ""
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "durationMs": round(self.duration_ms, 2),
            "details": self.details,
            "timestamp": self.timestamp,
        }


HealthCheckFunc = Callable[[], HealthCheckResult]


@dataclass
class ComponentHealth:
    """Health status of a component."""

    name: str
    check: HealthCheckFunc
    critical: bool = True
    timeout_seconds: float = 5.0
    cache_seconds: float = 0.0
    _last_result: HealthCheckResult | None = field(default=None, repr=False)
    _last_check_time: float = field(default=0.0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class HealthCheck:
    """Centralized health check management."""

    def __init__(self, service_name: str = "venomqa", version: str = "0.1.0") -> None:
        self.service_name = service_name
        self.version = version
        self._components: dict[str, ComponentHealth] = {}
        self._lock = threading.Lock()
        self._startup_time = time.time()

        self._register_default_checks()

    def _register_default_checks(self) -> None:
        """Register default health checks."""
        self.register("liveness", self._check_liveness, critical=True)
        self.register("readiness", self._check_readiness, critical=True)

    def register(
        self,
        name: str,
        check: HealthCheckFunc,
        critical: bool = True,
        timeout_seconds: float = 5.0,
        cache_seconds: float = 0.0,
    ) -> None:
        """Register a health check component."""
        with self._lock:
            self._components[name] = ComponentHealth(
                name=name,
                check=check,
                critical=critical,
                timeout_seconds=timeout_seconds,
                cache_seconds=cache_seconds,
            )

    def unregister(self, name: str) -> None:
        """Unregister a health check."""
        with self._lock:
            self._components.pop(name, None)

    def run_check(self, name: str) -> HealthCheckResult | None:
        """Run a specific health check."""
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
            result = component.check()
            result.duration_ms = (time.time() - start_time) * 1000

            if component.cache_seconds > 0:
                with component._lock:
                    component._last_result = result
                    component._last_check_time = time.time()

            return result

        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                duration_ms=(time.time() - start_time) * 1000,
                details={"exception": str(e)},
            )

    def run_all_checks(self) -> dict[str, HealthCheckResult]:
        """Run all health checks."""
        results = {}
        with self._lock:
            names = list(self._components.keys())

        for name in names:
            result = self.run_check(name)
            if result:
                results[name] = result

        return results

    def get_overall_status(
        self, results: dict[str, HealthCheckResult] | None = None
    ) -> HealthStatus:
        """Get overall health status."""
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
        """Get liveness probe response."""
        return {
            "status": "alive",
            "service": self.service_name,
            "version": self.version,
            "uptime_seconds": round(time.time() - self._startup_time, 2),
        }

    def readiness(self) -> dict[str, Any]:
        """Get readiness probe response."""
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
        """Get full health report."""
        results = self.run_all_checks()
        overall = self.get_overall_status(results)

        return {
            "status": overall.value,
            "service": self.service_name,
            "version": self.version,
            "uptime_seconds": round(time.time() - self._startup_time, 2),
            "checks": {name: result.to_dict() for name, result in results.items()},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def to_json(self, include_all: bool = True) -> str:
        """Export health status as JSON."""
        if include_all:
            return json.dumps(self.full_health(), indent=2)
        return json.dumps(self.readiness(), indent=2)

    def _check_liveness(self) -> HealthCheckResult:
        """Built-in liveness check."""
        return HealthCheckResult(
            name="liveness",
            status=HealthStatus.HEALTHY,
            message="Service is alive",
        )

    def _check_readiness(self) -> HealthCheckResult:
        """Built-in readiness check."""
        return HealthCheckResult(
            name="readiness",
            status=HealthStatus.HEALTHY,
            message="Service is ready",
        )


def create_database_health_check(
    name: str,
    connection_func: Callable[[], Any],
    query: str = "SELECT 1",
) -> HealthCheckFunc:
    """Create a database health check."""

    def check() -> HealthCheckResult:
        start_time = time.time()
        try:
            conn = connection_func()
            if hasattr(conn, "execute"):
                conn.execute(query)
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
                details={"exception": str(e)},
            )

    return check


def create_http_health_check(
    name: str,
    url: str,
    expected_status: int = 200,
    timeout_seconds: float = 5.0,
) -> HealthCheckFunc:
    """Create an HTTP endpoint health check."""

    def check() -> HealthCheckResult:
        import httpx

        start_time = time.time()
        try:
            response = httpx.get(url, timeout=timeout_seconds)
            duration_ms = (time.time() - start_time) * 1000

            if response.status_code == expected_status:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    message=f"HTTP {response.status_code}",
                    duration_ms=duration_ms,
                    details={"status_code": response.status_code, "url": url},
                )
            else:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.DEGRADED,
                    message=f"Unexpected status: {response.status_code}",
                    duration_ms=duration_ms,
                    details={"status_code": response.status_code, "url": url},
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


def create_memory_health_check(
    name: str = "memory",
    threshold_percent: float = 90.0,
) -> HealthCheckFunc:
    """Create a memory usage health check."""

    def check() -> HealthCheckResult:
        try:
            import psutil

            memory = psutil.virtual_memory()
            percent_used = memory.percent

            if percent_used >= threshold_percent:
                status = HealthStatus.UNHEALTHY
                message = f"Memory usage critical: {percent_used:.1f}%"
            elif percent_used >= threshold_percent * 0.8:
                status = HealthStatus.DEGRADED
                message = f"Memory usage high: {percent_used:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory usage normal: {percent_used:.1f}%"

            return HealthCheckResult(
                name=name,
                status=status,
                message=message,
                details={
                    "percent_used": round(percent_used, 2),
                    "total_mb": round(memory.total / (1024 * 1024), 2),
                    "available_mb": round(memory.available / (1024 * 1024), 2),
                    "used_mb": round(memory.used / (1024 * 1024), 2),
                },
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
) -> HealthCheckFunc:
    """Create a disk usage health check."""

    def check() -> HealthCheckResult:
        try:
            import psutil

            disk = psutil.disk_usage(path)
            percent_used = (disk.used / disk.total) * 100

            if percent_used >= threshold_percent:
                status = HealthStatus.UNHEALTHY
                message = f"Disk usage critical: {percent_used:.1f}%"
            elif percent_used >= threshold_percent * 0.8:
                status = HealthStatus.DEGRADED
                message = f"Disk usage high: {percent_used:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Disk usage normal: {percent_used:.1f}%"

            return HealthCheckResult(
                name=name,
                status=status,
                message=message,
                details={
                    "path": path,
                    "percent_used": round(percent_used, 2),
                    "total_gb": round(disk.total / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "used_gb": round(disk.used / (1024**3), 2),
                },
            )
        except ImportError:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message="Disk check skipped (psutil not available)",
            )

    return check
