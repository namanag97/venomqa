"""SQLite state manager using nested transactions and savepoints.

This module provides state management for SQLite databases using the
native SAVEPOINT mechanism. SQLite supports nested transactions via
savepoints, making it ideal for test state management with full rollback.

Example:
    >>> from venomqa.state import SQLiteStateManager
    >>> with SQLiteStateManager(
    ...     "sqlite:///test.db",
    ...     tables_to_reset=["users", "products"]
    ... ) as state:
    ...     state.checkpoint("clean")
    ...     # ... make changes ...
    ...     state.rollback("clean")  # All changes undone
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from venomqa.errors import (
    CheckpointError,
    ConnectionError,
    ErrorContext,
    ResetError,
    RollbackError,
    StateNotConnectedError,
)
from venomqa.state.base import BaseStateManager

logger = logging.getLogger(__name__)


class SQLiteStateManager(BaseStateManager):
    """SQLite state manager using nested transactions and savepoints.

    SQLite supports nested transactions via SAVEPOINT, making it ideal
    for test state management with full rollback capability. Unlike
    PostgreSQL, SQLite savepoints can be truly nested.

    Attributes:
        tables_to_reset: List of tables to truncate on reset().
        exclude_tables: Set of tables to exclude from reset.
        _conn: Active sqlite3 connection.
        _in_transaction: Whether currently in a transaction.

    Example:
        >>> manager = SQLiteStateManager("sqlite:///myapp_test.db")
        >>> manager.connect()
        >>> manager.checkpoint("initial")
        >>> # ... run tests ...
        >>> manager.rollback("initial")
        >>> manager.disconnect()

    Note:
        - SQLite uses DELETE instead of TRUNCATE (which it doesn't support)
        - Auto-increment counters are reset via sqlite_sequence
        - File-based databases persist between test runs unless deleted
    """

    def __init__(
        self,
        connection_url: str,
        tables_to_reset: list[str] | None = None,
        exclude_tables: list[str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the SQLite state manager.

        Args:
            connection_url: SQLite connection string or file path.
                Formats:
                - sqlite:///absolute/path/to/database.db
                - sqlite://relative/path/to/database.db
                - sqlite://:memory: (in-memory database)
                - /absolute/path/to/database.db (plain path)
            tables_to_reset: List of table names to reset on reset().
                If empty, all non-system tables will be discovered.
            exclude_tables: Tables to exclude from reset.
            timeout: Connection timeout in seconds. Defaults to 30.0.

        Raises:
            ValueError: If connection_url is invalid.
        """
        super().__init__(connection_url)
        self.tables_to_reset: list[str] = tables_to_reset or []
        self.exclude_tables: set[str] = set(exclude_tables or [])
        self.timeout: float = timeout
        self._conn: sqlite3.Connection | None = None
        self._in_transaction: bool = False

    def connect(self) -> None:
        """Establish connection to SQLite database.

        Opens the database file or creates an in-memory database.
        Connection is opened with autocommit disabled to enable
        transaction control.

        Raises:
            ConnectionError: If connection cannot be established.

        Example:
            >>> manager.connect()
            >>> assert manager.is_connected()
        """
        if self._connected and self._conn:
            logger.warning("Already connected, disconnecting first")
            self.disconnect()

        try:
            db_path = self._parse_connection_url()
            self._conn = sqlite3.connect(db_path, isolation_level=None, timeout=self.timeout)
            self._conn.row_factory = sqlite3.Row
            self._connected = True
            self._in_transaction = False
            self._checkpoints = []

            logger.info(f"Connected to SQLite database: {db_path}")

        except Exception as e:
            db_path = self._parse_connection_url()
            logger.error(f"Failed to connect to SQLite ({db_path}): {e}")
            raise ConnectionError(
                message=f"Failed to connect to SQLite: {e}",
                context=ErrorContext(extra={"database_path": db_path}),
                cause=e,
            ) from e

    def disconnect(self) -> None:
        """Close SQLite connection.

        Rolls back any active transaction before closing. Safe to call
        multiple times or when already disconnected.
        """
        if not self._conn:
            self._connected = False
            return

        try:
            if self._in_transaction:
                self._conn.rollback()
                logger.debug("Rolled back active transaction on disconnect")
            self._conn.close()
            logger.info("Disconnected from SQLite database")
        except Exception as e:
            logger.warning(f"Error during disconnect: {e}")
        finally:
            self._conn = None
            self._connected = False
            self._in_transaction = False
            self._checkpoints = []

    def _ensure_transaction(self) -> None:
        """Ensure we're in a transaction for savepoints to work.

        SQLite requires an active transaction to use savepoints.
        This method starts a transaction if one isn't already active.

        Raises:
            StateNotConnectedError: If not connected to database.
        """
        self._ensure_connected()

        if not self._in_transaction and self._conn:
            self._conn.execute("BEGIN")
            self._in_transaction = True
            logger.debug("Started new transaction")

    def checkpoint(self, name: str) -> None:
        """Create a SQL SAVEPOINT.

        Creates a named savepoint within the current transaction.

        Args:
            name: Unique identifier for this checkpoint. Will be sanitized
                for SQL safety (alphanumeric + underscore only).

        Raises:
            StateNotConnectedError: If not connected to database.
            CheckpointError: If savepoint creation fails.
            ValueError: If checkpoint name is invalid.
        """
        self._ensure_transaction()
        self._validate_checkpoint_name(name)

        safe_name = self._sanitize_checkpoint_name(name)

        try:
            if self._conn:
                self._conn.execute(f"SAVEPOINT {safe_name}")
                self._checkpoints.append(safe_name)
                logger.debug(f"Created SQLite savepoint: {safe_name}")
        except Exception as e:
            logger.error(f"Failed to create checkpoint '{name}': {e}")
            raise CheckpointError(
                message=f"Failed to create checkpoint '{name}': {e}",
                context=ErrorContext(extra={"checkpoint_name": name, "safe_name": safe_name}),
                cause=e,
            ) from e

    def rollback(self, name: str) -> None:
        """Rollback to a SAVEPOINT.

        Restores the database state to what it was when the checkpoint
        was created. The transaction remains active after rollback.

        Args:
            name: Name of the checkpoint to rollback to.

        Raises:
            StateNotConnectedError: If not connected to database.
            RollbackError: If checkpoint doesn't exist or rollback fails.
        """
        self._ensure_transaction()
        safe_name = self._sanitize_checkpoint_name(name)

        if safe_name not in self._checkpoints:
            raise RollbackError(
                message=f"Checkpoint '{name}' not found",
                context=ErrorContext(
                    extra={
                        "checkpoint_name": name,
                        "safe_name": safe_name,
                        "available_checkpoints": list(self._checkpoints),
                    }
                ),
            )

        try:
            if self._conn:
                self._conn.execute(f"ROLLBACK TO SAVEPOINT {safe_name}")
                idx = self._checkpoints.index(safe_name)
                self._checkpoints = self._checkpoints[: idx + 1]
                logger.debug(f"Rolled back to SQLite savepoint: {safe_name}")
        except Exception as e:
            logger.error(f"Failed to rollback to checkpoint '{name}': {e}")
            raise RollbackError(
                message=f"Failed to rollback to checkpoint '{name}': {e}",
                context=ErrorContext(extra={"checkpoint_name": name, "safe_name": safe_name}),
                cause=e,
            ) from e

    def release(self, name: str) -> None:
        """Release a SAVEPOINT.

        Releases the named savepoint. The savepoint can no longer be
        used for rollback after release.

        Args:
            name: Name of the checkpoint to release.
        """
        self._ensure_transaction()
        safe_name = self._sanitize_checkpoint_name(name)

        try:
            if self._conn:
                self._conn.execute(f"RELEASE SAVEPOINT {safe_name}")
                if safe_name in self._checkpoints:
                    self._checkpoints.remove(safe_name)
                logger.debug(f"Released SQLite savepoint: {safe_name}")
        except Exception as e:
            logger.warning(f"Failed to release checkpoint '{name}': {e}")

    def reset(self) -> None:
        """Reset database by deleting all rows from specified tables.

        Ends any active transaction and clears all tables in tables_to_reset
        (or all discovered tables if not specified). Also resets auto-increment
        counters via sqlite_sequence.

        Raises:
            ResetError: If reset operation fails.

        Warning:
            This operation cannot be undone and will permanently delete
            data from the affected tables.
        """
        self._ensure_connected()

        try:
            if self._conn:
                if self._in_transaction:
                    self._conn.rollback()
                    self._in_transaction = False
                    logger.debug("Rolled back active transaction before reset")

                tables = self._get_tables_to_reset()
                if tables:
                    self._conn.execute("BEGIN")
                    for table in tables:
                        quoted_table = self._quote_identifier(table)
                        self._conn.execute(f"DELETE FROM {quoted_table}")
                        self._conn.execute(
                            "DELETE FROM sqlite_sequence WHERE name=?",
                            (table,),
                        )
                    self._conn.commit()
                    logger.info(f"Reset {len(tables)} tables: {', '.join(tables)}")

                self._checkpoints = []

        except Exception as e:
            logger.error(f"Failed to reset database: {e}")
            raise ResetError(
                message=f"Failed to reset database: {e}",
                context=ErrorContext(
                    extra={
                        "tables_to_reset": self.tables_to_reset,
                        "exclude_tables": list(self.exclude_tables),
                    }
                ),
                cause=e,
            ) from e

    def commit(self) -> None:
        """Commit current transaction.

        Commits all changes made since the transaction began and releases
        all savepoints.
        """
        if self._conn and self._in_transaction:
            self._conn.commit()
            self._in_transaction = False
            self._checkpoints = []
            logger.debug("Committed transaction")

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        """Execute a SQL query and return results.

        Convenience method for running queries within the managed connection.

        Args:
            sql: SQL query to execute.
            params: Optional query parameters for parameterized queries.

        Returns:
            List of result rows as dictionaries.

        Raises:
            StateNotConnectedError: If not connected.
        """
        self._ensure_connected()

        if not self._conn:
            raise StateNotConnectedError(message="Database connection lost")

        cursor = self._conn.execute(sql, params or ())
        if cursor.description:
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]
        return []

    def _parse_connection_url(self) -> str:
        """Parse connection URL to extract database path.

        Supports multiple formats for flexibility.

        Returns:
            Database file path or ':memory:' for in-memory databases.
        """
        url = self.connection_url

        if url.startswith("sqlite:///"):
            path = url[10:]
            return str(Path(path).expanduser().absolute())

        if url.startswith("sqlite://"):
            path = url[9:]
            if path == ":memory:":
                return path
            return str(Path(path).expanduser().absolute())

        if url.startswith("file:"):
            path = url[5:]
            return str(Path(path).expanduser().absolute())

        return url

    def _get_tables_to_reset(self) -> list[str]:
        """Get list of tables to reset.

        Returns explicitly configured tables or discovers all non-system
        tables, excluding those in exclude_tables.

        Returns:
            List of table names to clear.
        """
        if self.tables_to_reset:
            return [t for t in self.tables_to_reset if t not in self.exclude_tables]

        if not self._conn:
            return []

        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        return [t for t in tables if t not in self.exclude_tables]

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """Quote a SQL identifier to prevent injection.

        Args:
            identifier: Table or column name to quote.

        Returns:
            Quoted identifier safe for SQL string interpolation.
        """
        return f'"{identifier.replace(chr(34), chr(34) + chr(34))}"'

    def get_database_path(self) -> str:
        """Get the resolved database file path.

        Returns:
            Absolute path to the database file, or ':memory:'.
        """
        return self._parse_connection_url()

    def get_database_size(self) -> int:
        """Get the size of the database file in bytes.

        Returns:
            File size in bytes, or 0 for in-memory databases.
        """
        db_path = self._parse_connection_url()
        if db_path == ":memory:":
            return 0

        try:
            return Path(db_path).stat().st_size
        except OSError:
            return 0

    def vacuum(self) -> None:
        """Run VACUUM to reclaim unused space.

        Warning:
            VACUUM cannot run inside a transaction. Any active transaction
            will be committed first.
        """
        self._ensure_connected()

        if self._conn:
            if self._in_transaction:
                self._conn.commit()
                self._in_transaction = False
                self._checkpoints = []

            self._conn.execute("VACUUM")
            logger.info("Vacuumed SQLite database")

    def get_table_info(self, table_name: str) -> list[dict[str, Any]]:
        """Get schema information for a table.

        Args:
            table_name: Name of the table to inspect.

        Returns:
            List of column info dictionaries with keys: cid, name, type,
            notnull, dflt_value, pk.
        """
        self._ensure_connected()

        if not self._conn:
            raise StateNotConnectedError(message="Database connection lost")

        cursor = self._conn.execute(f"PRAGMA table_info({self._quote_identifier(table_name)})")
        return [dict(row) for row in cursor.fetchall()]
