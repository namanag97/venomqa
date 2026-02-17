"""Unit tests for venomqa.v1.core.observers helper functions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from venomqa.v1.core.observers import (
    COMMON_QUERIES,
    aggregate,
    column_value,
    combine_observers,
    has_rows,
    latest_row,
    row_with_status,
)


def _make_adapter(execute_return=None):
    """Create a mock PostgresAdapter."""
    adapter = MagicMock()
    adapter.execute.return_value = execute_return or []
    return adapter


class TestHasRows:
    def test_has_rows_true(self):
        adapter = _make_adapter(execute_return=[(True,)])
        observer = has_rows("users")
        result = observer(adapter)
        assert result == {"has_users": True}

    def test_has_rows_false(self):
        adapter = _make_adapter(execute_return=[(False,)])
        observer = has_rows("users")
        result = observer(adapter)
        assert result == {"has_users": False}

    def test_has_rows_empty_result(self):
        adapter = _make_adapter(execute_return=[])
        observer = has_rows("orders")
        result = observer(adapter)
        assert result == {"has_orders": False}

    def test_has_rows_uses_table_name(self):
        adapter = _make_adapter(execute_return=[(True,)])
        observer = has_rows("invoices")
        result = observer(adapter)
        assert "has_invoices" in result


class TestLatestRow:
    def test_latest_row_found(self):
        adapter = _make_adapter(execute_return=[(42,)])
        observer = latest_row("orders")
        result = observer(adapter)
        assert result == {"latest_orders_id": 42}

    def test_latest_row_empty_table(self):
        adapter = _make_adapter(execute_return=[])
        observer = latest_row("orders")
        result = observer(adapter)
        assert result == {"latest_orders_id": None}

    def test_latest_row_custom_id_column(self):
        adapter = _make_adapter(execute_return=[(99,)])
        observer = latest_row("payments", id_column="payment_id")
        result = observer(adapter)
        assert result == {"latest_payments_payment_id": 99}


class TestRowWithStatus:
    def test_row_with_status_exists(self):
        adapter = _make_adapter(execute_return=[(True,)])
        observer = row_with_status("orders", "status", "pending")
        result = observer(adapter)
        assert result == {"has_pending_orders": True}

    def test_row_with_status_missing(self):
        adapter = _make_adapter(execute_return=[(False,)])
        observer = row_with_status("orders", "status", "pending")
        result = observer(adapter)
        assert result == {"has_pending_orders": False}

    def test_row_with_status_custom_values(self):
        adapter = _make_adapter(execute_return=[(True,)])
        observer = row_with_status("invoices", "state", "paid")
        result = observer(adapter)
        assert "has_paid_invoices" in result


class TestColumnValue:
    def test_column_value_found(self):
        adapter = _make_adapter(execute_return=[("alice@example.com",)])
        observer = column_value("users", "email")
        result = observer(adapter)
        assert result == {"users_email": "alice@example.com"}

    def test_column_value_not_found(self):
        adapter = _make_adapter(execute_return=[])
        observer = column_value("users", "email")
        result = observer(adapter)
        assert result == {"users_email": None}

    def test_column_value_custom_name(self):
        adapter = _make_adapter(execute_return=[("test@example.com",)])
        observer = column_value("users", "email", name="current_email")
        result = observer(adapter)
        assert "current_email" in result


class TestAggregate:
    def test_aggregate_sum(self):
        adapter = _make_adapter(execute_return=[(1234.56,)])
        observer = aggregate("orders", "SUM", "total")
        result = observer(adapter)
        assert result == {"orders_sum_total": 1234.56}

    def test_aggregate_count(self):
        adapter = _make_adapter(execute_return=[(7,)])
        observer = aggregate("orders", "COUNT", "id", name="order_count")
        result = observer(adapter)
        assert result == {"order_count": 7}

    def test_aggregate_empty(self):
        adapter = _make_adapter(execute_return=[])
        observer = aggregate("orders", "SUM", "total")
        result = observer(adapter)
        assert list(result.values())[0] is None


class TestCombineObservers:
    def test_combine_merges_results(self):
        def obs1(adapter):
            return {"a": 1}

        def obs2(adapter):
            return {"b": 2}

        combined = combine_observers(obs1, obs2)
        result = combined(MagicMock())
        assert result == {"a": 1, "b": 2}

    def test_combine_single(self):
        def obs(adapter):
            return {"x": 42}

        combined = combine_observers(obs)
        result = combined(MagicMock())
        assert result == {"x": 42}

    def test_combine_later_overrides_earlier(self):
        def obs1(adapter):
            return {"key": "first"}

        def obs2(adapter):
            return {"key": "second"}

        combined = combine_observers(obs1, obs2)
        result = combined(MagicMock())
        assert result["key"] == "second"


class TestCommonQueries:
    def test_common_queries_is_dict(self):
        assert isinstance(COMMON_QUERIES, dict)

    def test_common_queries_has_user_count(self):
        assert "user_count" in COMMON_QUERIES

    def test_common_queries_are_strings(self):
        for key, value in COMMON_QUERIES.items():
            assert isinstance(key, str)
            assert isinstance(value, str)
            assert "SELECT" in value.upper()
