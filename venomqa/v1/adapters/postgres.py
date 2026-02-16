"""PostgreSQL adapter with savepoint-based rollback."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import SystemCheckpoint


class PostgresAdapter:
    """PostgreSQL adapter using savepoints for checkpoint/rollback.

    This adapter wraps a PostgreSQL connection and provides:
    - checkpoint(): Creates a savepoint
    - rollback(): Rolls back to a savepoint
    - observe(): Queries configured tables
    """

    def __init__(
        self,
        connection_string: str,
        observe_tables: list[str] | None = None,
    ) -> None:
        self.connection_string = connection_string
        self.observe_tables = observe_tables or []
        self._conn: Any = None
        self._savepoint_counter = 0

    def connect(self) -> None:
        """Connect to the database."""
        try:
            import psycopg2
            self._conn = psycopg2.connect(self.connection_string)
            self._conn.autocommit = False
        except ImportError:
            raise ImportError("psycopg2 is required for PostgresAdapter")

    def close(self) -> None:
        """Close the connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Create a savepoint."""
        if not self._conn:
            self.connect()

        self._savepoint_counter += 1
        savepoint_name = f"venom_{name}_{self._savepoint_counter}"

        with self._conn.cursor() as cur:
            cur.execute(f"SAVEPOINT {savepoint_name}")

        return savepoint_name

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Roll back to a savepoint."""
        if not self._conn:
            raise RuntimeError("Not connected")

        savepoint_name = checkpoint
        with self._conn.cursor() as cur:
            cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")

    def observe(self) -> Observation:
        """Query tables and return observation."""
        if not self._conn:
            self.connect()

        data: dict[str, Any] = {}
        with self._conn.cursor() as cur:
            for table in self.observe_tables:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                data[f"{table}_count"] = count

        return Observation(
            system="db",
            data=data,
            observed_at=datetime.now(),
        )

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
        """Execute a query and return results."""
        if not self._conn:
            self.connect()

        with self._conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchall()
            return []

    def commit(self) -> None:
        """Commit the transaction."""
        if self._conn:
            self._conn.commit()

    def __enter__(self) -> PostgresAdapter:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
