from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    default_value: Any = None
    primary_key: bool = False
    foreign_key: dict[str, str] | None = None
    unique: bool = False
    index: bool = False
    auto_increment: bool = False
    comment: str | None = None


@dataclass
class IndexInfo:
    name: str
    columns: list[str]
    unique: bool
    primary: bool = False


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo]
    indexes: list[IndexInfo] = field(default_factory=list)
    row_count: int | None = None
    comment: str | None = None
    created_at: datetime | None = None


@dataclass
class QueryResult:
    rows: list[dict[str, Any]]
    affected_rows: int = 0
    last_insert_id: int | None = None
    columns: list[str] = field(default_factory=list)
    execution_time_ms: float = 0.0
    query: str = ""

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def first(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def scalar(self) -> Any:
        if self.rows and self.columns:
            return self.rows[0].get(self.columns[0])
        return None

    def values(self, column: str) -> list[Any]:
        return [row.get(column) for row in self.rows]


class DatabasePort(ABC):
    @abstractmethod
    def execute(
        self, query: str, params: tuple[Any, ...] | dict[str, Any] | None = None
    ) -> QueryResult:
        """
        Execute a raw SQL query.

        Args:
            query: SQL query string.
            params: Query parameters (positional or named).

        Returns:
            QueryResult with rows and metadata.
        """
        ...

    @abstractmethod
    def execute_many(self, query: str, params_list: list[tuple[Any, ...]]) -> list[QueryResult]:
        """
        Execute a query multiple times with different parameters.

        Args:
            query: SQL query string.
            params_list: List of parameter tuples.

        Returns:
            List of QueryResults.
        """
        ...

    @abstractmethod
    def query(
        self, query: str, params: tuple[Any, ...] | dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """
        Execute a SELECT query and return rows.

        Args:
            query: SELECT query string.
            params: Query parameters.

        Returns:
            List of row dictionaries.
        """
        ...

    @abstractmethod
    def query_one(
        self, query: str, params: tuple[Any, ...] | dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """
        Execute a query and return a single row.

        Args:
            query: SQL query string.
            params: Query parameters.

        Returns:
            Single row dictionary or None.
        """
        ...

    @abstractmethod
    def query_value(
        self, query: str, params: tuple[Any, ...] | dict[str, Any] | None = None
    ) -> Any:
        """
        Execute a query and return a single value.

        Args:
            query: SQL query string.
            params: Query parameters.

        Returns:
            Single scalar value.
        """
        ...

    @abstractmethod
    def insert(self, table: str, data: dict[str, Any]) -> QueryResult:
        """
        Insert a row into a table.

        Args:
            table: Table name.
            data: Column-value pairs to insert.

        Returns:
            QueryResult with last_insert_id.
        """
        ...

    @abstractmethod
    def insert_many(self, table: str, data_list: list[dict[str, Any]]) -> QueryResult:
        """
        Insert multiple rows into a table.

        Args:
            table: Table name.
            data_list: List of column-value dictionaries.

        Returns:
            QueryResult with affected_rows.
        """
        ...

    @abstractmethod
    def update(
        self,
        table: str,
        data: dict[str, Any],
        where: str,
        where_params: tuple[Any, ...] | None = None,
    ) -> QueryResult:
        """
        Update rows in a table.

        Args:
            table: Table name.
            data: Column-value pairs to update.
            where: WHERE clause (without the WHERE keyword).
            where_params: Parameters for WHERE clause.

        Returns:
            QueryResult with affected_rows.
        """
        ...

    @abstractmethod
    def delete(
        self, table: str, where: str, where_params: tuple[Any, ...] | None = None
    ) -> QueryResult:
        """
        Delete rows from a table.

        Args:
            table: Table name.
            where: WHERE clause (without the WHERE keyword).
            where_params: Parameters for WHERE clause.

        Returns:
            QueryResult with affected_rows.
        """
        ...

    @abstractmethod
    def upsert(
        self,
        table: str,
        data: dict[str, Any],
        conflict_columns: list[str],
        update_columns: list[str] | None = None,
    ) -> QueryResult:
        """
        Insert or update on conflict.

        Args:
            table: Table name.
            data: Column-value pairs.
            conflict_columns: Columns that define uniqueness.
            update_columns: Columns to update on conflict (default: all except conflict columns).

        Returns:
            QueryResult with affected info.
        """
        ...

    @abstractmethod
    def select(
        self,
        table: str,
        columns: list[str] | None = None,
        where: str | None = None,
        where_params: tuple[Any, ...] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> QueryResult:
        """
        Select rows from a table.

        Args:
            table: Table name.
            columns: Columns to select (default: all).
            where: WHERE clause.
            where_params: Parameters for WHERE clause.
            order_by: ORDER BY clause.
            limit: Maximum rows to return.
            offset: Number of rows to skip.

        Returns:
            QueryResult with rows.
        """
        ...

    @abstractmethod
    def count(
        self, table: str, where: str | None = None, where_params: tuple[Any, ...] | None = None
    ) -> int:
        """
        Count rows in a table.

        Args:
            table: Table name.
            where: WHERE clause.
            where_params: Parameters for WHERE clause.

        Returns:
            Number of matching rows.
        """
        ...

    @abstractmethod
    def exists(self, table: str, where: str, where_params: tuple[Any, ...] | None = None) -> bool:
        """
        Check if any rows match the condition.

        Args:
            table: Table name.
            where: WHERE clause.
            where_params: Parameters for WHERE clause.

        Returns:
            True if any rows match.
        """
        ...

    @abstractmethod
    def truncate(self, table: str, cascade: bool = False) -> None:
        """
        Truncate a table.

        Args:
            table: Table name.
            cascade: Whether to truncate dependent tables.
        """
        ...

    @abstractmethod
    def begin_transaction(self) -> None:
        """
        Begin a database transaction.
        """
        ...

    @abstractmethod
    def commit(self) -> None:
        """
        Commit the current transaction.
        """
        ...

    @abstractmethod
    def rollback(self) -> None:
        """
        Rollback the current transaction.
        """
        ...

    @abstractmethod
    def transaction(self) -> Any:
        """
        Context manager for transactions.

        Returns:
            Transaction context manager.
        """
        ...

    @abstractmethod
    def get_tables(self) -> list[str]:
        """
        Get list of all tables.

        Returns:
            List of table names.
        """
        ...

    @abstractmethod
    def get_table_info(self, table: str) -> TableInfo:
        """
        Get information about a table.

        Args:
            table: Table name.

        Returns:
            TableInfo with columns and metadata.
        """
        ...

    @abstractmethod
    def table_exists(self, table: str) -> bool:
        """
        Check if a table exists.

        Args:
            table: Table name.

        Returns:
            True if table exists.
        """
        ...

    @abstractmethod
    def create_table(
        self, table: str, columns: list[ColumnInfo], if_not_exists: bool = True
    ) -> None:
        """
        Create a new table.

        Args:
            table: Table name.
            columns: Column definitions.
            if_not_exists: Whether to ignore if table exists.
        """
        ...

    @abstractmethod
    def drop_table(self, table: str, if_exists: bool = True, cascade: bool = False) -> None:
        """
        Drop a table.

        Args:
            table: Table name.
            if_exists: Whether to ignore if table doesn't exist.
            cascade: Whether to drop dependent objects.
        """
        ...

    @abstractmethod
    def add_column(self, table: str, column: ColumnInfo) -> None:
        """
        Add a column to a table.

        Args:
            table: Table name.
            column: Column definition.
        """
        ...

    @abstractmethod
    def drop_column(self, table: str, column_name: str) -> None:
        """
        Drop a column from a table.

        Args:
            table: Table name.
            column_name: Name of column to drop.
        """
        ...

    @abstractmethod
    def create_index(
        self, table: str, columns: list[str], unique: bool = False, name: str | None = None
    ) -> None:
        """
        Create an index on a table.

        Args:
            table: Table name.
            columns: Columns to index.
            unique: Whether the index should be unique.
            name: Optional index name.
        """
        ...

    @abstractmethod
    def drop_index(self, name: str, table: str | None = None) -> None:
        """
        Drop an index.

        Args:
            name: Index name.
            table: Optional table name (required for some DBs).
        """
        ...

    @abstractmethod
    def run_migrations(self, migrations_dir: str | None = None) -> list[str]:
        """
        Run pending database migrations.

        Args:
            migrations_dir: Directory containing migration files.

        Returns:
            List of executed migration names.
        """
        ...

    @abstractmethod
    def rollback_migration(self, migration: str) -> None:
        """
        Rollback a specific migration.

        Args:
            migration: Migration name to rollback.
        """
        ...

    @abstractmethod
    def seed(self, table: str, data: list[dict[str, Any]]) -> None:
        """
        Seed a table with data.

        Args:
            table: Table name.
            data: Data to insert.
        """
        ...

    @abstractmethod
    def clean_table(self, table: str) -> None:
        """
        Remove all data from a table (for test cleanup).

        Args:
            table: Table name.
        """
        ...

    @abstractmethod
    def dump(self, tables: list[str] | None = None) -> dict[str, list[dict[str, Any]]]:
        """
        Dump table data for inspection or backup.

        Args:
            tables: Tables to dump (default: all).

        Returns:
            Dictionary of table name to rows.
        """
        ...

    @abstractmethod
    def restore(self, data: dict[str, list[dict[str, Any]]], truncate: bool = True) -> None:
        """
        Restore data from a dump.

        Args:
            data: Dictionary of table name to rows.
            truncate: Whether to truncate tables first.
        """
        ...
