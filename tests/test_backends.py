"""Tests for all database backends in VenomQA."""

from __future__ import annotations

from abc import abstractmethod
from unittest.mock import MagicMock, patch

import pytest

from venomqa.errors import RollbackError, StateNotConnectedError
from venomqa.state.base import BaseStateManager, StateManager
from venomqa.state.postgres import PostgreSQLStateManager


class TestStateManagerProtocol:
    """Tests for StateManager protocol compliance."""

    def test_protocol_has_required_methods(self) -> None:
        required_methods = [
            "connect",
            "disconnect",
            "checkpoint",
            "rollback",
            "release",
            "reset",
            "is_connected",
        ]

        for method in required_methods:
            assert hasattr(StateManager, method)


class TestBaseStateManager:
    """Tests for BaseStateManager abstract class."""

    def test_initialization(self) -> None:
        class ConcreteStateManager(BaseStateManager):
            def connect(self):
                pass

            def disconnect(self):
                pass

            def checkpoint(self, name):
                pass

            def rollback(self, name):
                pass

            def release(self, name):
                pass

            def reset(self):
                pass

        manager = ConcreteStateManager(connection_url="test://localhost/db")

        assert manager.connection_url == "test://localhost/db"
        assert manager._connected is False
        assert manager._checkpoints == []

    def test_is_connected_returns_false_initially(self) -> None:
        class ConcreteStateManager(BaseStateManager):
            def connect(self):
                pass

            def disconnect(self):
                pass

            def checkpoint(self, name):
                pass

            def rollback(self, name):
                pass

            def release(self, name):
                pass

            def reset(self):
                pass

        manager = ConcreteStateManager(connection_url="test://localhost/db")

        assert manager.is_connected() is False

    def test_is_connected_returns_true_after_connect(self) -> None:
        class ConcreteStateManager(BaseStateManager):
            def connect(self):
                self._connected = True

            def disconnect(self):
                pass

            def checkpoint(self, name):
                pass

            def rollback(self, name):
                pass

            def release(self, name):
                pass

            def reset(self):
                pass

        manager = ConcreteStateManager(connection_url="test://localhost/db")
        manager.connect()

        assert manager.is_connected() is True

    def test_ensure_connected_raises_when_not_connected(self) -> None:
        class ConcreteStateManager(BaseStateManager):
            def connect(self):
                pass

            def disconnect(self):
                pass

            def checkpoint(self, name):
                self._ensure_connected()

            def rollback(self, name):
                pass

            def release(self, name):
                pass

            def reset(self):
                pass

        manager = ConcreteStateManager(connection_url="test://localhost/db")

        with pytest.raises(StateNotConnectedError, match="not connected"):
            manager.checkpoint("test")


