"""Database actions for QA testing.

This module provides reusable database action functions supporting:
- Query execution
- CRUD operations (Insert, Update, Delete, Upsert)
- Transaction management

Supports: PostgreSQL, MySQL, SQLite

Example:
    >>> from venomqa.tools import db_query, db_insert, db_update
    >>>
    >>> # Query data
    >>> results = db_query(client, context, "SELECT * FROM users WHERE active = %s", [True])
    >>>
    >>> # Insert data
    >>> db_insert(client, context, "users", {"name": "John", "email": "john@example.com"})
    >>>
    >>> # Update data
    >>> db_update(client, context, "users", {"status": "active"}, {"id": 1})
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from venomqa.errors import VenomQAError

if TYPE_CHECKING:
    from venomqa.client import Client
    from venomqa.state.context import Context


class DatabaseError(VenomQAError):
    """Raised when a database operation fails."""

    pass


def _get_connection(client: Client, context: Context, alias: str = "default"):
    """Get database connection from client or context."""
    connection = None

    if hasattr(context, "_db_connections") and alias in context._db_connections:
        connection = context._db_connections[alias]
    elif hasattr(client, "db_connections") and alias in client.db_connections:
        connection = client.db_connections[alias]
    elif hasattr(context, "db_connection"):
        connection = context.db_connection
    elif hasattr(client, "db_connection"):
        connection = client.db_connection

    if connection is None:
        raise DatabaseError(
            f"No database connection found for alias '{alias}'. "
            "Ensure database is configured in venomqa.yaml or set context.db_connection"
        )

    return connection


def _get_placeholder_style(connection) -> str:
    """Determine placeholder style based on database driver."""
    conn_type = type(connection).__module__

    if "psycopg" in conn_type or "postgres" in conn_type:
        return "postgres"
    elif "mysql" in conn_type:
        return "pyformat"
    elif "sqlite" in conn_type:
        return "qmark"
    elif "aiosqlite" in conn_type:
        return "qmark"
    else:
        return "pyformat"


def _convert_sql(sql: str, params: list | tuple, style: str) -> tuple[str, list | tuple]:
    """Convert SQL placeholders to the appropriate style."""
    if style == "postgres":
        if "%s" in sql and "?" not in sql:
            return sql, params
        converted = sql
        new_params = list(params) if params else []
        placeholder_count = 0
        while "?" in converted:
            placeholder_count += 1
            converted = converted.replace("?", f"${placeholder_count}", 1)
        return converted, tuple(new_params)
    elif style == "qmark":
        if "?" in sql:
            return sql, params
        import re

        converted = sql
        for _i, _ in enumerate(params or []):
            converted = re.sub(r"%s", "?", converted, count=1)
        return converted, params
    else:
        if "%s" in sql or not params:
            return sql, params
        import re

        converted = sql
        for _i, _ in enumerate(params or []):
            converted = re.sub(r"\?", "%s", converted, count=1)
        return converted, params


def db_query(
    client: Client,
    context: Context,
    sql: str,
    params: list[Any] | tuple[Any, ...] | None = None,
    alias: str = "default",
) -> list[dict[str, Any]]:
    """Execute a SQL query and return results as list of dictionaries.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        sql: SQL query string with placeholders.
        params: Query parameters.
        alias: Database connection alias.

    Returns:
        list: Query results as list of dictionaries.

    Raises:
        DatabaseError: If query fails.

    Example:
        >>> # Query with parameters
        >>> users = db_query(
        ...     client, context,
        ...     "SELECT * FROM users WHERE status = %s AND created_at > %s",
        ...     ["active", "2024-01-01"]
        ... )
        >>> for user in users:
        ...     print(user["name"])
        >>>
        >>> # Simple query
        >>> count = db_query(client, context, "SELECT COUNT(*) as cnt FROM users")
        >>> print(count[0]["cnt"])
    """
    connection = _get_connection(client, context, alias)
    style = _get_placeholder_style(connection)
    converted_sql, converted_params = _convert_sql(sql, params or [], style)

    try:
        cursor = connection.cursor()
        cursor.execute(converted_sql, converted_params)

        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        cursor.close()

        results = [dict(zip(columns, row, strict=False)) for row in rows]

        if not hasattr(context, "_db_query_history"):
            context._db_query_history = []
        context._db_query_history.append(
            {
                "sql": sql,
                "params": params,
                "row_count": len(results),
            }
        )

        return results
    except Exception as e:
        raise DatabaseError(f"Database query failed: {sql}") from e


def db_query_one(
    client: Client,
    context: Context,
    sql: str,
    params: list[Any] | tuple[Any, ...] | None = None,
    alias: str = "default",
) -> dict[str, Any] | None:
    """Execute a SQL query and return a single result.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        sql: SQL query string with placeholders.
        params: Query parameters.
        alias: Database connection alias.

    Returns:
        dict | None: Single row as dictionary, or None if no results.

    Raises:
        DatabaseError: If query fails.

    Example:
        >>> user = db_query_one(
        ...     client, context,
        ...     "SELECT * FROM users WHERE id = %s",
        ...     [1]
        ... )
        >>> if user:
        ...     print(user["name"])
    """
    results = db_query(client, context, sql, params, alias)
    return results[0] if results else None


def db_execute(
    client: Client,
    context: Context,
    sql: str,
    params: list[Any] | tuple[Any, ...] | None = None,
    alias: str = "default",
    commit: bool = True,
) -> int:
    """Execute a SQL statement and return affected row count.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        sql: SQL statement string with placeholders.
        params: Statement parameters.
        alias: Database connection alias.
        commit: Whether to commit the transaction.

    Returns:
        int: Number of affected rows.

    Raises:
        DatabaseError: If execution fails.

    Example:
        >>> affected = db_execute(
        ...     client, context,
        ...     "UPDATE users SET last_login = NOW() WHERE id = %s",
        ...     [1]
        ... )
        >>> print(f"Updated {affected} row(s)")
    """
    connection = _get_connection(client, context, alias)
    style = _get_placeholder_style(connection)
    converted_sql, converted_params = _convert_sql(sql, params or [], style)

    try:
        cursor = connection.cursor()
        cursor.execute(converted_sql, converted_params)
        rowcount = cursor.rowcount
        cursor.close()

        if commit:
            connection.commit()

        return rowcount
    except Exception as e:
        if commit:
            connection.rollback()
        raise DatabaseError(f"Database execute failed: {sql}") from e


def db_insert(
    client: Client,
    context: Context,
    table: str,
    data: dict[str, Any],
    alias: str = "default",
    return_id: bool = True,
) -> int | None:
    """Insert a row into a database table.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        table: Table name.
        data: Column names and values to insert.
        alias: Database connection alias.
        return_id: Whether to return the inserted row's ID.

    Returns:
        int | None: Inserted row ID if return_id is True, else None.

    Raises:
        DatabaseError: If insert fails.

    Example:
        >>> user_id = db_insert(
        ...     client, context,
        ...     table="users",
        ...     data={"name": "John", "email": "john@example.com", "status": "active"}
        ... )
        >>> print(f"Created user with ID: {user_id}")
    """
    if not data:
        raise DatabaseError("No data provided for insert")

    connection = _get_connection(client, context, alias)
    columns = list(data.keys())
    placeholders = ["%s"] * len(columns)
    values = [data[col] for col in columns]

    style = _get_placeholder_style(connection)

    if style == "postgres":
        placeholders = [f"${i + 1}" for i in range(len(columns))]
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        if return_id:
            sql += " RETURNING id"
    elif style == "qmark":
        placeholders = ["?"] * len(columns)
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
    else:
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"

    try:
        cursor = connection.cursor()
        cursor.execute(sql, values)

        inserted_id = None
        if return_id:
            if style == "postgres":
                result = cursor.fetchone()
                inserted_id = result[0] if result else None
            else:
                inserted_id = cursor.lastrowid

        connection.commit()
        cursor.close()

        return inserted_id
    except Exception as e:
        connection.rollback()
        raise DatabaseError(f"Database insert failed: {table}") from e


def db_insert_many(
    client: Client,
    context: Context,
    table: str,
    rows: list[dict[str, Any]],
    alias: str = "default",
) -> int:
    """Insert multiple rows into a database table.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        table: Table name.
        rows: List of dictionaries with column names and values.
        alias: Database connection alias.

    Returns:
        int: Number of rows inserted.

    Raises:
        DatabaseError: If insert fails.

    Example:
        >>> count = db_insert_many(
        ...     client, context,
        ...     table="users",
        ...     rows=[
        ...         {"name": "John", "email": "john@example.com"},
        ...         {"name": "Jane", "email": "jane@example.com"},
        ...     ]
        ... )
        >>> print(f"Inserted {count} rows")
    """
    if not rows:
        return 0

    connection = _get_connection(client, context, alias)
    columns = list(rows[0].keys())
    placeholders = ["%s"] * len(columns)
    style = _get_placeholder_style(connection)

    if style == "postgres":
        placeholders = [f"${i + 1}" for i in range(len(columns))]
    elif style == "qmark":
        placeholders = ["?"] * len(columns)

    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
    values = [tuple(row[col] for col in columns) for row in rows]

    try:
        cursor = connection.cursor()
        cursor.executemany(sql, values)
        rowcount = cursor.rowcount
        connection.commit()
        cursor.close()
        return rowcount
    except Exception as e:
        connection.rollback()
        raise DatabaseError(f"Database batch insert failed: {table}") from e


def db_update(
    client: Client,
    context: Context,
    table: str,
    data: dict[str, Any],
    where: dict[str, Any],
    alias: str = "default",
) -> int:
    """Update rows in a database table.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        table: Table name.
        data: Column names and new values.
        where: WHERE clause conditions (column = value pairs, ANDed together).
        alias: Database connection alias.

    Returns:
        int: Number of rows affected.

    Raises:
        DatabaseError: If update fails.

    Example:
        >>> affected = db_update(
        ...     client, context,
        ...     table="users",
        ...     data={"status": "inactive"},
        ...     where={"id": 1}
        ... )
        >>> print(f"Updated {affected} row(s)")
        >>>
        >>> # Update multiple rows
        >>> affected = db_update(
        ...     client, context,
        ...     table="users",
        ...     data={"role": "premium"},
        ...     where={"subscription_tier": "gold"}
        ... )
    """
    if not data:
        raise DatabaseError("No data provided for update")
    if not where:
        raise DatabaseError("No WHERE clause provided - use db_execute for full table updates")

    connection = _get_connection(client, context, alias)
    style = _get_placeholder_style(connection)

    set_clauses = []
    set_values = []
    placeholder_idx = 1 if style == "postgres" else 0

    for col, val in data.items():
        if style == "postgres":
            set_clauses.append(f"{col} = ${placeholder_idx}")
            placeholder_idx += 1
        elif style == "qmark":
            set_clauses.append(f"{col} = ?")
        else:
            set_clauses.append(f"{col} = %s")
        set_values.append(val)

    where_clauses = []
    where_values = []

    for col, val in where.items():
        if style == "postgres":
            where_clauses.append(f"{col} = ${placeholder_idx}")
            placeholder_idx += 1
        elif style == "qmark":
            where_clauses.append(f"{col} = ?")
        else:
            where_clauses.append(f"{col} = %s")
        where_values.append(val)

    sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {' AND '.join(where_clauses)}"
    all_values = set_values + where_values

    try:
        cursor = connection.cursor()
        cursor.execute(sql, all_values)
        rowcount = cursor.rowcount
        connection.commit()
        cursor.close()
        return rowcount
    except Exception as e:
        connection.rollback()
        raise DatabaseError(f"Database update failed: {table}") from e


def db_delete(
    client: Client,
    context: Context,
    table: str,
    where: dict[str, Any],
    alias: str = "default",
) -> int:
    """Delete rows from a database table.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        table: Table name.
        where: WHERE clause conditions (column = value pairs, ANDed together).
        alias: Database connection alias.

    Returns:
        int: Number of rows deleted.

    Raises:
        DatabaseError: If delete fails.

    Example:
        >>> deleted = db_delete(
        ...     client, context,
        ...     table="users",
        ...     where={"id": 1}
        ... )
        >>> print(f"Deleted {deleted} row(s)")
    """
    if not where:
        raise DatabaseError("No WHERE clause provided - use db_execute for full table deletes")

    connection = _get_connection(client, context, alias)
    style = _get_placeholder_style(connection)

    where_clauses = []
    where_values = []
    placeholder_idx = 1 if style == "postgres" else 0

    for col, val in where.items():
        if style == "postgres":
            where_clauses.append(f"{col} = ${placeholder_idx}")
            placeholder_idx += 1
        elif style == "qmark":
            where_clauses.append(f"{col} = ?")
        else:
            where_clauses.append(f"{col} = %s")
        where_values.append(val)

    sql = f"DELETE FROM {table} WHERE {' AND '.join(where_clauses)}"

    try:
        cursor = connection.cursor()
        cursor.execute(sql, where_values)
        rowcount = cursor.rowcount
        connection.commit()
        cursor.close()
        return rowcount
    except Exception as e:
        connection.rollback()
        raise DatabaseError(f"Database delete failed: {table}") from e


def db_upsert(
    client: Client,
    context: Context,
    table: str,
    data: dict[str, Any],
    conflict_columns: list[str],
    update_columns: list[str] | None = None,
    alias: str = "default",
) -> int | None:
    """Insert or update a row (upsert) in a database table.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        table: Table name.
        data: Column names and values to insert/update.
        conflict_columns: Columns to check for conflicts (unique constraint).
        update_columns: Columns to update on conflict. If None, updates all except conflict columns.
        alias: Database connection alias.

    Returns:
        int | None: Row ID.

    Raises:
        DatabaseError: If upsert fails.

    Example:
        >>> user_id = db_upsert(
        ...     client, context,
        ...     table="users",
        ...     data={"email": "john@example.com", "name": "John", "status": "active"},
        ...     conflict_columns=["email"],
        ...     update_columns=["name", "status"]
        ... )
    """
    if not data:
        raise DatabaseError("No data provided for upsert")

    connection = _get_connection(client, context, alias)
    style = _get_placeholder_style(connection)

    columns = list(data.keys())
    values = [data[col] for col in columns]

    if style == "postgres":
        placeholders = [f"${i + 1}" for i in range(len(columns))]
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"

        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_columns]

        if update_columns:
            update_set = ", ".join(f"{col} = EXCLUDED.{col}" for col in update_columns)
            sql += f" ON CONFLICT ({', '.join(conflict_columns)}) DO UPDATE SET {update_set}"
        else:
            sql += f" ON CONFLICT ({', '.join(conflict_columns)}) DO NOTHING"

        sql += " RETURNING id"
    elif style == "qmark":
        placeholders = ["?"] * len(columns)
        cols_str = ", ".join(columns)
        sql = f"INSERT OR REPLACE INTO {table} ({cols_str}) VALUES ({', '.join(placeholders)})"
    else:
        placeholders = ["%s"] * len(columns)
        update_cols = (
            [c for c in columns if c not in conflict_columns]
            if update_columns is None
            else update_columns
        )
        update_set = ", ".join(f"{col} = VALUES({col})" for col in update_cols)
        sql = f"""INSERT INTO {table} ({", ".join(columns)}) VALUES ({", ".join(placeholders)})
                  ON DUPLICATE KEY UPDATE {update_set}"""

    try:
        cursor = connection.cursor()
        cursor.execute(sql, values)

        inserted_id = None
        if style == "postgres":
            result = cursor.fetchone()
            inserted_id = result[0] if result else None
        else:
            inserted_id = cursor.lastrowid

        connection.commit()
        cursor.close()
        return inserted_id
    except Exception as e:
        connection.rollback()
        raise DatabaseError(f"Database upsert failed: {table}") from e


def db_transaction(
    client: Client,
    context: Context,
    operations: list[tuple[str, list[Any] | None]],
    alias: str = "default",
) -> list[int]:
    """Execute multiple operations in a single transaction.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        operations: List of (sql, params) tuples to execute.
        alias: Database connection alias.

    Returns:
        list: Row counts for each operation.

    Raises:
        DatabaseError: If any operation fails (all rolled back).

    Example:
        >>> results = db_transaction(
        ...     client, context,
        ...     operations=[
        ...         ("INSERT INTO orders (user_id, total) VALUES (%s, %s)", [1, 100.00]),
        ...         ("UPDATE users SET order_count = order_count + 1 WHERE id = %s", [1]),
        ...         ("INSERT INTO audit_log (action, table_name) VALUES (%s, %s)",  # noqa: E501
        ...             ["insert", "orders"]),
        ...     ]
        ... )
    """
    connection = _get_connection(client, context, alias)
    style = _get_placeholder_style(connection)
    row_counts = []

    try:
        cursor = connection.cursor()

        for sql, params in operations:
            converted_sql, converted_params = _convert_sql(sql, params or [], style)
            cursor.execute(converted_sql, converted_params)
            row_counts.append(cursor.rowcount)

        connection.commit()
        cursor.close()
        return row_counts
    except Exception as e:
        connection.rollback()
        raise DatabaseError("Transaction failed, all changes rolled back") from e


def db_table_exists(
    client: Client,
    context: Context,
    table: str,
    alias: str = "default",
) -> bool:
    """Check if a table exists in the database.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        table: Table name to check.
        alias: Database connection alias.

    Returns:
        bool: True if table exists.

    Example:
        >>> if db_table_exists(client, context, "users"):
        ...     print("Users table exists")
    """
    connection = _get_connection(client, context, alias)
    style = _get_placeholder_style(connection)

    if style == "postgres":
        sql = "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)"
    elif style == "qmark":
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
    else:
        sql = "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)"

    results = db_query(client, context, sql, [table], alias)

    if results:
        first_val = list(results[0].values())[0]
        return bool(first_val)
    return False


def db_truncate(
    client: Client,
    context: Context,
    table: str,
    alias: str = "default",
    restart_identity: bool = False,
) -> int:
    """Truncate a database table.

    Args:
        client: VenomQA client instance.
        context: Test context containing configuration and state.
        table: Table name to truncate.
        alias: Database connection alias.
        restart_identity: Whether to restart auto-increment counter (PostgreSQL only).

    Returns:
        int: 0 on success.

    Raises:
        DatabaseError: If truncate fails.

    Example:
        >>> db_truncate(client, context, "test_table", restart_identity=True)
    """
    connection = _get_connection(client, context, alias)
    style = _get_placeholder_style(connection)

    if style == "postgres":
        sql = f"TRUNCATE TABLE {table}"
        if restart_identity:
            sql += " RESTART IDENTITY"
        sql += " CASCADE"
    elif style == "qmark":
        sql = f"DELETE FROM {table}"
    else:
        sql = f"TRUNCATE TABLE {table}"

    return db_execute(client, context, sql, alias=alias)
