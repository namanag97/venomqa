"""Integration tests for PostgresAdapter.

These tests require a running PostgreSQL instance.
Skip if not available.
"""

import os

import pytest

# Skip all tests if no database URL is provided
pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_POSTGRES_URL") is None,
    reason="TEST_POSTGRES_URL environment variable not set"
)


@pytest.fixture
def db_url():
    return os.environ.get("TEST_POSTGRES_URL")


@pytest.fixture
def adapter(db_url):
    from venomqa.adapters.postgres import PostgresAdapter

    adapter = PostgresAdapter(db_url, observe_tables=["test_table"])
    adapter.connect()

    # Setup test table
    adapter.execute("DROP TABLE IF EXISTS test_table")
    adapter.execute("CREATE TABLE test_table (id SERIAL PRIMARY KEY, name TEXT)")
    adapter.commit()

    yield adapter

    # Cleanup
    adapter.execute("DROP TABLE IF EXISTS test_table")
    adapter.commit()
    adapter.close()


class TestPostgresAdapter:
    def test_execute(self, adapter):
        adapter.execute("INSERT INTO test_table (name) VALUES ('test')")
        rows = adapter.execute("SELECT name FROM test_table")
        assert len(rows) == 1
        assert rows[0][0] == "test"

    def test_checkpoint_rollback(self, adapter):
        adapter.execute("INSERT INTO test_table (name) VALUES ('before')")

        cp = adapter.checkpoint("test_savepoint")

        adapter.execute("INSERT INTO test_table (name) VALUES ('after')")
        rows = adapter.execute("SELECT COUNT(*) FROM test_table")
        assert rows[0][0] == 2

        adapter.rollback(cp)

        rows = adapter.execute("SELECT COUNT(*) FROM test_table")
        assert rows[0][0] == 1

    def test_observe(self, adapter):
        adapter.execute("INSERT INTO test_table (name) VALUES ('a')")
        adapter.execute("INSERT INTO test_table (name) VALUES ('b')")

        obs = adapter.observe()
        assert obs.system == "db"
        assert obs.data["test_table_count"] == 2

    def test_multiple_savepoints(self, adapter):
        adapter.execute("INSERT INTO test_table (name) VALUES ('1')")
        cp1 = adapter.checkpoint("cp1")

        adapter.execute("INSERT INTO test_table (name) VALUES ('2')")
        cp2 = adapter.checkpoint("cp2")

        adapter.execute("INSERT INTO test_table (name) VALUES ('3')")

        # Rollback to cp2
        adapter.rollback(cp2)
        rows = adapter.execute("SELECT COUNT(*) FROM test_table")
        assert rows[0][0] == 2

        # Rollback to cp1
        adapter.rollback(cp1)
        rows = adapter.execute("SELECT COUNT(*) FROM test_table")
        assert rows[0][0] == 1
