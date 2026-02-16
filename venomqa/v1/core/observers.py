"""Common observation helpers and patterns.

This module provides reusable patterns for defining rich observations
that enable meaningful preconditions and invariants.
"""

from __future__ import annotations

from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from venomqa.v1.adapters.postgres import PostgresAdapter


def has_rows(table: str) -> Callable[["PostgresAdapter"], dict[str, Any]]:
    """Observer that checks if a table has any rows.

    Example:
        adapter.add_custom_observer(has_rows("users"))
        # Adds: {"has_users": True/False}
    """
    def observer(adapter: "PostgresAdapter") -> dict[str, Any]:
        result = adapter.execute(f"SELECT EXISTS(SELECT 1 FROM {table})")
        return {f"has_{table}": result[0][0] if result else False}
    return observer


def latest_row(table: str, id_column: str = "id") -> Callable[["PostgresAdapter"], dict[str, Any]]:
    """Observer that gets the latest row ID from a table.

    Example:
        adapter.add_custom_observer(latest_row("orders"))
        # Adds: {"latest_orders_id": 42}
    """
    def observer(adapter: "PostgresAdapter") -> dict[str, Any]:
        result = adapter.execute(
            f"SELECT {id_column} FROM {table} ORDER BY {id_column} DESC LIMIT 1"
        )
        return {f"latest_{table}_{id_column}": result[0][0] if result else None}
    return observer


def row_with_status(
    table: str,
    status_column: str = "status",
    status_value: str = "pending",
) -> Callable[["PostgresAdapter"], dict[str, Any]]:
    """Observer that checks if any row has a specific status.

    Example:
        adapter.add_custom_observer(row_with_status("orders", "status", "pending"))
        # Adds: {"has_pending_orders": True/False}
    """
    def observer(adapter: "PostgresAdapter") -> dict[str, Any]:
        result = adapter.execute(
            f"SELECT EXISTS(SELECT 1 FROM {table} WHERE {status_column} = %s)",
            (status_value,)
        )
        return {f"has_{status_value}_{table}": result[0][0] if result else False}
    return observer


def column_value(
    table: str,
    column: str,
    where: str | None = None,
    name: str | None = None,
) -> Callable[["PostgresAdapter"], dict[str, Any]]:
    """Observer that gets a specific column value.

    Example:
        adapter.add_custom_observer(
            column_value("users", "email", "id = 1", name="current_user_email")
        )
        # Adds: {"current_user_email": "user@example.com"}
    """
    def observer(adapter: "PostgresAdapter") -> dict[str, Any]:
        query = f"SELECT {column} FROM {table}"
        if where:
            query += f" WHERE {where}"
        query += " LIMIT 1"
        result = adapter.execute(query)
        field_name = name or f"{table}_{column}"
        return {field_name: result[0][0] if result else None}
    return observer


def aggregate(
    table: str,
    agg_func: str,
    column: str,
    where: str | None = None,
    name: str | None = None,
) -> Callable[["PostgresAdapter"], dict[str, Any]]:
    """Observer that runs an aggregate function.

    Example:
        adapter.add_custom_observer(
            aggregate("orders", "SUM", "total", name="total_order_value")
        )
        # Adds: {"total_order_value": 1234.56}
    """
    def observer(adapter: "PostgresAdapter") -> dict[str, Any]:
        query = f"SELECT {agg_func}({column}) FROM {table}"
        if where:
            query += f" WHERE {where}"
        result = adapter.execute(query)
        field_name = name or f"{table}_{agg_func.lower()}_{column}"
        return {field_name: result[0][0] if result else None}
    return observer


# Pre-built common observation queries for PostgresAdapter.observe_queries
COMMON_QUERIES = {
    # User state
    "has_users": "SELECT EXISTS(SELECT 1 FROM users)",
    "user_count": "SELECT COUNT(*) FROM users",

    # Order state
    "has_orders": "SELECT EXISTS(SELECT 1 FROM orders)",
    "has_pending_orders": "SELECT EXISTS(SELECT 1 FROM orders WHERE status = 'pending')",
    "has_completed_orders": "SELECT EXISTS(SELECT 1 FROM orders WHERE status = 'completed')",

    # Session state
    "has_active_sessions": "SELECT EXISTS(SELECT 1 FROM sessions WHERE expires_at > NOW())",
}


def combine_observers(
    *observers: Callable[["PostgresAdapter"], dict[str, Any]]
) -> Callable[["PostgresAdapter"], dict[str, Any]]:
    """Combine multiple observers into one.

    Example:
        adapter.add_custom_observer(
            combine_observers(
                has_rows("users"),
                has_rows("orders"),
                latest_row("orders"),
            )
        )
    """
    def combined(adapter: "PostgresAdapter") -> dict[str, Any]:
        result = {}
        for observer in observers:
            result.update(observer(adapter))
        return result
    return combined
