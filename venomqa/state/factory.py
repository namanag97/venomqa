"""Factory for creating state managers from configuration."""

from __future__ import annotations

import logging
from typing import Any

from venomqa.state.base import StateManager

logger = logging.getLogger(__name__)


class StateManagerFactory:
    """Factory to create state managers from configuration.

    Usage:
        # Create from backend name and URL
        manager = StateManagerFactory.create("postgres", "postgresql://user:pass@localhost/db")

        # Create from config dict
        manager = StateManagerFactory.from_config({
            "backend": "sqlite",
            "url": "sqlite:///test.db",
            "tables_to_reset": ["users", "orders"]
        })
    """

    @staticmethod
    def create(
        backend: str,
        url: str,
        **kwargs: Any,
    ) -> StateManager:
        """Create a state manager for the specified backend.

        Args:
            backend: Backend type ('postgres', 'postgresql', 'sqlite', 'mysql', 'memory')
            url: Connection URL for the database
            **kwargs: Additional backend-specific options

        Returns:
            StateManager instance

        Raises:
            ValueError: If backend is not supported
        """
        backend_lower = backend.lower()

        if backend_lower in ("postgres", "postgresql"):
            from venomqa.state.postgres import PostgreSQLStateManager

            return PostgreSQLStateManager(
                connection_url=url,
                tables_to_reset=kwargs.get("tables_to_reset"),
                exclude_tables=kwargs.get("exclude_tables"),
            )

        if backend_lower == "sqlite":
            from venomqa.state.sqlite import SQLiteStateManager

            return SQLiteStateManager(
                connection_url=url,
                tables_to_reset=kwargs.get("tables_to_reset"),
                exclude_tables=kwargs.get("exclude_tables"),
            )

        if backend_lower == "mysql":
            from venomqa.state.mysql import MySQLStateManager

            return MySQLStateManager(
                connection_url=url,
                tables_to_reset=kwargs.get("tables_to_reset"),
                exclude_tables=kwargs.get("exclude_tables"),
            )

        if backend_lower in ("memory", "inmemory", "in-memory"):
            from venomqa.state.memory import InMemoryStateManager

            return InMemoryStateManager(
                connection_url=url,
                initial_state=kwargs.get("initial_state"),
            )

        supported = ["postgres", "postgresql", "sqlite", "mysql", "memory", "inmemory", "in-memory"]
        raise ValueError(f"Unsupported backend '{backend}'. Supported backends: {supported}")

    @staticmethod
    def from_config(config: dict[str, Any]) -> StateManager:
        """Create a state manager from a configuration dictionary.

        Args:
            config: Configuration dict with keys:
                - backend: Backend type (required)
                - url: Connection URL (required)
                - tables_to_reset: List of tables to reset (optional)
                - exclude_tables: Tables to exclude from reset (optional)
                - initial_state: Initial state for memory backend (optional)

        Returns:
            StateManager instance
        """
        backend = config.get("backend")
        if not backend:
            raise ValueError("Configuration must include 'backend' key")

        url = config.get("url")
        if not url:
            raise ValueError("Configuration must include 'url' key")

        kwargs: dict[str, Any] = {}
        if "tables_to_reset" in config:
            kwargs["tables_to_reset"] = config["tables_to_reset"]
        if "exclude_tables" in config:
            kwargs["exclude_tables"] = config["exclude_tables"]
        if "initial_state" in config:
            kwargs["initial_state"] = config["initial_state"]

        return StateManagerFactory.create(backend, url, **kwargs)

    @staticmethod
    def from_url(url: str, **kwargs: Any) -> StateManager:
        """Create a state manager by inferring backend from URL.

        Args:
            url: Connection URL (e.g., 'postgresql://...', 'sqlite://...', etc.)
            **kwargs: Additional backend-specific options

        Returns:
            StateManager instance

        Raises:
            ValueError: If URL scheme cannot be determined
        """
        if url.startswith(("postgresql://", "postgres://")):
            return StateManagerFactory.create("postgres", url, **kwargs)

        if url.startswith("sqlite://"):
            return StateManagerFactory.create("sqlite", url, **kwargs)

        if url.startswith("mysql://"):
            return StateManagerFactory.create("mysql", url, **kwargs)

        if url.startswith("memory://"):
            return StateManagerFactory.create("memory", url, **kwargs)

        raise ValueError(
            f"Cannot infer backend from URL: {url}. "
            "URL must start with 'postgresql://', 'sqlite://', 'mysql://', or 'memory://'"
        )

    @staticmethod
    def get_supported_backends() -> list[str]:
        """Get list of supported backend types."""
        return ["postgres", "sqlite", "mysql", "memory"]
