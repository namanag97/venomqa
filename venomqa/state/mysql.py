"""MySQL state manager using SQL savepoints."""

from __future__ import annotations

import logging
from typing import Any

from venomqa.state.base import BaseStateManager

logger = logging.getLogger(__name__)


class MySQLStateManager(BaseStateManager):
    """MySQL state manager using SQL SAVEPOINT for state branching.

    Limitations:
    - MySQL savepoints do not support releasing (RELEASE SAVEPOINT exists but
      is advisory; memory is freed when transaction ends)
    - DDL statements (ALTER TABLE, CREATE INDEX, etc.) cause implicit commits,
      breaking savepoint rollback
    - Some storage engines (MyISAM) do not support transactions/savepoints
    - Maximum savepoint name length is 64 characters
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
        self._conn: Any = None
        self._in_transaction = False

    def connect(self) -> None:
        """Establish connection to MySQL database."""
        try:
            import mysql.connector

            config = self._parse_connection_url()
            self._conn = mysql.connector.connect(**config)
            self._conn.autocommit = False
            self._connected = True
            logger.info(f"Connected to MySQL database: {config.get('database', 'unknown')}")
        except ImportError:
            raise ImportError(
                "mysql-connector-python is required. "
                "Install with: pip install mysql-connector-python"
            ) from None
        except Exception as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            raise

    def disconnect(self) -> None:
        """Close MySQL connection."""
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
            cursor = self._conn.cursor()
            cursor.execute("START TRANSACTION")
            cursor.close()
            self._in_transaction = True

    def checkpoint(self, name: str) -> None:
        """Create a SQL SAVEPOINT."""
        self._ensure_transaction()
        safe_name = self._sanitize_name(name)

        cursor = self._conn.cursor()
        cursor.execute(f"SAVEPOINT {safe_name}")
        cursor.close()
        self._checkpoints.append(safe_name)
        logger.debug(f"Created checkpoint: {safe_name}")

    def rollback(self, name: str) -> None:
        """Rollback to a SAVEPOINT."""
        self._ensure_transaction()
        safe_name = self._sanitize_name(name)

        if safe_name not in self._checkpoints:
            raise ValueError(f"Checkpoint '{name}' not found")

        cursor = self._conn.cursor()
        cursor.execute(f"ROLLBACK TO SAVEPOINT {safe_name}")
        cursor.close()
        idx = self._checkpoints.index(safe_name)
        self._checkpoints = self._checkpoints[: idx + 1]
        logger.debug(f"Rolled back to checkpoint: {safe_name}")

    def release(self, name: str) -> None:
        """Release a SAVEPOINT.

        Note: In MySQL, RELEASE SAVEPOINT removes the savepoint definition but
        does not free resources until transaction ends. This is a MySQL limitation.
        """
        self._ensure_transaction()
        safe_name = self._sanitize_name(name)

        if self._conn:
            cursor = self._conn.cursor()
            cursor.execute(f"RELEASE SAVEPOINT {safe_name}")
            cursor.close()
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
                cursor = self._conn.cursor()
                cursor.execute("START TRANSACTION")
                for table in tables:
                    cursor.execute(f"TRUNCATE TABLE {table}")
                self._conn.commit()
                cursor.close()
                logger.info(f"Reset {len(tables)} tables: {', '.join(tables)}")

            self._checkpoints.clear()

    def commit(self) -> None:
        """Commit current transaction."""
        if self._conn and self._in_transaction:
            self._conn.commit()
            self._in_transaction = False
            self._checkpoints.clear()

    def _parse_connection_url(self) -> dict[str, Any]:
        """Parse MySQL connection URL to config dict.

        Supports formats:
        - mysql://user:pass@host:port/database
        - mysql://user:pass@host/database
        - mysql://host/database
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

        if "/" in host_part:
            host_port, database = host_part.split("/", 1)
            config["database"] = database
            if ":" in host_port:
                host, port = host_port.split(":", 1)
                config["host"] = host
                config["port"] = int(port)
            else:
                config["host"] = host_port
        else:
            config["host"] = host_part

        return config

    def _get_tables_to_reset(self) -> list[str]:
        """Get list of tables to reset."""
        if self.tables_to_reset:
            return [t for t in self.tables_to_reset if t not in self.exclude_tables]

        if not self._conn:
            return []

        cursor = self._conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return [t for t in tables if t not in self.exclude_tables]

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitize checkpoint name for SQL safety (MySQL max 64 chars)."""
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
        if safe and safe[0].isdigit():
            safe = "sp_" + safe
        return f"chk_{safe}"[:64]
