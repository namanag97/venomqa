"""State management for database savepoints and rollback.

This module provides the base classes and protocols for state management
across different database backends. State managers enable checkpoint-based
state branching, allowing tests to save and restore database state efficiently.

Example:
    >>> from venomqa.state import PostgreSQLStateManager
    >>> manager = PostgreSQLStateManager("postgresql://localhost/testdb")
    >>> manager.connect()
    >>> manager.checkpoint("initial_state")
    >>> # ... perform operations ...
    >>> manager.rollback("initial_state")  # Restore to checkpoint
    >>> manager.disconnect()
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Protocol, TypeVar

from venomqa.errors import StateNotConnectedError

T = TypeVar("T", bound="BaseStateManager")


class StateManager(Protocol):
    """Protocol defining the interface for state managers.

    This protocol enables duck typing for different state management backends.
    Any class implementing these methods can be used as a state manager,
    allowing for custom implementations beyond the built-in backends.

    The protocol follows the checkpoint/savepoint pattern common in databases:
    - checkpoint(name): Create a named savepoint
    - rollback(name): Restore to a previous savepoint
    - release(name): Free resources associated with a savepoint

    Example:
        >>> def run_test(state: StateManager) -> None:
        ...     state.connect()
        ...     state.checkpoint("setup")
        ...     # Run test code...
        ...     state.rollback("setup")
        ...     state.disconnect()
    """

    def connect(self) -> None:
        """Establish connection to the database/service.

        Must be called before any state operations.

        Raises:
            ConnectionError: If connection cannot be established.
        """
        ...

    def disconnect(self) -> None:
        """Close connection to the database/service.

        Should clean up all resources including open transactions.
        Safe to call multiple times.
        """
        ...

    def checkpoint(self, name: str) -> None:
        """Create a savepoint with the given name.

        Args:
            name: Unique identifier for this checkpoint. Will be sanitized
                  for SQL safety (alphanumeric + underscore only).

        Raises:
            StateNotConnectedError: If not connected to database.
            CheckpointError: If checkpoint creation fails.
        """
        ...

    def rollback(self, name: str) -> None:
        """Rollback to a previously created checkpoint.

        Args:
            name: Name of the checkpoint to rollback to.

        Raises:
            StateNotConnectedError: If not connected to database.
            RollbackError: If checkpoint doesn't exist or rollback fails.
        """
        ...

    def release(self, name: str) -> None:
        """Release a checkpoint (free resources).

        Args:
            name: Name of the checkpoint to release.

        Note:
            After release, the checkpoint can no longer be used for rollback.
        """
        ...

    def reset(self) -> None:
        """Reset database to clean state (truncate tables).

        This operation cannot be undone and will clear all data in
        configured tables. Use with caution in production environments.
        """
        ...

    def is_connected(self) -> bool:
        """Check if connection is active.

        Returns:
            True if connected, False otherwise.
        """
        ...


class BaseStateManager(ABC):
    """Abstract base class for state managers with common functionality.

    This class provides shared infrastructure for all state manager
    implementations including connection tracking, checkpoint management,
    and context manager support.

    Subclasses must implement the abstract methods for their specific
    database backend.

    Attributes:
        connection_url: Database connection string.
        _connected: Whether currently connected to database.
        _checkpoints: List of active checkpoint names in order created.

    Example:
        >>> class MyStateManager(BaseStateManager):
        ...     def connect(self) -> None:
        ...         # Implementation
        ...         self._connected = True
        ...
        ...     # ... implement other abstract methods
        >>>
        >>> with MyStateManager("mydb://localhost/test") as state:
        ...     state.checkpoint("start")
        ...     # ... operations ...
        ...     state.rollback("start")
    """

    MAX_CHECKPOINT_NAME_LENGTH: int = 63

    def __init__(self, connection_url: str) -> None:
        """Initialize the state manager.

        Args:
            connection_url: Database connection string. Format varies by backend:
                - PostgreSQL: postgresql://user:pass@host:port/database
                - SQLite: sqlite:///path/to/database.db
                - MySQL: mysql://user:pass@host:port/database
                - Memory: memory://identifier

        Raises:
            ValueError: If connection_url is empty or invalid.
        """
        if not connection_url or not connection_url.strip():
            raise ValueError("connection_url cannot be empty")

        self.connection_url = connection_url.strip()
        self._connected: bool = False
        self._checkpoints: list[str] = []

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the database/service.

        Subclasses should:
        1. Create the database connection
        2. Set self._connected = True on success
        3. Raise appropriate exceptions on failure
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the database/service.

        Subclasses should:
        1. Rollback any active transactions
        2. Close the connection
        3. Clean up resources
        4. Set self._connected = False
        5. Clear self._checkpoints

        Must be safe to call multiple times.
        """
        pass

    @abstractmethod
    def checkpoint(self, name: str) -> None:
        """Create a savepoint with the given name.

        Args:
            name: Unique identifier for this checkpoint.

        Note:
            Subclasses should call _ensure_connected() and sanitize
            the name using _sanitize_checkpoint_name().
        """
        pass

    @abstractmethod
    def rollback(self, name: str) -> None:
        """Rollback to a previously created checkpoint.

        Args:
            name: Name of the checkpoint to rollback to.
        """
        pass

    @abstractmethod
    def release(self, name: str) -> None:
        """Release a checkpoint (free resources).

        Args:
            name: Name of the checkpoint to release.
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset database to clean state.

        Subclasses should:
        1. End any active transactions
        2. Truncate or delete data from tables
        3. Clear self._checkpoints
        """
        pass

    def is_connected(self) -> bool:
        """Check if connection is active.

        Returns:
            True if connected to the database, False otherwise.
        """
        return self._connected

    def _ensure_connected(self) -> None:
        """Verify that the manager is connected to the database.

        Raises:
            StateNotConnectedError: If not connected.
        """
        if not self._connected:
            raise StateNotConnectedError(
                message="StateManager not connected. Call connect() first."
            )

    def _validate_checkpoint_name(self, name: str) -> None:
        """Validate a checkpoint name before use.

        Args:
            name: Checkpoint name to validate.

        Raises:
            ValueError: If name is empty or too long.
        """
        if not name or not name.strip():
            raise ValueError("Checkpoint name cannot be empty")

        if len(name) > self.MAX_CHECKPOINT_NAME_LENGTH:
            raise ValueError(
                f"Checkpoint name too long: max {self.MAX_CHECKPOINT_NAME_LENGTH} characters, "
                f"got {len(name)}"
            )

    @staticmethod
    def _sanitize_checkpoint_name(name: str, prefix: str = "chk") -> str:
        """Sanitize a checkpoint name for safe use in SQL.

        Removes or replaces characters that could be problematic in SQL
        identifiers. Ensures the result is a valid SQL identifier.

        Args:
            name: Raw checkpoint name to sanitize.
            prefix: Prefix to add to the sanitized name (default: "chk").

        Returns:
            Sanitized name safe for use in SQL statements.

        Examples:
            >>> BaseStateManager._sanitize_checkpoint_name("test-checkpoint")
            'chk_test_checkpoint'
            >>> BaseStateManager._sanitize_checkpoint_name("123start")
            'chk_sp_123start'
        """
        sanitized = "".join(c if c.isalnum() or c == "_" else "_" for c in name)

        if sanitized and sanitized[0].isdigit():
            sanitized = "sp_" + sanitized

        return f"{prefix}_{sanitized}"[: BaseStateManager.MAX_CHECKPOINT_NAME_LENGTH]

    @staticmethod
    def _sanitize_url_for_logging(url: str) -> str:
        """Remove credentials from a URL for safe logging.

        Args:
            url: Database connection URL possibly containing credentials.

        Returns:
            URL with password replaced by '***'.

        Examples:
            >>> BaseStateManager._sanitize_url_for_logging("postgresql://user:secret@host/db")
            'postgresql://user:***@host/db'
        """
        if "@" not in url:
            return url

        try:
            protocol, rest = url.split("://", 1)
            if "@" in rest:
                credentials, host_part = rest.rsplit("@", 1)
                if ":" in credentials:
                    user = credentials.split(":", 1)[0]
                    return f"{protocol}://{user}:***@{host_part}"
        except ValueError:
            pass

        return url

    def __enter__(self: T) -> T:
        """Enter context manager, automatically connecting.

        Returns:
            Self for use in with statement.
        """
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit context manager, disconnecting and handling any errors.

        Args:
            exc_type: Exception type if an error occurred.
            exc_val: Exception value if an error occurred.
            exc_tb: Exception traceback if an error occurred.
        """
        self.disconnect()

    def get_active_checkpoints(self) -> list[str]:
        """Get list of currently active checkpoint names.

        Returns:
            Copy of the internal checkpoint list in creation order.
        """
        return list(self._checkpoints)

    def has_checkpoint(self, name: str) -> bool:
        """Check if a checkpoint with the given name exists.

        Args:
            name: Checkpoint name to check.

        Returns:
            True if checkpoint exists, False otherwise.
        """
        return name in self._checkpoints

    def clear_all_checkpoints(self) -> None:
        """Clear all tracked checkpoints without releasing them in database.

        Warning:
            This only clears the internal tracking. It does not release
            the actual database savepoints. Use release() for proper cleanup.
        """
        self._checkpoints.clear()
