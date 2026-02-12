"""SQLite state manager using nested transactions and savepoints."""

from __future__ import annotations

import logging
import sqlite3

from venomqa.state.base import BaseStateManager

logger = logging.getLogger(__name__)


class SQLiteStateManager(BaseStateManager):
    """SQLite state manager using nested transactions and savepoints.

    SQLite supports nested transactions via SAVEPOINT, making it ideal
    for test state management with full rollback capability.
    """

    def __init__(
        self,
        connection_url: str,
        tables_to_reset: list[str] | None = None,
        exclude_tables: list[str] | None = None,
    ) -> None:
        super().__init__(connection_url)
        self.tables_to_reset = tables_to_reset or []
        self.exclude_tables = set(exclude_tables or [])
        self._conn: sqlite3.Connection | None = None
        self._in_transaction = False

    def connect(self) -> None:
        """Establish connection to SQLite database."""
        try:
            db_path = self._parse_connection_url()
            self._conn = sqlite3.connect(db_path, isolation_level=None)
            self._conn.row_factory = sqlite3.Row
            self._connected = True
            logger.info(f"Connected to SQLite database: {db_path}")
        except Exception as e:
            logger.error(f"Failed to connect to SQLite: {e}")
            raise

    def disconnect(self) -> None:
        """Close SQLite connection."""
        if self._conn:
            try:
                if self._in_transaction:
                    self._conn.rollback()
                self._conn.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self._conn = None
                self._connected = False
                self._in_transaction = False
                self._checkpoints.clear()

    def _ensure_transaction(self) -> None:
        """Ensure we're in a transaction for savepoints to work."""
        self._ensure_connected()
        if not self._in_transaction and self._conn:
            self._conn.execute("BEGIN")
            self._in_transaction = True

    def checkpoint(self, name: str) -> None:
        """Create a SQL SAVEPOINT."""
        self._ensure_transaction()
        safe_name = self._sanitize_name(name)

        if self._conn:
            self._conn.execute(f"SAVEPOINT {safe_name}")
            self._checkpoints.append(safe_name)
            logger.debug(f"Created checkpoint: {safe_name}")

    def rollback(self, name: str) -> None:
        """Rollback to a SAVEPOINT."""
        self._ensure_transaction()
        safe_name = self._sanitize_name(name)

        if safe_name not in self._checkpoints:
            raise ValueError(f"Checkpoint '{name}' not found")

        if self._conn:
            self._conn.execute(f"ROLLBACK TO SAVEPOINT {safe_name}")
            idx = self._checkpoints.index(safe_name)
            self._checkpoints = self._checkpoints[: idx + 1]
            logger.debug(f"Rolled back to checkpoint: {safe_name}")

    def release(self, name: str) -> None:
        """Release a SAVEPOINT."""
        self._ensure_transaction()
        safe_name = self._sanitize_name(name)

        if self._conn:
            self._conn.execute(f"RELEASE SAVEPOINT {safe_name}")
            if safe_name in self._checkpoints:
                self._checkpoints.remove(safe_name)
            logger.debug(f"Released checkpoint: {safe_name}")

    def reset(self) -> None:
        """Reset database by truncating specified tables."""
        self._ensure_connected()

        if self._conn:
            if self._in_transaction:
                self._conn.rollback()
                self._in_transaction = False

            tables = self._get_tables_to_reset()
            if tables:
                self._conn.execute("BEGIN")
                for table in tables:
                    self._conn.execute(f"DELETE FROM {table}")
                    self._conn.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")
                self._conn.commit()
                logger.info(f"Reset {len(tables)} tables: {', '.join(tables)}")

            self._checkpoints.clear()

    def commit(self) -> None:
        """Commit current transaction."""
        if self._conn and self._in_transaction:
            self._conn.commit()
            self._in_transaction = False
            self._checkpoints.clear()

    def _parse_connection_url(self) -> str:
        """Parse connection URL to extract database path."""
        if self.connection_url.startswith("sqlite:///"):
            return self.connection_url[10:]
        if self.connection_url.startswith("sqlite://"):
            return self.connection_url[9:]
        return self.connection_url

    def _get_tables_to_reset(self) -> list[str]:
        """Get list of tables to reset."""
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
    def _sanitize_name(name: str) -> str:
        """Sanitize checkpoint name for SQL safety."""
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
        if safe and safe[0].isdigit():
            safe = "sp_" + safe
        return f"chk_{safe}"
