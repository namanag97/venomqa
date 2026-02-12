"""State management for database savepoints and rollback."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol


class StateManager(Protocol):
    """Protocol for state managers - enables different backends."""

    def connect(self) -> None:
        """Establish connection to the database/service."""
        ...

    def disconnect(self) -> None:
        """Close connection to the database/service."""
        ...

    def checkpoint(self, name: str) -> None:
        """Create a savepoint with the given name."""
        ...

    def rollback(self, name: str) -> None:
        """Rollback to a previously created checkpoint."""
        ...

    def release(self, name: str) -> None:
        """Release a checkpoint (free resources)."""
        ...

    def reset(self) -> None:
        """Reset database to clean state (truncate tables)."""
        ...

    def is_connected(self) -> bool:
        """Check if connection is active."""
        ...


class BaseStateManager(ABC):
    """Abstract base class for state managers with common functionality."""

    def __init__(self, connection_url: str) -> None:
        self.connection_url = connection_url
        self._connected = False
        self._checkpoints: list[str] = []

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the database/service."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the database/service."""
        pass

    @abstractmethod
    def checkpoint(self, name: str) -> None:
        """Create a savepoint with the given name."""
        pass

    @abstractmethod
    def rollback(self, name: str) -> None:
        """Rollback to a previously created checkpoint."""
        pass

    @abstractmethod
    def release(self, name: str) -> None:
        """Release a checkpoint (free resources)."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset database to clean state."""
        pass

    def is_connected(self) -> bool:
        return self._connected

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("StateManager not connected. Call connect() first.")
