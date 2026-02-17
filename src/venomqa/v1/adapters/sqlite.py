"""SQLite adapter with file-copy-based rollback."""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import SystemCheckpoint


class SQLiteAdapter:
    """SQLite adapter using file copy for checkpoint/rollback.

    Unlike PostgreSQL which uses savepoints, SQLite checkpoints work by
    copying the entire database file. This is simple and reliable but
    slower for large databases.

    For in-memory databases (:memory:), we use sqlite3's backup API.
    """

    def __init__(
        self,
        database_path: str,
        observe_tables: list[str] | None = None,
    ) -> None:
        """Initialize the SQLite adapter.

        Args:
            database_path: Path to SQLite database file, or ":memory:"
            observe_tables: Tables to include in observations
        """
        self.database_path = database_path
        self.observe_tables = observe_tables or []
        self._conn: sqlite3.Connection | None = None
        self._is_memory = database_path == ":memory:"
        self._temp_dir = tempfile.mkdtemp(prefix="venomqa_sqlite_")

    def connect(self) -> None:
        """Connect to the database."""
        self._conn = sqlite3.connect(self.database_path)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        """Close the connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn  # type: ignore

    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Create a checkpoint by copying the database file.

        For file-based databases: copy the file
        For in-memory databases: use backup API to temp file
        """
        checkpoint_path = Path(self._temp_dir) / f"{name}_{datetime.now().timestamp()}.db"

        if self._is_memory:
            # Backup in-memory database to file
            backup_conn = sqlite3.connect(str(checkpoint_path))
            self.connection.backup(backup_conn)
            backup_conn.close()
        else:
            # Copy the database file
            # First, ensure all changes are written
            self.connection.execute("PRAGMA wal_checkpoint(FULL)")
            shutil.copy2(self.database_path, checkpoint_path)

        return str(checkpoint_path)

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Restore database from checkpoint file."""
        checkpoint_path = Path(checkpoint)

        if not checkpoint_path.exists():
            raise ValueError(f"Checkpoint file not found: {checkpoint_path}")

        if self._is_memory:
            # For in-memory databases: create a fresh connection and restore
            # backup into it. We cannot use backup() with self.connection as
            # destination while it is still open ("database in use" error).
            new_conn = sqlite3.connect(":memory:")
            new_conn.row_factory = sqlite3.Row
            backup_conn = sqlite3.connect(str(checkpoint_path))
            backup_conn.backup(new_conn)
            backup_conn.close()
            # Swap connections: close old, use new
            if self._conn is not None:
                self._conn.close()
            self._conn = new_conn
        else:
            # Close connection, copy file, reconnect
            self.close()
            shutil.copy2(checkpoint_path, self.database_path)
            self.connect()

    def observe(self) -> Observation:
        """Query tables and return observation."""
        data: dict[str, Any] = {}

        for table in self.observe_tables:
            cursor = self.connection.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            data[f"{table}_count"] = count

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
        cursor = self.connection.execute(query, params or ())
        if cursor.description:
            return cursor.fetchall()
        return []

    def executemany(
        self,
        query: str,
        params_list: list[tuple[Any, ...]],
    ) -> None:
        """Execute a query with multiple parameter sets."""
        self.connection.executemany(query, params_list)

    def commit(self) -> None:
        """Commit the current transaction."""
        self.connection.commit()

    def _get_tables(self) -> list[str]:
        """Get all user tables in the database."""
        cursor = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return [row[0] for row in cursor.fetchall()]

    def cleanup(self) -> None:
        """Clean up temporary checkpoint files."""
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    def __enter__(self) -> SQLiteAdapter:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
        self.cleanup()
