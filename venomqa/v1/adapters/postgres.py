"""PostgreSQL adapter with savepoint-based rollback."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import SystemCheckpoint

# Type for custom observation queries
ObservationQuery = Callable[["PostgresAdapter"], dict[str, Any]]


class PostgresAdapter:
    """PostgreSQL adapter using savepoints for checkpoint/rollback.

    This adapter wraps a PostgreSQL connection and provides:
    - checkpoint(): Creates a savepoint
    - rollback(): Rolls back to a savepoint
    - observe(): Queries configured tables

    Rich Observations:
    - Basic: Table row counts (configure via observe_tables)
    - Custom: Add custom queries via add_observation_query()
    - State flags: Track boolean state like "has_users", "order_pending"
    """

    def __init__(
        self,
        connection_string: str,
        observe_tables: list[str] | None = None,
        observe_queries: dict[str, str] | None = None,
    ) -> None:
        """Initialize PostgreSQL adapter.

        Args:
            connection_string: PostgreSQL connection string.
            observe_tables: Tables to count rows for observation.
            observe_queries: Custom SQL queries for observation.
                Key = observation field name
                Value = SQL query (must return single value)
        """
        self.connection_string = connection_string
        self.observe_tables = observe_tables or []
        self._observe_queries = observe_queries or {}
        self._custom_observers: list[ObservationQuery] = []
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

    def add_observation_query(self, name: str, query: str) -> None:
        """Add a custom observation query.

        Args:
            name: Field name in observation data.
            query: SQL query that returns a single value.

        Example:
            adapter.add_observation_query(
                "has_pending_orders",
                "SELECT EXISTS(SELECT 1 FROM orders WHERE status = 'pending')"
            )
        """
        self._observe_queries[name] = query

    def add_custom_observer(self, observer: ObservationQuery) -> None:
        """Add a custom observation function.

        Args:
            observer: Function that receives this adapter and returns
                     dict of observation data.

        Example:
            def observe_user_state(adapter):
                result = adapter.execute("SELECT id, email FROM users LIMIT 1")
                return {"current_user_id": result[0][0] if result else None}

            adapter.add_custom_observer(observe_user_state)
        """
        self._custom_observers.append(observer)

    def observe(self) -> Observation:
        """Query tables and return observation.

        Returns rich observation with:
        - Table counts (from observe_tables)
        - Custom query results (from observe_queries)
        - Custom observer results
        - Metadata (savepoint counter, not used for state identity)
        """
        if not self._conn:
            self.connect()

        data: dict[str, Any] = {}
        metadata: dict[str, Any] = {
            "savepoint_counter": self._savepoint_counter,
        }

        with self._conn.cursor() as cur:
            # Table counts
            for table in self.observe_tables:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                data[f"{table}_count"] = count

            # Custom queries
            for name, query in self._observe_queries.items():
                try:
                    cur.execute(query)
                    result = cur.fetchone()
                    data[name] = result[0] if result else None
                except Exception as e:
                    data[name] = f"ERROR: {e}"

        # Custom observers
        for observer in self._custom_observers:
            try:
                result = observer(self)
                data.update(result)
            except Exception as e:
                data["observer_error"] = str(e)

        return Observation.create(
            system="db",
            data=data,
            metadata=metadata,
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
