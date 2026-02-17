"""PostgreSQL state manager using SQL savepoints.

This module provides state management for PostgreSQL databases using the
native SAVEPOINT mechanism. It supports nested transactions and efficient
rollback to any named checkpoint.

Example:
    >>> from venomqa.state import PostgreSQLStateManager
    >>> with PostgreSQLStateManager(
    ...     "postgresql://user:pass@localhost/testdb",
    ...     tables_to_reset=["users", "orders"]
    ... ) as state:
    ...     state.checkpoint("clean_state")
    ...     # Insert test data...
    ...     state.checkpoint("with_test_data")
    ...     # Run tests...
    ...     state.rollback("clean_state")  # Restore clean state
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg
from psycopg.rows import dict_row

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


class PostgreSQLStateManager(BaseStateManager):
    """PostgreSQL state manager using SQL SAVEPOINT for state branching.

    This manager uses PostgreSQL's native SAVEPOINT mechanism to create
    named checkpoints within a transaction. Each checkpoint can be used
    to rollback to that specific point in time.

    PostgreSQL savepoints support:
    - Nested savepoints (savepoints within savepoints)
    - Partial rollback (rollback to savepoint keeps transaction alive)
    - Release savepoints (free resources while keeping transaction)

    Attributes:
        tables_to_reset: List of tables to truncate on reset().
        exclude_tables: Set of tables to exclude from reset.
        _conn: Active psycopg connection.
        _in_transaction: Whether currently in a transaction.

    Example:
        >>> manager = PostgreSQLStateManager(
        ...     "postgresql://localhost/mydb",
        ...     tables_to_reset=["users", "products"],
        ...     exclude_tables=["schema_migrations"]
        ... )
        >>> manager.connect()
        >>> manager.checkpoint("initial")
        >>> # ... make changes ...
        >>> manager.checkpoint("modified")
        >>> # ... more changes ...
        >>> manager.rollback("initial")  # All changes undone
        >>> manager.disconnect()

    Note:
        DDL statements (ALTER TABLE, CREATE INDEX, etc.) in PostgreSQL
        do NOT cause implicit commits, so savepoints work correctly
        even with schema changes.

    Warning:
        Long-running transactions can cause table bloat and prevent
        vacuum cleanup. Use commit() periodically in long test suites.
    """

    MAX_CHECKPOINT_NAME_LENGTH: int = 63

    def __init__(
        self,
        connection_url: str,
        tables_to_reset: list[str] | None = None,
        exclude_tables: list[str] | None = None,
        connection_timeout: int = 30,
    ) -> None:
        """Initialize the PostgreSQL state manager.

        Args:
            connection_url: PostgreSQL connection string.
                Format: postgresql://user:password@host:port/database
            tables_to_reset: List of table names to truncate on reset().
                If empty, all tables in public schema will be discovered.
            exclude_tables: Tables to exclude from reset even if they would
                otherwise be included. Useful for preserving migration tables.
            connection_timeout: Connection timeout in seconds. Defaults to 30.

        Raises:
            ValueError: If connection_url is invalid.
        """
        super().__init__(connection_url)
        self.tables_to_reset: list[str] = tables_to_reset or []
        self.exclude_tables: set[str] = set(exclude_tables or [])
        self.connection_timeout: int = connection_timeout
        self._conn: psycopg.Connection[Any] | None = None
        self._in_transaction: bool = False

    def connect(self) -> None:
        """Establish connection to PostgreSQL.

        Creates a new database connection with dictionary row factory
        for convenient result access. The connection starts in non-autocommit
        mode to enable transaction control.

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
            self._conn = psycopg.connect(
                self.connection_url,
                row_factory=dict_row,
                connect_timeout=self.connection_timeout,
            )
            self._conn.autocommit = False
            self._connected = True
            self._in_transaction = False
            self._checkpoints = []

            safe_url = self._sanitize_url_for_logging(self.connection_url)
            logger.info(f"Connected to PostgreSQL: {safe_url}")

        except Exception as e:
            safe_url = self._sanitize_url_for_logging(self.connection_url)
            logger.error(f"Failed to connect to PostgreSQL ({safe_url}): {e}")
            raise ConnectionError(
                message=f"Failed to connect to PostgreSQL: {e}",
                context=ErrorContext(extra={"connection_url": safe_url}),
                cause=e,
            ) from e

    def disconnect(self) -> None:
        """Close PostgreSQL connection.

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
            logger.info("Disconnected from PostgreSQL")
        except Exception as e:
            logger.warning(f"Error during disconnect: {e}")
        finally:
            self._conn = None
            self._connected = False
            self._in_transaction = False
            self._checkpoints = []

    def _ensure_transaction(self) -> None:
        """Ensure we're in a transaction for savepoints to work.

        PostgreSQL requires an active transaction to use savepoints.
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

        Creates a named savepoint within the current transaction that
        can be used to rollback to this specific point later.

        Args:
            name: Unique identifier for this checkpoint. Will be sanitized
                to ensure SQL safety (alphanumeric + underscore only).
                Maximum length is 63 characters (PostgreSQL limit).

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
                logger.debug(f"Created PostgreSQL savepoint: {safe_name}")
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
                logger.debug(f"Rolled back to PostgreSQL savepoint: {safe_name}")
        except Exception as e:
            logger.error(f"Failed to rollback to checkpoint '{name}': {e}")
            raise RollbackError(
                message=f"Failed to rollback to checkpoint '{name}': {e}",
                context=ErrorContext(extra={"checkpoint_name": name, "safe_name": safe_name}),
                cause=e,
            ) from e

    def release(self, name: str) -> None:
        """Release a SAVEPOINT.

        Releases the named savepoint, freeing any resources associated
        with it. The savepoint can no longer be used for rollback after
        release. The transaction remains active.

        Args:
            name: Name of the checkpoint to release.

        Note:
            In PostgreSQL, releasing a savepoint also releases all savepoints
            created after it. This is handled automatically by removing
            those checkpoints from our tracking list.
        """
        self._ensure_transaction()
        safe_name = self._sanitize_checkpoint_name(name)

        try:
            if self._conn:
                self._conn.execute(f"RELEASE SAVEPOINT {safe_name}")
                if safe_name in self._checkpoints:
                    self._checkpoints.remove(safe_name)
                logger.debug(f"Released PostgreSQL savepoint: {safe_name}")
        except Exception as e:
            logger.warning(f"Failed to release checkpoint '{name}': {e}")

    def reset(self) -> None:
        """Reset database by truncating specified tables.

        Ends any active transaction and truncates all tables in
        tables_to_reset (or all discovered tables if not specified).
        Tables in exclude_tables are preserved.

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
                        self._conn.execute(f"TRUNCATE TABLE {quoted_table} CASCADE")
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
        all savepoints. After commit, a new transaction will be started
        on the next checkpoint() call.

        Note:
            This clears all tracked checkpoints since they only exist
            within the committed transaction.
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

        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                return [dict(row) for row in cur.fetchall()]
            return []

    def _get_tables_to_reset(self) -> list[str]:
        """Get list of tables to reset.

        Returns explicitly configured tables or discovers all tables
        in the public schema, excluding system tables and those in
        exclude_tables.

        Returns:
            List of table names to truncate.
        """
        if self.tables_to_reset:
            return [t for t in self.tables_to_reset if t not in self.exclude_tables]

        if not self._conn:
            return []

        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename NOT LIKE 'pg_%'
                AND tablename NOT LIKE 'sql_%'
                """
            )
            tables = [row["tablename"] for row in cur.fetchall()]
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

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitize a checkpoint name for safe use in SQL.

        Args:
            name: Raw checkpoint name to sanitize.

        Returns:
            Sanitized name safe for use in SQL statements.
        """
        from venomqa.state.base import BaseStateManager

        return BaseStateManager._sanitize_checkpoint_name(name, prefix="chk")

    def get_connection_info(self) -> dict[str, Any]:
        """Get information about the current connection.

        Returns:
            Dictionary with connection details (sanitized for logging).
        """
        info: dict[str, Any] = {
            "connected": self._connected,
            "in_transaction": self._in_transaction,
            "checkpoint_count": len(self._checkpoints),
            "connection_url": self._sanitize_url_for_logging(self.connection_url),
        }

        if self._conn and self._connected:
            try:
                info["server_version"] = self._conn.info.server_version
                info["database"] = self._conn.info.dbname
            except Exception:
                pass

        return info
