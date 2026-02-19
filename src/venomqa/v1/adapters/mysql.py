"""MySQL adapter with savepoint-based rollback."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import SystemCheckpoint


def _quote_identifier(name: str) -> str:
    """Safely quote a MySQL identifier using backticks.

    Prevents SQL injection by escaping any backticks in the name.
    """
    # Escape any existing backticks by doubling them
    escaped = name.replace("`", "``")
    return f"`{escaped}`"


class MySQLAdapter:
    """MySQL adapter using savepoints for checkpoint/rollback.

    This adapter wraps a MySQL connection and provides:
    - checkpoint(): Creates a savepoint
    - rollback(): Rolls back to a savepoint
    - observe(): Queries configured tables

    Requires: mysql-connector-python or pymysql
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "test",
        observe_tables: list[str] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.observe_tables = observe_tables or []
        self._conn: Any = None
        self._savepoint_counter = 0

    def connect(self) -> None:
        """Connect to the database."""
        try:
            import mysql.connector
            self._conn = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                autocommit=False,
            )
        except ImportError:
            try:
                import pymysql
                self._conn = pymysql.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=self.database,
                    autocommit=False,
                )
            except ImportError:
                raise ImportError(
                    "mysql-connector-python or pymysql is required for MySQLAdapter"
                )

    def close(self) -> None:
        """Close the connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def connection(self) -> Any:
        if self._conn is None:
            self.connect()
        return self._conn

    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Create a savepoint."""
        self._savepoint_counter += 1
        savepoint_name = f"venom_{name}_{self._savepoint_counter}"

        cursor = self.connection.cursor()
        cursor.execute(f"SAVEPOINT {savepoint_name}")
        cursor.close()

        return savepoint_name

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Roll back to a savepoint."""
        savepoint_name = checkpoint
        cursor = self.connection.cursor()
        cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
        cursor.close()

    def observe(self) -> Observation:
        """Query tables and return observation."""
        data: dict[str, Any] = {}
        cursor = self.connection.cursor()

        for table in self.observe_tables:
            # Use _quote_identifier to prevent SQL injection
            safe_table = _quote_identifier(table)
            cursor.execute(f"SELECT COUNT(*) FROM {safe_table}")
            count = cursor.fetchone()[0]
            data[f"{table}_count"] = count

        cursor.close()
        return Observation(
            system="db",
            data=data,
            observed_at=datetime.now(),
        )

    def execute(
        self,
        query: str,
        params: tuple[Any, ...] | None = None,
    ) -> list[tuple[Any, ...]]:
        """Execute a query and return results."""
        cursor = self.connection.cursor()
        cursor.execute(query, params)
        if cursor.description:
            results = cursor.fetchall()
            cursor.close()
            return results
        cursor.close()
        return []

    def commit(self) -> None:
        """Commit the transaction."""
        self.connection.commit()

    def __enter__(self) -> MySQLAdapter:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
