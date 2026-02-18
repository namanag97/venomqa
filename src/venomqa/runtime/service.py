"""Service - Represents a running service in the test environment."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class HealthStatus(Enum):
    """Health status of a service.

    Values:
        UNKNOWN: Health has not been checked yet.
        STARTING: Service is starting up.
        HEALTHY: Service is responding and healthy.
        UNHEALTHY: Service is running but not healthy.
        STOPPED: Service has stopped.
    """

    UNKNOWN = "unknown"
    STARTING = "starting"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STOPPED = "stopped"


class ServiceType(Enum):
    """Type of service.

    Values:
        API: HTTP API service (the system under test).
        DATABASE: Database service (PostgreSQL, SQLite, etc.).
        CACHE: Cache service (Redis, Memcached, etc.).
        QUEUE: Message queue (RabbitMQ, Kafka, etc.).
        MOCK: Mock/stub service for testing.
        OTHER: Any other service type.
    """

    API = "api"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    MOCK = "mock"
    OTHER = "other"


@dataclass
class Service:
    """A running service in the test environment.

    Represents one component of the system under test, with its
    connection details and health status.

    Example::

        api_service = Service(
            name="my-api",
            type=ServiceType.API,
            endpoint="http://localhost:8000",
        )

        db_service = Service(
            name="postgres",
            type=ServiceType.DATABASE,
            endpoint="postgresql://localhost:5432/testdb",
        )

    Attributes:
        name: Human-readable service name.
        type: The kind of service (API, DATABASE, etc.).
        endpoint: Connection URL or address.
        health: Current health status.
        started_at: When the service was started (or detected).
        metadata: Additional service-specific metadata.
    """

    name: str
    type: ServiceType
    endpoint: str
    health: HealthStatus = HealthStatus.UNKNOWN
    started_at: datetime | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        """True if the service is in a healthy state."""
        return self.health == HealthStatus.HEALTHY

    @property
    def is_available(self) -> bool:
        """True if the service is healthy or starting."""
        return self.health in (HealthStatus.HEALTHY, HealthStatus.STARTING)

    def mark_healthy(self) -> None:
        """Mark this service as healthy."""
        self.health = HealthStatus.HEALTHY

    def mark_unhealthy(self) -> None:
        """Mark this service as unhealthy."""
        self.health = HealthStatus.UNHEALTHY

    def mark_stopped(self) -> None:
        """Mark this service as stopped."""
        self.health = HealthStatus.STOPPED


__all__ = ["HealthStatus", "Service", "ServiceType"]