class TestPostgreSQLStateManager:
    """Tests for PostgreSQL state manager."""

    def test_initialization_with_defaults(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        assert manager.connection_url == "postgresql://localhost/testdb"
        assert manager.tables_to_reset == []
        assert manager.exclude_tables == set()
        assert manager._connected is False
        assert manager._in_transaction is False

    def test_initialization_with_custom_tables(self) -> None:
        manager = PostgreSQLStateManager(
            connection_url="postgresql://localhost/testdb",
            tables_to_reset=["users", "orders"],
            exclude_tables=["migrations", "schema_info"],
        )

        assert manager.tables_to_reset == ["users", "orders"]
        assert manager.exclude_tables == {"migrations", "schema_info"}

    def test_connect_success(self) -> None:
        manager = PostgreSQLStateManager(
            connection_url="postgresql://user:pass@localhost:5432/testdb"
        )

        mock_conn = MagicMock()
        mock_conn.autocommit = True

        with patch("venomqa.state.postgres.psycopg.connect") as mock_connect:
            mock_connect.return_value = mock_conn
            manager.connect()

        assert manager._connected is True
        assert manager._conn is mock_conn
        mock_connect.assert_called_once()

    def test_connect_failure(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        with patch("venomqa.state.postgres.psycopg.connect") as mock_connect:
            mock_connect.side_effect = Exception("Connection refused")

            with pytest.raises(Exception, match="Connection refused"):
                manager.connect()

        assert manager._connected is False

    def test_disconnect_closes_connection(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = True
        manager._checkpoints = ["cp1", "cp2"]

        manager.disconnect()

        mock_conn.rollback.assert_called_once()
        mock_conn.close.assert_called_once()
        assert manager._connected is False
        assert manager._conn is None
        assert manager._in_transaction is False
        assert manager._checkpoints == []

    def test_disconnect_handles_exception(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        mock_conn.close.side_effect = Exception("Close error")
        manager._conn = mock_conn
        manager._connected = True

        manager.disconnect()

        assert manager._connected is False
        assert manager._conn is None

    def test_checkpoint_creates_savepoint(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = True

        manager.checkpoint("after_setup")

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args[0][0]
        assert "SAVEPOINT" in call_args
        assert "chk_after_setup" in call_args
        assert "chk_after_setup" in manager._checkpoints

    def test_checkpoint_sanitizes_name(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = True

        manager.checkpoint("test; DROP TABLE users;")

        call_args = mock_conn.execute.call_args[0][0]
        assert ";" not in call_args

    def test_checkpoint_starts_transaction_if_needed(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = False

        manager.checkpoint("test")

        calls = [call[0][0] for call in mock_conn.execute.call_args_list]
        assert "BEGIN" in calls[0]
        assert any("SAVEPOINT" in call for call in calls)

    def test_rollback_to_savepoint(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = True
        manager._checkpoints = ["chk_after_setup"]

        manager.rollback("after_setup")

        call_args = mock_conn.execute.call_args[0][0]
        assert "ROLLBACK TO SAVEPOINT" in call_args
        assert "chk_after_setup" in call_args

    def test_rollback_nonexistent_checkpoint_raises(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = True
        manager._checkpoints = ["chk_existing"]

        with pytest.raises(RollbackError, match="Checkpoint.*not found"):
            manager.rollback("nonexistent")

    def test_release_checkpoint(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = True
        manager._checkpoints = ["chk_after_setup"]

        manager.release("after_setup")

        call_args = mock_conn.execute.call_args[0][0]
        assert "RELEASE SAVEPOINT" in call_args
        assert "chk_after_setup" not in manager._checkpoints

    def test_reset_truncates_tables(self) -> None:
        manager = PostgreSQLStateManager(
            connection_url="postgresql://localhost/testdb",
            tables_to_reset=["users", "orders"],
        )

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = False
        manager._checkpoints = ["old_checkpoint"]

        manager.reset()

        assert mock_conn.execute.call_count >= 3
        mock_conn.commit.assert_called_once()
        assert manager._checkpoints == []

    def test_reset_ends_active_transaction(self) -> None:
        manager = PostgreSQLStateManager(
            connection_url="postgresql://localhost/testdb",
            tables_to_reset=["users"],
        )

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = True

        manager.reset()

        mock_conn.rollback.assert_called_once()

    def test_reset_excludes_tables(self) -> None:
        manager = PostgreSQLStateManager(
            connection_url="postgresql://localhost/testdb",
            tables_to_reset=["users", "orders", "migrations"],
            exclude_tables=["migrations"],
        )

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True

        manager.reset()

        executed_tables = []
        for call in mock_conn.execute.call_args_list:
            sql = call[0][0]
            if "TRUNCATE" in sql:
                executed_tables.append(sql)

        for sql in executed_tables:
            assert "migrations" not in sql

    def test_commit(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = True
        manager._checkpoints = ["cp1"]

        manager.commit()

        mock_conn.commit.assert_called_once()
        assert manager._in_transaction is False
        assert manager._checkpoints == []

    def test_commit_when_not_in_transaction(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = False

        manager.commit()

        mock_conn.commit.assert_not_called()

    def test_get_tables_to_reset_with_explicit_list(self) -> None:
        manager = PostgreSQLStateManager(
            connection_url="postgresql://localhost/testdb",
            tables_to_reset=["users", "orders"],
            exclude_tables=["orders"],
        )

        tables = manager._get_tables_to_reset()

        assert tables == ["users"]

    def test_get_tables_to_reset_discovery(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"tablename": "users"},
            {"tablename": "orders"},
            {"tablename": "migrations"},
        ]
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        manager._conn = mock_conn
        manager.exclude_tables = {"migrations"}

        tables = manager._get_tables_to_reset()

        assert "users" in tables
        assert "orders" in tables
        assert "migrations" not in tables


class TestSanitizeName:
    """Tests for checkpoint name sanitization."""

    def test_sanitize_simple_name(self) -> None:
        result = PostgreSQLStateManager._sanitize_name("simple_name")
        assert result == "chk_simple_name"

    def test_sanitize_name_with_special_chars(self) -> None:
        result = PostgreSQLStateManager._sanitize_name("test-name; DROP TABLE")
        assert "chk_" in result
        assert "-" not in result
        assert ";" not in result
        assert " " not in result

    def test_sanitize_name_starting_with_digit(self) -> None:
        result = PostgreSQLStateManager._sanitize_name("123_checkpoint")
        assert result.startswith("chk_sp_")

    def test_sanitize_truncates_long_name(self) -> None:
        long_name = "a" * 100
        result = PostgreSQLStateManager._sanitize_name(long_name)
        assert len(result) <= 63

    def test_sanitize_preserves_underscores(self) -> None:
        result = PostgreSQLStateManager._sanitize_name("test_checkpoint_name")
        assert "test_checkpoint_name" in result

    def test_sanitize_empty_name(self) -> None:
        result = PostgreSQLStateManager._sanitize_name("")
        assert result.startswith("chk_")


class TestStateManagerIntegration:
    """Integration tests for state manager workflow."""

    def test_checkpoint_rollback_workflow(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = True

        manager.checkpoint("initial")
        manager.checkpoint("after_create")
        manager.rollback("initial")

        assert manager._checkpoints == ["chk_initial", "chk_after_create"]

    def test_full_lifecycle(self) -> None:
        manager = PostgreSQLStateManager(
            connection_url="postgresql://localhost/testdb",
            tables_to_reset=["test_table"],
        )

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = False

        manager.checkpoint("start")
        manager.checkpoint("middle")
        manager.rollback("start")
        manager.release("start")
        manager.reset()

        assert manager._checkpoints == []

    def test_multiple_checkpoints_tracking(self) -> None:
        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = True

        manager.checkpoint("cp1")
        manager.checkpoint("cp2")
        manager.checkpoint("cp3")

        assert len(manager._checkpoints) == 3
        assert "chk_cp1" in manager._checkpoints
        assert "chk_cp2" in manager._checkpoints
        assert "chk_cp3" in manager._checkpoints


class TestInMemoryStateManager:
    """Tests for in-memory state manager (MockStateManager)."""

    def test_connect_sets_connected_flag(self) -> None:
        from tests.conftest import MockStateManager

        manager = MockStateManager()
        assert manager.is_connected() is False

        manager.connect()
        assert manager.is_connected() is True

    def test_disconnect_clears_connected_flag(self) -> None:
        from tests.conftest import MockStateManager

        manager = MockStateManager()
        manager.connect()
        manager.disconnect()

        assert manager.is_connected() is False

    def test_checkpoint_tracking(self) -> None:
        from tests.conftest import MockStateManager

        manager = MockStateManager()
        manager.connect()

        manager.checkpoint("cp1")
        manager.checkpoint("cp2")

        assert "cp1" in manager._checkpoints
        assert "cp2" in manager._checkpoints

    def test_rollback_validates_checkpoint_exists(self) -> None:
        from tests.conftest import MockStateManager

        manager = MockStateManager()
        manager.connect()

        manager.checkpoint("valid")
        manager.rollback("valid")

        with pytest.raises(ValueError):
            manager.rollback("invalid")

    def test_release_removes_checkpoint(self) -> None:
        from tests.conftest import MockStateManager

        manager = MockStateManager()
        manager.connect()
        manager.checkpoint("to_release")

        manager.release("to_release")

        assert "to_release" not in manager._checkpoints

    def test_reset_clears_all_checkpoints(self) -> None:
        from tests.conftest import MockStateManager

        manager = MockStateManager()
        manager.connect()
        manager.checkpoint("cp1")
        manager.checkpoint("cp2")
        manager.checkpoint("cp3")

        manager.reset()

        assert len(manager._checkpoints) == 0


class TestBackendSwitching:
    """Tests for switching between different backends."""

    @pytest.mark.skip(reason="Requires running PostgreSQL server")
    def test_runner_with_postgres_backend(self) -> None:
        from venomqa.runner import JourneyRunner
        from venomqa.core.models import Journey, Step, Checkpoint

        manager = PostgreSQLStateManager(connection_url="postgresql://localhost/testdb")

        mock_conn = MagicMock()
        manager._conn = mock_conn
        manager._connected = True
        manager._in_transaction = True

        def action(client, ctx):
            return type("Response", (), {"status_code": 200, "is_error": False, "headers": {}})()

        journey = Journey(
            name="backend_test",
            steps=[
                Step(name="step1", action=action),
                Checkpoint(name="cp1"),
            ],
        )

        mock_client = MagicMock()
        mock_client.history = []
        mock_client.last_request.return_value = None

        runner = JourneyRunner(client=mock_client, state_manager=manager)
        result = runner.run(journey)

        assert "chk_cp1" in manager._checkpoints

    def test_runner_with_mock_backend(self) -> None:
        from venomqa.runner import JourneyRunner
        from venomqa.core.models import Journey, Step, Checkpoint
        from tests.conftest import MockStateManager

        manager = MockStateManager()

        def action(client, ctx):
            return type("Response", (), {"status_code": 200, "is_error": False, "headers": {}})()

        journey = Journey(
            name="mock_backend_test",
            steps=[
                Step(name="step1", action=action),
                Checkpoint(name="cp1"),
            ],
        )

        mock_client = MagicMock()
        mock_client.history = []
        mock_client.last_request.return_value = None

        runner = JourneyRunner(client=mock_client, state_manager=manager)
        result = runner.run(journey)

        assert "cp1" in manager._checkpoints
