"""PostgreSQL state manager using savepoints."""

from __future__ import annotations

import logging
from typing import Any

import psycopg
from psycopg.rows import dict_row

from venomqa.state.base import BaseStateManager

logger = logging.getLogger(__name__)


class PostgreSQLStateManager(BaseStateManager):
    """PostgreSQL state manager using SQL SAVEPOINT for state branching."""

    def __init__(
        self,
        connection_url: str,
        tables_to_reset: list[str] | None = None,
        exclude_tables: list[str] | None = None,
    ) -> None:
        super().__init__(connection_url)
        self.tables_to_reset = tables_to_reset or []
        self.exclude_tables = set(exclude_tables or [])
        self._conn: psycopg.Connection[Any] | None = None
        self._in_transaction = False

    def connect(self) -> None:
        """Establish connection to PostgreSQL."""
        try:
            self._conn = psycopg.connect(self.connection_url, row_factory=dict_row)
            self._conn.autocommit = False
            self._connected = True
            logger.info("Connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    def disconnect(self) -> None:
        """Close PostgreSQL connection."""
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
                    self._conn.execute(f"TRUNCATE TABLE {table} CASCADE")
                self._conn.commit()
                logger.info(f"Reset {len(tables)} tables: {', '.join(tables)}")

            self._checkpoints.clear()

    def commit(self) -> None:
        """Commit current transaction."""
        if self._conn and self._in_transaction:
            self._conn.commit()
            self._in_transaction = False
            self._checkpoints.clear()

    def _get_tables_to_reset(self) -> list[str]:
        """Get list of tables to reset."""
        if self.tables_to_reset:
            return [t for t in self.tables_to_reset if t not in self.exclude_tables]

        if not self._conn:
            return []

        with self._conn.cursor() as cur:
            cur.execute("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename NOT LIKE 'pg_%'
                AND tablename NOT LIKE 'sql_%'
            """)
            tables = [row["tablename"] for row in cur.fetchall()]
            return [t for t in tables if t not in self.exclude_tables]

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitize checkpoint name for SQL safety."""
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
        if safe and safe[0].isdigit():
            safe = "sp_" + safe
        return f"chk_{safe}"[:63]
