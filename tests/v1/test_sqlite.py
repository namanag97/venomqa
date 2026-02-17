"""Unit tests for SQLiteAdapter checkpoint/rollback/observe."""

from __future__ import annotations

import sqlite3

import pytest

from venomqa.v1.adapters.sqlite import SQLiteAdapter


@pytest.fixture
def adapter():
    """In-memory SQLite adapter with a test table."""
    a = SQLiteAdapter(":memory:", observe_tables=["items"])
    a.connect()
    a._conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    a._conn.commit()
    yield a
    a.close()


class TestSQLiteAdapterConnect:
    def test_connect(self):
        a = SQLiteAdapter(":memory:")
        a.connect()
        assert a._conn is not None
        a.close()

    def test_close(self):
        a = SQLiteAdapter(":memory:")
        a.connect()
        a.close()
        assert a._conn is None

    def test_context_manager(self):
        with SQLiteAdapter(":memory:") as a:
            assert a._conn is not None


class TestSQLiteAdapterObserve:
    def test_observe_empty_table(self, adapter):
        obs = adapter.observe()
        assert obs.data["items_count"] == 0

    def test_observe_after_insert(self, adapter):
        adapter._conn.execute("INSERT INTO items (name) VALUES ('hello')")
        adapter._conn.commit()
        obs = adapter.observe()
        assert obs.data["items_count"] == 1

    def test_observe_no_tables(self):
        a = SQLiteAdapter(":memory:")
        a.connect()
        obs = a.observe()
        assert obs.data == {}
        a.close()

    def test_observe_system_field(self, adapter):
        obs = adapter.observe()
        assert obs.system == "db"


class TestSQLiteAdapterCheckpointRollback:
    def test_checkpoint_returns_id(self, adapter):
        cp = adapter.checkpoint("test")
        assert cp is not None

    def test_rollback_restores_state(self, adapter):
        # Checkpoint before insert
        cp = adapter.checkpoint("before")

        # Insert a row
        adapter._conn.execute("INSERT INTO items (name) VALUES ('new_item')")
        adapter._conn.commit()
        assert adapter.observe().data["items_count"] == 1

        # Rollback — row should be gone
        adapter.rollback(cp)
        assert adapter.observe().data["items_count"] == 0

    def test_multiple_checkpoints(self, adapter):
        cp1 = adapter.checkpoint("cp1")
        adapter._conn.execute("INSERT INTO items (name) VALUES ('a')")
        adapter._conn.commit()

        cp2 = adapter.checkpoint("cp2")
        adapter._conn.execute("INSERT INTO items (name) VALUES ('b')")
        adapter._conn.commit()
        assert adapter.observe().data["items_count"] == 2

        # Rollback to cp2 — should have 1 row
        adapter.rollback(cp2)
        assert adapter.observe().data["items_count"] == 1

        # Rollback to cp1 — should have 0 rows
        adapter.rollback(cp1)
        assert adapter.observe().data["items_count"] == 0

    def test_rollback_invalid_raises(self, adapter):
        with pytest.raises(Exception):
            adapter.rollback("invalid_checkpoint_that_does_not_exist")


class TestSQLiteAdapterExecute:
    def test_execute_query(self, adapter):
        adapter._conn.execute("INSERT INTO items (name) VALUES ('x')")
        adapter._conn.commit()
        rows = adapter.execute("SELECT name FROM items")
        assert rows[0][0] == "x"

    def test_execute_with_params(self, adapter):
        adapter._conn.execute("INSERT INTO items (name) VALUES ('test')")
        adapter._conn.commit()
        rows = adapter.execute("SELECT name FROM items WHERE name = ?", ("test",))
        assert len(rows) == 1
