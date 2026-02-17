"""Database assertions for VenomQA.

Provides assertion functions for validating database state, including
row existence, counts, and column values.

Example:
    >>> from venomqa.assertions import assert_row_exists, assert_row_count
    >>> assert_row_exists(db, "users", {"email": "test@example.com"})
    >>> assert_row_count(db, "orders", 5, {"status": "pending"})
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from venomqa.assertions.expect import AssertionFailed


class DatabaseAssertionError(AssertionFailed):
    """Raised when a database assertion fails."""

    pass


@runtime_checkable
class DatabaseConnection(Protocol):
    """Protocol for database connections."""

    def execute(self, query: str, params: tuple | None = None) -> Any:
        """Execute a query and return result."""
        ...

    def fetchone(self, query: str, params: tuple | None = None) -> tuple | None:
        """Fetch one row."""
        ...

    def fetchall(self, query: str, params: tuple | None = None) -> list[tuple]:
        """Fetch all rows."""
        ...

    def fetchval(self, query: str, params: tuple | None = None) -> Any:
        """Fetch single value."""
        ...


def _build_where_clause(conditions: dict[str, Any]) -> tuple[str, tuple]:
    """Build WHERE clause from conditions dict."""
    if not conditions:
        return "", ()

    clauses = []
    params = []
    for key, value in conditions.items():
        if value is None:
            clauses.append(f"{key} IS NULL")
        elif isinstance(value, (list, tuple)):
            placeholders = ", ".join(["%s"] * len(value))
            clauses.append(f"{key} IN ({placeholders})")
            params.extend(value)
        else:
            clauses.append(f"{key} = %s")
            params.append(value)

    return " WHERE " + " AND ".join(clauses), tuple(params)


def assert_row_exists(
    db: DatabaseConnection,
    table: str,
    conditions: dict[str, Any],
    message: str | None = None,
) -> None:
    """Assert at least one row exists matching conditions.

    Args:
        db: Database connection with execute/fetch methods.
        table: Table name to query.
        conditions: Column-value conditions to match.
        message: Custom error message.

    Raises:
        DatabaseAssertionError: If no matching row found.

    Example:
        >>> assert_row_exists(db, "users", {"email": "test@example.com"})
    """
    where_clause, params = _build_where_clause(conditions)
    query = f"SELECT COUNT(*) FROM {table}{where_clause}"

    try:
        count = db.fetchval(query, params) if hasattr(db, "fetchval") else db.execute(query, params)
        if hasattr(count, "fetchone"):
            count = count.fetchone()[0]
    except Exception as e:
        raise DatabaseAssertionError(
            f"Database query failed: {e}",
            actual=str(e),
            expected="successful query",
        ) from e

    if not count or count == 0:
        msg = message or f"No row found in {table} matching {conditions}"
        raise DatabaseAssertionError(
            msg,
            actual=0,
            expected=">= 1",
        )


def assert_row_not_exists(
    db: DatabaseConnection,
    table: str,
    conditions: dict[str, Any],
    message: str | None = None,
) -> None:
    """Assert no row exists matching conditions.

    Args:
        db: Database connection.
        table: Table name to query.
        conditions: Column-value conditions to match.
        message: Custom error message.

    Raises:
        DatabaseAssertionError: If matching row found.

    Example:
        >>> assert_row_not_exists(db, "users", {"email": "deleted@example.com"})
    """
    where_clause, params = _build_where_clause(conditions)
    query = f"SELECT COUNT(*) FROM {table}{where_clause}"

    try:
        count = db.fetchval(query, params) if hasattr(db, "fetchval") else db.execute(query, params)
        if hasattr(count, "fetchone"):
            count = count.fetchone()[0]
    except Exception as e:
        raise DatabaseAssertionError(
            f"Database query failed: {e}",
            actual=str(e),
            expected="successful query",
        ) from e

    if count and count > 0:
        msg = message or f"Found {count} row(s) in {table} matching {conditions}, expected 0"
        raise DatabaseAssertionError(
            msg,
            actual=count,
            expected=0,
        )


def assert_row_count(
    db: DatabaseConnection,
    table: str,
    expected_count: int,
    conditions: dict[str, Any] | None = None,
    message: str | None = None,
) -> int:
    """Assert exact number of rows match conditions.

    Args:
        db: Database connection.
        table: Table name to query.
        expected_count: Expected number of rows.
        conditions: Optional column-value conditions.
        message: Custom error message.

    Returns:
        Actual row count.

    Raises:
        DatabaseAssertionError: If count doesn't match.

    Example:
        >>> assert_row_count(db, "orders", 5, {"status": "pending"})
    """
    where_clause, params = _build_where_clause(conditions or {})
    query = f"SELECT COUNT(*) FROM {table}{where_clause}"

    try:
        count = db.fetchval(query, params) if hasattr(db, "fetchval") else db.execute(query, params)
        if hasattr(count, "fetchone"):
            count = count.fetchone()[0]
    except Exception as e:
        raise DatabaseAssertionError(
            f"Database query failed: {e}",
            actual=str(e),
            expected="successful query",
        ) from e

    actual_count = count or 0
    if actual_count != expected_count:
        msg = message or f"Expected {expected_count} rows in {table}, found {actual_count}"
        if conditions:
            msg += f" matching {conditions}"
        raise DatabaseAssertionError(
            msg,
            actual=actual_count,
            expected=expected_count,
        )

    return actual_count


def assert_row_count_at_least(
    db: DatabaseConnection,
    table: str,
    minimum: int,
    conditions: dict[str, Any] | None = None,
    message: str | None = None,
) -> int:
    """Assert at least N rows match conditions.

    Args:
        db: Database connection.
        table: Table name to query.
        minimum: Minimum expected row count.
        conditions: Optional column-value conditions.
        message: Custom error message.

    Returns:
        Actual row count.

    Raises:
        DatabaseAssertionError: If count below minimum.

    Example:
        >>> assert_row_count_at_least(db, "products", 10)
    """
    where_clause, params = _build_where_clause(conditions or {})
    query = f"SELECT COUNT(*) FROM {table}{where_clause}"

    try:
        count = db.fetchval(query, params) if hasattr(db, "fetchval") else db.execute(query, params)
        if hasattr(count, "fetchone"):
            count = count.fetchone()[0]
    except Exception as e:
        raise DatabaseAssertionError(
            f"Database query failed: {e}",
            actual=str(e),
            expected="successful query",
        ) from e

    actual_count = count or 0
    if actual_count < minimum:
        msg = message or f"Expected at least {minimum} rows in {table}, found {actual_count}"
        raise DatabaseAssertionError(
            msg,
            actual=actual_count,
            expected=f">= {minimum}",
        )

    return actual_count


def assert_row_count_at_most(
    db: DatabaseConnection,
    table: str,
    maximum: int,
    conditions: dict[str, Any] | None = None,
    message: str | None = None,
) -> int:
    """Assert at most N rows match conditions.

    Args:
        db: Database connection.
        table: Table name to query.
        maximum: Maximum expected row count.
        conditions: Optional column-value conditions.
        message: Custom error message.

    Returns:
        Actual row count.

    Raises:
        DatabaseAssertionError: If count above maximum.

    Example:
        >>> assert_row_count_at_most(db, "errors", 0)
    """
    where_clause, params = _build_where_clause(conditions or {})
    query = f"SELECT COUNT(*) FROM {table}{where_clause}"

    try:
        count = db.fetchval(query, params) if hasattr(db, "fetchval") else db.execute(query, params)
        if hasattr(count, "fetchone"):
            count = count.fetchone()[0]
    except Exception as e:
        raise DatabaseAssertionError(
            f"Database query failed: {e}",
            actual=str(e),
            expected="successful query",
        ) from e

    actual_count = count or 0
    if actual_count > maximum:
        msg = message or f"Expected at most {maximum} rows in {table}, found {actual_count}"
        raise DatabaseAssertionError(
            msg,
            actual=actual_count,
            expected=f"<= {maximum}",
        )

    return actual_count


def assert_column_values(
    db: DatabaseConnection,
    table: str,
    column: str,
    expected_values: list[Any],
    conditions: dict[str, Any] | None = None,
    order_by: str | None = None,
    message: str | None = None,
) -> None:
    """Assert column values exactly match expected list.

    Args:
        db: Database connection.
        table: Table name to query.
        column: Column name to check.
        expected_values: Expected list of values.
        conditions: Optional column-value conditions.
        order_by: Optional ORDER BY clause.
        message: Custom error message.

    Raises:
        DatabaseAssertionError: If values don't match.

    Example:
        >>> assert_column_values(db, "products", "name", ["A", "B", "C"])
    """
    where_clause, params = _build_where_clause(conditions or {})
    order_clause = f" ORDER BY {order_by}" if order_by else ""
    query = f"SELECT {column} FROM {table}{where_clause}{order_clause}"

    try:
        rows = db.fetchall(query, params) if hasattr(db, "fetchall") else db.execute(query, params)
        if hasattr(rows, "fetchall"):
            rows = rows.fetchall()
    except Exception as e:
        raise DatabaseAssertionError(
            f"Database query failed: {e}",
            actual=str(e),
            expected="successful query",
        ) from e

    actual_values = [row[0] for row in rows]

    if actual_values != expected_values:
        msg = message or f"Column {column} values mismatch"
        raise DatabaseAssertionError(
            msg,
            actual=actual_values,
            expected=expected_values,
        )


def assert_column_contains(
    db: DatabaseConnection,
    table: str,
    column: str,
    expected_values: list[Any],
    conditions: dict[str, Any] | None = None,
    message: str | None = None,
) -> None:
    """Assert column contains all expected values (order-independent).

    Args:
        db: Database connection.
        table: Table name to query.
        column: Column name to check.
        expected_values: Values that must be present.
        conditions: Optional column-value conditions.
        message: Custom error message.

    Raises:
        DatabaseAssertionError: If any expected value missing.

    Example:
        >>> assert_column_contains(db, "tags", "name", ["python", "testing"])
    """
    where_clause, params = _build_where_clause(conditions or {})
    query = f"SELECT {column} FROM {table}{where_clause}"

    try:
        rows = db.fetchall(query, params) if hasattr(db, "fetchall") else db.execute(query, params)
        if hasattr(rows, "fetchall"):
            rows = rows.fetchall()
    except Exception as e:
        raise DatabaseAssertionError(
            f"Database query failed: {e}",
            actual=str(e),
            expected="successful query",
        ) from e

    actual_values = {row[0] for row in rows}
    expected_set = set(expected_values)
    missing = expected_set - actual_values

    if missing:
        msg = message or f"Column {column} missing values: {missing}"
        raise DatabaseAssertionError(
            msg,
            actual=list(actual_values),
            expected=expected_values,
        )


def assert_column_value_equals(
    db: DatabaseConnection,
    table: str,
    column: str,
    expected: Any,
    conditions: dict[str, Any],
    message: str | None = None,
) -> None:
    """Assert single column value equals expected.

    Args:
        db: Database connection.
        table: Table name to query.
        column: Column name to check.
        expected: Expected value.
        conditions: Conditions to identify row.
        message: Custom error message.

    Raises:
        DatabaseAssertionError: If value doesn't match.

    Example:
        >>> assert_column_value_equals(db, "users", "status", "active", {"id": 1})
    """
    where_clause, params = _build_where_clause(conditions)
    query = f"SELECT {column} FROM {table}{where_clause} LIMIT 1"

    try:
        row = db.fetchone(query, params) if hasattr(db, "fetchone") else db.execute(query, params)
        if hasattr(row, "fetchone"):
            row = row.fetchone()
    except Exception as e:
        raise DatabaseAssertionError(
            f"Database query failed: {e}",
            actual=str(e),
            expected="successful query",
        ) from e

    if row is None:
        msg = message or f"No row found in {table} matching {conditions}"
        raise DatabaseAssertionError(
            msg,
            actual=None,
            expected=expected,
        )

    actual = row[0]
    if actual != expected:
        msg = message or f"Column {column} value {actual!r} != expected {expected!r}"
        raise DatabaseAssertionError(
            msg,
            actual=actual,
            expected=expected,
        )


def assert_column_sum(
    db: DatabaseConnection,
    table: str,
    column: str,
    expected: int | float,
    conditions: dict[str, Any] | None = None,
    message: str | None = None,
) -> None:
    """Assert sum of column equals expected value.

    Args:
        db: Database connection.
        table: Table name to query.
        column: Column name to sum.
        expected: Expected sum value.
        conditions: Optional column-value conditions.
        message: Custom error message.

    Raises:
        DatabaseAssertionError: If sum doesn't match.

    Example:
        >>> assert_column_sum(db, "orders", "total", 1000.0)
    """
    where_clause, params = _build_where_clause(conditions or {})
    query = f"SELECT SUM({column}) FROM {table}{where_clause}"

    try:
        result = (
            db.fetchval(query, params) if hasattr(db, "fetchval") else db.execute(query, params)
        )
        if hasattr(result, "fetchone"):
            result = result.fetchone()[0]
    except Exception as e:
        raise DatabaseAssertionError(
            f"Database query failed: {e}",
            actual=str(e),
            expected="successful query",
        ) from e

    actual = result or 0
    if actual != expected:
        msg = message or f"SUM({column}) = {actual}, expected {expected}"
        raise DatabaseAssertionError(
            msg,
            actual=actual,
            expected=expected,
        )


def assert_column_avg(
    db: DatabaseConnection,
    table: str,
    column: str,
    expected: float,
    tolerance: float = 0.01,
    conditions: dict[str, Any] | None = None,
    message: str | None = None,
) -> None:
    """Assert average of column is within tolerance of expected.

    Args:
        db: Database connection.
        table: Table name to query.
        column: Column name to average.
        expected: Expected average value.
        tolerance: Allowed deviation (default 1%).
        conditions: Optional column-value conditions.
        message: Custom error message.

    Raises:
        DatabaseAssertionError: If average outside tolerance.

    Example:
        >>> assert_column_avg(db, "products", "price", 50.0, tolerance=0.05)
    """
    where_clause, params = _build_where_clause(conditions or {})
    query = f"SELECT AVG({column}) FROM {table}{where_clause}"

    try:
        result = (
            db.fetchval(query, params) if hasattr(db, "fetchval") else db.execute(query, params)
        )
        if hasattr(result, "fetchone"):
            result = result.fetchone()[0]
    except Exception as e:
        raise DatabaseAssertionError(
            f"Database query failed: {e}",
            actual=str(e),
            expected="successful query",
        ) from e

    if result is None:
        raise DatabaseAssertionError(
            f"No rows found to compute average of {column}",
            actual=None,
            expected=expected,
        )

    actual = float(result)
    diff = abs(actual - expected) / expected if expected != 0 else abs(actual)

    if diff > tolerance:
        msg = (
            message
            or f"AVG({column}) = {actual:.4f}, expected ~{expected} (tolerance {tolerance:.0%})"
        )
        raise DatabaseAssertionError(
            msg,
            actual=actual,
            expected=f"{expected} ± {tolerance:.0%}",
        )


def assert_column_unique(
    db: DatabaseConnection,
    table: str,
    column: str,
    conditions: dict[str, Any] | None = None,
    message: str | None = None,
) -> None:
    """Assert column has no duplicate values.

    Args:
        db: Database connection.
        table: Table name to query.
        column: Column name to check.
        conditions: Optional column-value conditions.
        message: Custom error message.

    Raises:
        DatabaseAssertionError: If duplicates found.

    Example:
        >>> assert_column_unique(db, "users", "email")
    """
    where_clause, params = _build_where_clause(conditions or {})
    query = f"""
        SELECT {column}, COUNT(*) as cnt
        FROM {table}{where_clause}
        GROUP BY {column}
        HAVING COUNT(*) > 1
    """

    try:
        rows = db.fetchall(query, params) if hasattr(db, "fetchall") else db.execute(query, params)
        if hasattr(rows, "fetchall"):
            rows = rows.fetchall()
    except Exception as e:
        raise DatabaseAssertionError(
            f"Database query failed: {e}",
            actual=str(e),
            expected="successful query",
        ) from e

    if rows:
        duplicates = [row[0] for row in rows[:5]]
        msg = message or f"Column {column} has duplicate values: {duplicates}"
        raise DatabaseAssertionError(
            msg,
            actual=f"{len(rows)} duplicate values",
            expected="unique values",
        )


def assert_foreign_key_valid(
    db: DatabaseConnection,
    table: str,
    column: str,
    foreign_table: str,
    foreign_column: str = "id",
    conditions: dict[str, Any] | None = None,
    message: str | None = None,
) -> None:
    """Assert all foreign key values reference existing rows.

    Args:
        db: Database connection.
        table: Table containing foreign key.
        column: Foreign key column name.
        foreign_table: Referenced table.
        foreign_column: Referenced column (default "id").
        conditions: Optional conditions on source table.
        message: Custom error message.

    Raises:
        DatabaseAssertionError: If orphaned references found.

    Example:
        >>> assert_foreign_key_valid(db, "orders", "user_id", "users")
    """
    where_clause, params = _build_where_clause(conditions or {})
    query = f"""
        SELECT t.{column}
        FROM {table} t
        LEFT JOIN {foreign_table} f ON t.{column} = f.{foreign_column}
        WHERE f.{foreign_column} IS NULL
        {where_clause.replace("WHERE", "AND") if where_clause else ""}
    """

    try:
        rows = db.fetchall(query, params) if hasattr(db, "fetchall") else db.execute(query, params)
        if hasattr(rows, "fetchall"):
            rows = rows.fetchall()
    except Exception as e:
        raise DatabaseAssertionError(
            f"Database query failed: {e}",
            actual=str(e),
            expected="successful query",
        ) from e

    if rows:
        orphans = [row[0] for row in rows[:5]]
        msg = message or f"Foreign key {column} has orphaned references: {orphans}"
        raise DatabaseAssertionError(
            msg,
            actual=f"{len(rows)} orphaned references",
            expected="all references valid",
        )


class SQLInvariant:
    """Database invariant checker for journey validation.

    Defines a database constraint that should hold true after journey execution.

    Example:
        >>> invariant = SQLInvariant(
        ...     name="order_total_matches_items",
        ...     query="SELECT SUM(price) FROM order_items WHERE order_id = :order_id",
        ...     expected=lambda row: row[0] == expected_total,
        ...     message="Order total should match sum of item prices"
        ... )
        >>> invariant.check(db, {"order_id": 123})
    """

    def __init__(
        self,
        name: str,
        query: str,
        expected: Any | Callable[[Any], bool],
        params: dict[str, Any] | None = None,
        message: str = "",
        severity: str = "high",
    ) -> None:
        """Initialize a SQL invariant.

        Args:
            name: Invariant name for identification.
            query: SQL query to execute (use :param for parameters).
            expected: Expected value or callable that takes result and returns bool.
            params: Query parameters.
            message: Human-readable description of the invariant.
            severity: Issue severity if invariant fails ("critical", "high", "medium", "low").
        """
        self.name = name
        self.query = query
        self.expected = expected
        self.params = params or {}
        self.message = message or f"Invariant '{name}' failed"
        self.severity = severity

    def check(
        self,
        db: DatabaseConnection,
        params: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """Check if the invariant holds.

        Args:
            db: Database connection.
            params: Additional query parameters (merged with constructor params).

        Returns:
            Tuple of (passed, error_message).
        """
        merged_params = {**self.params, **(params or {})}

        try:
            formatted_query = self._format_query(self.query, merged_params)
            result = (
                db.fetchone(formatted_query, ())
                if hasattr(db, "fetchone")
                else db.execute(formatted_query, ())
            )
            if hasattr(result, "fetchone"):
                result = result.fetchone()
        except Exception as e:
            return False, f"Query failed: {e}"

        if result is None:
            return False, "Query returned no results"

        if callable(self.expected):
            try:
                passed = self.expected(result)
            except Exception as e:
                return False, f"Expected check failed: {e}"
        else:
            passed = result == self.expected

        if not passed:
            return False, f"{self.message}. Got: {result}, Expected: {self.expected}"

        return True, ""

    def _format_query(self, query: str, params: dict[str, Any]) -> str:
        """Format query with named parameters."""
        formatted = query
        for key, value in params.items():
            placeholder = f":{key}"
            if isinstance(value, str):
                formatted = formatted.replace(placeholder, f"'{value}'")
            elif value is None:
                formatted = formatted.replace(placeholder, "NULL")
            else:
                formatted = formatted.replace(placeholder, str(value))
        return formatted


class RowCountInvariant(SQLInvariant):
    """Invariant that checks row count in a table."""

    def __init__(
        self,
        name: str,
        table: str,
        expected: int | Callable[[int], bool],
        conditions: dict[str, Any] | None = None,
        message: str = "",
    ) -> None:
        where_clause, _ = _build_where_clause(conditions or {})
        query = f"SELECT COUNT(*) FROM {table}{where_clause}"

        def check_count(row: Any) -> bool:
            count = row[0] if row else 0
            if callable(expected):
                return expected(count)
            return count == expected

        msg = message or f"Row count invariant on {table}"
        super().__init__(name, query, check_count, conditions, msg)


class ColumnValueInvariant(SQLInvariant):
    """Invariant that checks a column value."""

    def __init__(
        self,
        name: str,
        table: str,
        column: str,
        expected: Any | Callable[[Any], bool],
        conditions: dict[str, Any],
        message: str = "",
    ) -> None:
        where_clause, _ = _build_where_clause(conditions)
        query = f"SELECT {column} FROM {table}{where_clause} LIMIT 1"

        def check_value(row: Any) -> bool:
            if row is None:
                return False
            value = row[0]
            if callable(expected):
                return expected(value)
            return value == expected

        msg = message or f"Column {column} invariant on {table}"
        super().__init__(name, query, check_value, conditions, msg)


class NoNullsInvariant(SQLInvariant):
    """Invariant that checks a column has no NULL values."""

    def __init__(
        self,
        name: str,
        table: str,
        column: str,
        conditions: dict[str, Any] | None = None,
        message: str = "",
    ) -> None:
        where_clause, _ = _build_where_clause(conditions or {})
        query = f"SELECT COUNT(*) FROM {table}{where_clause} AND {column} IS NULL"

        def check_no_nulls(row: Any) -> bool:
            count = row[0] if row else 0
            return count == 0

        msg = message or f"No NULLs in {table}.{column}"
        super().__init__(name, query, check_no_nulls, conditions, msg)


class ReferentialIntegrityInvariant(SQLInvariant):
    """Invariant that checks foreign key integrity."""

    def __init__(
        self,
        name: str,
        table: str,
        column: str,
        foreign_table: str,
        foreign_column: str = "id",
        message: str = "",
    ) -> None:
        query = f"""
            SELECT COUNT(*)
            FROM {table} t
            LEFT JOIN {foreign_table} f ON t.{column} = f.{foreign_column}
            WHERE f.{foreign_column} IS NULL AND t.{column} IS NOT NULL
        """

        def check_integrity(row: Any) -> bool:
            count = row[0] if row else 0
            return count == 0

        msg = (
            message
            or f"Referential integrity: {table}.{column} -> {foreign_table}.{foreign_column}"
        )
        super().__init__(name, query, check_integrity, {}, msg)
