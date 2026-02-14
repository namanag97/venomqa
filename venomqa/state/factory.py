"""Factory for creating state managers from configuration.

This module provides a factory class for creating state manager instances
based on backend type or connection URL. It supports all built-in backends
and can be extended with custom implementations.

Example:
    >>> from venomqa.state import StateManagerFactory
    >>>
    >>> # Create from backend name
    >>> manager = StateManagerFactory.create("postgres", "postgresql://localhost/test")
    >>>
    >>> # Create from config dict
    >>> manager = StateManagerFactory.from_config({
    ...     "backend": "sqlite",
    ...     "url": "sqlite:///test.db",
    ...     "tables_to_reset": ["users"]
    ... })
    >>>
    >>> # Infer backend from URL
    >>> manager = StateManagerFactory.from_url("postgresql://localhost/mydb")
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from venomqa.state.base import StateManager

if TYPE_CHECKING:
    from venomqa.state.memory import InMemoryStateManager
    from venomqa.state.mysql import MySQLStateManager
    from venomqa.state.postgres import PostgreSQLStateManager
    from venomqa.state.sqlite import SQLiteStateManager

logger = logging.getLogger(__name__)


class StateManagerFactory:
    """Factory to create state managers from configuration.

    This factory supports creating state managers from:
    - Backend name and connection URL
    - Configuration dictionary
    - Auto-detection from URL scheme

    The factory can also be extended with custom backends via the
    register_backend() method.

    Example:
        >>> # Simple creation
        >>> manager = StateManagerFactory.create("memory", "memory://test")
        >>> manager.connect()
        >>> assert manager.is_connected()
        >>>
        >>> # With configuration
        >>> manager = StateManagerFactory.from_config({
        ...     "backend": "postgres",
        ...     "url": "postgresql://localhost/test",
        ...     "tables_to_reset": ["users", "orders"],
        ...     "exclude_tables": ["migrations"]
        ... })
    """

    _custom_backends: dict[str, Callable[..., StateManager]] = {}

    @classmethod
    def create(
        cls,
        backend: str,
        url: str,
        **kwargs: Any,
    ) -> StateManager:
        """Create a state manager for the specified backend.

        Args:
            backend: Backend type. Built-in options:
                - 'postgres' or 'postgresql': PostgreSQL database
                - 'sqlite': SQLite database
                - 'mysql': MySQL/MariaDB database
                - 'memory' or 'inmemory': In-memory state
            url: Connection URL for the database.
            **kwargs: Backend-specific options:
                - tables_to_reset: List of tables to truncate on reset
                - exclude_tables: Tables to exclude from reset
                - initial_state: Initial state dict (memory backend only)
                - connection_timeout: Connection timeout in seconds
                - charset: Character set (MySQL only)

        Returns:
            Configured StateManager instance.

        Raises:
            ValueError: If backend is not supported or URL is invalid.

        Example:
            >>> manager = StateManagerFactory.create(
            ...     "postgres",
            ...     "postgresql://user:pass@localhost:5432/mydb",
            ...     tables_to_reset=["users", "products"],
            ...     exclude_tables=["schema_migrations"]
            ... )
        """
        if not backend:
            raise ValueError("Backend type cannot be empty")

        if not url:
            raise ValueError("Connection URL cannot be empty")

        backend_lower = backend.lower().strip()

        if backend_lower in ("postgres", "postgresql"):
            return cls._create_postgres(url, **kwargs)

        if backend_lower == "sqlite":
            return cls._create_sqlite(url, **kwargs)

        if backend_lower == "mysql":
            return cls._create_mysql(url, **kwargs)

        if backend_lower in ("memory", "inmemory", "in-memory"):
            return cls._create_memory(url, **kwargs)

        if backend_lower in cls._custom_backends:
            return cls._custom_backends[backend_lower](connection_url=url, **kwargs)

        supported = cls.get_supported_backends()
        raise ValueError(
            f"Unsupported backend '{backend}'. "
            f"Supported backends: {supported}. "
            f"To add custom backends, use register_backend()."
        )

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> StateManager:
        """Create a state manager from a configuration dictionary.

        Args:
            config: Configuration dictionary with keys:
                - backend (required): Backend type name
                - url (required): Connection URL
                - tables_to_reset (optional): List of tables to reset
                - exclude_tables (optional): Tables to exclude from reset
                - initial_state (optional): Initial state for memory backend
                - connection_timeout (optional): Connection timeout
                - charset (optional): Character set for MySQL

        Returns:
            Configured StateManager instance.

        Raises:
            ValueError: If required keys are missing or invalid.

        Example:
            >>> manager = StateManagerFactory.from_config({
            ...     "backend": "sqlite",
            ...     "url": "sqlite:///test.db",
            ...     "tables_to_reset": ["users"]
            ... })
        """
        if not isinstance(config, dict):
            raise ValueError(f"Configuration must be a dictionary, got {type(config).__name__}")

        backend = config.get("backend")
        if not backend:
            raise ValueError("Configuration must include 'backend' key")

        url = config.get("url")
        if not url:
            raise ValueError("Configuration must include 'url' key")

        kwargs: dict[str, Any] = {}

        optional_keys = [
            "tables_to_reset",
            "exclude_tables",
            "initial_state",
            "connection_timeout",
            "timeout",
            "charset",
        ]

        for key in optional_keys:
            if key in config:
                kwargs[key] = config[key]

        return cls.create(backend, url, **kwargs)

    @classmethod
    def from_url(cls, url: str, **kwargs: Any) -> StateManager:
        """Create a state manager by inferring backend from URL scheme.

        Automatically detects the backend type from the URL prefix:
        - postgresql:// or postgres:// → PostgreSQL
        - sqlite:// → SQLite
        - mysql:// → MySQL
        - memory:// → In-memory

        Args:
            url: Connection URL with scheme prefix.
            **kwargs: Additional backend-specific options.

        Returns:
            Configured StateManager instance.

        Raises:
            ValueError: If URL scheme cannot be determined.

        Example:
            >>> manager = StateManagerFactory.from_url(
            ...     "postgresql://localhost/mydb",
            ...     tables_to_reset=["users"]
            ... )
        """
        if not url:
            raise ValueError("Connection URL cannot be empty")

        url_stripped = url.strip()

        if url_stripped.startswith(("postgresql://", "postgres://")):
            return cls.create("postgres", url, **kwargs)

        if url_stripped.startswith("sqlite://"):
            return cls.create("sqlite", url, **kwargs)

        if url_stripped.startswith("mysql://"):
            return cls.create("mysql", url, **kwargs)

        if url_stripped.startswith("memory://"):
            return cls.create("memory", url, **kwargs)

        raise ValueError(
            f"Cannot infer backend from URL: '{url}'. "
            "URL must start with 'postgresql://', 'postgres://', "
            "'sqlite://', 'mysql://', or 'memory://'. "
            "Use create() with explicit backend parameter for other formats."
        )

    @classmethod
    def register_backend(cls, name: str, factory_func: Callable[..., StateManager]) -> None:
        """Register a custom backend factory function.

        Allows extending the factory with custom state manager implementations.

        Args:
            name: Backend name (case-insensitive). Will override existing
                backends with the same name.
            factory_func: Factory function that accepts connection_url
                and any additional kwargs, returning a StateManager.

        Example:
            >>> class MyCustomStateManager(BaseStateManager):
            ...     # ... implementation ...
            ...     pass
            >>>
            >>> StateManagerFactory.register_backend(
            ...     "custom",
            ...     lambda connection_url, **kw: MyCustomStateManager(connection_url, **kw)
            ... )
            >>> manager = StateManagerFactory.create("custom", "custom://test")
        """
        if not name:
            raise ValueError("Backend name cannot be empty")

        if not callable(factory_func):
            raise ValueError("Factory function must be callable")

        cls._custom_backends[name.lower()] = factory_func
        logger.info(f"Registered custom state manager backend: {name}")

    @classmethod
    def unregister_backend(cls, name: str) -> bool:
        """Unregister a custom backend.

        Args:
            name: Backend name to unregister.

        Returns:
            True if backend was removed, False if it didn't exist.

        Note:
            Cannot unregister built-in backends.
        """
        name_lower = name.lower()
        if name_lower in cls._custom_backends:
            del cls._custom_backends[name_lower]
            return True
        return False

    @classmethod
    def get_supported_backends(cls) -> list[str]:
        """Get list of all supported backend types.

        Returns:
            List of backend names (both built-in and custom).
        """
        built_in = ["postgres", "sqlite", "mysql", "memory"]
        custom = list(cls._custom_backends.keys())
        return built_in + custom

    @classmethod
    def is_backend_supported(cls, backend: str) -> bool:
        """Check if a backend type is supported.

        Args:
            backend: Backend name to check.

        Returns:
            True if supported, False otherwise.
        """
        backend_lower = backend.lower().strip()
        built_in = {"postgres", "postgresql", "sqlite", "mysql", "memory", "inmemory", "in-memory"}
        return backend_lower in built_in or backend_lower in cls._custom_backends

    @classmethod
    def _create_postgres(cls, url: str, **kwargs: Any) -> PostgreSQLStateManager:
        """Create a PostgreSQL state manager."""
        from venomqa.state.postgres import PostgreSQLStateManager

        return PostgreSQLStateManager(
            connection_url=url,
            tables_to_reset=kwargs.get("tables_to_reset"),
            exclude_tables=kwargs.get("exclude_tables"),
            connection_timeout=kwargs.get("connection_timeout", 30),
        )

    @classmethod
    def _create_sqlite(cls, url: str, **kwargs: Any) -> SQLiteStateManager:
        """Create a SQLite state manager."""
        from venomqa.state.sqlite import SQLiteStateManager

        return SQLiteStateManager(
            connection_url=url,
            tables_to_reset=kwargs.get("tables_to_reset"),
            exclude_tables=kwargs.get("exclude_tables"),
            timeout=kwargs.get("timeout", kwargs.get("connection_timeout", 30.0)),
        )

    @classmethod
    def _create_mysql(cls, url: str, **kwargs: Any) -> MySQLStateManager:
        """Create a MySQL state manager."""
        from venomqa.state.mysql import MySQLStateManager

        return MySQLStateManager(
            connection_url=url,
            tables_to_reset=kwargs.get("tables_to_reset"),
            exclude_tables=kwargs.get("exclude_tables"),
            connection_timeout=kwargs.get("connection_timeout", 30),
            charset=kwargs.get("charset", "utf8mb4"),
        )

    @classmethod
    def _create_memory(cls, url: str, **kwargs: Any) -> InMemoryStateManager:
        """Create an in-memory state manager."""
        from venomqa.state.memory import InMemoryStateManager

        return InMemoryStateManager(
            connection_url=url,
            initial_state=kwargs.get("initial_state"),
        )

    @classmethod
    def create_for_testing(
        cls, initial_state: dict[str, Any] | None = None
    ) -> InMemoryStateManager:
        """Create an in-memory state manager optimized for unit testing.

        Convenience method for creating a memory backend with sensible
        defaults for testing scenarios.

        Args:
            initial_state: Optional initial state dictionary.

        Returns:
            Connected InMemoryStateManager instance.

        Example:
            >>> manager = StateManagerFactory.create_for_testing({"count": 0})
            >>> assert manager.is_connected()
        """
        manager = cls._create_memory("memory://test", initial_state=initial_state)
        manager.connect()
        return manager
