"""Abstract base class for infrastructure management."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol


class InfrastructureManager(Protocol):
    """Protocol for infrastructure managers - enables different backends."""

    def start(self) -> None:
        """Spin up services."""
        ...

    def stop(self) -> None:
        """Tear down services."""
        ...

    def wait_healthy(self, timeout: float = 60.0) -> bool:
        """Wait for services to be healthy.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            True if healthy within timeout, False otherwise.
        """
        ...

    def logs(self, service_name: str) -> str:
        """Get logs from a specific service.

        Args:
            service_name: Name of the service to get logs from.

        Returns:
            Service logs as string.
        """
        ...

    def is_running(self) -> bool:
        """Check if infrastructure is currently running.

        Returns:
            True if services are up, False otherwise.
        """
        ...


class BaseInfrastructureManager(ABC):
    """Abstract base class for infrastructure managers."""

    def __init__(self, compose_file: str | None = None, project_name: str | None = None) -> None:
        self.compose_file = compose_file
        self.project_name = project_name
        self._running = False

    @abstractmethod
    def start(self) -> None:
        """Spin up services."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Tear down services."""
        pass

    @abstractmethod
    def wait_healthy(self, timeout: float = 60.0) -> bool:
        """Wait for services to be healthy."""
        pass

    @abstractmethod
    def logs(self, service_name: str) -> str:
        """Get logs from a specific service."""
        pass

    @abstractmethod
    def is_running(self) -> bool:
        """Check if infrastructure is currently running."""
        pass

    def _ensure_running(self) -> None:
        if not self._running:
            raise RuntimeError("Infrastructure not running. Call start() first.")
