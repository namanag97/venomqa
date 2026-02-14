"""MySQL state manager using SQL savepoints.

This module provides state management for MySQL databases using the
native SAVEPOINT mechanism. It supports nested transactions for test
state management with rollback capability.

Example:
    >>> from venomqa.state import MySQLStateManager
    >>> with MySQLStateManager(
    ...     "mysql://user:pass@localhost/testdb",
    ...     tables_to_reset=["users", "orders"]
    ... ) as state:
    ...     state.checkpoint("clean_state")
    ...     # ... make changes ...
    ...     state.rollback("clean_state")

Warning:
    MySQL has some limitations compared to PostgreSQL:
    - DDL statements (ALTER TABLE, CREATE INDEX, etc.) cause implicit commits
    - Some storage engines (MyISAM) do not support transactions/savepoints
    - Maximum savepoint name length is 64 characters
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs

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


class MySQLStateManager(BaseStateManager):
    """MySQL state manager using SQL SAVEPOINT for state branching.

    This manager uses MySQL's native SAVEPOINT mechanism to create
    named checkpoints within a transaction.

    MySQL Limitations:
    - DDL statements (ALTER TABLE, CREATE INDEX, etc.) cause implicit
      commits, breaking savepoint rollback. Use with caution when tests
      modify schema.
    - RELEASE SAVEPOINT removes the savepoint definition but does not
      free significant resources until transaction ends.
    - MyISAM storage engine does not support transactions - use InnoDB.
    - Maximum savepoint name length is 64 characters.

    Attributes:
        tables_to_reset: List of tables to truncate on reset().
        exclude_tables: Set of tables to exclude from reset.
        _conn: Active MySQL connection.
        _in_transaction: Whether currently in a transaction.

    Example:
        >>> manager = MySQLStateManager(
        ...     "mysql://root@localhost/mydb",
        ...     tables_to_reset=["users"]
        ... )
        >>> manager.connect()
        >>> manager.checkpoint("initial")
        >>> # ... run tests ...
        >>> manager.rollback("initial")
        >>> manager.disconnect()
    """

    MAX_CHECKPOINT_NAME_LENGTH: int = 64

    def __init__(
        self,
        connection_url: str,
        tables_to_reset: list[str] | None = None,
        exclude_tables: list[str] | None = None,
        connection_timeout: int = 30,
        charset: str = "utf8mb4",
    ) -> None:
        """Initialize the MySQL state manager.

        Args:
            connection_url: MySQL connection string.
                Format: mysql://user:password@host:port/database
                Query parameters supported: ?charset=utf8mb4&ssl=true
            tables_to_reset: List of table names to truncate on reset().
                If empty, all tables will be discovered.
            exclude_tables: Tables to exclude from reset.
            connection_timeout: Connection timeout in seconds. Defaults to 30.
            charset: Character set for connection. Defaults to utf8mb4.

        Raises:
            ValueError: If connection_url is invalid.
            ImportError: If mysql-connector-python is not installed.
        """
        super().__init__(connection_url)
        self.tables_to_reset: list[str] = tables_to_reset or []
        self.exclude_tables: set[str] = set(exclude_tables or [])
        self.connection_timeout: int = connection_timeout
        self.charset: str = charset
        self._conn: Any = None
        self._in_transaction: bool = False

    def connect(self) -> None:
        """Establish connection to MySQL database.

        Creates a new database connection with autocommit disabled
        to enable transaction control.

        Raises:
            ConnectionError: If connection cannot be established.
            ImportError: If mysql-connector-python is not installed.
        """
        if self._connected and self._conn:
            logger.warning("Already connected, disconnecting first")
            self.disconnect()

        try:
            import mysql.connector
        except ImportError as e:
            raise ImportError(
                "mysql-connector-python is required for MySQL support. "
                "Install with: pip install mysql-connector-python"
            ) from e

        try:
            config = self._parse_connection_url()
            config["autocommit"] = False
            config["connection_timeout"] = self.connection_timeout

            if "charset" not in config:
                config["charset"] = self.charset

            self._conn = mysql.connector.connect(**config)
            self._connected = True
            self._in_transaction = False
            self._checkpoints = []

            safe_url = self._sanitize_url_for_logging(self.connection_url)
            logger.info(f"Connected to MySQL database: {safe_url}")

        except Exception as e:
            safe_url = self._sanitize_url_for_logging(self.connection_url)
            logger.error(f"Failed to connect to MySQL ({safe_url}): {e}")
            raise ConnectionError(
                message=f"Failed to connect to MySQL: {e}",
                context=ErrorContext(extra={"connection_url": safe_url}),
                cause=e,
            ) from e

    def disconnect(self) -> None:
        """Close MySQL connection.

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
            logger.info("Disconnected from MySQL database")
        except Exception as e:
            logger.warning(f"Error during disconnect: {e}")
        finally:
            self._conn = None
            self._connected = False
            self._in_transaction = False
            self._checkpoints = []

    def _ensure_transaction(self) -> None:
        """Ensure we're in a transaction for savepoints to work.

        MySQL requires an active transaction to use savepoints.
        Uses START TRANSACTION rather than BEGIN for clarity.

        Raises:
            StateNotConnectedError: If not connected to database.
        """
        self._ensure_connected()

        if not self._in_transaction and self._conn:
            cursor = self._conn.cursor()
            try:
                cursor.execute("START TRANSACTION")
                self._in_transaction = True
                logger.debug("Started new transaction")
            finally:
                cursor.close()

    def checkpoint(self, name: str) -> None:
        """Create a SQL SAVEPOINT.

        Creates a named savepoint within the current transaction.

        Args:
            name: Unique identifier for this checkpoint. Will be sanitized
                for SQL safety. Maximum length is 64 characters.

        Raises:
            StateNotConnectedError: If not connected to database.
            CheckpointError: If savepoint creation fails.
            ValueError: If checkpoint name is invalid.
        """
        self._ensure_transaction()
        self._validate_checkpoint_name(name)

        safe_name = self._sanitize_checkpoint_name(name)

        cursor = None
        try:
            cursor = self._conn.cursor()
            cursor.execute(f"SAVEPOINT {safe_name}")
            self._checkpoints.append(safe_name)
            logger.debug(f"Created MySQL savepoint: {safe_name}")
        except Exception as e:
            logger.error(f"Failed to create checkpoint '{name}': {e}")
            raise CheckpointError(
                message=f"Failed to create checkpoint '{name}': {e}",
                context=ErrorContext(extra={"checkpoint_name": name, "safe_name": safe_name}),
                cause=e,
            ) from e
        finally:
            if cursor:
                cursor.close()

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

        cursor = None
        try:
            cursor = self._conn.cursor()
            cursor.execute(f"ROLLBACK TO SAVEPOINT {safe_name}")
            idx = self._checkpoints.index(safe_name)
            self._checkpoints = self._checkpoints[: idx + 1]
            logger.debug(f"Rolled back to MySQL savepoint: {safe_name}")
        except Exception as e:
            logger.error(f"Failed to rollback to checkpoint '{name}': {e}")
            raise RollbackError(
                message=f"Failed to rollback to checkpoint '{name}': {e}",
                context=ErrorContext(extra={"checkpoint_name": name, "safe_name": safe_name}),
                cause=e,
            ) from e
        finally:
            if cursor:
                cursor.close()

    def release(self, name: str) -> None:
        """Release a SAVEPOINT.

        Removes the savepoint definition. Note that in MySQL, this does
        not free significant resources - memory is freed when the
        transaction ends.

        Args:
            name: Name of the checkpoint to release.
        """
        self._ensure_transaction()
        safe_name = self._sanitize_checkpoint_name(name)

        cursor = None
        try:
            cursor = self._conn.cursor()
            cursor.execute(f"RELEASE SAVEPOINT {safe_name}")
            if safe_name in self._checkpoints:
                self._checkpoints.remove(safe_name)
            logger.debug(f"Released MySQL savepoint: {safe_name}")
        except Exception as e:
            logger.warning(f"Failed to release checkpoint '{name}': {e}")
        finally:
            if cursor:
                cursor.close()

    def reset(self) -> None:
        """Reset database by truncating specified tables.

        Ends any active transaction and truncates all tables in
        tables_to_reset. Tables in exclude_tables are preserved.

        Raises:
            ResetError: If reset operation fails.

        Warning:
            This operation cannot be undone. TRUNCATE is faster than DELETE
            but cannot be rolled back within a transaction in MySQL.
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
                    cursor = None
                    try:
                        cursor = self._conn.cursor()
                        cursor.execute("START TRANSACTION")
                        for table in tables:
                            quoted_table = self._quote_identifier(table)
                            cursor.execute(f"TRUNCATE TABLE {quoted_table}")
                        self._conn.commit()
                        logger.info(f"Reset {len(tables)} tables: {', '.join(tables)}")
                    finally:
                        if cursor:
                            cursor.close()

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

        cursor = None
        try:
            cursor = self._conn.cursor(dictionary=True)
            cursor.execute(sql, params or ())
            if cursor.description:
                return cursor.fetchall() or []
            return []
        finally:
            if cursor:
                cursor.close()

    def _parse_connection_url(self) -> dict[str, Any]:
        """Parse MySQL connection URL to config dict.

        Supports various URL formats and query parameters.

        Returns:
            Dictionary with connection configuration.
        """
        url = self.connection_url

        if url.startswith("mysql://"):
            url = url[8:]

        config: dict[str, Any] = {}

        if "@" in url:
            auth, host_part = url.split("@", 1)
            if ":" in auth:
                user, password = auth.split(":", 1)
                config["user"] = user
                config["password"] = password
            else:
                config["user"] = auth
        else:
            host_part = url

        if "?" in host_part:
            host_port_db, query_string = host_part.split("?", 1)
            query_params = parse_qs(query_string)
            for key, value in query_params.items():
                if key == "ssl" and value[0].lower() in ("true", "1", "yes"):
                    config["ssl_disabled"] = False
                elif key == "charset":
                    config["charset"] = value[0]
                elif len(value) == 1:
                    config[key] = value[0]
                else:
                    config[key] = value
        else:
            host_port_db = host_part

        if "/" in host_port_db:
            host_port, database = host_port_db.split("/", 1)
            config["database"] = database
            if ":" in host_port:
                host, port = host_port.split(":", 1)
                config["host"] = host
                config["port"] = int(port)
            else:
                config["host"] = host_port
        else:
            config["host"] = host_port_db

        return config

    def _get_tables_to_reset(self) -> list[str]:
        """Get list of tables to reset.

        Returns explicitly configured tables or discovers all tables
        in the current database, excluding system tables and those in
        exclude_tables.

        Returns:
            List of table names to truncate.
        """
        if self.tables_to_reset:
            return [t for t in self.tables_to_reset if t not in self.exclude_tables]

        if not self._conn:
            return []

        cursor = None
        try:
            cursor = self._conn.cursor()
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
            return [t for t in tables if t not in self.exclude_tables]
        finally:
            if cursor:
                cursor.close()

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """Quote a SQL identifier to prevent injection.

        Args:
            identifier: Table or column name to quote.

        Returns:
            Quoted identifier safe for SQL string interpolation.
        """
        return f"`{identifier.replace(chr(96), chr(96) + chr(96))}`"

    def get_server_version(self) -> tuple[int, int, int]:
        """Get MySQL server version.

        Returns:
            Tuple of (major, minor, patch) version numbers.
        """
        self._ensure_connected()

        if not self._conn:
            raise StateNotConnectedError(message="Database connection lost")

        cursor = None
        try:
            cursor = self._conn.cursor()
            cursor.execute("SELECT VERSION()")
            version_str = cursor.fetchone()[0]
            parts = version_str.split(".")
            return (int(parts[0]), int(parts[1]), int(parts[2].split("-")[0]))
        finally:
            if cursor:
                cursor.close()

    def get_table_count(self) -> int:
        """Get the number of tables in the database.

        Returns:
            Number of tables.
        """
        self._ensure_connected()

        if not self._conn:
            raise StateNotConnectedError(message="Database connection lost")

        cursor = None
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()"
            )
            return cursor.fetchone()[0]
        finally:
            if cursor:
                cursor.close()

    def set_foreign_key_checks(self, enabled: bool) -> None:
        """Enable or disable foreign key checks.

        Useful when truncating tables with foreign key constraints.

        Args:
            enabled: True to enable, False to disable.
        """
        self._ensure_connected()

        if not self._conn:
            raise StateNotConnectedError(message="Database connection lost")

        cursor = None
        try:
            cursor = self._conn.cursor()
            cursor.execute(f"SET FOREIGN_KEY_CHECKS = {1 if enabled else 0}")
        finally:
            if cursor:
                cursor.close()
